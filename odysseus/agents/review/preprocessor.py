"""Code pre-processor for the Review Agent.

Pure computation functions that transform raw ScoreReports, SearchState,
and historical data into a ReviewBriefing. No external dependencies
beyond stdlib (difflib).
"""

from __future__ import annotations

import difflib
import logging
import re
import statistics
from collections import Counter
from typing import Any

from odysseus.agents.prompt_builder.search import Candidate
from odysseus.agents.review.models import (
    CandidateAnalysis,
    ClassRecallEntry,
    DiminishingReturns,
    DirectiveOutcome,
    DiversityMetrics,
    ExampleSummary,
    FrontComparison,
    MetricDeltas,
    MutationHistory,
    MutationRecord,
    NearMissCandidate,
    OracleMetrics,
    ReviewBriefing,
)
from odysseus.agents.routing_context import RoutingContext
from odysseus.eval.models import ScoreReport

_log = logging.getLogger(__name__)


def _extract_metric(report: dict[str, Any], metric: str) -> float | None:
    """Extract a metric value from a ScoreReport dict, or None if absent."""
    metrics = report.get("metrics")
    if not isinstance(metrics, dict) or metric not in metrics:
        return None
    return float(metrics[metric])


def _delta(a: float | None, b: float | None) -> float | None:
    """Subtract two nullable floats. Returns None if either operand is None."""
    if a is None or b is None:
        return None
    return a - b


def _compute_recall_deltas(
    candidate_report: dict[str, Any],
    reference_report: dict[str, Any],
) -> dict[str, float]:
    """Compute per-class recall deltas between two reports."""
    candidate_metrics = candidate_report.get("metrics", {})
    reference_metrics = reference_report.get("metrics", {})

    deltas: dict[str, float] = {}
    for key, value in candidate_metrics.items():
        if key.startswith("recall/"):
            route = key.removeprefix("recall/")
            ref_value = reference_metrics.get(key)
            if ref_value is None:
                continue
            deltas[route] = value - ref_value
    return deltas


def build_candidate_comparisons(
    *,
    score_reports: dict[str, dict[str, Any]],
    mutation_descriptions: dict[str, str],
    parent_versions: dict[str, str | None],
    front_versions: list[str],
    primary_metric: str = "accuracy",
) -> list[CandidateAnalysis]:
    """Build per-candidate analysis with deltas vs parent and front.

    Args:
        score_reports: All available reports keyed by version (candidates + front).
        mutation_descriptions: What changed, keyed by candidate version.
        parent_versions: Parent version for each candidate.
        front_versions: Versions currently on the Pareto front.
        primary_metric: The quality metric to use for deltas.
    """
    candidate_versions = list(mutation_descriptions.keys())
    results: list[CandidateAnalysis] = []

    for version in candidate_versions:
        report = score_reports[version]
        parent = parent_versions.get(version)
        candidate_quality = _extract_metric(report, primary_metric)
        candidate_cost = _extract_metric(report, "cost")

        # Delta vs parent
        if parent and parent in score_reports:
            parent_report = score_reports[parent]
            if candidate_quality is None:
                _log.warning("Metric %r missing from candidate %s", primary_metric, version)
            parent_quality = _extract_metric(parent_report, primary_metric)
            delta_parent = MetricDeltas(
                quality_delta=_delta(candidate_quality, parent_quality),
                cost_delta=_delta(candidate_cost, _extract_metric(parent_report, "cost")),
                per_class_recall_deltas=_compute_recall_deltas(report, parent_report),
            )
        else:
            delta_parent = MetricDeltas(quality_delta=None, cost_delta=None, per_class_recall_deltas={})

        # Delta vs each front member
        delta_front: list[FrontComparison] = []
        for fv in front_versions:
            if fv in score_reports:
                front_report = score_reports[fv]
                front_quality = _extract_metric(front_report, primary_metric)
                front_cost = _extract_metric(front_report, "cost")
                delta_front.append(
                    FrontComparison(
                        front_candidate_version=fv,
                        quality_delta=_delta(candidate_quality, front_quality),
                        cost_delta=_delta(candidate_cost, front_cost),
                    )
                )

        results.append(
            CandidateAnalysis(
                candidate_version=version,
                parent_version=parent,
                mutation_description=mutation_descriptions[version],
                score_report=ScoreReport.model_validate(report),
                delta_vs_parent=delta_parent,
                delta_vs_front=delta_front,
            )
        )

    return results


def _best_recall_per_class(
    reports: dict[str, dict[str, Any]],
) -> dict[str, tuple[float, int]]:
    """From a set of reports, get the best recall and support per class."""
    best: dict[str, tuple[float, int]] = {}
    for report in reports.values():
        metrics = report.get("metrics", {})
        for key, value in metrics.items():
            if key.startswith("recall/"):
                route = key.removeprefix("recall/")
                support_key = f"support/{route}"
                support = int(metrics.get(support_key, 0))
                if route not in best or value > best[route][0]:
                    best[route] = (value, support)
    return best


def extract_per_class_recall(
    *,
    current_reports: dict[str, dict[str, Any]],
    historical_reports: dict[int, dict[str, dict[str, Any]]],
    current_round: int,
) -> dict[str, ClassRecallEntry]:
    """Extract per-route recall with trends and regression flags.

    Uses the best recall per class across candidates in each round
    to build the trend. Regression is flagged when the current round's
    best recall is lower than the previous round's best.
    """
    # Build trend: best recall per class for each historical round
    all_rounds: dict[int, dict[str, tuple[float, int]]] = {}
    for round_num, reports in historical_reports.items():
        all_rounds[round_num] = _best_recall_per_class(reports)
    all_rounds[current_round] = _best_recall_per_class(current_reports)

    # Collect all known classes
    all_classes: set[str] = set()
    for round_data in all_rounds.values():
        all_classes.update(round_data.keys())

    result: dict[str, ClassRecallEntry] = {}
    for route in sorted(all_classes):
        trend: list[float] = []
        support = 0
        for round_num in sorted(all_rounds.keys()):
            if route in all_rounds[round_num]:
                recall_val, support_val = all_rounds[round_num][route]
                trend.append(recall_val)
                support = support_val  # Use latest support count

        current_recall = trend[-1] if trend else 0.0
        previous_recall = trend[-2] if len(trend) >= 2 else current_recall
        regression_flag = current_recall < previous_recall

        result[route] = ClassRecallEntry(
            recall=current_recall,
            support=support,
            trend=trend,
            regression_flag=regression_flag,
        )

    return result


def _extract_example_ids(prompt_text: str) -> set[str]:
    """Extract example identifiers from a prompt following the Markdown convention."""
    return set(re.findall(r"###\s+Example\s+(\S+)", prompt_text))


def _pairwise_dissimilarity(texts: list[str]) -> float:
    """Average pairwise dissimilarity (1 - SequenceMatcher ratio) across texts."""
    if len(texts) < 2:
        return 0.0
    total = 0.0
    pairs = 0
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            ratio = difflib.SequenceMatcher(None, texts[i], texts[j]).ratio()
            total += 1.0 - ratio
            pairs += 1
    return total / pairs if pairs > 0 else 0.0


def _example_overlap_ratio(prompt_texts: dict[str, str]) -> float:
    """Fraction of examples shared across all prompts on the front."""
    if len(prompt_texts) < 2:
        return 1.0
    example_sets = [_extract_example_ids(text) for text in prompt_texts.values()]
    all_examples = set().union(*example_sets) if example_sets else set()
    if not all_examples:
        return 1.0
    shared = set.intersection(*example_sets) if example_sets else set()
    return len(shared) / len(all_examples)


def compute_diversity_metrics(
    *,
    prompt_texts: dict[str, str],
    mutation_log: list[MutationRecord],
) -> DiversityMetrics:
    """Compute diversity metrics across Pareto front prompts.

    prompt_similarity: 0.0 = identical, approaching 1.0 = very different.
    example_overlap_ratio: 1.0 = all prompts use same examples, 0.0 = no overlap.
    """
    texts = list(prompt_texts.values())
    type_counts = Counter(m.mutation_type for m in mutation_log)

    return DiversityMetrics(
        example_overlap_ratio=_example_overlap_ratio(prompt_texts),
        prompt_similarity=_pairwise_dissimilarity(texts),
        mutation_type_distribution=dict(type_counts),
    )


def compute_near_misses(
    candidates: list[Candidate],
    front: list[Candidate],
) -> list[NearMissCandidate]:
    """For each dominated candidate, find its minimum domination gap to the front.

    A candidate is a near-miss if it is dominated by at least one front member.
    The gap is the minimum (quality_deficit, cost_excess) pair across all dominators.
    Candidates that are incomparable with the entire front are excluded.
    """
    front_versions = {c.prompt_version for c in front}
    near_misses: list[NearMissCandidate] = []
    for candidate in candidates:
        if candidate.prompt_version in front_versions:
            continue
        min_gap_quality = float("inf")
        min_gap_cost = float("inf")
        dominated_by_any = False
        for f in front:
            if (
                f.quality_score >= candidate.quality_score
                and f.cost <= candidate.cost
                and (f.quality_score > candidate.quality_score or f.cost < candidate.cost)
            ):
                dominated_by_any = True
                gap_q = f.quality_score - candidate.quality_score
                gap_c = candidate.cost - f.cost
                if gap_q + gap_c < min_gap_quality + min_gap_cost:
                    min_gap_quality = gap_q
                    min_gap_cost = gap_c
        if dominated_by_any:
            near_misses.append(NearMissCandidate(
                version=candidate.prompt_version,
                domination_gap_quality=min_gap_quality,
                domination_gap_cost=min_gap_cost,
            ))
    return near_misses


def compute_diminishing_returns(
    *,
    score_trajectory: list[float],
    stagnation_threshold: float = 0.005,
) -> DiminishingReturns:
    """Analyze score trajectory for diminishing returns.

    improvement_trend is the average improvement over the last 3 rounds
    (or fewer if not enough data). stagnation_flag is True when improvement
    is below the threshold and there are at least 2 data points.
    """
    if len(score_trajectory) < 2:
        return DiminishingReturns(
            score_trajectory=score_trajectory,
            improvement_trend=0.0,
            stagnation_flag=False,
            improvement_stddev=0.0,
            effective_threshold=stagnation_threshold,
        )

    # Use last 7 rounds for trend (or all if fewer)
    window = score_trajectory[-min(7, len(score_trajectory)) :]
    deltas = [window[i] - window[i - 1] for i in range(1, len(window))]
    trend = sum(deltas) / len(deltas) if deltas else 0.0
    stddev = statistics.pstdev(deltas) if len(deltas) >= 2 else 0.0

    return DiminishingReturns(
        score_trajectory=score_trajectory,
        improvement_trend=trend,
        stagnation_flag=trend < stagnation_threshold,
        improvement_stddev=stddev,
        effective_threshold=stagnation_threshold,
    )


_ALL_MUTATION_TYPES = [
    "example_swap",
    "rule_edit",
    "schema_change",
    "rule_add",
    "rule_remove",
    "vocabulary_edit",
]


def correlate_mutations(
    *,
    mutation_log: list[MutationRecord],
    score_history: dict[str, float],
    all_mutation_types: list[str] | None = None,
) -> MutationHistory:
    """Classify mutations as effective or ineffective based on score changes.

    A mutation is effective if the child's score exceeds the parent's score.

    Args:
        mutation_log: All mutations recorded so far.
        score_history: version -> primary metric score.
        all_mutation_types: Full list of possible mutation types (defaults to built-in list).
    """
    if all_mutation_types is None:
        all_mutation_types = _ALL_MUTATION_TYPES

    effective: list[MutationRecord] = []
    ineffective: list[MutationRecord] = []
    unscored: list[MutationRecord] = []
    tried_types: set[str] = set()

    for mutation in mutation_log:
        tried_types.add(mutation.mutation_type)
        child_score = score_history.get(mutation.child_version)
        parent_score = score_history.get(mutation.parent_version)
        if child_score is None or parent_score is None:
            _log.warning(
                "Missing score for mutation %s -> %s, skipping classification",
                mutation.parent_version,
                mutation.child_version,
            )
            unscored.append(mutation)
            continue
        if child_score > parent_score:
            effective.append(mutation)
        else:
            ineffective.append(mutation)

    untried = [t for t in all_mutation_types if t not in tried_types]

    return MutationHistory(
        effective_mutations=effective,
        ineffective_mutations=ineffective,
        untried_mutation_types=untried,
        unscored_mutations=unscored,
    )


def compute_oracle_metrics(
    *,
    oracle_cost_change: float,
    oracle_quality_change: float,
    candidate_cost_change: float,
    candidate_cost_change_with_overhead: float,
    candidate_quality_change: float,
) -> OracleMetrics:
    """Compute how much of the theoretical routing improvement has been captured."""
    return OracleMetrics(
        oracle_cost_change=oracle_cost_change,
        oracle_quality_change=oracle_quality_change,
        candidate_cost_captured=(
            candidate_cost_change / oracle_cost_change if oracle_cost_change != 0.0 else None
        ),
        candidate_cost_captured_with_overhead=(
            candidate_cost_change_with_overhead / oracle_cost_change if oracle_cost_change != 0.0 else None
        ),
        candidate_quality_captured=(
            candidate_quality_change / oracle_quality_change if oracle_quality_change != 0.0 else None
        ),
    )


def compute_oracle_metrics_from_report(
    *,
    metrics: dict[str, float],
) -> OracleMetrics | None:
    """Extract oracle metrics from a ScoreReport metrics dict.

    Returns None if required oracle metric keys are absent.
    """
    required = [
        "oracle_cost_change",
        "oracle_quality_change",
        "cost_change",
        "cost_change_with_overhead",
        "quality_change",
    ]
    missing = [k for k in required if k not in metrics]
    if missing:
        return None

    return compute_oracle_metrics(
        oracle_cost_change=metrics["oracle_cost_change"],
        oracle_quality_change=metrics["oracle_quality_change"],
        candidate_cost_change=metrics["cost_change"],
        candidate_cost_change_with_overhead=metrics["cost_change_with_overhead"],
        candidate_quality_change=metrics["quality_change"],
    )


def _build_score_trajectory(
    historical_reports: dict[int, dict[str, dict[str, Any]]],
    current_reports: dict[str, dict[str, Any]],
    current_round: int,
    primary_metric: str,
) -> list[float]:
    """Build a score trajectory: best primary metric per round."""
    trajectory: list[float] = []
    for round_num in sorted(historical_reports.keys()):
        reports = historical_reports[round_num]
        scores = [s for s in (_extract_metric(r, primary_metric) for r in reports.values()) if s is not None]
        if scores:
            trajectory.append(max(scores))
    # Current round
    current_scores = [
        s for s in (_extract_metric(r, primary_metric) for r in current_reports.values())
        if s is not None
    ]
    if current_scores:
        trajectory.append(max(current_scores))
    return trajectory


def _build_score_history(
    historical_reports: dict[int, dict[str, dict[str, Any]]],
    current_reports: dict[str, dict[str, Any]],
    primary_metric: str,
) -> dict[str, float]:
    """Build a flat version -> score map from all reports."""
    scores: dict[str, float] = {}
    for reports in historical_reports.values():
        for version, report in reports.items():
            score = _extract_metric(report, primary_metric)
            if score is not None:
                scores[version] = score
    for version, report in current_reports.items():
        score = _extract_metric(report, primary_metric)
        if score is not None:
            scores[version] = score
    return scores


def generate_executive_summary(briefing: ReviewBriefing, primary_metric: str = "accuracy") -> str:
    """Generate a purely factual executive summary of the briefing data."""
    lines: list[str] = []

    # Round and scale
    n_candidates = len(briefing.candidates)
    n_front = len(briefing.elite_set)
    lines.append(f"Round {briefing.round}. {n_candidates} candidate(s) evaluated against {n_front} front member(s).")

    # Best candidate by quality delta vs parent
    candidates_with_quality = [
        c for c in briefing.candidates if c.delta_vs_parent.quality_delta is not None
    ]
    if candidates_with_quality:
        best = max(candidates_with_quality, key=lambda c: c.delta_vs_parent.quality_delta)  # type: ignore[arg-type]
        metrics = best.score_report.metrics or {}
        quality = metrics.get(primary_metric)
        cost = metrics.get("cost")
        parts = [f"Best candidate: {best.candidate_version}"]
        if quality is not None:
            parts.append(f"quality={quality:.3f}")
        if cost is not None:
            parts.append(f"cost={cost:.4f}")
        if best.delta_vs_parent.quality_delta is not None:
            sign = "+" if best.delta_vs_parent.quality_delta >= 0 else ""
            parts.append(f"delta vs parent: {sign}{best.delta_vs_parent.quality_delta:.3f}")
        lines.append(", ".join(parts) + ".")

    # Regressions — sorted by support (lowest first = most critical)
    regressions = [
        (route, entry)
        for route, entry in briefing.per_class_recall.items()
        if entry.regression_flag
    ]
    if regressions:
        regressions.sort(key=lambda r: r[1].support)
        for route, entry in regressions:
            prev = entry.trend[-2] if len(entry.trend) >= 2 else None
            prev_str = f"{prev:.2f}" if prev is not None else "?"
            lines.append(
                f"REGRESSION: {route} recall {prev_str} -> {entry.recall:.2f} (support={entry.support})."
            )

    # Oracle gap
    om = briefing.oracle_metrics
    if om is not None:
        parts = []
        if om.candidate_quality_captured is not None:
            parts.append(f"quality {om.candidate_quality_captured:.0%} captured")
        else:
            parts.append("quality: no headroom (oracle change is 0)")
        if om.candidate_cost_captured is not None:
            parts.append(f"cost {om.candidate_cost_captured:.0%} captured")
        else:
            parts.append("cost: no headroom (oracle change is 0)")
        lines.append("Oracle gap: " + ", ".join(parts) + ".")

    # Stagnation
    dr = briefing.diminishing_returns
    sign = "+" if dr.improvement_trend >= 0 else ""
    stag = " Stagnation flag is set." if dr.stagnation_flag else ""
    lines.append(f"Improvement trend: {sign}{dr.improvement_trend:.4f}/round.{stag}")

    # Diversity
    dm = briefing.diversity_metrics
    lines.append(f"Diversity: prompt_similarity={dm.prompt_similarity:.2f} (0=identical, 1=different).")
    untried = briefing.mutation_history.untried_mutation_types
    if untried:
        lines.append(f"Untried mutation types: {', '.join(untried)}.")
    else:
        lines.append("All mutation types have been tried.")

    return "\n".join(lines)


def build_review_briefing(
    *,
    search_state: Any,
    score_reports: dict[str, dict[str, Any]],
    historical_reports: dict[int, dict[str, dict[str, Any]]],
    prompt_texts: dict[str, str],
    mutation_log: list[MutationRecord],
    directive_history: list[DirectiveOutcome],
    holdout_examples: list[ExampleSummary],
    candidate_versions: list[str],
    parent_versions: dict[str, str | None],
    routing_context: RoutingContext | None = None,
) -> ReviewBriefing:
    """Assemble a complete ReviewBriefing from raw pipeline data.

    This is the main orchestrator that calls all computation functions.
    """
    current_round: int = search_state.round
    primary_metric: str = search_state.primary_metric_name or "accuracy"
    pareto_front = search_state.elite_set
    front_versions = [c.prompt_version for c in pareto_front]

    # Mutation descriptions for current candidates
    mutation_descriptions: dict[str, str] = {}
    for version in candidate_versions:
        matching = [m for m in mutation_log if m.child_version == version]
        mutation_descriptions[version] = matching[-1].description if matching else "No mutation record"

    # 1. Candidate comparisons
    candidates = build_candidate_comparisons(
        score_reports=score_reports,
        mutation_descriptions=mutation_descriptions,
        parent_versions=parent_versions,
        front_versions=front_versions,
        primary_metric=primary_metric,
    )

    # 2. Per-class recall
    per_class_recall = extract_per_class_recall(
        current_reports=score_reports,
        historical_reports=historical_reports,
        current_round=current_round,
    )

    # 3. Diversity metrics (front prompts only)
    front_prompt_texts = {v: prompt_texts[v] for v in front_versions if v in prompt_texts}
    diversity_metrics = compute_diversity_metrics(
        prompt_texts=front_prompt_texts,
        mutation_log=mutation_log,
    )

    # 4. Diminishing returns
    score_trajectory = _build_score_trajectory(
        historical_reports,
        score_reports,
        current_round,
        primary_metric,
    )
    best_score = max(score_trajectory) if score_trajectory else 0.0
    effective_threshold = max(0.005, 0.01 * best_score)
    diminishing_returns = compute_diminishing_returns(
        score_trajectory=score_trajectory,
        stagnation_threshold=effective_threshold,
    )

    # 5. Mutation correlation
    score_history = _build_score_history(
        historical_reports,
        score_reports,
        primary_metric,
    )
    mutation_history = correlate_mutations(
        mutation_log=mutation_log,
        score_history=score_history,
    )

    # 6. Oracle metrics — use the best current candidate's report
    best_candidate = max(
        candidate_versions,
        key=lambda v: _extract_metric(score_reports.get(v, {}), primary_metric) or 0.0,
    )
    oracle_metrics = compute_oracle_metrics_from_report(
        metrics=score_reports[best_candidate].get("metrics", {}),
    )

    # 7. Near-miss candidates
    current_candidates = [
        Candidate(
            prompt_version=v,
            parent_version=parent_versions.get(v),
            quality_score=_extract_metric(score_reports[v], primary_metric) or 0.0,
            cost=_extract_metric(score_reports[v], "cost") or 0.0,
            round_introduced=current_round,
        )
        for v in candidate_versions
        if v in score_reports
    ]
    near_misses = compute_near_misses(current_candidates, pareto_front)

    # Hill-climb stagnation signal — other strategies will write a different
    # dict shape into this same field from their own preprocessor paths.
    stagnation_signal: dict[str, Any] = {
        "count": search_state.stagnation_count,
        "limit": search_state.stagnation_limit,
        "mutation_mode": search_state.mutation_mode,
    }

    briefing = ReviewBriefing(
        round=current_round,
        candidates=candidates,
        elite_set=pareto_front,
        per_class_recall=per_class_recall,
        diversity_metrics=diversity_metrics,
        diminishing_returns=diminishing_returns,
        mutation_history=mutation_history,
        oracle_metrics=oracle_metrics,
        prompt_versions=prompt_texts,
        holdout_examples=holdout_examples,
        routing_context=routing_context,
        directive_history=directive_history,
        near_miss_candidates=near_misses,
        stagnation_signal=stagnation_signal,
    )
    return briefing.model_copy(
        update={"executive_summary": generate_executive_summary(briefing, primary_metric)},
    )
