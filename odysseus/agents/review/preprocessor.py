"""Code pre-processor for the Review Agent.

Pure computation functions that transform raw ScoreReports, SearchState,
and historical data into a ReviewBriefing. No external dependencies
beyond stdlib.
"""

from __future__ import annotations

import json
import logging
import operator as _operator_mod
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from odysseus.agents.prompt_builder.search import Candidate
from odysseus.agents.review.models import (
    BatchOutcome,
    CandidateAnalysis,
    ChildVariant,
    ClassRecallEntry,
    ConfusionImpact,
    DiminishingReturns,
    DirectiveOutcome,
    DiversityMetrics,
    MetricDeltas,
    NearMissCandidate,
    OracleMetrics,
    ReviewBriefing,
    UserTarget,
    UserTargetProgress,
)
from odysseus.agents.routing_context import RoutingContext
from odysseus.eval.models import EvalResult, Example, ScoreReport

_log = logging.getLogger(__name__)

_PRIMARY_METRICS = frozenset({
    "accuracy", "cost_change", "cost_change_with_overhead", "quality_change", "f1/macro",
})


def _filter_metric_deltas(
    deltas: dict[str, float],
    primary_metrics: frozenset[str] | set[str] = _PRIMARY_METRICS,
    target_metrics: set[str] | None = None,
    threshold: float = 0.01,
) -> dict[str, float]:
    """Filter metric deltas to significant changes only.

    Keeps: primary metrics, metrics matching user targets, and any metric
    with abs(delta) > threshold. Removes confusion/* keys.
    """
    target_metrics = target_metrics or set()
    filtered: dict[str, float] = {}
    for key, value in deltas.items():
        if key.startswith("confusion/"):
            continue
        if key in primary_metrics or key in target_metrics or abs(value) > threshold:
            filtered[key] = value
    return filtered


@dataclass
class _TargetSlackResult:
    """Local result type for compute_target_slack — decoupled from TargetSlack model."""

    metric: str
    surplus: float
    regression_budget: float
    priority_weight: float
    current_value: float | None = None


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


def _compute_metric_deltas(
    candidate_report: dict[str, Any],
    reference_report: dict[str, Any],
) -> dict[str, float]:
    """Compute deltas for all shared metrics between candidate and reference."""
    candidate_metrics = candidate_report.get("metrics", {})
    reference_metrics = reference_report.get("metrics", {})
    deltas: dict[str, float] = {}
    for key in candidate_metrics:
        if key in reference_metrics:
            deltas[key] = candidate_metrics[key] - reference_metrics[key]
    return deltas


def build_candidate_comparisons(
    *,
    score_reports: dict[str, dict[str, Any]],
    mutation_descriptions: dict[str, str],
    parent_versions: dict[str, str | None],
    primary_metric: str = "accuracy",
) -> list[CandidateAnalysis]:
    """Build per-candidate analysis with deltas vs parent.

    Args:
        score_reports: All available reports keyed by version (candidates + elite).
        mutation_descriptions: What changed, keyed by candidate version.
        parent_versions: Parent version for each candidate.
        primary_metric: The quality metric to use for deltas.
    """
    candidate_versions = list(mutation_descriptions.keys())
    results: list[CandidateAnalysis] = []

    for version in candidate_versions:
        if version not in score_reports:
            _log.warning("Skipping candidate %s: no score report loaded", version)
            continue
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

        # Filter confusion/* keys from score_report metrics (copy, do not mutate original)
        report_dict: dict[str, Any] = report
        if report_dict.get("metrics"):
            report_dict = {**report_dict, "metrics": {
                k: v for k, v in report_dict["metrics"].items()
                if not k.startswith("confusion/")
            }}

        results.append(
            CandidateAnalysis(
                candidate_version=version,
                parent_version=parent,
                mutation_description=mutation_descriptions[version],
                score_report=ScoreReport.model_validate(report_dict),
                delta_vs_parent=delta_parent,
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

        trend = trend[-5:]  # Keep last 5 rounds only

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
) -> DiversityMetrics:
    """Compute diversity metrics across elite set prompts.

    example_overlap_ratio: 1.0 = all prompts use same examples, 0.0 = no overlap.
    """
    return DiversityMetrics(example_overlap_ratio=_example_overlap_ratio(prompt_texts))


def compute_target_slack(
    targets: list[UserTarget],
    best_metrics: dict[str, float],
) -> list[_TargetSlackResult]:
    """Compute per-target surplus/deficit for aggressiveness allocation."""
    slacks: list[_TargetSlackResult] = []
    for t in targets:
        current = best_metrics.get(t.metric)
        if current is None:
            slacks.append(_TargetSlackResult(
                metric=t.metric,
                surplus=-abs(t.threshold) if t.threshold != 0 else -1.0,
                regression_budget=0.0,
                priority_weight=1.0,
                current_value=None,
            ))
            continue

        if t.operator in (">=", ">"):
            surplus = current - t.threshold
        elif t.operator in ("<=", "<"):
            surplus = t.threshold - current
        else:
            surplus = -abs(current - t.threshold)

        slacks.append(_TargetSlackResult(
            metric=t.metric,
            surplus=surplus,
            regression_budget=max(0.0, surplus),
            priority_weight=0.0,
            current_value=current,
        ))

    deficits = [max(0.0, -s.surplus) for s in slacks]
    total_deficit = sum(deficits)
    if total_deficit > 0:
        for i, s in enumerate(slacks):
            slacks[i] = _TargetSlackResult(
                metric=s.metric,
                surplus=s.surplus,
                regression_budget=s.regression_budget,
                priority_weight=deficits[i] / total_deficit,
                current_value=s.current_value,
            )

    return slacks


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
            score_trajectory=score_trajectory[-8:],
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
        score_trajectory=score_trajectory[-8:],
        improvement_trend=trend,
        stagnation_flag=trend < stagnation_threshold,
        improvement_stddev=stddev,
        effective_threshold=stagnation_threshold,
    )


def parse_user_targets(report_text: str) -> list[UserTarget]:
    """Parse target metrics from a validated input report's '### Target Metrics' section."""
    # Find the Target Metrics section
    section_match = re.search(
        r"###\s*Target\s+Metrics\s*\n(.*?)(?=\n###|\n##|\Z)",
        report_text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section_match:
        return []

    section_text = section_match.group(1)
    targets: list[UserTarget] = []
    # Match lines like: - `cost_change_with_overhead` <= -0.45
    # or: - cost_change_with_overhead <= -0.45
    pattern = re.compile(r"-\s*`?(\w+)`?\s*(<=|>=|<|>|==)\s*(-?[\d.]+)")
    for match in pattern.finditer(section_text):
        metric = match.group(1)
        op = match.group(2)
        threshold = float(match.group(3))
        # The regex guarantees op is one of the valid Literal values
        targets.append(UserTarget(metric=metric, operator=op, threshold=threshold))  # type: ignore[arg-type]

    return targets


_OPERATOR_MAP: dict[str, Any] = {
    "<=": _operator_mod.le,
    ">=": _operator_mod.ge,
    "<": _operator_mod.lt,
    ">": _operator_mod.gt,
    "==": _operator_mod.eq,
}

# Map user-facing metric names to oracle metric keys
_ORACLE_METRIC_MAP: dict[str, str] = {
    "cost_change": "oracle_cost_change",
    "cost_change_with_overhead": "oracle_cost_change",
    "quality_change": "oracle_quality_change",
}


def _count_targets_met(targets: list[UserTarget], metrics: dict[str, float]) -> int:
    """Return the number of targets whose threshold is satisfied by the given metrics."""
    count = 0
    for target in targets:
        value = metrics.get(target.metric)
        if value is None:
            continue
        op_fn = _OPERATOR_MAP[target.operator]
        if bool(op_fn(value, target.threshold)):
            count += 1
    return count


def _sum_capped_progress(targets: list[UserTarget], metrics: dict[str, float]) -> float:
    """Return the sum of per-target progress ratios, each capped at 1.0."""
    total = 0.0
    for target in targets:
        value = metrics.get(target.metric)
        if value is None:
            continue
        progress = abs(value / target.threshold) if target.threshold != 0 else (
            1.0 if bool(_OPERATOR_MAP[target.operator](value, target.threshold)) else 0.0
        )
        total += min(progress, 1.0)
    return total


def _min_progress(targets: list[UserTarget], metrics: dict[str, float]) -> float:
    """Return the minimum per-target capped progress ratio (worst-performing target)."""
    minimum = float("inf")
    has_any = False
    for target in targets:
        value = metrics.get(target.metric)
        if value is None:
            continue
        has_any = True
        progress = abs(value / target.threshold) if target.threshold != 0 else (
            1.0 if bool(_OPERATOR_MAP[target.operator](value, target.threshold)) else 0.0
        )
        minimum = min(minimum, min(progress, 1.0))
    return minimum if has_any else 0.0


def compute_target_progress(
    targets: list[UserTarget],
    best_metrics: dict[str, float],
    oracle_metrics: OracleMetrics | None,
    full_dataset_oracle: dict[str, float] | None = None,
    dev_oracle: dict[str, float] | None = None,
    source_version: str | None = None,
) -> list[UserTargetProgress]:
    """Compute progress toward each user target from the best candidate's metrics."""
    results: list[UserTargetProgress] = []
    for target in targets:
        current_value = best_metrics.get(target.metric)

        # Evaluate whether target is met
        if current_value is not None:
            op_fn = _OPERATOR_MAP[target.operator]
            met = bool(op_fn(current_value, target.threshold))
        else:
            met = False

        # Compute progress ratio (0.0 = no progress, 1.0 = target met)
        progress_ratio: float | None = None
        if current_value is not None and target.threshold != 0.0:
            progress_ratio = max(0.0, abs(current_value / target.threshold))
            # Ensure met targets always show ratio >= 1.0
            if met and progress_ratio < 1.0:
                progress_ratio = 1.0

        # Oracle ceiling lookup
        oracle_ceiling: float | None = None
        target_above_oracle = False
        oracle_key = _ORACLE_METRIC_MAP.get(target.metric)
        if oracle_key is not None:
            # Prefer dev_oracle (precomputed dataset-level) over per-eval oracle_metrics
            if dev_oracle is not None:
                oracle_ceiling = dev_oracle.get(oracle_key)
            elif oracle_metrics is not None:
                oracle_ceiling = getattr(oracle_metrics, oracle_key, None)
            if oracle_ceiling is not None and target.threshold != 0.0:
                # Check if target is more aggressive than oracle
                if target.operator in ("<=", "<"):
                    # For cost: target wants lower, oracle is the floor
                    target_above_oracle = target.threshold < oracle_ceiling
                elif target.operator in (">=", ">"):
                    # For quality: target wants higher, oracle is the ceiling
                    target_above_oracle = target.threshold > oracle_ceiling

        # Full-dataset oracle translation
        full_dataset_oracle_ceiling: float | None = None
        capture_ratio: float | None = None
        translated_threshold: float | None = None
        if full_dataset_oracle is not None and oracle_key is not None:
            full_oracle_value = full_dataset_oracle.get(oracle_key)
            if full_oracle_value is not None:
                full_dataset_oracle_ceiling = full_oracle_value
                if full_oracle_value != 0.0:
                    capture_ratio = target.threshold / full_oracle_value
                    # Translate target threshold to dev-set scale using dev oracle ceiling
                    dev_oracle_ceiling = oracle_ceiling
                    if dev_oracle_ceiling is not None and dev_oracle_ceiling != 0.0:
                        translated_threshold = capture_ratio * dev_oracle_ceiling
                    # Override target_above_oracle using capture_ratio
                    target_above_oracle = abs(capture_ratio) > 1.0
                    # Override met and progress_ratio using translated threshold
                    if translated_threshold is not None and current_value is not None:
                        op_fn = _OPERATOR_MAP[target.operator]
                        met = bool(op_fn(current_value, translated_threshold))
                        if translated_threshold != 0.0:
                            progress_ratio = max(0.0, abs(current_value / translated_threshold))
                            if met and progress_ratio < 1.0:
                                progress_ratio = 1.0

        results.append(UserTargetProgress(
            target=target,
            current_value=current_value,
            met=met,
            progress_ratio=progress_ratio,
            oracle_ceiling=oracle_ceiling,
            full_dataset_oracle_ceiling=full_dataset_oracle_ceiling,
            target_above_oracle=target_above_oracle,
            translated_threshold=translated_threshold,
            capture_ratio=capture_ratio,
            source_version=source_version,
        ))

    return results


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
            (1 + candidate_quality_change) / (1 + oracle_quality_change) if oracle_quality_change != 0.0 else None
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


def generate_executive_summary(
    briefing: ReviewBriefing,
    primary_metric: str = "accuracy",
    best_ever_version: str | None = None,
) -> str:
    """Generate a purely factual executive summary of the briefing data."""
    lines: list[str] = []

    # Round and scale
    n_candidates = len(briefing.candidates)
    n_elite = len(briefing.elite_set)
    lines.append(f"Round {briefing.round}. {n_candidates} candidate(s) evaluated against {n_elite} elite candidate(s).")

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

    # Top confusion cells
    if briefing.confusion_analysis:
        for ci in briefing.confusion_analysis[:3]:
            persist_label = "structural" if ci.persistence_rate > 0.8 else (
                "prompt-sensitive" if ci.persistence_rate < 0.3 else "mixed"
            )
            lines.append(
                f"CONFUSION: {ci.true_route}->{ci.predicted_route}: "
                f"{ci.count}/{ci.support} samples ({ci.misroute_rate:.0%}), "
                f"cost impact {ci.cost_impact:+.4f}, quality impact {ci.quality_impact:+.4f}, "
                f"persistence {ci.persistence_rate:.0%} ({persist_label})."
            )

    # Oracle gap
    om = briefing.oracle_metrics
    if om is not None:
        parts = []
        if om.candidate_quality_captured is not None:
            parts.append(f"quality {om.candidate_quality_captured:.0%} of oracle")
        else:
            parts.append("quality: no headroom (oracle change is 0)")
        if om.candidate_cost_captured is not None:
            parts.append(f"cost {om.candidate_cost_captured:.0%} captured")
        else:
            parts.append("cost: no headroom (oracle change is 0)")
        lines.append("Oracle gap: " + ", ".join(parts) + ".")

    # User target progress
    if briefing.target_progress:
        all_met = all(tp.met for tp in briefing.target_progress)
        if all_met:
            lines.append("USER TARGETS: All targets met.")
        elif any(tp.met for tp in briefing.target_progress):
            lines.append("USER TARGETS: Some targets unmet.")
        else:
            lines.append("USER TARGETS: No targets met yet.")

        for tp in briefing.target_progress:
            t = tp.target
            current_str = f"{tp.current_value:.4f}" if tp.current_value is not None else "N/A"
            progress_str = f"{tp.progress_ratio:.0%}" if tp.progress_ratio is not None else "N/A"
            status = "MET" if tp.met else "UNMET"
            line = f"  {t.metric} {t.operator} {t.threshold}"
            if tp.translated_threshold is not None:
                line += f" (dev target: {tp.translated_threshold:.4f}, capture: {tp.capture_ratio:.0%})"
            line += f": current={current_str}, progress={progress_str} [{status}]"
            if tp.target_above_oracle:
                line += " WARNING: target exceeds oracle ceiling"
            if tp.oracle_ceiling is not None or tp.full_dataset_oracle_ceiling is not None:
                full_str = (
                    f"{tp.full_dataset_oracle_ceiling:.4f}"
                    if tp.full_dataset_oracle_ceiling is not None
                    else "N/A"
                )
                dev_str = f"{tp.oracle_ceiling:.4f}" if tp.oracle_ceiling is not None else "N/A"
                line += f"\n    oracle: full_dataset={full_str}, dev_set={dev_str}"
            lines.append(line)

    # Target slack (now merged into target_progress items)
    for tp in briefing.target_progress:
        if tp.surplus is not None:
            if tp.surplus < 0:
                lines.append(
                    f"  DEFICIT: {tp.target.metric} short by {abs(tp.surplus):.4f} "
                    f"(priority weight: {tp.priority_weight:.0%})"
                )
            elif tp.surplus > 0:
                lines.append(
                    f"  SURPLUS: {tp.target.metric} ahead by {tp.surplus:.4f} "
                    f"(regression budget: {tp.regression_budget:.4f})"
                )

    # Stagnation
    dr = briefing.diminishing_returns
    sign = "+" if dr.improvement_trend >= 0 else ""
    stag = " Stagnation flag is set." if dr.stagnation_flag else ""
    lines.append(f"Improvement trend: {sign}{dr.improvement_trend:.4f}/round.{stag}")

    # Backtracking
    if briefing.backtracking:
        version_str = f" ({best_ever_version})" if best_ever_version else ""
        lines.append(
            f"Backtracking active: all hypotheses will target best-ever version{version_str}."
        )

    return "\n".join(lines)


def _compute_persistence(
    *,
    cell_samples: dict[tuple[str, str], list[str]],
    examples_by_id: dict[str, Example],
    elite_versions: list[str],
    parent_versions: list[str],
    run_dir: Path | None,
    max_versions: int = 6,
) -> dict[tuple[str, str], tuple[int, int]]:
    """Compute (persistent_count, count) for each confusion cell.

    persistent_count = number of samples that are wrong in ALL loaded versions.
    """
    # If no run_dir, return zeros
    if run_dir is None:
        return {key: (0, len(ids)) for key, ids in cell_samples.items()}

    # Collect and deduplicate versions to load, cap at max_versions
    all_versions: list[str] = []
    seen: set[str] = set()
    for v in elite_versions + parent_versions:
        if v not in seen:
            seen.add(v)
            all_versions.append(v)
    versions_to_load = all_versions[:max_versions]

    # Load misclassified example_ids per version
    # version -> set of example_ids that were wrong in that version
    version_wrong: dict[str, set[str]] = {}
    loaded_versions: list[str] = []
    for version in versions_to_load:
        results_path = run_dir / "eval" / version / "results.jsonl"
        if not results_path.exists():
            continue
        wrong_ids: set[str] = set()
        with open(results_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Skip __meta__ fingerprint lines
                if row.get("__meta__"):
                    continue
                eid = row.get("example_id")
                output = row.get("output")
                if eid is None:
                    continue
                predicted = output.get("route") if isinstance(output, dict) else None
                # Look up expected route
                example = examples_by_id.get(eid)
                if example is None:
                    continue
                expected = example.expected.route
                if predicted != expected:
                    wrong_ids.add(eid)
        version_wrong[version] = wrong_ids
        loaded_versions.append(version)

    # If no versions loaded, return zeros
    if not loaded_versions:
        return {key: (0, len(ids)) for key, ids in cell_samples.items()}

    result: dict[tuple[str, str], tuple[int, int]] = {}
    for cell_key, sample_ids in cell_samples.items():
        count = len(sample_ids)
        persistent = sum(
            1 for eid in sample_ids
            if all(eid in version_wrong[v] for v in loaded_versions)
        )
        result[cell_key] = (persistent, count)
    return result


def build_confusion_analysis(
    *,
    eval_results: list[EvalResult],
    examples: list[Example],
    elite_versions: list[str],
    parent_versions: list[str],
    run_dir: Path | None,
    max_cells: int = 20,
) -> list[ConfusionImpact]:
    """Build an impact-weighted confusion analysis from eval results.

    Accepts concatenated results from one or more candidates. Deduplicates
    by (example_id, true_route, predicted_route) so each unique misrouted
    example contributes to a cell at most once, keeping counts candidate-
    count-independent.

    Returns at most max_cells ConfusionImpact objects sorted by
    abs(cost_impact) + abs(quality_impact) descending.
    """
    # 1. Build examples_by_id lookup
    examples_by_id: dict[str, Example] = {ex.id: ex for ex in examples}

    # 2. Collect misclassification data per (true_route, predicted_route) cell
    #    Dedup by (example_id, true_route, predicted_route) triple.
    cell_samples: dict[tuple[str, str], list[str]] = {}
    cell_cost_deltas: dict[tuple[str, str], list[float]] = {}
    cell_quality_deltas: dict[tuple[str, str], list[float]] = {}
    seen_triples: set[tuple[str, str, str]] = set()

    for result in eval_results:
        if result.output is None:
            continue
        predicted = result.output.get("route")
        if predicted is None:
            continue
        example = examples_by_id.get(result.example_id)
        if example is None:
            continue
        expected = example.expected.route
        if predicted == expected:
            continue
        # Only include if predicted route exists in the example's routes dict
        routes = example.expected.routes
        if predicted not in routes:
            continue

        # Dedup: skip if this (example_id, true_route, predicted_route) triple was seen
        triple = (result.example_id, expected, predicted)
        if triple in seen_triples:
            continue
        seen_triples.add(triple)

        cost_delta = (
            (routes[predicted].cost or 0.0) - (routes[expected].cost or 0.0)
            if expected in routes
            else 0.0
        )
        quality_delta = (
            (routes[predicted].quality_score or 0.0) - (routes[expected].quality_score or 0.0)
            if expected in routes
            else 0.0
        )

        cell_key = (expected, predicted)
        cell_samples.setdefault(cell_key, []).append(result.example_id)
        cell_cost_deltas.setdefault(cell_key, []).append(cost_delta)
        cell_quality_deltas.setdefault(cell_key, []).append(quality_delta)

    if not cell_samples:
        return []

    # 3. Compute support per true_route from ALL results (count all examples)
    support_counter: Counter[str] = Counter()
    for ex in examples:
        support_counter[ex.expected.route] += 1

    # 4. Compute persistence
    persistence = _compute_persistence(
        cell_samples=cell_samples,
        examples_by_id=examples_by_id,
        elite_versions=elite_versions,
        parent_versions=parent_versions,
        run_dir=run_dir,
    )

    # 5. Build ConfusionImpact objects
    impacts: list[ConfusionImpact] = []
    for cell_key, sample_ids in cell_samples.items():
        true_route, predicted_route = cell_key
        count = len(sample_ids)
        support = support_counter[true_route]
        cost_deltas = cell_cost_deltas[cell_key]
        quality_deltas = cell_quality_deltas[cell_key]
        total_cost = sum(cost_deltas)
        total_quality = sum(quality_deltas)
        avg_cost = total_cost / count if count else 0.0
        avg_quality = total_quality / count if count else 0.0
        misroute_rate = count / support if support > 0 else 0.0
        persistent_count, _ = persistence.get(cell_key, (0, count))
        volatile_count = count - persistent_count
        persistence_rate = persistent_count / count if count > 0 else 0.0

        impacts.append(ConfusionImpact(
            true_route=true_route,
            predicted_route=predicted_route,
            count=count,
            support=support,
            misroute_rate=misroute_rate,
            cost_impact=total_cost,
            quality_impact=total_quality,
            avg_cost_impact=avg_cost,
            avg_quality_impact=avg_quality,
            persistence_rate=persistence_rate,
            persistent_count=persistent_count,
            volatile_count=volatile_count,
        ))

    # Sort by abs(cost_impact) + abs(quality_impact) descending, cap at max_cells
    impacts.sort(key=lambda c: abs(c.cost_impact) + abs(c.quality_impact), reverse=True)
    return impacts[:max_cells]


def enrich_confusion_with_history(
    impacts: list[ConfusionImpact],
    cell_history: dict[str, list[dict[str, Any]]],
) -> list[ConfusionImpact]:
    """Enrich ConfusionImpact objects with attempt history and re-sort by effective_impact.

    Applies exponential decay: effective_impact = raw_impact * (0.5 ^ failed_attempt_count).
    A successful attempt resets failed_attempt_count to 0.
    """
    enriched: list[ConfusionImpact] = []
    for ci in impacts:
        cell_key = f"{ci.true_route}/{ci.predicted_route}"
        entries = cell_history.get(cell_key, [])

        if not entries:
            raw_impact = abs(ci.cost_impact) + abs(ci.quality_impact)
            enriched.append(ci.model_copy(update={"effective_impact": raw_impact}))
            continue

        attempt_count = len(entries)

        # Determine best_outcome across all attempts
        best_outcome: str | None = None
        last_round: int | None = None
        outcome_priority = {"improved": 2, "no_effect": 1, "regressed": 0}
        for entry in entries:
            outcome = entry.get("outcome", "no_effect")
            if best_outcome is None or outcome_priority.get(outcome, 0) > outcome_priority.get(best_outcome, 0):
                best_outcome = outcome
            round_num = entry.get("round")
            if round_num is not None:
                last_round = max(last_round or 0, round_num)

        # Count failed attempts since last success
        failed_count = 0
        for entry in reversed(entries):
            if entry.get("outcome") == "improved":
                break
            if entry.get("outcome") in ("no_effect", "regressed"):
                failed_count += 1

        raw_impact = abs(ci.cost_impact) + abs(ci.quality_impact)
        effective = raw_impact * (0.5 ** failed_count)

        enriched.append(ci.model_copy(update={
            "attempt_count": attempt_count,
            "failed_attempt_count": failed_count,
            "last_attempted_round": last_round,
            "best_outcome": best_outcome,
            "effective_impact": effective,
        }))

    # Re-sort by effective_impact descending
    enriched.sort(key=lambda c: c.effective_impact, reverse=True)
    return enriched


def build_review_briefing(
    *,
    search_state: Any,
    score_reports: dict[str, dict[str, Any]],
    historical_reports: dict[int, dict[str, dict[str, Any]]],
    prompt_texts: dict[str, str],
    directive_history: list[DirectiveOutcome],
    candidate_versions: list[str],
    parent_versions: dict[str, str | None],
    routing_context: RoutingContext | None = None,
    child_variants: list[ChildVariant] | None = None,
    pending_candidates: list[Candidate] | None = None,
    user_targets: list[UserTarget] | None = None,
    full_dataset_oracle: dict[str, float] | None = None,
    dev_oracle: dict[str, float] | None = None,
    eval_results: list[EvalResult] | None = None,
    examples: list[Example] | None = None,
    run_dir: Path | None = None,
    cell_attempt_history: dict[str, list[dict[str, Any]]] | None = None,
) -> ReviewBriefing:
    """Assemble a complete ReviewBriefing from raw pipeline data.

    This is the main orchestrator that calls all computation functions.
    """
    current_round: int = search_state.round
    primary_metric: str = search_state.primary_metric_name or "accuracy"
    elite_set = search_state.elite_set
    elite_versions = [c.prompt_version for c in elite_set]

    # Mutation descriptions for current candidates
    mutation_descriptions: dict[str, str] = {v: "" for v in candidate_versions}

    # 1. Candidate comparisons
    candidates = build_candidate_comparisons(
        score_reports=score_reports,
        mutation_descriptions=mutation_descriptions,
        parent_versions=parent_versions,
        primary_metric=primary_metric,
    )

    # 2. Per-class recall
    per_class_recall = extract_per_class_recall(
        current_reports=score_reports,
        historical_reports=historical_reports,
        current_round=current_round,
    )

    # 3. Diversity metrics (elite set prompts only)
    front_prompt_texts = {v: prompt_texts[v] for v in elite_versions if v in prompt_texts}
    diversity_metrics = compute_diversity_metrics(
        prompt_texts=front_prompt_texts,
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

    # 5. Oracle metrics — prefer full-dataset oracle (dataset-level, constant across versions)
    oracle_versions = candidate_versions or elite_versions
    if full_dataset_oracle is not None and oracle_versions:
        best_candidate = max(
            oracle_versions,
            key=lambda v: _extract_metric(score_reports.get(v, {}), primary_metric) or 0.0,
        )
        best_metrics = score_reports.get(best_candidate, {}).get("metrics", {})
        oracle_metrics = compute_oracle_metrics(
            oracle_cost_change=full_dataset_oracle["oracle_cost_change"],
            oracle_quality_change=full_dataset_oracle["oracle_quality_change"],
            candidate_cost_change=best_metrics.get("cost_change", 0.0),
            candidate_cost_change_with_overhead=best_metrics.get("cost_change_with_overhead", 0.0),
            candidate_quality_change=best_metrics.get("quality_change", 0.0),
        )
    else:
        # Fallback: extract from best candidate's report
        if oracle_versions:
            best_candidate = max(
                oracle_versions,
                key=lambda v: _extract_metric(score_reports.get(v, {}), primary_metric) or 0.0,
            )
            oracle_metrics = compute_oracle_metrics_from_report(
                metrics=score_reports.get(best_candidate, {}).get("metrics", {}),
            )
        else:
            oracle_metrics = compute_oracle_metrics_from_report(metrics={})

    # 6b. User target progress (with slack merged in) — single-version semantics
    target_progress_list: list[UserTargetProgress] = []
    if user_targets:
        # Pick the single best version by holistic scoring tuple, then read all target
        # metrics off it — avoids a phantom composite built from different versions.
        best_versions = candidate_versions or elite_versions
        if best_versions:
            best_version = max(
                best_versions,
                key=lambda v: (
                    _count_targets_met(user_targets, score_reports.get(v, {}).get("metrics", {})),
                    _sum_capped_progress(user_targets, score_reports.get(v, {}).get("metrics", {})),
                    _min_progress(user_targets, score_reports.get(v, {}).get("metrics", {})),
                ),
            )
            best_metrics = score_reports.get(best_version, {}).get("metrics", {})
            target_progress_list = compute_target_progress(
                user_targets,
                best_metrics,
                oracle_metrics,
                full_dataset_oracle=full_dataset_oracle,
                dev_oracle=dev_oracle,
                source_version=best_version,
            )
            # Merge target slack into target progress items
            slack_by_metric = {
                s.metric: s for s in compute_target_slack(user_targets, best_metrics)
            }
            merged: list[UserTargetProgress] = []
            for tp in target_progress_list:
                slack = slack_by_metric.get(tp.target.metric)
                if slack is not None:
                    merged.append(tp.model_copy(update={
                        "surplus": slack.surplus,
                        "regression_budget": slack.regression_budget,
                        "priority_weight": slack.priority_weight,
                        "source_version": best_version,
                    }))
                else:
                    merged.append(tp.model_copy(update={
                        "source_version": best_version,
                    }))
            target_progress_list = merged
        single_candidate_meets_all = bool(
            target_progress_list and all(tp.met for tp in target_progress_list)
        )
    else:
        single_candidate_meets_all = False

    # 7. Build batch outcomes — match child variants to candidates via variant_id
    beam_width = getattr(search_state, "beam_width", 2)
    batch_outcomes: list[BatchOutcome] = []

    if child_variants and pending_candidates is not None:
        # Build a lookup: source_directive_batch_id -> Candidate
        candidate_by_variant = {
            c.source_directive_batch_id: c
            for c in pending_candidates
            if getattr(c, "source_directive_batch_id", None) is not None
        }

        # best_ever_quality for is_new_best check
        best_ever_quality: float = getattr(search_state, "best_ever_quality", 0.0)

        # Build parent quality lookup from elite set
        parent_quality = {c.prompt_version: c.quality_score for c in elite_set}

        for cv in child_variants:
            if cv.variant_id is None:
                continue
            candidate = candidate_by_variant.get(cv.variant_id)
            if candidate is not None:
                parent_q = parent_quality.get(candidate.parent_version or "")
                quality_delta = (
                    candidate.quality_score - parent_q
                    if parent_q is not None and candidate.eval_status == "scored"
                    else None
                )
                # Compute full metric deltas vs primary parent
                parent_report = score_reports.get(candidate.parent_version or "")
                metric_deltas_vs_parent = (
                    _compute_metric_deltas(score_reports[candidate.prompt_version], parent_report)
                    if candidate.eval_status == "scored" and candidate.prompt_version in score_reports and parent_report
                    else None
                )

                # Compute full metric deltas vs secondary parent (merge only)
                secondary_pv = getattr(candidate, "secondary_parent_version", None)
                metric_deltas_vs_secondary = None
                if secondary_pv and candidate.eval_status == "scored" and candidate.prompt_version in score_reports:
                    secondary_report = score_reports.get(secondary_pv)
                    if secondary_report:
                        metric_deltas_vs_secondary = _compute_metric_deltas(
                            score_reports[candidate.prompt_version], secondary_report
                        )

                target_metric_names = {t.metric for t in (user_targets or [])}
                if metric_deltas_vs_parent:
                    metric_deltas_vs_parent = _filter_metric_deltas(
                        metric_deltas_vs_parent, target_metrics=target_metric_names,
                    )
                if metric_deltas_vs_secondary:
                    metric_deltas_vs_secondary = _filter_metric_deltas(
                        metric_deltas_vs_secondary, target_metrics=target_metric_names,
                    )

                batch_outcomes.append(BatchOutcome(
                    variant_id=cv.variant_id,
                    parent_version=candidate.parent_version or "",
                    mutation_strategy=candidate.mutation_strategy or "targeted",  # type: ignore[arg-type]
                    directive_ids=[d.directive_id for d in cv.directives],
                    candidate_version=candidate.prompt_version,
                    eval_status=candidate.eval_status if candidate.eval_status in ("scored", "failed") else None,
                    quality_delta_vs_parent=quality_delta,
                    is_new_best=candidate.quality_score > best_ever_quality,
                    secondary_parent_version=secondary_pv,
                    metric_deltas_vs_parent=metric_deltas_vs_parent,
                    metric_deltas_vs_secondary_parent=metric_deltas_vs_secondary,
                ))
            else:
                batch_outcomes.append(BatchOutcome(
                    variant_id=cv.variant_id,
                    parent_version=cv.parent_version or "",
                    mutation_strategy="targeted",
                    directive_ids=[d.directive_id for d in cv.directives],
                    candidate_version=None,
                    eval_status=None,
                    quality_delta_vs_parent=None,
                    is_new_best=False,
                ))

    recent_directive_history = directive_history[-15:]

    backtracking = (
        getattr(search_state, "stagnation_count", 0)
        >= getattr(search_state, "backtrack_threshold", float("inf"))
    )
    best_ever_version_val: str | None = getattr(search_state, "best_ever_version", None)

    # Build hill-climb stagnation signal from core search state fields
    stagnation_signal: dict[str, Any] | None = None
    stagnation_count = getattr(search_state, "stagnation_count", None)
    stagnation_limit = getattr(search_state, "stagnation_limit", None)
    mutation_mode = getattr(search_state, "mutation_mode", None)
    if stagnation_count is not None and stagnation_limit is not None and mutation_mode is not None:
        stagnation_signal = {
            "count": stagnation_count,
            "limit": stagnation_limit,
            "mutation_mode": mutation_mode,
        }

    # Confusion analysis
    confusion_analysis: list[ConfusionImpact] = []
    if eval_results and examples:
        confusion_analysis = build_confusion_analysis(
            eval_results=eval_results,
            examples=examples,
            elite_versions=[c.prompt_version for c in elite_set],
            parent_versions=[c.parent_version for c in elite_set if c.parent_version],
            run_dir=run_dir,
            max_cells=20,
        )

    if confusion_analysis and cell_attempt_history:
        confusion_analysis = enrich_confusion_with_history(confusion_analysis, cell_attempt_history)

    briefing = ReviewBriefing(
        round=current_round,
        candidates=candidates,
        elite_set=elite_set,
        per_class_recall=per_class_recall,
        diversity_metrics=diversity_metrics,
        diminishing_returns=diminishing_returns,
        oracle_metrics=oracle_metrics,
        routing_context=routing_context,
        directive_history=recent_directive_history,
        beam_width=beam_width,
        batch_outcomes=batch_outcomes,
        target_progress=target_progress_list,
        single_candidate_meets_all=single_candidate_meets_all,
        backtracking=backtracking,
        child_variants=child_variants or [],
        stagnation_signal=stagnation_signal,
        confusion_analysis=confusion_analysis,
    )
    return briefing.model_copy(
        update={
            "executive_summary": generate_executive_summary(
                briefing, primary_metric, best_ever_version_val
            )
        },
    )
