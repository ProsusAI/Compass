"""Review tools — briefing builder, directive outcomes, and query tools."""

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

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
from odysseus.eval.models import RunReport, ScoreReport
from odysseus.mcp.server import mcp
from odysseus.project_dir import resolve_project_dir as _resolve_project_dir


def _load_score_report_dict(
    report_path: Path,
    results_path: Path | None = None,
) -> dict[str, Any]:
    """Load a report.json and return a ScoreReport-shaped dict.

    If report_path already contains a ScoreReport-shaped dict (i.e., all of
    ``errors``, ``diff``, ``report_path``, and ``results_path`` are present),
    it is returned as-is (idempotent).  Otherwise the file is parsed as a
    ``RunReport`` and converted via ``ScoreReport.from_run_report``.

    Args:
        report_path: Path to the report JSON file.
        results_path: Path to the corresponding results JSONL file.  When
            ``None``, derived by convention as ``report_path.parent /
            "results.jsonl"``.

    Returns:
        A dict that satisfies ``ScoreReport.model_validate(...)``.
    """
    if results_path is None:
        results_path = report_path.parent / "results.jsonl"

    raw: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))

    # Idempotency check: already ScoreReport-shaped
    _score_report_keys = {"errors", "diff", "report_path", "results_path"}
    if _score_report_keys.issubset(raw.keys()):
        return raw

    # Convert RunReport → ScoreReport
    run_report = RunReport.model_validate(raw)
    return ScoreReport.from_run_report(
        report=run_report,
        report_path=str(report_path),
        results_path=str(results_path),
        previous_report=None,
    ).model_dump(mode="json")


def _select_confusion_candidates(state: SearchState) -> list[str]:
    """Select candidate versions for confusion analysis.

    Defaults to the strategy's elite_set. Tests can monkey-patch this
    helper to override selection without changing the tool signature.
    """
    return [c.prompt_version for c in (state.elite_set or [])]


@mcp.tool()
async def build_review_briefing_tool(
    ctx: Context,
    run_id: str,
    candidate_versions: list[str] | None = None,
    parent_versions: dict[str, str | None] | None = None,
    report_paths: dict[str, str] | None = None,
    output_dir: str = "outputs",
    trajectory_id: int | None = None,
) -> str:
    """[Stage 4: Refinement Loop -- Review] Build a ReviewBriefing for the Review Agent.

    Pre-processes all numerical data.

    Loads search state, score reports, prompt texts, and child variants,
    then computes candidate comparisons, per-class recall, diversity metrics,
    diminishing returns, oracle metrics, and batch outcomes linking directives
    to eval results. Directive history is synthesized in code from batch_outcomes.

    All parameters except run_id are optional and auto-discovered.

    Args:
        run_id: Pipeline run identifier.
        candidate_versions: Versions evaluated in the current round. Auto-discovered
            from pending candidates on disk if omitted.
        parent_versions: Mapping of candidate -> parent version. Auto-discovered
            from pending candidates if omitted.
        report_paths: Mapping of version -> path to its RunReport JSON (auto-converted to ScoreReport on load).
            Auto-discovered from disk (outputs/<run_id>/eval/<version>/report.json)
            if omitted.
        output_dir: Output directory (default "outputs").
        trajectory_id: EMOSA only. When provided, populate EMOSA-specific briefing
            fields (weight_vector, binding_axis, acceptance_history) from this
            specific trajectory rather than using the default round-robin pick.
            Pass the trajectory's integer ID (0-indexed). Ignored for non-EMOSA runs.

    Returns:
        JSON-serialized ReviewBriefing.
    """
    from odysseus.agents.prompt_builder.search_ops import get_search_state
    from odysseus.agents.review.ops import (
        load_all_trajectory_child_variants,
        load_cell_attempt_history,
        load_child_variants,
        load_round_reports,
        update_cell_attempt_history,
    )
    from odysseus.agents.review.preprocessor import build_review_briefing, parse_user_targets
    from odysseus.prompts.manager import FilePromptManager

    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    # Load search state — must exist (pre-initialised by _ensure_stage4_search_state
    # at Stage 4 entry).  Missing state is a hard error so regressions surface immediately.
    try:
        state = get_search_state(run_id=run_id, output_dir=out)
    except FileNotFoundError as exc:
        raise ToolError("search_state.json missing — Stage 4 not initialised") from exc

    # EMOSA-specific: auto-fire calibration on first review entry.
    # Calibration is pure computation (no LLM), so it lives in the backend
    # transition rather than as a separate user-facing step.
    if state.algorithm == "emosa" and not state.elite_set:
        pending_for_calib = _load_pending(run_id, out)
        scored_for_calib = [c for c in pending_for_calib if c.eval_status in ("complete", None)]
        num_traj = state.algorithm_state.get("num_trajectories", 0)
        if num_traj and len(scored_for_calib) >= num_traj:
            from odysseus.agents.prompt_builder.search_ops import _calibration_complete

            _calibration_complete(run_id, state, out)
            state = get_search_state(run_id=run_id, output_dir=out)

    # Auto-discover pending candidates
    pending_candidates_list = _load_pending(run_id, out)

    # Auto-populate candidate_versions and parent_versions from pending candidates
    if candidate_versions is None:
        candidate_versions = [c.prompt_version for c in pending_candidates_list]
    if parent_versions is None:
        parent_versions = {c.prompt_version: c.parent_version for c in pending_candidates_list}

    # Load score reports for current candidates + front + parents
    all_versions: set[str] = set(candidate_versions)
    for c in state.elite_set:
        all_versions.add(c.prompt_version)
    for parent in parent_versions.values():
        if parent is not None:
            all_versions.add(parent)

    # Load historical round reports
    historical = load_round_reports(run_id, output_dir=out)

    # Auto-discover report_paths from disk if not provided
    if report_paths is None:
        report_paths = {}
        for version in candidate_versions:
            default_path = out / run_id / "eval" / version / "report.json"
            if default_path.exists():
                report_paths[version] = str(default_path)

    # Load current round reports via report_paths param; fall back to historical for front members
    score_reports: dict[str, Any] = {}
    for version in all_versions:
        if version in report_paths:
            rp = Path(report_paths[version])
            if rp.exists():
                results_path = rp.parent / "results.jsonl"
                score_reports[version] = _load_score_report_dict(rp, results_path)
        elif version not in score_reports:
            for round_data in historical.values():
                if version in round_data:
                    synthetic_report_path = out / run_id / "eval" / version / "report.json"
                    synthetic_results_path = out / run_id / "eval" / version / "results.jsonl"
                    historical_dict = round_data[version]
                    _score_report_keys = {"errors", "diff", "report_path", "results_path"}
                    if _score_report_keys.issubset(historical_dict.keys()):
                        score_reports[version] = historical_dict
                    else:
                        run_report = RunReport.model_validate(historical_dict)
                        score_reports[version] = ScoreReport.from_run_report(
                            report=run_report,
                            report_path=str(synthetic_report_path),
                            results_path=str(synthetic_results_path),
                            previous_report=None,
                        ).model_dump(mode="json")
                    break

    # Load prompt texts (used internally for diversity metrics, not surfaced in briefing)
    run_prompts_dir = out / run_id / "prompts"
    project_prompts_dir = project_dir / "prompts"
    prompt_texts: dict[str, str] = {}
    for version in all_versions:
        for prompts_dir in (run_prompts_dir, project_prompts_dir):
            try:
                prompt_texts[version] = FilePromptManager(prompts_dir).load(version)
                break
            except FileNotFoundError:
                continue

    # Load child variants for batch outcome tracking. Prefer per-trajectory files
    # (EMOSA K-way fanout) when present; otherwise fall back to the single-slot sentinel.
    search_dir_for_load = out / run_id / "search"
    if search_dir_for_load.exists() and any(search_dir_for_load.glob("child_variants_t*.json")):
        child_variants = load_all_trajectory_child_variants(run_id, output_dir=out) or None
    else:
        child_variants = load_child_variants(run_id, output_dir=out) or None

    # Load routing context
    routing_context = None
    routing_context_path = out / run_id / "validation" / "routing_context.json"
    if routing_context_path.exists():
        from odysseus.agents.routing_context import RoutingContext

        routing_context = RoutingContext.model_validate_json(routing_context_path.read_text(encoding="utf-8"))

    # Load user targets from validated input report
    user_targets = None
    input_report_path = out / run_id / "validation" / "input_report.md"
    if input_report_path.exists():
        user_targets = parse_user_targets(input_report_path.read_text(encoding="utf-8"))

    # Load full-dataset oracle if available
    full_dataset_oracle: dict[str, float] | None = None
    oracle_path = out / run_id / "eval" / "oracle_metrics.json"
    if oracle_path.exists():
        full_dataset_oracle = json.loads(oracle_path.read_text(encoding="utf-8"))

    # Load dev-set oracle if available
    dev_oracle: dict[str, float] | None = None
    dev_oracle_path = out / run_id / "eval" / "dev_oracle_metrics.json"
    if dev_oracle_path.exists():
        dev_oracle = json.loads(dev_oracle_path.read_text(encoding="utf-8"))

    # Load raw eval results and examples for confusion analysis
    eval_results_for_confusion = None
    examples_for_confusion = None

    selected_versions = _select_confusion_candidates(state)
    if selected_versions:
        from odysseus.eval.models import EvalResult, Example

        all_eval_results: list[EvalResult] = []
        for version in selected_versions:
            results_path = out / run_id / "eval" / version / "results.jsonl"
            if results_path.exists():
                for line in results_path.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        row = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                    if row.get("__meta__"):
                        continue
                    try:
                        all_eval_results.append(EvalResult.model_validate(row))
                    except Exception:
                        continue
        if all_eval_results:
            eval_results_for_confusion = all_eval_results

        # Load dataset examples (dev set)
        dev_path = out / run_id / "analysis" / "dev.jsonl"
        if dev_path.exists():
            loaded_examples: list[Example] = []
            for line in dev_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    loaded_examples.append(Example.model_validate_json(stripped))
                except Exception:
                    continue
            if loaded_examples:
                examples_for_confusion = loaded_examples

    # Load cell attempt history for confusion cell exhaustion tracking
    cell_attempt_history = load_cell_attempt_history(run_id, output_dir=out)

    # Build briefing
    briefing = build_review_briefing(
        search_state=state,
        score_reports=score_reports,
        historical_reports=historical,
        prompt_texts=prompt_texts,
        candidate_versions=candidate_versions,
        parent_versions=parent_versions,
        routing_context=routing_context,
        child_variants=child_variants,
        pending_candidates=pending_candidates_list,
        user_targets=user_targets,
        full_dataset_oracle=full_dataset_oracle,
        dev_oracle=dev_oracle,
        eval_results=eval_results_for_confusion,
        examples=examples_for_confusion,
        run_dir=out / run_id,
        cell_attempt_history=cell_attempt_history or None,
        emosa_trajectory_id=trajectory_id,
    )

    # Update cell attempt history from batch outcomes (links prior child variants to outcomes)
    if briefing.batch_outcomes and child_variants:
        update_cell_attempt_history(
            run_id,
            briefing.batch_outcomes,
            child_variants,
            briefing.confusion_analysis,
            current_round=state.round,
            output_dir=out,
        )

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
    loop_signal: dict[str, Any] | None = None,
    child_variants: list[dict[str, Any]] | None = None,
    review_result: dict[str, Any] | None = None,
    candidate_ranking: list[dict[str, Any]] | None = None,
    promotion_decisions: list[dict[str, Any]] | None = None,
    regression_guards: list[dict[str, Any]] | None = None,
    trajectory_id: int | None = None,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Refinement Loop -- Review] Record the Review Agent's result fields.

    Records loop_signal, child_variants, candidate_ranking, promotion_decisions, and
    regression_guards from the Review Agent. Directive outcomes are no longer passed
    here — they are synthesized fully in code from batch_outcomes by build_review_briefing_tool.

    Also accepts the Review Agent's loop_signal to control search convergence.
    When loop_signal.action is "exit", the search loop is terminated immediately
    (converged=true). When "refine", the signal is persisted for advance_round
    to consume (budget extensions, mutation mode overrides).

    Prefer passing ReviewResult fields as separate parameters (candidate_ranking,
    promotion_decisions, regression_guards) rather than as a single review_result
    dict to avoid hitting JSON size limits.

    Args:
        run_id: Pipeline run identifier.
        loop_signal: Optional LoopSignal dict from the Review Agent.
        child_variants: Optional list of ChildVariant dicts (Review Agent output).
            For cold-start / warm-up seeds, set each variant's parent_version to
            briefing.initial_parent_version (default "base").
        review_result: Optional full ReviewResult dict to persist to disk. Legacy fallback —
            prefer decomposed parameters. When provided, child_variants and loop_signal are
            extracted from it as fallbacks for any of those params not explicitly provided.
        candidate_ranking: Decomposed ReviewResult field — list of ranked candidate dicts.
            Recommended over review_result to avoid size limits.
        promotion_decisions: Decomposed ReviewResult field — list of promotion decision dicts.
            Recommended over review_result to avoid size limits.
        regression_guards: Decomposed ReviewResult field — list of regression guard dicts.
            Recommended over review_result to avoid size limits.
        trajectory_id: EMOSA-only — when provided together with child_variants, persists
            variants to child_variants_t<trajectory_id>.json via
            save_trajectory_child_variants and records the trajectory as dispatched via
            record_trajectory_dispatched. Variant ids use the format cv-{round}-t{trajectory_id}-{i}.
            When None (default), the single-slot child_variants.json path is used.
        output_dir: Output directory (default "outputs").

    Returns:
        JSON object with child_variants_saved, variants_summary, and loop_signal status.
    """
    import contextlib

    from odysseus.agents.review.models import ChildVariant, LoopSignal
    from odysseus.agents.review.ops import (
        record_trajectory_dispatched,
        save_child_variants,
        save_trajectory_child_variants,
    )

    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    # When decomposed params are provided, assemble and persist an audit ReviewResult.
    # When only review_result is provided, persist it as-is (legacy path).
    if review_result is None and any([candidate_ranking, promotion_decisions, regression_guards]):
        from odysseus.agents.review.ops import save_review_result

        reconstructed: dict[str, Any] = {
            "candidate_ranking": candidate_ranking or [],
            "promotion_decisions": promotion_decisions or [],
            "regression_guards": regression_guards or [],
        }
        if child_variants is not None:
            reconstructed["child_variants"] = child_variants
        if loop_signal is not None:
            reconstructed["loop_signal"] = loop_signal
        save_review_result(run_id, reconstructed, output_dir=out)
    elif review_result is not None:
        from odysseus.agents.review.ops import save_review_result

        save_review_result(run_id, review_result, output_dir=out)

    result: dict[str, Any] = {}

    # Persist child variants.
    # EMOSA path (trajectory_id is not None): write per-trajectory file and record dispatch.
    # Single-slot path (trajectory_id is None): write the canonical child_variants.json sentinel.
    if child_variants is not None:
        parsed_variants = [ChildVariant.model_validate(v) for v in child_variants]

        # Assign stable variant_ids using the global monotonic counter stored in
        # SearchState so that ids are sequential across all rounds (v1, v2, …).
        current_round = 0
        with contextlib.suppress(FileNotFoundError):
            state = _load_state(run_id, out)
            current_round = state.round
            next_seq = state.next_variant_seq
            for i, v in enumerate(parsed_variants):
                if v.variant_id is None:
                    parsed_variants[i] = v.model_copy(update={"variant_id": f"v{next_seq}"})
                    next_seq += 1
            _save_state(run_id, state.model_copy(update={"next_variant_seq": next_seq}), out)

        if trajectory_id is not None:
            # EMOSA K-way fanout: use per-trajectory variant ids and file.
            for i, v in enumerate(parsed_variants):
                if v.variant_id is None:
                    parsed_variants[i] = v.model_copy(update={"variant_id": f"cv-{current_round}-t{trajectory_id}-{i}"})
            parsed_variants = [v.model_copy(update={"trajectory_id": trajectory_id}) for v in parsed_variants]
            save_trajectory_child_variants(run_id, trajectory_id, parsed_variants, output_dir=out)
            record_trajectory_dispatched(run_id, trajectory_id, output_dir=out)
        else:
            # Single-slot path (hill-climb).
            for i, v in enumerate(parsed_variants):
                if v.variant_id is None:
                    parsed_variants[i] = v.model_copy(update={"variant_id": f"cv-{current_round}-{i}"})

            save_child_variants(run_id, parsed_variants, output_dir=out)

            # Write the shared child_variants.json sentinel so review_fanout_status
            # can confirm the fanout is complete without knowledge of directive format.
            child_variants_path = out / run_id / "search" / "child_variants.json"
            child_variants_path.parent.mkdir(parents=True, exist_ok=True)
            child_variants_path.write_text(
                json.dumps([v.model_dump(mode="json") for v in parsed_variants], indent=2),
                encoding="utf-8",
            )

        result["child_variants_saved"] = len(parsed_variants)
        result["variants_summary"] = [
            {"variant_id": v.variant_id, "hypothesis": v.hypothesis[:80]} for v in parsed_variants
        ]

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
                updated = state.model_copy(
                    update={
                        "converged": True,
                        "round_history": [*state.round_history, summary],
                    }
                )
                _save_state(run_id, updated, out)
            result["loop_signal_applied"] = "exit"
            return json.dumps(result)

        # action == "refine": persist signal for advance_round to consume
        _save_loop_signal(run_id, parsed_signal, out)
        result["loop_signal_applied"] = "refine"

    # Transition search loop to build phase so orchestrator spawns Prompt Builder next.
    with contextlib.suppress(FileNotFoundError):
        _set_loop_phase(run_id, "build", output_dir=out)
    # For EMOSA K-way fanout (trajectory_id is not None), preserve review_dispatched.json
    # so trajectory_fanout_missing can track in-flight vs completed slots across N sub-agent
    # calls.  For single-slot algorithms, clear the marker so complete_stage("review") can
    # proceed.
    if trajectory_id is None:
        clear_review_dispatched(run_id, output_dir=out)
    return json.dumps(result)


@mcp.tool()
async def query_holdout_examples_tool(
    ctx: Context,
    run_id: str,
    route: str | None = None,
    offset: int = 0,
    limit: int = 20,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Refinement Loop -- Review] Query holdout examples, optionally filtered by route.

    Returns full example objects from the holdout dataset including input text
    and per-route cost/quality data. Use this to find examples for specific
    routes when crafting few-shot example directives.

    Args:
        run_id: Pipeline run identifier.
        route: Filter by expected route name. Returns all routes if omitted.
        offset: Skip the first N matching examples (default 0). Use with limit for pagination.
        limit: Maximum number of examples to return (default 20).
        output_dir: Output directory (default "outputs").

    Returns:
        JSON object with examples list and total_matching count.
    """
    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    holdout_path = out / run_id / "analysis" / "holdout.jsonl"
    if not holdout_path.exists():
        return json.dumps({"examples": [], "total_matching": 0, "error": "holdout.jsonl not found"})

    examples: list[dict[str, Any]] = []
    total_matching = 0
    for line in holdout_path.read_text(encoding="utf-8").strip().splitlines():
        if not line.strip():
            continue
        example = json.loads(line)
        expected_route = example.get("expected", {}).get("route", "")
        if route is not None and expected_route != route:
            continue
        total_matching += 1
        if total_matching <= offset:
            continue
        if len(examples) < limit:
            examples.append(example)

    return json.dumps({"examples": examples, "total_matching": total_matching})


@mcp.tool()
async def get_prompt_text_tool(
    ctx: Context,
    version: str,
    run_id: str,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Refinement Loop -- Review] Retrieve the full text of a prompt version.

    Use this to inspect the actual prompt content for a specific version
    when analyzing misrouting patterns or reviewing directive effects.

    Args:
        version: Prompt version string (e.g., "v3").
        run_id: Pipeline run identifier. Looks in outputs/<run_id>/prompts/ first,
            then falls back to the project-level prompts/ directory.
        output_dir: Output directory (default "outputs").

    Returns:
        The full prompt text.
    """
    from odysseus.prompts.manager import FilePromptManager

    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    for prompts_dir in (out / run_id / "prompts", project_dir / "prompts"):
        try:
            return FilePromptManager(prompts_dir).load(version)
        except FileNotFoundError:
            continue
    return json.dumps({"error": f"Prompt version '{version}' not found"})


@mcp.tool()
async def get_score_report_tool(
    ctx: Context,
    version: str,
    run_id: str,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Refinement Loop] Retrieve the ScoreReport for an evaluated prompt version.

    Reads outputs/<run_id>/eval/<version>/report.json and returns a
    ScoreReport-shaped dict (errors, diff, report_path, results_path),
    converting from RunReport on the fly if needed.

    Args:
        version: Prompt version string (e.g., "v3").
        run_id: Pipeline run identifier.
        output_dir: Output directory (default "outputs").

    Returns:
        JSON-serialized ScoreReport dict, or {"error": "..."} if the report
        does not exist.
    """
    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    report_path = out / run_id / "eval" / version / "report.json"
    if not report_path.exists():
        return json.dumps({"error": f"ScoreReport for version '{version}' not found"})

    return json.dumps(_load_score_report_dict(report_path))
