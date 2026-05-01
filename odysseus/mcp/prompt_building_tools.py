"""Prompt building tools — search state, candidates, eval, holdout filter."""

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

import odysseus.project_dir as _project_dir_mod
from odysseus.agents.eval_runner import EvalRunnerAgent
from odysseus.agents.pipeline.dispatch import clear_build_dispatched, record_build_dispatched
from odysseus.agents.pipeline.guards import check_artifacts
from odysseus.agents.prompt_builder.search import SearchState
from odysseus.agents.prompt_builder.search_ops import (
    advance_round,
    advance_round_sms_emoa,
    advance_warmup_batch,
    get_search_state,
    init_search_state,
    record_eval_result,
    register_candidate,
)
from odysseus.eval.backends.registry import BackendRegistry
from odysseus.eval.models import MetricConfig, OutputConfig, RunConfig, ScoreReport
from odysseus.mcp.server import mcp


def build_pipeline_config(
    state: SearchState,
    prompt_version: str,
    data_source: str,
    run_id: str,
    project_dir: Path,
    eval_subdir: str = "eval",
) -> RunConfig:
    """Build a RunConfig from pipeline state — no YAML file needed."""
    metrics: list[MetricConfig] = [
        MetricConfig(name="accuracy"),
        MetricConfig(name="confusion"),
        MetricConfig(name="f1"),
        MetricConfig(name="cost_quality_change"),
    ]
    if state.primary_metric_name:
        metric_name = state.primary_metric_name.split("/")[0]
        if metric_name not in ("accuracy", "confusion", "f1"):
            params = {}
            if "/" in state.primary_metric_name:
                params["average"] = state.primary_metric_name.split("/", 1)[1]
            metrics.append(MetricConfig(name=metric_name, params=params))

    eval_dir = project_dir / "outputs" / run_id / eval_subdir / prompt_version
    output = OutputConfig(
        results_path=str(eval_dir / "results.jsonl"),
        report_path=str(eval_dir / "report.json"),
    )

    return RunConfig(
        backend=state.backend,
        prompt_version=prompt_version,
        data_source=data_source,
        metrics=metrics,
        output=output,
    )


@mcp.tool()
async def init_search_state_tool(
    ctx: Context,
    run_id: str,
    backend: str,
    max_rounds: int = 50,
    stagnation_limit: int = 3,
    convergence_limit: int = 5,
    primary_metric_name: str | None = None,
) -> str:
    """[Stage 4: Refinement Loop] Initialise a new prompt-builder search state.

    The search algorithm is hardcoded per branch via ``_BRANCH_ALGORITHM`` in
    ``search_ops.py``; callers pass only ``run_id``, ``backend``, and optional
    max-rounds knobs.

    Args:
        run_id: Pipeline run identifier.
        backend: Backend identifier (e.g. "anthropic", "openai").
        max_rounds: Maximum number of search rounds before forced convergence.
        stagnation_limit: Stagnation rounds before switching to exploratory mode.
        convergence_limit: Stagnation rounds that trigger convergence.
        primary_metric_name: Optional name of the primary quality metric.

    Returns:
        JSON-serialized SearchState for the new search run.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    check_artifacts(
        project_dir / "outputs" / run_id / "analysis" / "dev.jsonl",
        stage=4,
        stage_name="Refinement Loop",
        hint="Complete data validation and dataset split first.",
    )

    state = init_search_state(
        backend=backend,
        run_id=run_id,
        max_rounds=max_rounds,
        stagnation_limit=stagnation_limit,
        convergence_limit=convergence_limit,
        primary_metric_name=primary_metric_name,
    )
    return state.model_dump_json(indent=2)


@mcp.tool()
async def register_candidate_tool(
    run_id: str,
    prompt_version: str,
    parent_version: str | None = None,
    example_ids: list[str] | None = None,
) -> str:
    """[Stage 4: Refinement Loop] Register a new candidate prompt version for the current search round.

    Also writes ``build_dispatched.json`` so that ``complete_stage(prompt_building)``
    knows a Prompt Builder sub-agent is in-flight.  The marker is cleared by
    ``advance_step_tool`` when the round is complete.

    Args:
        run_id: Pipeline run identifier.
        prompt_version: Unique version identifier for the new prompt candidate.
        parent_version: Parent prompt version, if any. Round-1 / cold-start candidates
            use the canonical "base" (matches ReviewBriefing.initial_parent_version).
        example_ids: Holdout example IDs used as few-shots in this prompt version (backend tracking only).

    Returns:
        JSON object confirming the registered prompt version.
    """
    try:
        state = register_candidate(
            run_id=run_id,
            prompt_version=prompt_version,
            parent_version=parent_version,
            example_ids=example_ids,
        )
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    # Record that the Prompt Builder is now in-flight for this round.
    record_build_dispatched(run_id, round=state.round)
    return json.dumps({"registered": prompt_version})


@mcp.tool()
async def run_eval(
    ctx: Context,
    prompt_version: str,
    backend: str = "",
    config_path: str = "outputs/run_config.yaml",
    run_id: str | None = None,
) -> str:
    """[Stage 4: Refinement Loop] Run an evaluation of a prompt version against the dev dataset.

    The dev dataset path is hardcoded to ``outputs/<run_id>/analysis/dev.jsonl``
    for pipeline runs.  Standalone runs read ``data_source`` from the YAML config.

    Args:
        prompt_version: Prompt version identifier (e.g. "v3", "latest").
        backend: Backend label. Optional for pipeline runs (resolved from search state).
        config_path: Path to YAML config. Ignored for pipeline runs.
        run_id: Pipeline run identifier. When provided, config is built
                from pipeline state instead of reading a YAML file.

    Returns:
        JSON object with report_path and results_path pointing to
        the full evaluation output on disk, OR an action_required
        object on first run.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)

    run_config: RunConfig | None = None
    data_source: str | None = None
    if run_id is not None:
        check_artifacts(
            project_dir / "outputs" / run_id / "analysis" / "dev.jsonl",
            stage=4,
            stage_name="Refinement Loop",
            hint="Complete data validation and dataset split first.",
        )

        # Hardcode dev split — agents cannot choose the dataset
        data_source = str(project_dir / "outputs" / run_id / "analysis" / "dev.jsonl")

        state = get_search_state(run_id=run_id)

        # Pre-flight: signal backend setup needed when backend is missing
        if not state.backend:
            registry = BackendRegistry.from_directory(project_dir / "backends")
            return json.dumps(
                {
                    "action_required": "backend_setup",
                    "run_id": run_id,
                    "available_backends": registry.list_profiles(),
                }
            )

        # Build config from pipeline state
        run_config = build_pipeline_config(
            state=state,
            prompt_version=prompt_version,
            data_source=data_source,
            run_id=run_id,
            project_dir=project_dir,
        )

    agent = EvalRunnerAgent()
    context: dict[str, Any] = {
        "prompt_version": prompt_version,
        "backend": run_config.backend if run_config else backend,
        "run_id": run_id,
    }
    if data_source is not None:
        context["data_source"] = data_source
    if run_config is not None:
        context["run_config"] = run_config
    else:
        context["config_path"] = config_path

    result = await agent.run(context)

    if "error" in result:
        err = result["error"]
        raise ToolError(f"run_eval failed: [{err['category']}] {err['detail']}")

    score_report: ScoreReport = result[ScoreReport.CONTEXT_KEY]
    return json.dumps(
        {
            "report_path": score_report.report_path,
            "results_path": score_report.results_path,
            "metrics": score_report.metrics,
            "summary": score_report.summary.model_dump(mode="json"),
        }
    )


@mcp.tool()
async def run_batch_eval(
    ctx: Context,
    run_id: str,
    candidates: list[dict],
) -> str:
    """[Stage 4] Evaluate multiple prompt candidates concurrently.

    Each entry in `candidates` is a dict with keys:
      - prompt_version: str
      - parent_version: str | None (default None)
      - example_ids: list[str] (default [])

    Returns a JSON-serialised BatchEvalResult with `succeeded` and
    `failed` lists. Per-candidate failures land in `failed`; only
    programming errors raise.

    Recovery mode (calling with `candidates=[]`) is wired in commit 4.
    """
    # Lazy import to avoid circular dependency:
    # batch_eval imports build_pipeline_config from this module.
    from odysseus.eval.batch_eval import BatchEvalCandidate, run_batch_eval_impl

    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    output_dir = project_dir / "outputs"
    try:
        parsed = [BatchEvalCandidate.model_validate(c) for c in candidates]
        result = await run_batch_eval_impl(run_id, parsed, output_dir=output_dir)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    except Exception as exc:
        raise ToolError(f"run_batch_eval failed: {type(exc).__name__}: {exc}") from exc
    return result.model_dump_json()


@mcp.tool()
async def record_eval_result_tool(
    run_id: str,
    prompt_version: str,
    quality_score: float,
    cost: float,
) -> str:
    """[Stage 4: Refinement Loop] Record evaluation results for a pending candidate.

    Args:
        run_id: Pipeline run identifier.
        prompt_version: Version identifier of the candidate being evaluated.
        quality_score: Evaluation quality score.
        cost: Evaluation cost.

    Returns:
        JSON object with prompt_version, quality_score, and cost.
    """
    try:
        result = record_eval_result(
            run_id=run_id,
            prompt_version=prompt_version,
            quality_score=quality_score,
            cost=cost,
        )
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return json.dumps(result)


def _advance_hill_climb(run_id: str) -> str:
    """Hill-climb arm of advance_step_tool.

    Processes all pending candidates, updates the Pareto front, adjusts
    stagnation tracking, and checks for convergence.  Returns a
    JSON-serialized RoundSummary.

    Also clears the build-dispatch marker so the orchestrator knows the
    Prompt Builder sub-agent has finished.
    """
    try:
        summary = advance_round(run_id=run_id)
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    # Round is complete — clear the in-flight marker so complete_stage can proceed.
    clear_build_dispatched(run_id)
    return summary.model_dump_json(indent=2)


def _advance_sms_emoa(run_id: str) -> str:
    """SMS-EMOA arm of advance_step_tool.

    Dispatches to ``advance_warmup_batch`` or ``advance_round_sms_emoa``
    depending on ``state.loop_phase``:

    - ``"warmup_reduce"`` → ``advance_warmup_batch``
    - ``"review"`` or ``"build"`` → ``advance_round_sms_emoa``
    - Any other phase → ``ValueError`` (defensive guard).

    Returns a JSON-serialized RoundSummary and clears the build-dispatch marker.
    """
    from odysseus.agents.prompt_builder.search_ops import _default_output_dir, _load_state

    output_dir = _default_output_dir()
    try:
        state = _load_state(run_id, output_dir)
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc

    loop_phase = state.loop_phase
    try:
        if loop_phase == "warmup_reduce":
            summary = advance_warmup_batch(run_id=run_id)
        elif loop_phase in ("review", "build"):
            summary = advance_round_sms_emoa(run_id=run_id)
        else:
            raise ValueError(
                f"_advance_sms_emoa: unsupported loop_phase '{loop_phase}' — "
                f"expected 'warmup_reduce', 'review', or 'build'"
            )
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise ToolError(str(exc)) from exc

    clear_build_dispatched(run_id)
    return summary.model_dump_json(indent=2)


@mcp.tool()
async def advance_step_tool(run_id: str) -> str:
    """[Stage 4: Refinement Loop] Advance the search loop by one step.

    Dispatches to the strategy-specific advance logic determined by the
    ``algorithm`` field of the current SearchState.  Both ``"hill_climb"``
    and ``"sms_emoa"`` are implemented on this branch; ``"beam"`` and
    ``"emosa"`` still raise NotImplementedError and will be wired when their
    feature branches land.

    Args:
        run_id: Pipeline run identifier.

    Returns:
        JSON-serialized RoundSummary for the completed round.
    """
    try:
        state = get_search_state(run_id=run_id)
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc

    algorithm = state.algorithm
    if algorithm == "hill_climb":
        return _advance_hill_climb(run_id)
    elif algorithm == "sms_emoa":
        return _advance_sms_emoa(run_id)

    raise NotImplementedError(f"advance_step_tool: algorithm '{algorithm}' not implemented on this branch")


@mcp.tool()
async def get_search_state_tool(run_id: str) -> str:
    """[Stage 4: Refinement Loop] Load and return the current search state.

    Args:
        run_id: Pipeline run identifier.

    Returns:
        JSON-serialized SearchState.
    """
    try:
        state = get_search_state(run_id=run_id)
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    return state.model_dump_json(indent=2)


@mcp.tool()
async def save_prompt_tool(
    ctx: Context,
    run_id: str,
    prompt_version: str,
    content: str,
) -> str:
    """[Stage 4: Refinement Loop] Save a compiled routing prompt to disk.

    Writes the prompt content to outputs/<run_id>/prompts/<prompt_version>.txt.
    Use this instead of writing prompt files directly — it ensures correct
    encoding and avoids content truncation from special characters.

    Args:
        run_id: Pipeline run identifier.
        prompt_version: Version identifier (e.g. "v1", "v2").
        content: Full prompt text to save.

    Returns:
        JSON object with prompt_path pointing to the written file.
    """
    if not content:
        raise ToolError("content must not be empty")

    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    prompt_path = project_dir / "outputs" / run_id / "prompts" / f"{prompt_version}.txt"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(content, encoding="utf-8")

    return json.dumps({"prompt_path": str(prompt_path)})


@mcp.tool()
async def get_child_variants_tool(
    ctx: Context,
    run_id: str,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Refinement Loop] Retrieve the Review Agent's child variants for the current round.

    Returns the list of ChildVariant objects persisted by the Review Agent
    via record_directive_outcomes_tool. Each variant specifies a parent version
    and the directives to apply together as one child prompt.

    Args:
        run_id: Pipeline run identifier.
        output_dir: Output directory (default "outputs").

    Returns:
        JSON-serialized list of ChildVariant objects.
    """
    from odysseus.agents.review.ops import load_child_variants

    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir
    variants = load_child_variants(run_id, output_dir=out)

    # Dedup: if secondary version matches primary, set to None
    variants = [
        v.model_copy(update={"secondary_parent_version": None})
        if v.secondary_parent_version is not None and v.secondary_parent_version == v.parent_version
        else v
        for v in variants
    ]

    return json.dumps([v.model_dump(mode="json") for v in variants], indent=2)


@mcp.tool()
async def get_edit_directives_tool(
    ctx: Context,
    run_id: str,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Refinement Loop] Retrieve flattened edit directives across all child variants.

    Flattens directives from all ChildVariant objects persisted by the Review
    Agent via record_directive_outcomes_tool. This is a back-compat helper for
    callers that need a flat directive list. Callers that need per-variant
    grouping (e.g. the Prompt Builder compiling one prompt per variant) should
    use get_child_variants_tool instead.

    Args:
        run_id: Pipeline run identifier.
        output_dir: Output directory (default "outputs").

    Returns:
        JSON-serialized flat list of EditDirective objects across all child variants.
    """
    from odysseus.agents.review.ops import load_child_variants

    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir
    variants = load_child_variants(run_id, output_dir=out)
    directives = [d for v in variants for d in v.directives]
    return json.dumps([d.model_dump(mode="json") for d in directives], indent=2)


@mcp.tool()
async def signal_eval_complete_tool(
    ctx: Context,
    run_id: str,
    output_dir: str = "outputs",
) -> str:
    """[Stage 4: Refinement Loop] Deprecated back-compat shim.

    Eval-complete is now signaled automatically when the Prompt Builder calls
    ``advance_step_tool``, which clears the build-dispatch marker and flips
    ``loop_phase`` to ``"review"``.

    Retained for back-compat: calling this tool clears the build-dispatch
    marker and flips ``loop_phase`` to ``"review"`` if they have not already
    been cleared/flipped.  This prevents deadlock in pipelines that were
    paused mid-run before the automated marker clearing was deployed.

    Args:
        run_id: Pipeline run identifier.
        output_dir: Output directory (default "outputs").

    Returns:
        JSON object with ``deprecated=true`` and the resulting ``loop_phase``.
    """
    from odysseus.agents.prompt_builder.search_ops import _load_state, _save_state

    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    out = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir

    clear_build_dispatched(run_id, output_dir=out)
    try:
        state = _load_state(run_id, out)
        if state.loop_phase == "build":
            updated = state.model_copy(update={"loop_phase": "review"})
            _save_state(run_id, updated, out)
    except FileNotFoundError:
        pass
    return json.dumps({"deprecated": True, "loop_phase": "review"})
