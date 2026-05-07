"""Markdown renderer for ReviewBriefing — progressive-disclosure summary."""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odysseus.agents.review.models import ReviewBriefing


def _render_round_summary(briefing: ReviewBriefing) -> str:
    lines = [f"## Round {briefing.round} — summary", ""]
    om = briefing.oracle_metrics
    if om is not None:
        lines.append(f"- oracle_cost_change: {om.oracle_cost_change:.3f}")
        lines.append(f"- oracle_quality_change: {om.oracle_quality_change:.3f}")
        if om.candidate_quality_captured is not None:
            lines.append(f"- candidate_quality_captured: {om.candidate_quality_captured:.3f}")
        if om.candidate_cost_captured is not None:
            lines.append(f"- candidate_cost_captured: {om.candidate_cost_captured:.3f}")
    lines.append(f"- single_candidate_meets_all: {briefing.single_candidate_meets_all}")
    lines.append(f"- backtracking: {briefing.backtracking}")
    return "\n".join(lines)


def _render_routing_context(briefing: ReviewBriefing) -> str:
    rc = briefing.routing_context
    if rc is None:
        return ""
    routes = ", ".join(r.name for r in rc.routes) if rc.routes else "(none)"
    pm = getattr(rc, "primary_metric_name", None) or "(not set)"
    lines = [
        "## Routing context",
        "",
        f"- dataset: {getattr(rc, 'domain', '(unknown)')}",
        f"- routes ({len(rc.routes)}): {routes}",
        f"- primary metric: {pm}",
    ]
    return "\n".join(lines)


def _render_per_class_recall(briefing: ReviewBriefing) -> str:
    pcr = briefing.per_class_recall
    if not pcr:
        return ""
    supports = [e.support for e in pcr.values()]
    med = statistics.median(supports) if supports else 0

    rows: list[tuple[str, float, int, str, bool]] = []
    for route, entry in pcr.items():
        if entry.regression_flag or entry.support >= med:
            trend_str = " → ".join(f"{v:.2f}" for v in entry.trend[-3:]) if entry.trend else "—"
            rows.append((route, entry.recall, entry.support, trend_str, entry.regression_flag))

    if not rows:
        return (
            "## Per-class recall (regressions and high-support routes only)\n\nNo regressions or high-support routes."
        )

    lines = [
        "## Per-class recall (regressions and high-support routes only)",
        "",
        "| route | recall | support | trend | regression |",
        "|---|---|---|---|---|",
    ]
    for route, recall, support, trend, reg in rows:
        lines.append(f"| {route} | {recall:.3f} | {support} | {trend} | {reg} |")
    return "\n".join(lines)


def _render_diversity(briefing: ReviewBriefing) -> str:
    dm = briefing.diversity_metrics
    dr = briefing.diminishing_returns
    lines = [
        "## Diversity & diminishing returns",
        "",
        f"- example_overlap_ratio: {dm.example_overlap_ratio:.3f}",
    ]
    if dr.score_trajectory:
        last3 = dr.score_trajectory[-3:]
        lines.append("- score_trajectory (last 3): " + " → ".join(f"{v:.3f}" for v in last3))
    lines.append(f"- improvement_trend: {dr.improvement_trend:.3f}")
    lines.append(f"- stagnation_flag: {dr.stagnation_flag}")
    sig = briefing.stagnation_signal
    if sig:
        lines.append(f"- stagnation_signal: {sig}")
    return "\n".join(lines)


def _render_target_progress(briefing: ReviewBriefing) -> str:
    tp = briefing.target_progress
    if not tp:
        return ""
    lines = [
        "## Target progress",
        "",
        "| metric | operator | threshold | current | met | progress |",
        "|---|---|---|---|---|---|",
    ]
    for p in tp:
        t = p.target
        current = f"{p.current_value:.3f}" if p.current_value is not None else "—"
        progress = f"{p.progress_ratio:.3f}" if p.progress_ratio is not None else "—"
        met = "✓" if p.met else "✗"
        lines.append(f"| {t.metric} | {t.operator} | {t.threshold} | {current} | {met} | {progress} |")
    return "\n".join(lines)


def _render_confusion_analysis(briefing: ReviewBriefing, n: int = 5) -> str:
    ca = briefing.confusion_analysis
    if not ca:
        return ""
    top = sorted(ca, key=lambda c: c.effective_impact, reverse=True)[:n]
    lines = [
        "## Confusion analysis (top N by impact)",
        "",
        "| true → predicted | count | misroute% | quality_impact | cost_impact | persistence | attempted |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in top:
        cell = f"`{c.true_route}` → `{c.predicted_route}`"
        misroute_pct = f"{c.misroute_rate * 100:.1f}%"
        lines.append(
            f"| {cell} | {c.count} | {misroute_pct} | {c.quality_impact:.3f} | {c.cost_impact:.3f}"
            f" | {c.persistence_rate:.2f} | {c.attempt_count} |"
        )
    lines.append("")
    lines.append("Use `get_confusion_cell_tool(true_route=..., predicted_route=...)` for cell-level detail.")
    return "\n".join(lines)


def _render_candidates(briefing: ReviewBriefing) -> str:
    cands = briefing.candidates
    if not cands:
        return ""
    lines = [
        "## Candidates this round",
        "",
        "| version | parent | Δquality | Δcost | mutation |",
        "|---|---|---|---|---|",
    ]
    for c in cands:
        ver = f"`{c.candidate_version}`"
        par = f"`{c.parent_version}`" if c.parent_version else "—"
        dq = f"{c.delta_vs_parent.quality_delta:.3f}" if c.delta_vs_parent.quality_delta is not None else "—"
        dc = f"{c.delta_vs_parent.cost_delta:.3f}" if c.delta_vs_parent.cost_delta is not None else "—"
        mut = c.mutation_description[:50] if c.mutation_description else "—"
        lines.append(f"| {ver} | {par} | {dq} | {dc} | {mut} |")
    lines.append("")
    lines.append("Use `get_score_report_tool(version=...)` for full errors.")
    return "\n".join(lines)


def _render_elite_set(briefing: ReviewBriefing) -> str:
    es = briefing.elite_set
    if not es:
        return ""
    lines = [
        "## Elite set",
        "",
        "| version | quality | cost |",
        "|---|---|---|",
    ]
    for c in es:
        ver = f"`{c.prompt_version}`"
        q = f"{c.quality_score:.3f}" if c.quality_score is not None else "—"
        cost = f"{c.cost:.4f}" if c.cost is not None else "—"
        lines.append(f"| {ver} | {q} | {cost} |")
    return "\n".join(lines)


def _render_last_round_directives(briefing: ReviewBriefing) -> str:
    prev_round = briefing.round - 1
    if prev_round < 1:
        return ""

    dh = [d for d in briefing.directive_history]
    bo = [b for b in briefing.batch_outcomes]

    if not dh and not bo:
        return ""

    lines = [
        "## Last round directives & outcomes",
        "",
    ]
    for d in dh:
        lines.append(f"- `{d.prior_directive_id}` → {d.outcome}")

    lines.append("")
    lines.append(
        "Use `get_directive_history_tool(since_round=...)` for older history; "
        "`get_batch_outcomes_tool(round=...)` for full outcome metrics."
    )
    return "\n".join(lines)


def _render_child_variants(briefing: ReviewBriefing) -> str:
    cvs = briefing.child_variants
    if not cvs:
        return ""
    lines = ["## This round's child variants", ""]
    for cv in cvs:
        vid = cv.variant_id or "(unassigned)"
        hyp = cv.hypothesis or "(no hypothesis)"
        lines.append(f"### `{vid}` — {hyp}")
        for d in cv.directives:
            lines.append(f"- `{d.directive_id}` [{d.block_type}]")
    lines.append("")
    lines.append(
        "Use `get_round_child_variants_tool(run_id, round, with_directive_bodies=True)` for full directive bodies."
    )
    return "\n".join(lines)


def _render_emosa_trajectory(briefing: ReviewBriefing) -> str:
    if briefing.trajectory_id is None:
        return ""
    lines = [
        "## EMOSA trajectory",
        "",
        f"- trajectory_id: {briefing.trajectory_id}",
    ]
    if briefing.weight_vector is not None:
        lq, lc = briefing.weight_vector
        lines.append(f"- weight_vector: λ_q={lq:.3f}, λ_c={lc:.3f}")
    if briefing.binding_axis is not None:
        lines.append(f"- binding_axis: {briefing.binding_axis}")
    if briefing.acceptance_history is not None:
        last5 = briefing.acceptance_history[-5:]
        hist_str = " ".join("✓" if a else "✗" for a in last5)
        lines.append(f"- acceptance_history (last 5): {hist_str}")
    return "\n".join(lines)


def render_briefing_summary(briefing: ReviewBriefing) -> str:
    """Render a ReviewBriefing as a markdown progressive-disclosure summary."""
    sections: list[str] = []

    if briefing.executive_summary:
        sections.append(f"# Executive summary\n\n{briefing.executive_summary}")

    sections.append(_render_round_summary(briefing))

    rc = _render_routing_context(briefing)
    if rc:
        sections.append(rc)

    pcr = _render_per_class_recall(briefing)
    if pcr:
        sections.append(pcr)

    sections.append(_render_diversity(briefing))

    tp = _render_target_progress(briefing)
    if tp:
        sections.append(tp)

    ca = _render_confusion_analysis(briefing)
    if ca:
        sections.append(ca)

    cands = _render_candidates(briefing)
    if cands:
        sections.append(cands)

    es = _render_elite_set(briefing)
    if es:
        sections.append(es)

    lrd = _render_last_round_directives(briefing)
    if lrd:
        sections.append(lrd)

    cv = _render_child_variants(briefing)
    if cv:
        sections.append(cv)

    em = _render_emosa_trajectory(briefing)
    if em:
        sections.append(em)

    return "\n\n".join(s for s in sections if s)
