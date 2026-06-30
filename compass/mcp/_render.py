# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Pure markdown renderers for MCP-facing artifact views."""

from __future__ import annotations

import json
from typing import Any

from compass.agents.final_report.models import BaselineComparison
from compass.agents.prompt_builder.search import SearchState
from compass.agents.review.models import ReviewBriefing
from compass.agents.routing_context import RoutingContext
from compass.eval.models import RunReport, ScoreReport


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|")


def _format_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, tuple):
        return "(" + ", ".join(_format_value(item) for item in value) + ")"
    if isinstance(value, list):
        return "[" + ", ".join(_format_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def render_routing_context_md(routing_context: RoutingContext) -> str:
    """Render a RoutingContext as markdown."""
    primary_metric_name = getattr(routing_context, "primary_metric_name", None) or "(not set)"
    lines = [
        "## Routing context",
        "",
        f"- dataset: {getattr(routing_context, 'domain', '(unknown)')}",
        f"- primary metric: {primary_metric_name}",
        "",
        f"### Routes ({len(routing_context.routes)})",
        "",
        "| name | description |",
        "|---|---|",
    ]
    for route in routing_context.routes:
        lines.append(f"| {route.name} | {_escape_cell(route.description)} |")

    if routing_context.routing_dimensions:
        lines.extend(
            [
                "",
                "### Routing dimensions",
                "",
                "| name | direction | description |",
                "|---|---|---|",
            ]
        )
        for dimension in routing_context.routing_dimensions:
            lines.append(f"| {dimension.name} | {dimension.direction} | {_escape_cell(dimension.description)} |")

    if routing_context.route_ordering is not None:
        ordering = ", ".join(routing_context.route_ordering.order)
        lines.extend(
            [
                "",
                f"- ordering: dimension={routing_context.route_ordering.dimension}, order=[{ordering}]",
            ]
        )

    return "\n".join(lines)


_ALGORITHM_RENDERERS: dict[str, dict[str, tuple[str, Any]]] = {
    "beam": {
        "beam_width": ("beam_width", _format_value),
        "hypervolume": ("hypervolume", _format_value),
        "reference_point": ("reference_point", _format_value),
        "ideal_point": ("ideal_point", _format_value),
        "nadir_point": ("nadir_point", _format_value),
    },
    "emosa": {
        "trajectory_id": ("trajectory_id", _format_value),
        "weight_vector": ("weight_vector", _format_value),
        "binding_axis": ("binding_axis", _format_value),
        "acceptance_history": ("acceptance_history", _format_value),
        "hypervolume": ("hypervolume", _format_value),
        "reference_point": ("reference_point", _format_value),
        "temperatures": ("temperatures", _format_value),
    },
    "sms_emoa": {
        "hypervolume": ("hypervolume", _format_value),
        "reference_point": ("reference_point", _format_value),
        "reduce_case": ("reduce_case", _format_value),
        "evicted_version": ("evicted_version", _format_value),
    },
    "hill_climb": {
        "mutation_mode": ("mutation_mode", _format_value),
        "stagnation_count": ("stagnation_count", _format_value),
        "target_improvement": ("target_improvement", _format_value),
    },
}


def render_algorithm_state_md(algorithm_state: dict[str, Any], algorithm: str) -> str:
    """Render the algorithm-specific SearchState pocket as markdown."""
    if not algorithm_state:
        return ""

    field_renderers = _ALGORITHM_RENDERERS.get(algorithm)
    rows: list[tuple[str, str]] = []

    if field_renderers is not None:
        for key, (label, formatter) in field_renderers.items():
            if key in algorithm_state:
                rows.append((label, formatter(algorithm_state[key])))
        if rows:
            lines = [
                f"## Algorithm state (`{algorithm}`)",
                "",
                "| field | value |",
                "|---|---|",
            ]
            lines.extend(f"| {label} | {_escape_cell(value)} |" for label, value in rows)
            return "\n".join(lines)

    lines = [
        f"## Algorithm state (`{algorithm}`)",
        "",
        "| field | value |",
        "|---|---|",
    ]
    for key in sorted(algorithm_state):
        lines.append(f"| {key} | {_escape_cell(_format_value(algorithm_state[key]))} |")
    return "\n".join(lines)


def render_search_state_md(state: SearchState, round_history_limit: int | None = 3) -> str:
    """Render SearchState as markdown, defaulting to the last 3 rounds of history."""
    lines = [
        f"## Search state — `{state.search_state_id}`",
        "",
        f"- backend: `{state.backend}`",
        f"- algorithm: `{state.algorithm}`",
        f"- round: {state.round}",
        f"- loop_phase: `{state.loop_phase}`",
        f"- converged: {state.converged}",
        f"- mutation_mode: `{state.mutation_mode}`",
        f"- stagnation: {state.stagnation_count}/{state.stagnation_limit}",
        f"- evaluation_budget: {state.evaluation_budget}",
        "",
        "### Elite set",
        "",
        "| version | parent | quality | cost | round |",
        "|---|---|---|---|---|",
    ]
    for candidate in state.elite_set:
        parent = f"`{candidate.parent_version}`" if candidate.parent_version else "—"
        lines.append(
            f"| `{candidate.prompt_version}` | {parent} | {candidate.quality_score:.3f} | "
            f"{candidate.cost:.4f} | {candidate.round_introduced} |"
        )

    history = state.round_history if round_history_limit is None else state.round_history[-round_history_limit:]
    if history:
        title = "### Recent rounds"
        if round_history_limit is not None and len(state.round_history) > len(history):
            title += f" (last {len(history)} of {len(state.round_history)})"
        lines.extend(
            [
                "",
                title,
                "",
                "| round | candidates | new elite | elite size | target delta | converged |",
                "|---|---|---|---|---|---|",
            ]
        )
        for summary in history:
            lines.append(
                f"| {summary.round} | {len(summary.candidates_evaluated)} | {summary.new_elite_entries} | "
                f"{summary.elite_size} | {summary.target_improvement:.3f} | {summary.converged} |"
            )

    algorithm_state_md = render_algorithm_state_md(state.algorithm_state, state.algorithm)
    if algorithm_state_md:
        lines.extend(["", algorithm_state_md])

    return "\n".join(lines)


def _coerce_score_report(report: ScoreReport | RunReport) -> tuple[ScoreReport, str | None]:
    if isinstance(report, ScoreReport):
        return report, None
    score_report = ScoreReport.from_run_report(
        report,
        report_path="(in-memory)",
        results_path="(in-memory)",
        previous_report=None,
    )
    return score_report, report.config.prompt_version


def _score_report_title(score_report: ScoreReport, prompt_version_hint: str | None) -> str:
    if prompt_version_hint:
        return f"## Score report — `{prompt_version_hint}`"
    if score_report.report_path not in {"", "(in-memory)"}:
        parts = score_report.report_path.split("/")
        if len(parts) >= 2:
            return f"## Score report — `{parts[-2]}`"
    return "## Score report"


def render_score_report_md(report: ScoreReport | RunReport) -> str:
    """Render a ScoreReport or RunReport as markdown."""
    score_report, prompt_version_hint = _coerce_score_report(report)

    lines = [_score_report_title(score_report, prompt_version_hint), ""]
    if score_report.metrics:
        lines.extend(["### Metrics", "", "| metric | value |", "|---|---|"])
        for key, value in score_report.metrics.items():
            cell = f"{value:.4f}" if isinstance(value, float) else str(value)
            lines.append(f"| {key} | {cell} |")

    summary = score_report.summary
    lines.extend(
        [
            "",
            "### Summary",
            "",
            "| total | succeeded | failed | total_cost | duration_seconds |",
            "|---|---|---|---|---|",
            (
                f"| {summary.total} | {summary.succeeded} | {summary.failed} | "
                f"{summary.total_cost:.4f} | {summary.duration_seconds:.2f} |"
            ),
        ]
    )

    if score_report.errors:
        lines.extend(
            ["", f"### Errors ({len(score_report.errors)})", "", "| example_id | error | retries |", "|---|---|---|"]
        )
        for error in score_report.errors:
            lines.append(f"| {error.example_id} | {_escape_cell(error.error)} | {error.retries} |")

    if score_report.diff is not None:
        lines.extend(["", "### Diff", "", "| metric | old | new | status |", "|---|---|---|---|"])
        for metric_diff in score_report.diff.metric_diffs:
            lines.append(
                f"| {metric_diff.key} | {_format_value(metric_diff.old)} | {_format_value(metric_diff.new)}"
                f" | {metric_diff.status} |"
            )
        if score_report.diff.overhead_diff is not None:
            overhead_diff = score_report.diff.overhead_diff
            lines.extend(
                [
                    "",
                    "| overhead | old | new |",
                    "|---|---|---|",
                    f"| cost | {_format_value(overhead_diff.old_cost)} | {_format_value(overhead_diff.new_cost)} |",
                    (
                        f"| duration | {_format_value(overhead_diff.old_duration)}"
                        f" | {_format_value(overhead_diff.new_duration)} |"
                    ),
                ]
            )

    return "\n".join(lines)


def render_baselines_md(baseline_comparison: BaselineComparison | None) -> str:
    """Render BaselineComparison as a compact markdown table."""
    if baseline_comparison is None:
        return ""

    lines = [
        "## Baseline comparison",
        "",
        "| strategy | route | quality | cost |",
        "|---|---|---|---|",
    ]
    for baseline in baseline_comparison.baselines:
        lines.append(
            f"| {baseline.strategy} | `{baseline.route}` | {baseline.quality_score:.4f} | {baseline.cost:.4f} |"
        )
    optimized = baseline_comparison.optimized
    lines.append(
        f"| {optimized.strategy} | `{optimized.route}` | {optimized.quality_score:.4f} | {optimized.cost:.4f} |"
    )
    return "\n".join(lines)


def render_review_briefing_md(briefing: ReviewBriefing) -> str:
    """Render ReviewBriefing via the existing review-summary renderer."""
    from compass.agents.review.render import render_briefing_summary

    return render_briefing_summary(briefing)
