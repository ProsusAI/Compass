"""Prompt building tools — search state, candidates, eval, holdout filter."""

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

import odysseus.project_dir as _project_dir_mod
from odysseus.agents.eval_runner import EvalRunnerAgent
from odysseus.agents.pipeline.guards import check_artifacts
from odysseus.agents.prompt_builder.search import SearchState
from odysseus.agents.prompt_builder.search_ops import (
    advance_round,
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
        MetricConfig(name="cost_quality_reduction"),
    ]
    if state.primary_metric_name:
        metric_name = state.primary_metric_name.split("/")[0]
        if metric_name != "accuracy":
            params = {}
            if "/" in state.primary_metric_name:
                params["average"] = state.primary_metric_name.split("/", 1)[1]
            metrics.append(MetricConfig(name=metric_name, params=params))

    eval_dir = project_dir / "outputs" / run_id / eval_subdir
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
) -> str:
    """[Stage 4: Refinement Loop] Register a new candidate prompt version for the current search round.

    Args:
        run_id: Pipeline run identifier.
        prompt_version: Unique version identifier for the new prompt candidate.
        parent_version: Parent prompt version, if any.

    Returns:
        JSON object confirming the registered prompt version.
    """
    try:
        register_candidate(
            run_id=run_id,
            prompt_version=prompt_version,
            parent_version=parent_version,
        )
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
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


@mcp.tool()
async def advance_round_tool(run_id: str) -> str:
    """[Stage 4: Refinement Loop] Advance the search loop by one round.

    Processes all pending candidates, updates the Pareto front, adjusts
    stagnation tracking, and checks for convergence.

    Args:
        run_id: Pipeline run identifier.

    Returns:
        JSON-serialized RoundSummary for the completed round.
    """
    try:
        summary = advance_round(run_id=run_id)
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return summary.model_dump_json(indent=2)


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
