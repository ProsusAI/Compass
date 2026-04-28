"""Review tools — briefing builder and directive outcomes."""

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context

from odysseus.agents.pipeline.dispatch import (
    clear_review_dispatched,
    record_review_dispatched,
)
from odysseus.agents.prompt_builder.search import RoundSummary, SearchState
from odysseus.agents.prompt_builder.search_ops import (
    _load_pending,
    _load_state,
    _save_loop_signal,
    _save_state,
)
from odysseus.agents.prompt_builder.search_ops import (
    set_loop_phase as _set_loop_phase,
)
from odysseus.mcp.server import mcp
from odysseus.project_dir import resolve_project_dir as _resolve_project_dir


@mcp.tool()
async def build_review_briefing_tool(
    ctx: Context,
    run_id: str,
    candidate_versions: list[str],
    parent_versions: dict[str, str | None],
    report_paths: dict[str, str],
    holdout_jsonl_path: str = "",
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Refinement Loop -- Review] Build a ReviewBriefing for the Review Agent.

    Pre-processes all numerical data.

    Loads search state, score reports, prompt texts, mutation log, and directive
    history, then computes candidate comparisons, per-class recall, diversity
    metrics, diminishing returns, mutation correlation, and oracle metrics.

    Args:
        run_id: Pipeline run identifier.
        candidate_versions: Versions evaluated in the current round.
        parent_versions: Mapping of candidate -> parent version.
        report_paths: Mapping of version -> path to its ScoreReport JSON.
        holdout_jsonl_path: Path to holdout JSONL file (optional).
        output_dir: Output directory (default "outputs").

    Returns:
        JSON-serialized ReviewBriefing.
    """
    from odysseus.agents.prompt_builder.search_ops import get_search_state
    from odysseus.agents.review.models import ExampleSummary
    from odysseus.agents.review.ops import (
        load_directive_history,
        load_mutation_log,
        load_round_reports,
        save_round_report,
    )
    from odysseus.agents.review.preprocessor import build_review_briefing
    from odysseus.prompts.manager import FilePromptManager

    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    # Load search state; cold start (no loop initialised yet) gets a bare default
    try:
        state = get_search_state(run_id=run_id, output_dir=out)
    except FileNotFoundError:
        state = SearchState(search_state_id=run_id, backend="")

    # Load score reports for current candidates + front + parents
    all_versions: set[str] = set(candidate_versions)
    for c in state.elite_set:
        all_versions.add(c.prompt_version)
    for parent in parent_versions.values():
        if parent is not None:
            all_versions.add(parent)

    # Load historical round reports
    historical = load_round_reports(run_id, output_dir=out)

    # Load current round reports via report_paths param; fall back to historical for front members
    score_reports: dict[str, Any] = {}
    for version in all_versions:
        if version in report_paths:
            rp = Path(report_paths[version])
            if rp.exists():
                score_reports[version] = json.loads(rp.read_text(encoding="utf-8"))
        elif version not in score_reports:
            for round_data in historical.values():
                if version in round_data:
                    score_reports[version] = round_data[version]
                    break

    # Load prompt texts
    import contextlib

    prompt_mgr = FilePromptManager(project_dir / "prompts")
    prompt_texts: dict[str, str] = {}
    for version in all_versions:
        with contextlib.suppress(FileNotFoundError):
            prompt_texts[version] = prompt_mgr.load(version)

    # Load mutation log and directive history
    mutation_log = load_mutation_log(run_id, output_dir=out)
    directive_history = load_directive_history(run_id, output_dir=out)

    # Auto-discover holdout path if not explicitly provided
    if not holdout_jsonl_path:
        default_holdout = out / run_id / "analysis" / "holdout.jsonl"
        if default_holdout.exists():
            holdout_jsonl_path = str(default_holdout)

    # Load holdout examples from JSONL file if path provided
    holdout_examples: list[ExampleSummary] = []
    if holdout_jsonl_path:
        holdout_path = Path(holdout_jsonl_path)
        if holdout_path.exists():
            for line in holdout_path.read_text(encoding="utf-8").strip().splitlines():
                example = json.loads(line)
                holdout_examples.append(
                    ExampleSummary(
                        example_id=example.get("id", ""),
                        route=example.get("expected", {}).get("route", ""),
                        input_text=example.get("input"),
                    )
                )

    # Load routing context
    routing_context = None
    routing_context_path = out / run_id / "validation" / "routing_context.json"
    if routing_context_path.exists():
        from odysseus.agents.routing_context import RoutingContext
        routing_context = RoutingContext.model_validate_json(
            routing_context_path.read_text(encoding="utf-8")
        )

    # Build briefing
    briefing = build_review_briefing(
        search_state=state,
        score_reports=score_reports,
        historical_reports=historical,
        prompt_texts=prompt_texts,
        mutation_log=mutation_log,
        directive_history=directive_history,
        holdout_examples=holdout_examples,
        candidate_versions=candidate_versions,
        parent_versions=parent_versions,
        routing_context=routing_context,
    )

    # Save current round's reports for future historical access
    current_round_reports = {v: score_reports[v] for v in candidate_versions if v in score_reports}
    save_round_report(run_id, state.round, current_round_reports, output_dir=out)

    # Record that the Review Agent sub-agent is now in-flight for this round.
    record_review_dispatched(run_id, round=state.round, output_dir=out)

    output_parts: list[str] = []
    if briefing.executive_summary:
        output_parts.append("# Executive Summary\n\n")
        output_parts.append(briefing.executive_summary)
        output_parts.append("\n\n# Full Briefing Data\n\n")
    output_parts.append(briefing.model_dump_json(indent=2))
    return "".join(output_parts)


@mcp.tool()
async def record_directive_outcomes_tool(
    ctx: Context,
    run_id: str,
    outcomes: list[dict[str, Any]],
    loop_signal: dict[str, Any] | None = None,
    edit_directives: list[dict[str, Any]] | None = None,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Refinement Loop -- Review] Record the outcomes of prior Review Agent directives.

    Also accepts the Review Agent's loop_signal to control search convergence.
    When loop_signal.action is "exit", the search loop is terminated immediately
    (converged=true). When "refine", the signal is persisted for advance_round
    to consume (budget extensions, mutation mode overrides).

    Args:
        run_id: Pipeline run identifier.
        outcomes: List of DirectiveOutcome dicts to record.
        loop_signal: Optional LoopSignal dict from the Review Agent.
        edit_directives: Optional list of EditDirective dicts to persist for the Prompt Builder.
        output_dir: Output directory (default "outputs").

    Returns:
        JSON object with recorded count, new total, and loop_signal status.
    """
    import contextlib

    from odysseus.agents.review.models import DirectiveOutcome, LoopSignal
    from odysseus.agents.review.ops import load_directive_history, save_directive_history

    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir
    parsed = [DirectiveOutcome.model_validate(o) for o in outcomes]
    existing = load_directive_history(run_id, output_dir=out)
    save_directive_history(run_id, existing + parsed, output_dir=out)

    result: dict[str, Any] = {
        "recorded": len(parsed),
        "total": len(existing) + len(parsed),
    }

    # Persist edit directives for Prompt Builder consumption.
    # Also writes child_variants.json — the canonical fanout-completion sentinel
    # checked by review_fanout_status / complete_stage("review").
    if edit_directives is not None:
        from odysseus.agents.review.models import EditDirective
        from odysseus.agents.review.ops import save_edit_directives

        parsed_directives = [EditDirective.model_validate(d) for d in edit_directives]
        save_edit_directives(run_id, parsed_directives, output_dir=out)
        result["edit_directives_saved"] = len(parsed_directives)

        # Write the shared child_variants.json sentinel so review_fanout_status
        # can confirm the fanout is complete without knowledge of directive format.
        child_variants_path = out / run_id / "search" / "child_variants.json"
        child_variants_path.parent.mkdir(parents=True, exist_ok=True)
        child_variants_path.write_text(
            json.dumps([d.model_dump(mode="json") for d in parsed_directives], indent=2),
            encoding="utf-8",
        )

    # Handle loop signal from Review Agent
    if loop_signal is not None:
        parsed_signal = LoopSignal.model_validate(loop_signal)

        if parsed_signal.action == "exit":
            # Terminate the loop — record final round summary, set converged=true
            with contextlib.suppress(FileNotFoundError):
                state = _load_state(run_id, out)
                pending = _load_pending(run_id, out)
                summary = RoundSummary(
                    round=state.round,
                    candidates_evaluated=[c.prompt_version for c in pending],
                    new_elite_entries=0,
                    elite_size=len(state.elite_set),
                    mutation_mode=state.mutation_mode,
                    stagnation_count=state.stagnation_count,
                    converged=True,
                    convergence_reason="review_exit",
                )
                updated = state.model_copy(update={
                    "converged": True,
                    "round_history": [*state.round_history, summary],
                })
                _save_state(run_id, updated, out)
            result["loop_signal_applied"] = "exit"
            return json.dumps(result)

        # action == "refine": persist signal for advance_round to consume
        _save_loop_signal(run_id, parsed_signal, out)
        result["loop_signal_applied"] = "refine"

    # Transition search loop to build phase so orchestrator spawns Prompt Builder next.
    # Also clear the review-dispatch marker so complete_stage("review") can proceed.
    with contextlib.suppress(FileNotFoundError):
        _set_loop_phase(run_id, "build", output_dir=out)
    clear_review_dispatched(run_id, output_dir=out)
    return json.dumps(result)
