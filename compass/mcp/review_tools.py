# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Review tools — briefing builder, directive outcomes, and query tools."""

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

from compass.agents.pipeline.dispatch import (
    clear_review_dispatched,
    record_review_dispatched,
)
from compass.agents.prompt_builder.search import RoundSummary, SearchState
from compass.agents.prompt_builder.search_ops import (
    _load_pending,
    _load_state,
    _save_loop_signal,
    _save_state,
)
from compass.agents.prompt_builder.search_ops import (
    set_loop_phase as _set_loop_phase,
)
from compass.eval.models import EvalResult, RunReport, ScoreReport
from compass.mcp._render import render_review_briefing_md, render_score_report_md
from compass.mcp.server import mcp
from compass.project_dir import resolve_project_dir as _resolve_project_dir


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


_DATASET_QUERY_MAX_LIMIT = 50

_DEPRECATED_REVIEW_HISTORY_MESSAGE = (
    "Deprecated: {tool_name} no longer returns historical data.\n\n"
    "The source it depended on (`outputs/<run_id>/search/round_reports/`) is no longer written by any "
    "production code path.\n\n"
    "Current context:\n"
    "- directive outcomes appear in `build_review_briefing` under the section starting with "
    "`## Last round directives & outcomes`\n"
    "- per-version score detail is available via `get_score_report`\n\n"
    "This tool is retained as a surface placeholder and may be removed in a future release."
)


def _query_jsonl_dataset(
    dataset_path: Path,
    *,
    route: str | None,
    example_ids: list[str] | None,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    """Return a page of dataset rows, filtered by ids or expected.route."""
    if offset < 0:
        raise ToolError("offset must be >= 0")
    if limit <= 0:
        raise ToolError("limit must be > 0")
    if limit > _DATASET_QUERY_MAX_LIMIT:
        raise ToolError(f"limit must be <= {_DATASET_QUERY_MAX_LIMIT}")

    example_id_set = set(example_ids) if example_ids else None
    examples: list[dict[str, Any]] = []
    skipped = 0

    with dataset_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            example = json.loads(line)
            expected_route = example.get("expected", {}).get("route", "")
            if example_id_set is not None:
                if example.get("id") not in example_id_set:
                    continue
            elif route is not None and expected_route != route:
                continue
            if skipped < offset:
                skipped += 1
                continue
            examples.append(example)
            if len(examples) >= limit:
                break

    return {"examples": examples}


def _truncate_input_excerpt(text: str, max_chars: int = 300) -> str:
    """Render a single-line input excerpt capped at max_chars characters."""
    single_line = " ".join(text.split())
    if len(single_line) <= max_chars:
        return single_line
    if max_chars <= 3:
        return single_line[:max_chars]
    return single_line[: max_chars - 3] + "..."


@mcp.tool()
async def build_review_briefing(
    ctx: Context,
    run_id: str,
    candidate_versions: list[str] | None = None,
    parent_versions: dict[str, str | None] | None = None,
    report_paths: dict[str, str] | None = None,
    output_dir: str = "outputs",
    trajectory_id: int | None = None,
) -> str:
    """[Stage 4: Refinement Loop -- Review] Build a ReviewBriefing with pre-computed metrics for the Review Agent.

    Args:
        run_id: Pipeline run identifier.
        candidate_versions: Versions evaluated this round (auto-discovered if omitted).
        parent_versions: Mapping of candidate -> parent version (auto-discovered if omitted).
        report_paths: Mapping of version -> report.json path (auto-discovered if omitted).
        output_dir: Output directory (default "outputs").
        trajectory_id: EMOSA only — selects per-trajectory fields; ignored otherwise.

    Returns:
        Markdown progressive-disclosure ReviewBriefing summary.
    """
    from compass.agents.prompt_builder.search_ops import get_search_state
    from compass.agents.review.ops import (
        load_cell_attempt_history,
        load_child_variants,
        load_historical_eval_reports,
        update_cell_attempt_history,
    )
    from compass.agents.review.preprocessor import build_review_briefing as _build_review_briefing_impl
    from compass.agents.review.preprocessor import parse_user_targets
    from compass.prompts.manager import FilePromptManager

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
            from compass.agents.prompt_builder import search_ops as _search_ops

            calibration_complete = getattr(_search_ops, "_calibration_complete", None)
            if calibration_complete is not None:
                calibration_complete(run_id, state, out)
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
    historical = load_historical_eval_reports(run_id, state, output_dir=out)

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

    # Load child variants for batch outcome tracking.
    search_dir_for_load = out / run_id / "search"
    if search_dir_for_load.exists() and any(search_dir_for_load.glob("child_variants_t*.json")):
        from compass.agents.review.ops import (
            load_all_trajectory_child_variants,  # pyright: ignore[reportAttributeAccessIssue]
        )

        child_variants = load_all_trajectory_child_variants(run_id, output_dir=out) or None
    else:
        child_variants = load_child_variants(run_id, output_dir=out) or None

    # Load routing context
    routing_context = None
    routing_context_path = out / run_id / "validation" / "routing_context.json"
    if routing_context_path.exists():
        from compass.agents.routing_context import RoutingContext

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
        from compass.eval.models import EvalResult, Example

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
    briefing = _build_review_briefing_impl(
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

    return render_review_briefing_md(briefing)


@mcp.tool()
async def record_directive_outcomes(
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
    """[Stage 4: Refinement Loop -- Review] Persist Review Agent outputs and advance the loop to build phase.

    Args:
        run_id: Run identifier.
        loop_signal: "exit" converges; "refine" persists for advance_round.
        child_variants: ChildVariant dicts to save.
        review_result: Legacy full ReviewResult dict (prefer decomposed params).
        candidate_ranking: Ranked candidates.
        promotion_decisions: Promotion decisions.
        regression_guards: Regression guards.
        trajectory_id: EMOSA only — writes per-trajectory file.
        output_dir: Output directory (default "outputs").

    Returns:
        JSON with child_variants_saved, variants_summary, loop_signal status.
    """
    import contextlib

    from compass.agents.review.models import (
        INITIAL_PARENT_VERSION,
        ChildVariant,
        LoopSignal,
        PromotionDecision,
        RankedCandidate,
        RegressionFlag,
    )
    from compass.agents.review.ops import (
        save_child_variants,
    )

    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    # --- Validate all inputs before touching state or disk ---
    parsed_variants: list[ChildVariant] = []
    if child_variants is not None:
        parsed_variants = [ChildVariant.model_validate(v) for v in child_variants]
    if loop_signal is not None:
        LoopSignal.model_validate(loop_signal)
    if candidate_ranking is not None:
        [RankedCandidate.model_validate(r) for r in candidate_ranking]
    if promotion_decisions is not None:
        [PromotionDecision.model_validate(p) for p in promotion_decisions]
    if regression_guards is not None:
        [RegressionFlag.model_validate(r) for r in regression_guards]

    # When decomposed params are provided, assemble and persist an audit ReviewResult.
    # When only review_result is provided, persist it as-is (legacy path).
    if review_result is None and any([candidate_ranking, promotion_decisions, regression_guards]):
        from compass.agents.review.ops import save_review_result

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
        from compass.agents.review.ops import save_review_result

        save_review_result(run_id, review_result, output_dir=out)

    result: dict[str, Any] = {}

    # Persist child variants.
    # EMOSA path (trajectory_id is not None): write per-trajectory file and record dispatch.
    # Single-slot path (trajectory_id is None): write the canonical child_variants.json sentinel.
    if child_variants is not None:
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

        # Cold-start: parent_version is infrastructure, not agent responsibility.
        # Coerce unconditionally so agents need not set it on round 0.
        if current_round == 0:
            parsed_variants = [v.model_copy(update={"parent_version": INITIAL_PARENT_VERSION}) for v in parsed_variants]
            if loop_signal is None:
                loop_signal = {"action": "refine", "reason": "cold_start_default"}

        if trajectory_id is not None:
            # EMOSA K-way fanout: use per-trajectory variant ids and file.
            from compass.agents.review.ops import (  # type: ignore[attr-defined]  # noqa: PLC0415
                record_trajectory_dispatched,  # pyright: ignore[reportAttributeAccessIssue]
                save_trajectory_child_variants,  # pyright: ignore[reportAttributeAccessIssue]
            )

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
async def query_holdout_examples(
    ctx: Context,
    run_id: str,
    route: str | None = None,
    example_ids: list[str] | None = None,
    offset: int = 0,
    limit: int = 20,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Refinement Loop -- Review] Query holdout examples by route or by ids.

    Returns full example objects from the holdout dataset including input text
    and per-route cost/quality data. Use this to find examples for specific
    routes when crafting few-shot example directives.

    Args:
        run_id: Pipeline run identifier.
        route: Filter by expected route name. Ignored when example_ids is set.
        example_ids: Filter to these specific example ids. Takes precedence over route.
        offset: Skip the first N matching examples (default 0). Use with limit for pagination.
        limit: Maximum number of examples to return (default 20).
        output_dir: Output directory (default "outputs").

    Returns:
        JSON object with an examples list.
    """
    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    holdout_path = out / run_id / "analysis" / "holdout.jsonl"
    if not holdout_path.exists():
        return json.dumps({"examples": [], "error": "holdout.jsonl not found"})

    return json.dumps(
        _query_jsonl_dataset(holdout_path, route=route, example_ids=example_ids, offset=offset, limit=limit)
    )


@mcp.tool()
async def query_dev_examples(
    ctx: Context,
    run_id: str,
    route: str | None = None,
    example_ids: list[str] | None = None,
    offset: int = 0,
    limit: int = 20,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Refinement Loop -- Review] Query dev examples by route or by ids.

    Returns full example objects from the dev dataset including input text
    and per-route cost/quality data. Use this when you need concrete dev-set
    rows without assuming dataset content is already in context.

    Args:
        run_id: Pipeline run identifier.
        route: Filter by expected route name. Ignored when example_ids is set.
        example_ids: Filter to these specific example ids. Takes precedence over route.
        offset: Skip the first N matching examples (default 0). Use with limit for pagination.
        limit: Maximum number of examples to return (default 20, capped server-side).
        output_dir: Output directory (default "outputs").

    Returns:
        JSON object with an examples list.
    """
    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    dev_path = out / run_id / "analysis" / "dev.jsonl"
    if not dev_path.exists():
        return json.dumps({"examples": [], "error": "dev.jsonl not found"})

    return json.dumps(_query_jsonl_dataset(dev_path, route=route, example_ids=example_ids, offset=offset, limit=limit))


@mcp.tool()
async def query_eval_results(
    ctx: Context,
    run_id: str,
    version: str,
    true_route: str | None = None,
    predicted_route: str | None = None,
    example_ids: list[str] | None = None,
    misroutes_only: bool = False,
    limit: int = 20,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Review] Return per-example eval rows joined with dev inputs.

    Args:
        run_id: Pipeline run identifier.
        version: Prompt version whose results.jsonl should be inspected.
        true_route: Filter by oracle route when paired with predicted_route.
        predicted_route: Filter by predicted route when paired with true_route.
        example_ids: Filter to these specific example ids. Takes precedence over other filters.
        misroutes_only: When true, include only rows where predicted_route != oracle_route.
        limit: Maximum number of rows to render (default 20, capped server-side at 50).
        output_dir: Output directory (default "outputs").

    Returns:
        Markdown detail for matching eval rows, joined with dev-set input text.
    """
    if limit <= 0:
        raise ToolError("limit must be > 0")
    if limit > _DATASET_QUERY_MAX_LIMIT:
        raise ToolError(f"limit must be <= {_DATASET_QUERY_MAX_LIMIT}")

    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    results_path = out / run_id / "eval" / version / "results.jsonl"
    if not results_path.exists():
        return (
            f"## Eval results — `{run_id}` / `{version}`\n\n"
            f"`results.jsonl` not found at `{results_path}`. "
            "Per-example eval inspection is only available after Stage 4 evaluation has completed."
        )

    dev_path = out / run_id / "analysis" / "dev.jsonl"
    if not dev_path.exists():
        return (
            f"## Eval results — `{run_id}` / `{version}`\n\n"
            f"`dev.jsonl` not found at `{dev_path}`. "
            "Per-example eval inspection requires Stage 2 (Data Analysis) artifacts."
        )

    dev_index: dict[str, dict[str, Any]] = {}
    for raw_line in dev_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        row_id = row.get("id")
        expected = row.get("expected", {})
        if not isinstance(row_id, str) or not isinstance(expected, dict):
            continue
        dev_index[row_id] = {
            "input": row.get("input", ""),
            "oracle_route": expected.get("route"),
            "routes": expected.get("routes", {}),
        }

    example_id_set = set(example_ids) if example_ids else None
    rows: list[dict[str, Any]] = []

    with results_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("__meta__"):
                continue
            try:
                result = EvalResult.model_validate(payload)
            except Exception:
                continue

            dev_row = dev_index.get(result.example_id)
            if dev_row is None or not isinstance(result.output, dict):
                continue

            oracle_route = dev_row.get("oracle_route")
            predicted = result.output.get("route")
            if not isinstance(oracle_route, str) or not isinstance(predicted, str):
                continue

            if example_id_set is not None:
                if result.example_id not in example_id_set:
                    continue
            elif true_route is not None and predicted_route is not None:
                if oracle_route != true_route or predicted != predicted_route:
                    continue
            elif misroutes_only and predicted == oracle_route:
                continue

            routes = dev_row.get("routes")
            predicted_metrics = routes.get(predicted, {}) if isinstance(routes, dict) else {}
            rows.append(
                {
                    "example_id": result.example_id,
                    "input": dev_row.get("input", ""),
                    "oracle_route": oracle_route,
                    "predicted_route": predicted,
                    "cost": result.cost,
                    "quality_score": predicted_metrics.get("quality_score"),
                }
            )
            if len(rows) >= limit:
                break

    lines = [f"## Eval results — `{run_id}` / `{version}`", "", f"### Rows ({len(rows)} shown)", ""]
    if not rows:
        lines.append("No matching eval results.")
        return "\n".join(lines)

    for row in rows:
        lines.append(f"**{row['example_id']}**")
        lines.append(f"- input: {_truncate_input_excerpt(str(row['input']))}")
        cost = row["cost"]
        quality = row["quality_score"]
        cost_str = f"{cost:.4f}" if isinstance(cost, float) else "—"
        quality_str = f"{quality:.4f}" if isinstance(quality, float) else "—"
        lines.append(
            f"- oracle_route: `{row['oracle_route']}` | predicted_route: `{row['predicted_route']}`"
            f" | cost: {cost_str} | quality_score: {quality_str}"
        )
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def get_prompt_text(
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
    from compass.prompts.manager import FilePromptManager

    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    for prompts_dir in (out / run_id / "prompts", project_dir / "prompts"):
        try:
            return FilePromptManager(prompts_dir).load(version)
        except FileNotFoundError:
            continue
    return json.dumps({"error": f"Prompt version '{version}' not found"})


@mcp.tool()
async def get_score_report(
    ctx: Context,
    run_id: str,
    version: str,
    top_k_errors: int = 30,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Review] Return a markdown ScoreReport for a candidate version.

    Args:
        run_id: Pipeline run identifier.
        version: Prompt version (e.g. "v3").
        top_k_errors: Max error rows to include (default 30).
        output_dir: Output directory (default "outputs").

    Returns:
        Markdown with metrics table, summary line, top-K errors, and diff if present.
    """
    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    report_path = out / run_id / "eval" / version / "report.json"
    if not report_path.exists():
        return f"No report found for version `{version}` at `{report_path}`."
    results_path = report_path.parent / "results.jsonl"
    try:
        data = _load_score_report_dict(report_path, results_path)
    except Exception as exc:
        return f"Failed to load report: {exc}"

    score_report = ScoreReport.model_validate(data)
    if top_k_errors < len(score_report.errors):
        score_report = score_report.model_copy(update={"errors": score_report.errors[:top_k_errors]})
    return render_score_report_md(score_report)


@mcp.tool()
async def get_confusion_cell(
    ctx: Context,
    run_id: str,
    true_route: str,
    predicted_route: str,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Review] Return markdown detail for a single confusion cell.

    Args:
        run_id: Pipeline run identifier.
        true_route: The ground-truth route label.
        predicted_route: The predicted route label.
        output_dir: Output directory (default "outputs").

    Returns:
        Markdown with cell-level confusion impact fields.
    """
    # Recompute via full briefing builder; slice out the matching cell.
    from compass.agents.prompt_builder.search_ops import get_search_state
    from compass.agents.review.ops import (
        load_cell_attempt_history,
        load_child_variants,
        load_historical_eval_reports,
    )
    from compass.agents.review.preprocessor import build_review_briefing as _build_review_briefing_impl
    from compass.agents.review.preprocessor import parse_user_targets
    from compass.prompts.manager import FilePromptManager

    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    try:
        state = get_search_state(run_id=run_id, output_dir=out)
    except FileNotFoundError:
        return "search_state.json not found — Stage 4 not initialised."

    from compass.agents.prompt_builder.search_ops import _load_pending

    pending = _load_pending(run_id, out)
    candidate_versions = [c.prompt_version for c in pending]
    parent_versions = {c.prompt_version: c.parent_version for c in pending}

    all_versions: set[str] = set(candidate_versions)
    for c in state.elite_set:
        all_versions.add(c.prompt_version)
    for p in parent_versions.values():
        if p:
            all_versions.add(p)

    historical = load_historical_eval_reports(run_id, state, output_dir=out)
    report_paths: dict[str, str] = {}
    for v in candidate_versions:
        rp = out / run_id / "eval" / v / "report.json"
        if rp.exists():
            report_paths[v] = str(rp)

    score_reports: dict[str, Any] = {}
    for v in all_versions:
        if v in report_paths:
            rp = Path(report_paths[v])
            if rp.exists():
                score_reports[v] = _load_score_report_dict(rp, rp.parent / "results.jsonl")
        elif v not in score_reports:
            for rd in historical.values():
                if v in rd:
                    synth = out / run_id / "eval" / v / "report.json"
                    synth_r = synth.parent / "results.jsonl"
                    row = rd[v]
                    _sk = {"errors", "diff", "report_path", "results_path"}
                    if _sk.issubset(row.keys()):
                        score_reports[v] = row
                    else:
                        from compass.eval.models import RunReport

                        rr = RunReport.model_validate(row)
                        from compass.eval.models import ScoreReport

                        score_reports[v] = ScoreReport.from_run_report(
                            report=rr, report_path=str(synth), results_path=str(synth_r), previous_report=None
                        ).model_dump(mode="json")
                    break

    run_prompts_dir = out / run_id / "prompts"
    project_prompts_dir = project_dir / "prompts"
    prompt_texts: dict[str, str] = {}
    for v in all_versions:
        for pd in (run_prompts_dir, project_prompts_dir):
            try:
                prompt_texts[v] = FilePromptManager(pd).load(v)
                break
            except FileNotFoundError:
                continue

    cv_list = load_child_variants(run_id, output_dir=out) or None

    routing_context = None
    rc_path = out / run_id / "validation" / "routing_context.json"
    if rc_path.exists():
        from compass.agents.routing_context import RoutingContext

        routing_context = RoutingContext.model_validate_json(rc_path.read_text(encoding="utf-8"))

    user_targets = None
    ir_path = out / run_id / "validation" / "input_report.md"
    if ir_path.exists():
        user_targets = parse_user_targets(ir_path.read_text(encoding="utf-8"))

    full_oracle: dict[str, float] | None = None
    op = out / run_id / "eval" / "oracle_metrics.json"
    if op.exists():
        full_oracle = json.loads(op.read_text(encoding="utf-8"))

    dev_oracle: dict[str, float] | None = None
    dop = out / run_id / "eval" / "dev_oracle_metrics.json"
    if dop.exists():
        dev_oracle = json.loads(dop.read_text(encoding="utf-8"))

    eval_results = None
    examples = None
    selected = _select_confusion_candidates(state)
    if selected:
        from compass.eval.models import EvalResult, Example

        all_er: list[EvalResult] = []
        for v in selected:
            rsp = out / run_id / "eval" / v / "results.jsonl"
            if rsp.exists():
                for line in rsp.read_text(encoding="utf-8").splitlines():
                    s = line.strip()
                    if not s:
                        continue
                    try:
                        row2 = json.loads(s)
                    except json.JSONDecodeError:
                        continue
                    if row2.get("__meta__"):
                        continue
                    try:
                        all_er.append(EvalResult.model_validate(row2))
                    except Exception:
                        continue
        if all_er:
            eval_results = all_er
        dev_p = out / run_id / "analysis" / "dev.jsonl"
        if dev_p.exists():
            loaded: list[Example] = []
            for line in dev_p.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s:
                    continue
                try:
                    loaded.append(Example.model_validate_json(s))
                except Exception:
                    continue
            if loaded:
                examples = loaded

    cell_hist = load_cell_attempt_history(run_id, output_dir=out)

    briefing = _build_review_briefing_impl(
        search_state=state,
        score_reports=score_reports,
        historical_reports=historical,
        prompt_texts=prompt_texts,
        candidate_versions=candidate_versions,
        parent_versions=parent_versions,
        routing_context=routing_context,
        child_variants=cv_list,
        pending_candidates=pending,
        user_targets=user_targets,
        full_dataset_oracle=full_oracle,
        dev_oracle=dev_oracle,
        eval_results=eval_results,
        examples=examples,
        run_dir=out / run_id,
        cell_attempt_history=cell_hist or None,
    )

    cell = next(
        (c for c in briefing.confusion_analysis if c.true_route == true_route and c.predicted_route == predicted_route),
        None,
    )
    if cell is None:
        return f"No confusion cell found for `{true_route}` → `{predicted_route}`."

    lines = [
        f"## Confusion cell: `{true_route}` → `{predicted_route}`",
        "",
        f"- count: {cell.count}",
        f"- support: {cell.support}",
        f"- misroute_rate: {cell.misroute_rate:.3f}",
        f"- quality_impact: {cell.quality_impact:.3f}",
        f"- cost_impact: {cell.cost_impact:.3f}",
        f"- persistence_rate: {cell.persistence_rate:.3f}",
        f"- attempt_count: {cell.attempt_count}",
        f"- failed_attempt_count: {cell.failed_attempt_count}",
        f"- best_outcome: {cell.best_outcome}",
        f"- effective_impact: {cell.effective_impact:.3f}",
    ]
    return "\n".join(lines)


@mcp.tool()
async def get_directive_history(
    ctx: Context,
    run_id: str,
    since_round: int | None = None,
    limit: int = 20,
    output_dir: str = "outputs",
) -> str:
    """Deprecated. This tool no longer returns historical directive outcomes.

    Replacement paths:
    - recent directive outcomes appear in `build_review_briefing` under the
      section starting with `## Last round directives & outcomes`
    - per-version score detail remains available via `get_score_report`
    """
    return _DEPRECATED_REVIEW_HISTORY_MESSAGE.format(tool_name="get_directive_history")


@mcp.tool()
async def get_batch_outcomes(
    ctx: Context,
    run_id: str,
    round: int | None = None,
    output_dir: str = "outputs",
) -> str:
    """Deprecated. This tool no longer returns historical batch outcomes.

    Replacement paths:
    - recent directive outcomes appear in `build_review_briefing` under the
      section starting with `## Last round directives & outcomes`
    - per-version score detail remains available via `get_score_report`
    """
    return _DEPRECATED_REVIEW_HISTORY_MESSAGE.format(tool_name="get_batch_outcomes")


@mcp.tool()
async def get_round_child_variants(
    ctx: Context,
    run_id: str,
    round: int,
    with_directive_bodies: bool = False,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Review] Return markdown of child variants for a specific round.

    Args:
        run_id: Pipeline run identifier.
        round: Round number to load child variants for.
        with_directive_bodies: Include full directive text (default False).
        output_dir: Output directory (default "outputs").

    Returns:
        Markdown grouped by variant_id with directives listed.
    """
    from compass.agents.review.ops import (
        load_child_variants,
    )

    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    variants = load_child_variants(run_id, output_dir=out)

    if not variants:
        return f"No child variants found for run `{run_id}`."

    lines = [f"## Child variants — round {round}", ""]
    for cv in variants:
        vid = cv.variant_id or "(unassigned)"
        hyp = cv.hypothesis or "(no hypothesis)"
        lines.append(f"### `{vid}`")
        lines.append(f"**hypothesis:** {hyp}")
        lines.append("")
        if cv.parent_version:
            lines.append(f"parent: `{cv.parent_version}`")
        if cv.target_confusion_cell:
            lines.append(f"target_confusion_cell: `{cv.target_confusion_cell}`")
        lines.append("")
        lines.append("**directives:**")
        for d in cv.directives:
            if with_directive_bodies:
                lines.append(f"- `{d.directive_id}` [{d.block_type}] ({d.priority}): {d.directive}")
            else:
                lines.append(f"- `{d.directive_id}` [{d.block_type}] ({d.priority})")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def get_dataset_oracle_distribution(
    ctx: Context,
    run_id: str,
    route: str | None = None,
    example_ids: list[str] | None = None,
    limit: int = 50,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Review] Return per-route oracle distribution aggregates and optional row-level detail.

    Args:
        run_id: Pipeline run identifier.
        route: Filter row-level output to examples whose oracle_route matches this value.
        example_ids: Filter row-level output to these specific example ids (takes precedence over route).
        limit: Maximum number of rows to include in the rows section (default 50).
        output_dir: Output directory (default "outputs").

    Returns:
        Markdown with aggregates table and (when filtered) row-level cost/quality detail.
    """
    from collections import defaultdict

    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    dev_path = out / run_id / "analysis" / "dev.jsonl"
    if not dev_path.exists():
        return (
            f"## Oracle distribution — `{run_id}`\n\n"
            f"`dev.jsonl` not found at `{dev_path}`. "
            "Oracle distribution is only available after Stage 2 (Data Analysis) has completed."
        )

    # Parse all rows
    raw_rows: list[dict[str, Any]] = []
    for line in dev_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            raw_rows.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue

    if not raw_rows:
        return f"## Oracle distribution — `{run_id}`\n\n`dev.jsonl` is empty."

    # --- Aggregates (always computed) ---
    route_n: dict[str, int] = defaultdict(int)
    route_costs: dict[str, list[float]] = defaultdict(list)
    route_qualities: dict[str, list[float]] = defaultdict(list)
    pareto_counts: dict[str, int] = defaultdict(int)
    ties_cheaper: dict[str, int] = defaultdict(int)

    for row in raw_rows:
        expected = row.get("expected", {})
        oracle_route = expected.get("route", "")
        routes_data: dict[str, Any] = expected.get("routes", {})
        if not oracle_route or not routes_data:
            continue

        route_n[oracle_route] += 1
        oracle_entry = routes_data.get(oracle_route, {})
        oracle_cost = oracle_entry.get("cost") or 0.0
        oracle_quality = oracle_entry.get("quality_score") or 0.0
        route_costs[oracle_route].append(oracle_cost)
        route_qualities[oracle_route].append(oracle_quality)

        # Pareto: oracle_route is pareto-optimal if no other route strictly dominates it
        # (lower cost AND >= quality, with at least one strict)
        is_pareto = True
        for r_name, r_entry in routes_data.items():
            if r_name == oracle_route:
                continue
            r_cost = r_entry.get("cost") or 0.0
            r_quality = r_entry.get("quality_score") or 0.0
            if (
                r_cost <= oracle_cost
                and r_quality >= oracle_quality
                and (r_cost < oracle_cost or r_quality > oracle_quality)
            ):
                is_pareto = False
                break
        if is_pareto:
            pareto_counts[oracle_route] += 1

        # Ties with cheaper: a cheaper route ties or exceeds oracle quality
        for r_name, r_entry in routes_data.items():
            if r_name == oracle_route:
                continue
            r_cost = r_entry.get("cost") or 0.0
            r_quality = r_entry.get("quality_score") or 0.0
            if r_cost < oracle_cost and r_quality >= oracle_quality:
                ties_cheaper[oracle_route] += 1
                break

    all_routes = sorted(set(route_n.keys()))

    lines: list[str] = [f"## Oracle distribution — `{run_id}`", ""]
    lines += [
        "### Aggregates",
        "",
        "| route | n_labeled | mean_oracle_cost | mean_oracle_quality"
        " | pareto_optimal_count | ties_with_cheaper_route_count |",
        "|---|---|---|---|---|---|",
    ]
    for r in all_routes:
        n = route_n[r]
        mean_cost = sum(route_costs[r]) / n if n else 0.0
        mean_qual = sum(route_qualities[r]) / n if n else 0.0
        pareto = pareto_counts.get(r, 0)
        ties = ties_cheaper.get(r, 0)
        lines.append(f"| {r} | {n} | {mean_cost:.4f} | {mean_qual:.4f} | {pareto} | {ties} |")

    # --- Row-level detail (only when filtered) ---
    if example_ids is not None or route is not None:
        example_id_set = set(example_ids) if example_ids else None

        filtered: list[dict[str, Any]] = []
        for row in raw_rows:
            row_id = row.get("id", "")
            expected = row.get("expected", {})
            oracle_route = expected.get("route", "")
            if example_id_set is not None:
                if row_id in example_id_set:
                    filtered.append(row)
            else:
                if oracle_route == route:
                    filtered.append(row)
            if len(filtered) >= limit:
                break

        lines += ["", f"### Rows ({len(filtered)} shown)", ""]
        for row in filtered:
            row_id = row.get("id", "?")
            expected = row.get("expected", {})
            oracle_route_val = expected.get("route", "?")
            routes_data = expected.get("routes", {})
            lines.append(f"**{row_id}** — oracle_route: `{oracle_route_val}`")
            lines.append("")
            lines.append("| route | cost | quality_score |")
            lines.append("|---|---|---|")
            for r_name in sorted(routes_data.keys()):
                r_entry = routes_data[r_name]
                r_cost = r_entry.get("cost", "—")
                r_qual = r_entry.get("quality_score", "—")
                cost_str = f"{r_cost:.4f}" if isinstance(r_cost, float) else str(r_cost)
                qual_str = f"{r_qual:.4f}" if isinstance(r_qual, float) else str(r_qual)
                lines.append(f"| {r_name} | {cost_str} | {qual_str} |")
            lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def get_per_class_recall(
    ctx: Context,
    run_id: str,
    round_id: int | None = None,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Review] Return the full per-class recall table for all routes without filtering.

    Use this when the briefing footer indicates routes were hidden from the summary view.

    Args:
        run_id: Pipeline run identifier.
        round_id: Round number to use (default: latest round from search state).
        output_dir: Output directory (default "outputs").

    Returns:
        Markdown table with all routes: route | recall | support | trend (last 3) | regression.
    """
    from compass.agents.prompt_builder.search_ops import get_search_state
    from compass.agents.review.ops import load_historical_eval_reports
    from compass.agents.review.preprocessor import extract_per_class_recall

    project_dir = await _resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    try:
        state = get_search_state(run_id=run_id, output_dir=out)
    except FileNotFoundError:
        return "search_state.json not found — Stage 4 not initialised."

    current_round = round_id if round_id is not None else state.round
    historical = load_historical_eval_reports(run_id, state, output_dir=out)

    # Build current round reports from pending candidates + elite set
    pending = _load_pending(run_id, out)
    candidate_versions = [c.prompt_version for c in pending]
    all_versions: set[str] = set(candidate_versions)
    for c in state.elite_set:
        all_versions.add(c.prompt_version)

    import contextlib

    current_reports: dict[str, Any] = {}
    for version in all_versions:
        rp = out / run_id / "eval" / version / "report.json"
        if rp.exists():
            with contextlib.suppress(Exception):
                current_reports[version] = _load_score_report_dict(rp, rp.parent / "results.jsonl")
        else:
            for rd in historical.values():
                if version in rd:
                    current_reports[version] = rd[version]
                    break

    per_class_recall = extract_per_class_recall(
        current_reports=current_reports,
        historical_reports=historical,
        current_round=current_round,
    )

    if not per_class_recall:
        return f"## Full per-class recall — `{run_id}` round {current_round}\n\nNo recall data available."

    lines = [
        f"## Full per-class recall — `{run_id}` round {current_round}",
        "",
        "| route | recall | support | trend (last 3) | regression |",
        "|---|---|---|---|---|",
    ]
    for route, entry in sorted(per_class_recall.items()):
        trend_str = " → ".join(f"{v:.2f}" for v in entry.trend[-3:]) if entry.trend else "—"
        lines.append(f"| {route} | {entry.recall:.3f} | {entry.support} | {trend_str} | {entry.regression_flag} |")
    return "\n".join(lines)
