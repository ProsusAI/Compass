"""Orchestrator tools — pipeline entry point and status."""

import json

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

import odysseus.project_dir as _project_dir_mod
from odysseus.agents.pipeline.guards import check_artifacts  # noqa: F401
from odysseus.agents.pipeline.status import get_pipeline_status as _get_pipeline_status
from odysseus.mcp.server import (
    _STAGE_PROMPT_MAP,
    STAGE_REGISTRY,
    _load_text,
    get_active_stage,
    mcp,
    set_active_stage,
)


@mcp.tool()
async def optimize_routing_prompt(ctx: Context) -> str:
    """Start the Odysseus routing prompt optimization pipeline.

    This is the pipeline entry-point tool for orchestrators; it is not a
    stage sub-agent tool. Returns pipeline status and the stage system prompt.
    Call `get_pipeline_status` to determine next action after this call.
    """
    try:
        system_prompt = _load_text("odysseus/agents/prompts/user_input_system.md")
    except FileNotFoundError as e:
        raise ToolError(f"User Input Agent system prompt not found — MCP server installation may be broken: {e}") from e

    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    outputs_dir = project_dir / "outputs"

    try:
        status = _get_pipeline_status(outputs_dir=outputs_dir, run_id=None, project_dir=project_dir)
    except Exception as e:
        raise ToolError(f"Failed to read pipeline status from {outputs_dir}: {e}") from e

    status_json = json.dumps(status, indent=2)

    return (
        f"<pipeline_status>\n{status_json}\n</pipeline_status>\n\n"
        f"<instructions>\n"
        f"You are now operating as the User Input Agent for the Odysseus pipeline.\n"
        f"The pipeline status above has already been checked — use it to decide whether\n"
        f"to greet the user for a fresh run or surface existing runs and offer to bootstrap.\n"
        f"Follow your system prompt below exactly.\n"
        f"</instructions>\n\n"
        f"<system_prompt>\n{system_prompt}\n</system_prompt>"
    )


@mcp.tool()
async def get_pipeline_status(ctx: Context, run_id: str | None = None) -> str:
    """Check pipeline progress and get guidance on the next step.

    Call this at any time. Accepts optional run_id; if omitted, uses the
    most recent pipeline run.

    The response includes a ``subagent_instruction`` field. If it is non-null,
    you MUST spawn a sub-agent with that instruction before calling any tools
    for the current stage. The instruction names the MCP prompt to activate and
    lists the tools the sub-agent may call. Do not call stage tools yourself.

    After the sub-agent exits, call this tool again to verify stage completion
    and receive the next instruction.

    Args:
        run_id: Optional pipeline run identifier.

    Returns:
        JSON object with stage checklist, current stage, next action, and
        subagent_instruction (non-null when a sub-agent must be spawned).
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    outputs_dir = project_dir / "outputs"
    result = _get_pipeline_status(outputs_dir=outputs_dir, run_id=run_id, project_dir=project_dir)
    current_stage = result.get("current_stage")
    activate_prompt = result.get("activate_prompt")
    subagent_instruction = result.get("subagent_instruction")

    # For Stage 6, look up system prompt by activate_prompt name (dynamic per loop_phase).
    # For all other stages, look up by stage number.
    lookup_key: int | str | None = activate_prompt if current_stage == 6 and activate_prompt else current_stage

    if lookup_key in _STAGE_PROMPT_MAP and subagent_instruction:
        placeholder = "<stage_system_prompt></stage_system_prompt>"
        if placeholder in subagent_instruction:
            try:
                system_prompt = _load_text(_STAGE_PROMPT_MAP[lookup_key])
                result["subagent_instruction"] = subagent_instruction.replace(
                    placeholder,
                    f"<stage_system_prompt>\n{system_prompt}\n</stage_system_prompt>",
                )
            except FileNotFoundError as e:
                raise ToolError(
                    f"Stage {current_stage} system prompt not found — MCP server installation may be broken: {e}"
                ) from e
    return json.dumps(result, indent=2)


@mcp.tool()
async def start_stage(stage: str, run_id: str | None = None) -> str:  # noqa: ARG001
    """Activate a pipeline stage, scoping visible tools to that stage.

    The orchestrator calls this before spawning a sub-agent so the sub-agent
    only sees the tools relevant to its stage.  After the sub-agent finishes,
    call ``complete_stage`` to return to orchestrator scope.

    Args:
        stage: Stage name — must be a key in ``STAGE_REGISTRY``.
        run_id: Pipeline run identifier. Optional for the ``input_report``
            stage (which creates the run_id); required for all other stages.

    Returns:
        Confirmation message listing the tools now available.
    """
    current = get_active_stage()
    if current != "orchestrator":
        raise ToolError(
            f"start_stage can only be called from orchestrator scope "
            f"(current scope: '{current}'). Call complete_stage first."
        )

    if stage not in STAGE_REGISTRY:
        valid = ", ".join(sorted(STAGE_REGISTRY))
        raise ToolError(f"Unknown stage '{stage}'. Valid stages: {valid}")

    if run_id is None and stage != "input_report":
        raise ToolError(
            f"run_id is required for stage '{stage}'. "
            f"Only the 'input_report' stage can be started without a run_id."
        )

    set_active_stage(stage)
    tools = STAGE_REGISTRY[stage]
    run_label = f" for run {run_id}" if run_id else ""
    return (
        f"Stage '{stage}' activated{run_label}. "
        f"Available tools: {', '.join(tools)}"
    )


@mcp.tool()
async def complete_stage(run_id: str) -> str:  # noqa: ARG001
    """Complete the current stage and return to orchestrator scope.

    Resets the active stage to ``orchestrator`` so the orchestrator's full
    tool set is visible again.

    Args:
        run_id: Pipeline run identifier.

    Returns:
        Confirmation message with the previously active stage name.
    """
    previous = get_active_stage()
    if previous == "orchestrator":
        raise ToolError(
            "complete_stage can only be called from within a stage scope "
            "(current scope is already 'orchestrator'). "
            "Call start_stage first to enter a stage."
        )

    set_active_stage("orchestrator")
    return (
        f"Stage '{previous}' completed for run {run_id}. "
        f"Returned to orchestrator scope."
    )
