"""Code pre-processor for the Review Agent.

Pure computation functions that transform raw ScoreReports, SearchState,
and historical data into a ReviewBriefing. No external dependencies
beyond stdlib (difflib).
"""

from __future__ import annotations

import difflib
import re
from collections import Counter
from typing import Any

from odysseus.agents.review_models import (
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
    OracleMetrics,
    ReviewBriefing,
)
from odysseus.eval.models import ScoreReport


def _extract_metric(report: dict[str, Any], metric: str) -> float:
    """Extract a metric value from a ScoreReport dict, defaulting to 0.0."""
    return float(report.get("metrics", {}).get(metric, 0.0))


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
            ref_value = reference_metrics.get(key, 0.0)
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

        # Delta vs parent
        if parent and parent in score_reports:
            parent_report = score_reports[parent]
            delta_parent = MetricDeltas(
                quality_delta=_extract_metric(report, primary_metric) - _extract_metric(parent_report, primary_metric),
                cost_delta=_extract_metric(report, "cost") - _extract_metric(parent_report, "cost"),
                per_class_recall_deltas=_compute_recall_deltas(report, parent_report),
            )
        else:
            delta_parent = MetricDeltas(quality_delta=0.0, cost_delta=0.0, per_class_recall_deltas={})

        # Delta vs each front member
        delta_front: list[FrontComparison] = []
        for fv in front_versions:
            if fv in score_reports:
                front_report = score_reports[fv]
                delta_front.append(
                    FrontComparison(
                        front_candidate_version=fv,
                        quality_delta=_extract_metric(report, primary_metric)
                        - _extract_metric(front_report, primary_metric),
                        cost_delta=_extract_metric(report, "cost") - _extract_metric(front_report, "cost"),
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
        )

    # Use last 3 rounds for trend (or all if fewer)
    window = score_trajectory[-min(4, len(score_trajectory)) :]
    deltas = [window[i] - window[i - 1] for i in range(1, len(window))]
    trend = sum(deltas) / len(deltas) if deltas else 0.0

    return DiminishingReturns(
        score_trajectory=score_trajectory,
        improvement_trend=trend,
        stagnation_flag=trend < stagnation_threshold,
    )


_ALL_MUTATION_TYPES = [
    "example_swap",
    "rule_edit",
    "schema_change",
    "rule_add",
    "rule_remove",
    "assembly_policy",
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
    tried_types: set[str] = set()

    for mutation in mutation_log:
        tried_types.add(mutation.mutation_type)
        child_score = score_history.get(mutation.child_version, 0.0)
        parent_score = score_history.get(mutation.parent_version, 0.0)
        if child_score > parent_score:
            effective.append(mutation)
        else:
            ineffective.append(mutation)

    untried = [t for t in all_mutation_types if t not in tried_types]

    return MutationHistory(
        effective_mutations=effective,
        ineffective_mutations=ineffective,
        untried_mutation_types=untried,
    )


def compute_oracle_metrics(
    *,
    oracle_cost_reduction: float,
    oracle_quality_reduction: float,
    candidate_cost_reduction: float,
    candidate_quality_reduction: float,
) -> OracleMetrics:
    """Compute how much of the theoretical routing improvement has been captured."""
    return OracleMetrics(
        oracle_cost_reduction=oracle_cost_reduction,
        oracle_quality_reduction=oracle_quality_reduction,
        candidate_cost_captured=(
            candidate_cost_reduction / oracle_cost_reduction if oracle_cost_reduction != 0.0 else None
        ),
        candidate_quality_captured=(
            candidate_quality_reduction / oracle_quality_reduction if oracle_quality_reduction != 0.0 else None
        ),
    )


def compute_oracle_metrics_from_report(
    *,
    metrics: dict[str, float],
) -> OracleMetrics:
    """Extract oracle metrics from a ScoreReport metrics dict.

    Raises ValueError if oracle metric keys are absent.
    """
    required = [
        "oracle_cost_reduction",
        "oracle_quality_reduction",
        "cost_reduction",
        "quality_reduction",
    ]
    missing = [k for k in required if k not in metrics]
    if missing:
        msg = f"oracle metrics missing from ScoreReport: {missing}"
        raise ValueError(msg)

    return compute_oracle_metrics(
        oracle_cost_reduction=metrics["oracle_cost_reduction"],
        oracle_quality_reduction=metrics["oracle_quality_reduction"],
        candidate_cost_reduction=metrics["cost_reduction"],
        candidate_quality_reduction=metrics["quality_reduction"],
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
        best = max(
            (_extract_metric(r, primary_metric) for r in reports.values()),
            default=0.0,
        )
        trajectory.append(best)
    # Current round
    best_current = max(
        (_extract_metric(r, primary_metric) for r in current_reports.values()),
        default=0.0,
    )
    trajectory.append(best_current)
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
            scores[version] = _extract_metric(report, primary_metric)
    for version, report in current_reports.items():
        scores[version] = _extract_metric(report, primary_metric)
    return scores


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
) -> ReviewBriefing:
    """Assemble a complete ReviewBriefing from raw pipeline data.

    This is the main orchestrator that calls all computation functions.
    """
    current_round: int = search_state.round
    primary_metric: str = search_state.primary_metric_name or "accuracy"
    pareto_front = search_state.pareto_front
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
    diminishing_returns = compute_diminishing_returns(
        score_trajectory=score_trajectory,
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
        key=lambda v: _extract_metric(score_reports.get(v, {}), primary_metric),
    )
    oracle_metrics = compute_oracle_metrics_from_report(
        metrics=score_reports[best_candidate].get("metrics", {}),
    )

    return ReviewBriefing(
        round=current_round,
        candidates=candidates,
        pareto_front=pareto_front,
        per_class_recall=per_class_recall,
        diversity_metrics=diversity_metrics,
        diminishing_returns=diminishing_returns,
        mutation_history=mutation_history,
        oracle_metrics=oracle_metrics,
        prompt_versions=prompt_texts,
        holdout_examples=holdout_examples,
    )
