"""Pre-processor for the Final Report Agent.

Gathers all pipeline artifacts from a completed run and computes a
structured FinalReportBriefing with derived metrics, comparisons,
and optimization journey charts.
"""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path

from odysseus.agents.final_report.models import (
    ChartPaths,
    DatasetOverview,
    ErrorSummary,
    EvalMetricComparison,
    FinalReportBriefing,
    MisroutedExample,
    OptimizationJourney,
    OracleAnalysis,
    PerClassPerformance,
    PromptSummary,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_final_report_briefing(
    *,
    run_id: str,
    run_dir: Path,
    project_dir: Path,
) -> FinalReportBriefing:
    """Build a complete briefing from pipeline artifacts.

    All file reads are wrapped in try/except with graceful fallbacks
    so partial pipeline state doesn't crash the report.
    """
    problem_summary = _load_problem_summary(run_dir)
    dataset_overview = _load_dataset_overview(run_dir)
    search_state = _load_json(run_dir / "search" / "search_state.json")
    mutation_log = _load_json(run_dir / "search" / "mutation_log.json", default=[])
    dev_report = _load_json(run_dir / "eval" / "report.json")
    holdout_report = _load_json(run_dir / "holdout_eval" / "report.json")

    optimization_journey = _build_optimization_journey(search_state, mutation_log)
    pareto_front = _extract_pareto_front(search_state)
    best_prompt, best_prompt_text = _identify_best_prompt(pareto_front, run_dir)
    eval_comparison = _build_eval_comparison(dev_report, holdout_report)
    per_class = _extract_per_class_performance(holdout_report)
    oracle_analysis = _extract_oracle_analysis(holdout_report)
    error_summary = _build_error_summary(run_dir)
    charts = _generate_charts(run_dir, optimization_journey, pareto_front)

    backend_name = search_state.get("backend", "unknown") if search_state else "unknown"

    return FinalReportBriefing(
        run_id=run_id,
        backend_name=backend_name,
        problem_summary=problem_summary,
        dataset_overview=dataset_overview,
        optimization_journey=optimization_journey,
        best_prompt=best_prompt,
        best_prompt_text=best_prompt_text,
        pareto_front=pareto_front,
        eval_comparison=eval_comparison,
        per_class_performance=per_class,
        oracle_analysis=oracle_analysis,
        error_summary=error_summary,
        charts=charts,
    )


# ---------------------------------------------------------------------------
# Artifact loaders
# ---------------------------------------------------------------------------


def _load_json(path: Path, default: dict | list | None = None) -> dict | list | None:
    """Load a JSON file, returning *default* on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.debug("Could not load %s", path)
        return default


def _load_problem_summary(run_dir: Path) -> str:
    """Load the raw input report markdown."""
    path = run_dir / "input" / "input_report.md"
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return "(Input report not available)"


def _load_dataset_overview(run_dir: Path) -> DatasetOverview:
    """Build dataset overview from split report and routing context."""
    split_report = _load_json(run_dir / "analysis" / "split_report.json")
    routing_ctx = _load_json(run_dir / "validation" / "routing_context.json")

    # Count lines as fallback
    dev_count = _count_jsonl_lines(run_dir / "analysis" / "dev.jsonl")
    holdout_count = _count_jsonl_lines(run_dir / "analysis" / "holdout.jsonl")

    if split_report and isinstance(split_report, dict):
        dev_count = split_report.get("dev_count", dev_count)
        holdout_count = split_report.get("holdout_count", holdout_count)
        route_dist = split_report.get("route_distribution", {})
    else:
        route_dist = {}

    routes: list[str] = []
    dimensions: list[str] = []
    if routing_ctx and isinstance(routing_ctx, dict):
        routes = [r.get("name", r.get("route", "")) for r in routing_ctx.get("routes", [])]
        dimensions = [d.get("name", "") for d in routing_ctx.get("dimensions", [])]

    return DatasetOverview(
        total_examples=dev_count + holdout_count,
        dev_count=dev_count,
        holdout_count=holdout_count,
        route_distribution=route_dist,
        routes=routes,
        dimensions=dimensions,
    )


def _count_jsonl_lines(path: Path) -> int:
    """Count non-empty lines in a JSONL file."""
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Search state processing
# ---------------------------------------------------------------------------


def _build_optimization_journey(
    search_state: dict | list | None,
    mutation_log: dict | list | None,
) -> OptimizationJourney:
    """Extract optimization journey from search state and mutation log."""
    if not search_state or not isinstance(search_state, dict):
        return OptimizationJourney(
            total_rounds=0,
            convergence_reason="unknown",
            stagnation_count=0,
            mutation_mode="unknown",
            best_quality_per_round=[],
            best_cost_per_round=[],
            pareto_front_size_per_round=[],
            mutation_type_counts={},
            effective_mutation_types=[],
            ineffective_mutation_types=[],
        )

    round_history: list[dict] = search_state.get("round_history", [])
    total_rounds = search_state.get("round", 0)

    # Determine convergence reason
    stagnation_count = search_state.get("stagnation_count", 0)
    convergence_limit = search_state.get("convergence_limit", 5)
    max_rounds = search_state.get("max_rounds", 50)
    if stagnation_count >= convergence_limit:
        convergence_reason = f"Stagnation limit reached ({stagnation_count} rounds without Pareto improvement)"
    elif total_rounds >= max_rounds:
        convergence_reason = f"Maximum rounds reached ({max_rounds})"
    else:
        convergence_reason = "Loop exited by Review Agent"

    # Per-round trajectories — derive from round_history
    best_quality: list[float] = []
    best_cost: list[float] = []
    front_sizes: list[int] = []
    # Round history has front_size but not best quality/cost directly.
    # We reconstruct from the pareto_front at end of run for the final point,
    # and from round summaries for front size.
    for rh in round_history:
        front_sizes.append(rh.get("front_size", 0))

    # For quality/cost trajectory, use pareto_front candidates sorted by round_introduced
    pareto_front: list[dict] = search_state.get("pareto_front", [])
    # Build cumulative best quality per round
    _build_quality_cost_trajectory(pareto_front, total_rounds, best_quality, best_cost)

    # Mutation analysis
    mutation_type_counts: dict[str, int] = {}
    effective_types: set[str] = set()
    ineffective_types: set[str] = set()
    if isinstance(mutation_log, list):
        for entry in mutation_log:
            if not isinstance(entry, dict):
                continue
            mt = entry.get("mutation_type", "unknown")
            mutation_type_counts[mt] = mutation_type_counts.get(mt, 0) + 1
            # Classify based on whether child is on current front
            front_versions = {c.get("prompt_version") for c in pareto_front}
            if entry.get("child_version") in front_versions:
                effective_types.add(mt)
            else:
                ineffective_types.add(mt)

    return OptimizationJourney(
        total_rounds=total_rounds,
        convergence_reason=convergence_reason,
        stagnation_count=stagnation_count,
        mutation_mode=search_state.get("mutation_mode", "unknown"),
        best_quality_per_round=best_quality,
        best_cost_per_round=best_cost,
        pareto_front_size_per_round=front_sizes,
        mutation_type_counts=mutation_type_counts,
        effective_mutation_types=sorted(effective_types),
        ineffective_mutation_types=sorted(ineffective_types - effective_types),
    )


def _build_quality_cost_trajectory(
    pareto_front: list[dict],
    total_rounds: int,
    quality_out: list[float],
    cost_out: list[float],
) -> None:
    """Build per-round best quality and cost from Pareto front history.

    For each round, the best quality is the max quality_score of any front
    member introduced at or before that round. Cost is the cost of that member.
    """
    if not pareto_front or total_rounds == 0:
        return

    # Sort candidates by round_introduced
    candidates = sorted(pareto_front, key=lambda c: c.get("round_introduced", 0))

    for r in range(1, total_rounds + 1):
        eligible = [c for c in candidates if c.get("round_introduced", 0) <= r]
        if eligible:
            best = max(eligible, key=lambda c: (c.get("quality_score", 0), -c.get("cost", 0)))
            quality_out.append(best.get("quality_score", 0))
            cost_out.append(best.get("cost", 0))
        elif quality_out:
            quality_out.append(quality_out[-1])
            cost_out.append(cost_out[-1])


def _extract_pareto_front(search_state: dict | list | None) -> list[PromptSummary]:
    """Extract Pareto front members as PromptSummary list."""
    if not search_state or not isinstance(search_state, dict):
        return []
    front = search_state.get("pareto_front", [])
    return [
        PromptSummary(
            version=c.get("prompt_version", "unknown"),
            quality_score=c.get("quality_score", 0),
            cost=c.get("cost", 0),
            round_introduced=c.get("round_introduced", 0),
        )
        for c in front
        if isinstance(c, dict)
    ]


def _identify_best_prompt(
    pareto_front: list[PromptSummary],
    run_dir: Path,
) -> tuple[PromptSummary, str]:
    """Find the best prompt (highest quality, lowest cost tiebreak) and load its text."""
    if not pareto_front:
        dummy = PromptSummary(version="unknown", quality_score=0, cost=0, round_introduced=0)
        return dummy, "(No prompt available)"

    best = max(pareto_front, key=lambda p: (p.quality_score, -p.cost))

    # Load prompt text
    prompts_dir = run_dir / "prompts"
    prompt_text = "(Prompt text not found)"
    if prompts_dir.is_dir():
        for ext in [".txt", ".md", ".yaml", ".yml"]:
            candidate = prompts_dir / f"{best.version}{ext}"
            if candidate.is_file():
                with contextlib.suppress(Exception):
                    prompt_text = candidate.read_text(encoding="utf-8")
                break

    return best, prompt_text


# ---------------------------------------------------------------------------
# Eval comparison
# ---------------------------------------------------------------------------


def _build_eval_comparison(
    dev_report: dict | list | None,
    holdout_report: dict | list | None,
) -> list[EvalMetricComparison]:
    """Compare metrics between dev and holdout eval reports."""
    if not isinstance(dev_report, dict) or not isinstance(holdout_report, dict):
        return []

    dev_metrics: dict[str, float] = dev_report.get("metrics", {})
    holdout_metrics: dict[str, float] = holdout_report.get("metrics", {})

    comparisons: list[EvalMetricComparison] = []
    # Use holdout keys as the reference set, include dev values where available
    all_keys = sorted(set(dev_metrics) | set(holdout_metrics))
    # Filter to top-level metrics (skip per-class breakdowns for the comparison table)
    top_level = [k for k in all_keys if "/" not in k or k.startswith("f1/macro")]
    for key in top_level:
        dev_val = dev_metrics.get(key)
        holdout_val = holdout_metrics.get(key)
        if dev_val is not None and holdout_val is not None:
            comparisons.append(
                EvalMetricComparison(
                    metric=key,
                    dev_value=round(dev_val, 4),
                    holdout_value=round(holdout_val, 4),
                    delta=round(holdout_val - dev_val, 4),
                )
            )
    return comparisons


def _extract_per_class_performance(
    holdout_report: dict | list | None,
) -> list[PerClassPerformance]:
    """Extract per-route precision, recall, F1, support from holdout metrics."""
    if not isinstance(holdout_report, dict):
        return []

    metrics = holdout_report.get("metrics", {})
    # Collect all route names from recall/<route>, precision/<route>, f1/<route> keys
    route_names: set[str] = set()
    for key in metrics:
        for prefix in ("recall/", "precision/", "f1/"):
            if key.startswith(prefix) and not key.endswith("/macro"):
                route_names.add(key[len(prefix) :])

    results: list[PerClassPerformance] = []
    for route in sorted(route_names):
        results.append(
            PerClassPerformance(
                route=route,
                precision=metrics.get(f"precision/{route}"),
                recall=metrics.get(f"recall/{route}"),
                f1=metrics.get(f"f1/{route}"),
                support=int(metrics[f"support/{route}"]) if f"support/{route}" in metrics else None,
            )
        )
    return results


def _extract_oracle_analysis(holdout_report: dict | list | None) -> OracleAnalysis | None:
    """Extract oracle metrics from holdout eval report."""
    if not isinstance(holdout_report, dict):
        return None

    metrics = holdout_report.get("metrics", {})
    oracle_cost = metrics.get("oracle_cost_reduction")
    oracle_quality = metrics.get("oracle_quality_reduction")
    if oracle_cost is None and oracle_quality is None:
        return None

    return OracleAnalysis(
        oracle_cost_reduction=oracle_cost or 0.0,
        oracle_quality_reduction=oracle_quality or 0.0,
        candidate_cost_reduction=metrics.get("cost_reduction"),
        candidate_cost_reduction_with_overhead=metrics.get("cost_reduction_with_overhead"),
        candidate_quality_reduction=metrics.get("quality_reduction"),
    )


# ---------------------------------------------------------------------------
# Error analysis
# ---------------------------------------------------------------------------


def _build_error_summary(run_dir: Path) -> ErrorSummary:
    """Build error summary from holdout eval results."""
    results_path = run_dir / "holdout_eval" / "results.jsonl"
    holdout_path = run_dir / "analysis" / "holdout.jsonl"

    # Load holdout examples for expected routes and input text
    examples_by_id: dict[str, dict] = {}
    try:
        for line in holdout_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            ex = json.loads(stripped)
            examples_by_id[ex.get("id", "")] = ex
    except Exception:
        pass

    # Load eval results
    eval_results: list[dict] = []
    try:
        for line in results_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            if row.get("meta") == "__meta__":
                continue
            eval_results.append(row)
    except Exception:
        return ErrorSummary(total_evaluated=0, total_errors=0, error_rate=0, misrouted_samples=[])

    total = len(eval_results)
    misrouted: list[MisroutedExample] = []

    for r in eval_results:
        eid = r.get("example_id", "")
        output = r.get("output")
        error = r.get("error")
        ex = examples_by_id.get(eid, {})
        expected_route = ex.get("expected", {}).get("route", "unknown")

        if error:
            predicted = "(error)"
        elif output:
            predicted = output.get("route", "(no route)")
        else:
            predicted = "(no output)"

        if predicted != expected_route:
            input_text = ex.get("input", "")
            misrouted.append(
                MisroutedExample(
                    example_id=eid,
                    input_preview=input_text[:200],
                    expected_route=expected_route,
                    predicted_route=predicted,
                )
            )

    # Sample up to 10
    samples = misrouted[:10]

    return ErrorSummary(
        total_evaluated=total,
        total_errors=len(misrouted),
        error_rate=round(len(misrouted) / total, 4) if total > 0 else 0,
        misrouted_samples=samples,
    )


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------


def _generate_charts(
    run_dir: Path,
    journey: OptimizationJourney,
    pareto_front: list[PromptSummary],
) -> ChartPaths:
    """Generate optimization journey charts using matplotlib.

    Charts are saved as PNG files under ``reports/charts/`` within the run directory.
    Returns a ChartPaths with relative paths (from run_dir) to each generated chart.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not installed — skipping chart generation")
        return ChartPaths()

    charts_dir = run_dir / "reports" / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    quality_path = _chart_quality_progression(plt, journey, charts_dir)
    cost_path = _chart_cost_progression(plt, journey, charts_dir)
    pareto_path = _chart_pareto_front(plt, pareto_front, charts_dir)

    return ChartPaths(
        quality_progression=str(quality_path.relative_to(run_dir)) if quality_path else None,
        cost_progression=str(cost_path.relative_to(run_dir)) if cost_path else None,
        pareto_front=str(pareto_path.relative_to(run_dir)) if pareto_path else None,
    )


def _chart_quality_progression(
    plt: object,  # matplotlib.pyplot module
    journey: OptimizationJourney,
    charts_dir: Path,
) -> Path | None:
    """Line chart: best quality score per round."""
    if not journey.best_quality_per_round:
        return None

    try:
        fig, ax = plt.subplots(figsize=(10, 5))  # type: ignore[union-attr]
        rounds = list(range(1, len(journey.best_quality_per_round) + 1))
        ax.plot(rounds, journey.best_quality_per_round, "o-", color="#2563eb", linewidth=2, markersize=5)
        ax.set_xlabel("Round", fontsize=12)
        ax.set_ylabel("Best Quality Score", fontsize=12)
        ax.set_title("Quality Score Progression", fontsize=14, fontweight="bold")
        ax.grid(True, alpha=0.3)

        # Annotate final value
        final_q = journey.best_quality_per_round[-1]
        ax.annotate(
            f"{final_q:.4f}",
            xy=(rounds[-1], final_q),
            xytext=(10, 10),
            textcoords="offset points",
            fontsize=10,
            fontweight="bold",
            color="#2563eb",
        )

        fig.tight_layout()
        path = charts_dir / "quality_progression.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)  # type: ignore[union-attr]
        return path
    except Exception:
        logger.debug("Failed to generate quality progression chart", exc_info=True)
        return None


def _chart_cost_progression(
    plt: object,  # matplotlib.pyplot module
    journey: OptimizationJourney,
    charts_dir: Path,
) -> Path | None:
    """Line chart: best prompt cost per round."""
    if not journey.best_cost_per_round:
        return None

    try:
        fig, ax = plt.subplots(figsize=(10, 5))  # type: ignore[union-attr]
        rounds = list(range(1, len(journey.best_cost_per_round) + 1))
        ax.plot(rounds, journey.best_cost_per_round, "s-", color="#dc2626", linewidth=2, markersize=5)
        ax.set_xlabel("Round", fontsize=12)
        ax.set_ylabel("Cost", fontsize=12)
        ax.set_title("Cost Progression", fontsize=14, fontweight="bold")
        ax.grid(True, alpha=0.3)

        final_c = journey.best_cost_per_round[-1]
        ax.annotate(
            f"{final_c:.4f}",
            xy=(rounds[-1], final_c),
            xytext=(10, 10),
            textcoords="offset points",
            fontsize=10,
            fontweight="bold",
            color="#dc2626",
        )

        fig.tight_layout()
        path = charts_dir / "cost_progression.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)  # type: ignore[union-attr]
        return path
    except Exception:
        logger.debug("Failed to generate cost progression chart", exc_info=True)
        return None


def _chart_pareto_front(
    plt: object,  # matplotlib.pyplot module
    pareto_front: list[PromptSummary],
    charts_dir: Path,
) -> Path | None:
    """Scatter chart: Pareto front (cost vs quality)."""
    if not pareto_front:
        return None

    try:
        fig, ax = plt.subplots(figsize=(10, 6))  # type: ignore[union-attr]
        costs = [p.cost for p in pareto_front]
        qualities = [p.quality_score for p in pareto_front]
        versions = [p.version for p in pareto_front]

        ax.scatter(costs, qualities, s=100, c="#2563eb", zorder=5, edgecolors="white", linewidth=1.5)

        # Connect front points sorted by cost for the frontier line
        sorted_pairs = sorted(zip(costs, qualities, strict=True))
        ax.plot(
            [p[0] for p in sorted_pairs],
            [p[1] for p in sorted_pairs],
            "--",
            color="#2563eb",
            alpha=0.4,
            linewidth=1.5,
        )

        # Label each point
        for cost, quality, version in zip(costs, qualities, versions, strict=True):
            ax.annotate(
                version,
                xy=(cost, quality),
                xytext=(8, 8),
                textcoords="offset points",
                fontsize=9,
            )

        ax.set_xlabel("Cost", fontsize=12)
        ax.set_ylabel("Quality Score", fontsize=12)
        ax.set_title("Pareto Front: Cost vs Quality", fontsize=14, fontweight="bold")
        ax.grid(True, alpha=0.3)

        fig.tight_layout()
        path = charts_dir / "pareto_front.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)  # type: ignore[union-attr]
        return path
    except Exception:
        logger.debug("Failed to generate Pareto front chart", exc_info=True)
        return None
