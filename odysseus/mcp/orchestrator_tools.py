"""Orchestrator tools — pipeline entry point and status."""

import json
import logging

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

import odysseus.project_dir as _project_dir_mod
from odysseus.agents.pipeline.dispatch import (
    is_build_dispatched,
    review_fanout_status,
)
from odysseus.agents.pipeline.guards import check_artifacts  # noqa: F401
from odysseus.agents.pipeline.status import get_pipeline_status as _get_pipeline_status
from odysseus.mcp.server import (
    _REVIEW_AGENT_PROMPT_NAMES,
    _STAGE_PROMPT_MAP,
    STAGE_REGISTRY,
    _load_text,
    get_active_stage,
    mcp,
    set_active_stage,
)

logger = logging.getLogger(__name__)


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
        f"You are the Odysseus pipeline orchestrator. You have two modes:\n\n"
        f"1. STAGE 1 — User Input: You personally act as the User Input Agent (system prompt below).\n"
        f"2. ALL OTHER STAGES — Dispatcher: When get_pipeline_status returns DISPATCH_REQUIRED: true,\n"
        f"   you MUST spawn a sub-agent using the subagent_instruction. Never call stage tools yourself.\n\n"
        f"DISPATCH PROTOCOL (for all stages after Stage 1):\n"
        f"  a. Call get_pipeline_status(run_id=...) to get the next action\n"
        f"  b. If DISPATCH_REQUIRED is true → read subagent_instruction\n"
        f"  c. Call start_stage() as specified in the instruction\n"
        f"  d. Spawn a sub-agent with the system prompt from <stage_system_prompt>\n"
        f"  e. After the sub-agent returns → call complete_stage()\n"
        f"  f. Call get_pipeline_status again → repeat until pipeline complete\n\n"
        f"USER INPUT MEDIATION (for stages that need user decisions):\n"
        f"  Sub-agents CANNOT interact with users directly. When a sub-agent needs user input,\n"
        f"  it writes partial artifacts and exits. You detect this via get_pipeline_status:\n\n"
        f"  a. After a sub-agent returns, call get_pipeline_status(run_id=...)\n"
        f"  b. If the stage is 'incomplete' with a non-empty 'detail' field:\n"
        f"     - Read the detail value (e.g. 'mapping_confirmation_needed', 'backend_selection_needed',\n"
        f"       'pricing_missing', 'version_selection_needed')\n"
        f"     - The subagent_instruction tells you what file to read and what to ask the user\n"
        f"     - Present the information to the user and collect their response\n"
        f"     - Re-dispatch the sub-agent with the user's response in the conversation context\n"
        f"  c. The sub-agent detects the response in its conversation context (Step 0 mode)\n"
        f"     and continues autonomously\n"
        f"  d. If the stage remains incomplete after the re-dispatch limit, report and halt\n\n"
        f"  CRITICAL — NO HALLUCINATED INPUT:\n"
        f"  When a detail field indicates user input is needed, you MUST actually ask the user\n"
        f"  and wait for their real reply. NEVER assume, guess, auto-confirm, or fabricate what\n"
        f"  the user would say. Do not proceed with a re-dispatch until the user has explicitly\n"
        f"  responded. This applies to ALL detail-driven input requests.\n\n"
        f"  You are the ONLY agent that talks to the user (except during Stage 1 where you act\n"
        f"  as the User Input Agent). Sub-agents must never stop-and-wait for user input.\n\n"
        f"STAGE 1 INSTRUCTIONS:\n"
        f"The pipeline status above has already been checked — use it to decide how to greet the user.\n\n"
        f"The `discovered_runs` array in pipeline_status lists all known runs with:\n"
        f"  - run_id: the run identifier\n"
        f"  - current_stage: the stage the run is currently at\n"
        f"  - has_converged_prompt: true if Stage 4 has converged (a final prompt exists)\n\n"
        f"If discovered_runs is non-empty, surface the three options below.\n"
        f"Only show option 2 (rerun) for runs where has_converged_prompt is true.\n\n"
        f"IMPORTANT: Skip the Entry Verification section of your system prompt — pipeline status\n"
        f"is already provided above. If discovered_runs is non-empty, go directly to the\n"
        f"Pipeline Discovery section. If discovered_runs is empty, proceed with the fresh run\n"
        f"flow starting from 'Your job'.\n"
        f"</instructions>\n\n"
        f"<system_prompt>\n{system_prompt}\n</system_prompt>"
    )


@mcp.tool()
async def get_pipeline_status(ctx: Context, run_id: str | None = None) -> str:
    """Check pipeline progress and get the next dispatch instruction.

    Call this at any time. Accepts optional run_id; if omitted, uses the
    most recent pipeline run.

    The response includes a ``DISPATCH_REQUIRED`` boolean and a
    ``subagent_instruction`` field. When ``DISPATCH_REQUIRED`` is true, you
    MUST spawn a sub-agent using ``subagent_instruction`` — do NOT call stage
    tools yourself. The instruction specifies the stage to activate via
    ``start_stage`` and the system prompt for the sub-agent.

    After the sub-agent exits, call ``complete_stage``, then call this tool
    again to verify stage completion and receive the next instruction.

    Args:
        run_id: Optional pipeline run identifier.

    Returns:
        JSON object with current stage, DISPATCH_REQUIRED flag, and
        subagent_instruction (non-null when a sub-agent must be spawned).
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    outputs_dir = project_dir / "outputs"
    result = _get_pipeline_status(outputs_dir=outputs_dir, run_id=run_id, project_dir=project_dir)
    current_stage = result.get("current_stage")
    activate_prompt = result.get("activate_prompt")
    algorithm = result.get("algorithm", "hill_climb")
    subagent_instruction = result.get("subagent_instruction")

    # Stage 4 has dynamic prompt lookup by activate_prompt name (cold-start/review/build phase).
    # All other stages look up by stage number.
    lookup_key: int | str | None = activate_prompt if current_stage == 4 and activate_prompt else current_stage

    if subagent_instruction:
        placeholder = "<stage_system_prompt></stage_system_prompt>"
        if placeholder in subagent_instruction:
            try:
                if activate_prompt in _REVIEW_AGENT_PROMPT_NAMES:
                    # Strategy-aware assembly: base + phase-base + strategy overlay
                    from odysseus.mcp.prompts import assemble_review_prompt

                    if activate_prompt == "odysseus_review_agent_cold_start":
                        phase = "cold_start"
                    elif activate_prompt == "odysseus_review_agent_post_coldstart":
                        phase = "post_coldstart"
                    else:
                        phase = "iterative"
                    system_prompt = assemble_review_prompt(algorithm, phase)
                elif lookup_key in _STAGE_PROMPT_MAP:
                    system_prompt = _load_text(_STAGE_PROMPT_MAP[lookup_key])
                else:
                    system_prompt = None

                if system_prompt is not None:
                    result["subagent_instruction"] = subagent_instruction.replace(
                        placeholder,
                        f"<stage_system_prompt>\n{system_prompt}\n</stage_system_prompt>",
                    )
            except FileNotFoundError as e:
                raise ToolError(
                    f"Stage {current_stage} system prompt not found — MCP server installation may be broken: {e}"
                ) from e
            except ValueError as e:
                raise ToolError(
                    f"Review Agent prompt assembly failed — unknown algorithm or phase: {e}"
                ) from e

    if result.get("subagent_instruction"):
        result["subagent_instruction"] = (
            "⚠️ DISPATCH REQUIRED — You must spawn a sub-agent. "
            "Do NOT call stage tools yourself.\n\n" + result["subagent_instruction"]
        )
        output = {
            "run_id": result["run_id"],
            "current_stage": result["current_stage"],
            "current_stage_name": result["current_stage_name"],
            "DISPATCH_REQUIRED": True,
            "subagent_instruction": result["subagent_instruction"],
            "stages": result["stages"],
            "discovered_runs": result.get("discovered_runs", []),
        }
        return json.dumps(output, indent=2)
    return json.dumps(result, indent=2)


@mcp.tool()
async def start_stage(ctx: Context, stage: str, run_id: str | None = None) -> str:  # noqa: ARG001
    """Activate a pipeline stage, scoping visible tools to that stage.

    The orchestrator calls this before spawning a sub-agent so the sub-agent
    only sees the tools relevant to its stage.  After the sub-agent finishes,
    call ``complete_stage`` to return to orchestrator scope.

    Sends a ``notifications/tools/list_changed`` notification so the client
    refreshes its cached tool list with the newly visible stage tools.

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
            f"run_id is required for stage '{stage}'. Only the 'input_report' stage can be started without a run_id."
        )

    set_active_stage(stage)
    try:
        await ctx.session.send_tool_list_changed()
    except Exception:
        logger.warning("Failed to send tool list notification for stage '%s'", stage)
    tools = STAGE_REGISTRY[stage]
    run_label = f" for run {run_id}" if run_id else ""
    return f"Stage '{stage}' activated{run_label}. Available tools: {', '.join(tools)}"


@mcp.tool()
async def complete_stage(ctx: Context, run_id: str) -> str:  # noqa: ARG001
    """Complete the current stage and return to orchestrator scope.

    Resets the active stage to ``orchestrator`` so the orchestrator's full
    tool set is visible again.

    Sends a ``notifications/tools/list_changed`` notification so the client
    refreshes its cached tool list.

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

    # Dispatch-marker guards: reject completion while a sub-agent is still in-flight.
    if previous == "prompt_building" and is_build_dispatched(run_id):
        raise ToolError(
            "Build sub-agent still dispatched; cannot complete stage. "
            "Wait for the Prompt Builder to finish (eval completion clears this marker)."
        )

    if previous == "review":
        status = review_fanout_status(run_id, expected=1)
        if not status.is_complete:
            raise ToolError(
                f"Review fanout incomplete: missing={status.missing}. "
                "Wait for all Review Agent sub-agents to finish before completing the stage."
            )

    set_active_stage("orchestrator")
    try:
        await ctx.session.send_tool_list_changed()
    except Exception:
        logger.warning("Failed to send tool list notification after completing stage '%s'", previous)
    return f"Stage '{previous}' completed for run {run_id}. Returned to orchestrator scope."


@mcp.tool()
async def initiate_rerun(
    ctx: Context,
    run_id: str,
    source_prompt_version: str | None = None,
) -> str:
    """Initiate a rerun of a completed pipeline run with a different backend.

    Only valid when Stage 4 has converged for the given run_id (a final prompt
    version exists). This tool:
    - Finds the best prompt version from the Pareto front (or uses source_prompt_version if provided)
    - Renames search/search_state.json to search/search_state_original.json
    - Writes outputs/<run_id>/rerun_config.json with mode="rerun" and new_backend=null

    After this tool returns, proceed to Stage 3 to configure the new backend. The
    pipeline will then route through a restructure-only Stage 4 (single eval round)
    followed by Stage 5 for the final report.

    Args:
        run_id: Pipeline run identifier. Must have a converged Stage 4.
        source_prompt_version: Optional override for which prompt version to rerun.
            If None, the best candidate on the Pareto front is selected automatically
            (highest quality, ties broken by lowest cost).

    Returns:
        JSON confirmation with source_prompt_version, original_backend, and instructions.
    """
    from odysseus.mcp._initiate_rerun import initiate_rerun_logic

    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    outputs_dir = project_dir / "outputs"

    try:
        result = initiate_rerun_logic(
            outputs_dir=outputs_dir,
            run_id=run_id,
            source_prompt_version=source_prompt_version,
        )
    except (ValueError, FileNotFoundError) as e:
        raise ToolError(str(e)) from e

    return json.dumps(result, indent=2)
