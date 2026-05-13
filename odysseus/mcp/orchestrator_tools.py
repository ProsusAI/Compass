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
from odysseus.agents.prompt_builder.search_ops import _BRANCH_ALGORITHM

# Pre-loaded stage prompt bodies — populated at import time in prompts.py.
# Imported here so start_stage reads from the cache rather than hitting disk.
from odysseus.mcp.prompts import _STAGE_PROMPT_BODIES  # noqa: E402
from odysseus.mcp.server import (
    _REVIEW_AGENT_PROMPT_NAMES,
    STAGE_REGISTRY,
    _load_text,
    get_active_stage,
    mcp,
    set_active_stage,
)

logger = logging.getLogger(__name__)


def recommended_model_for(activate_prompt: str | None) -> str:
    """Return the recommended Claude Code Agent model for a given activate_prompt.

    Returns ``"sonnet"`` for review-phase prompts (high-stakes synthesis) and
    ``"haiku"`` for all other pipeline stages (tool-driven / rote tasks).

    This is advisory text for Claude Code orchestrators only.  Non-Claude-Code
    MCP consumers see the hint as plain text and may ignore it.
    """
    return "sonnet" if activate_prompt in _REVIEW_AGENT_PROMPT_NAMES else "haiku"


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
        f"2. ALL OTHER STAGES — Dispatcher: When get_pipeline_status returns a non-null\n"
        f"   `subagent_instruction`, you MUST spawn a sub-agent using it. Never call stage tools yourself.\n\n"
        f"DISPATCH PROTOCOL (for all stages after Stage 1):\n"
        f"  a. Call get_pipeline_status(run_id=...) to get the next action\n"
        f"  b. If `subagent_instruction` is non-null → read it for your dispatch checklist\n"
        f"  c. Call `start_stage(...)`. ITS RESPONSE CONTAINS the `sub_agent_prompt` field —\n"
        f"     that is the sub-agent's prompt. Keep it for step (d).\n"
        f"  d. Spawn a sub-agent. The sub-agent's INITIAL USER MESSAGE MUST be the `sub_agent_prompt`\n"
        f"     field from `start_stage`'s response, VERBATIM. Do NOT include `subagent_instruction`\n"
        f"     text — that brief is for you, not the sub-agent. Do not paraphrase, summarise, or\n"
        f"     rewrite. Each dispatch is for ONE phase only.\n"
        f"  e. After the sub-agent returns → call complete_stage()\n"
        f"  f. Call get_pipeline_status again → repeat until pipeline complete\n\n"
        f"MODEL CAPABILITY (applies to all consumers):\n"
        f"  - review / review_cold sub-agents perform high-stakes synthesis and\n"
        f"    deserve a strong reasoning model.\n"
        f"  - All other sub-agents (input_report, data_validation,\n"
        f"    prompt_building, final_report) are tool-driven and can run on a\n"
        f"    smaller, faster, cheaper model without quality loss.\n\n"
        f"CLAUDE CODE BINDING (applies only if you are running on Claude Code with\n"
        f"access to the model aliases below — ignore this block otherwise):\n"
        f"  Every Agent({{...}}) you spawn MUST include a literal `model` parameter.\n"
        f"  Omitting it inherits the orchestrator's model (Sonnet under auto mode),\n"
        f"  which silently violates the routing rule.\n\n"
        f"  Required values:\n"
        f'    - review / review_cold      → model: "sonnet"\n'
        f'    - all other sub-agents      → model: "haiku"\n\n'
        f"  Each get_pipeline_status response tells you which value to pass for\n"
        f"  the current dispatch. If your Claude Code installation does not have\n"
        f"  access to one of these aliases, fall back to the closest available\n"
        f"  tier and report it in the run summary.\n\n"
        f'  DO NOT pass isolation="worktree" on any Agent() call. Sub-agents must\n'
        f"  share the orchestrator's cwd so the pipeline can read their outputs\n"
        f"  from outputs/<run_id>/ on return (and so it can run in non-git dirs).\n\n"
        f"USER INPUT MEDIATION (for stages that need user decisions):\n"
        f"  Sub-agents CANNOT interact with users directly. When a sub-agent needs user input,\n"
        f"  it writes partial artifacts and exits. You detect this via get_pipeline_status:\n\n"
        f"  a. After a sub-agent returns, call get_pipeline_status(run_id=...)\n"
        f"  b. If the stage is 'incomplete' with a non-null 'detail' object:\n"
        f"     - Inspect detail.kind: 'user_input_needed' or 'halt'\n"
        f"     - Read the file at detail.artifact_path (relative to outputs/<run_id>/)\n"
        f"     - Present detail.prompt_to_user to the user\n"
        f"     - For 'user_input_needed': wait for their real reply, then call start_stage again\n"
        f"       and re-dispatch the sub-agent with the reply in context\n"
        f"     - For 'halt': do NOT proceed; report the error and stop\n"
        f"     - detail.halt_on_failure_after gives the maximum re-dispatch attempts before halting\n"
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

    Returns a dispatch checklist (``subagent_instruction``) for the orchestrator.
    The stage system prompt itself is NOT included here — it is returned by
    ``start_stage`` in the ``sub_agent_prompt`` field, which the orchestrator
    forwards verbatim as the sub-agent's initial user message.

    Args:
        run_id: Optional pipeline run identifier.

    Returns:
        JSON object with current stage, subagent_instruction (non-null when dispatch
        is needed, null when the pipeline is at a terminal state), and stage details.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    outputs_dir = project_dir / "outputs"
    result = _get_pipeline_status(outputs_dir=outputs_dir, run_id=run_id, project_dir=project_dir)
    activate_prompt = result.get("activate_prompt")

    subagent_instruction: str | None = result.get("subagent_instruction")
    if subagent_instruction:
        recommended_model = recommended_model_for(activate_prompt)
        tier = "strong" if recommended_model == "sonnet" else "fast"
        model_alias = '"sonnet"' if recommended_model == "sonnet" else '"haiku"'
        subagent_instruction = (
            "⚠️ DISPATCH REQUIRED — Spawn a sub-agent. "
            "Do NOT call stage tools yourself.\n\n"
            f"  Agent() parameters you MUST set:\n"
            f"    - model: {model_alias}   (REQUIRED — Claude Code only; omission inherits\n"
            f"      the orchestrator's model. Recommended tier for this dispatch: {tier}.\n"
            f"      Other runtimes: select the equivalent tier on your backend.)\n\n"
            f"  Agent() parameters you MUST NOT set:\n"
            f'    - isolation              (do NOT pass isolation="worktree". Sub-agents\n'
            f"      MUST share the orchestrator's cwd so artifacts under outputs/<run_id>/\n"
            f"      are visible on return, and the pipeline can run in non-git working\n"
            f"      directories.)\n\n" + subagent_instruction
        )

    output = {
        "run_id": result["run_id"],
        "current_stage": result["current_stage"],
        "current_stage_name": result["current_stage_name"],
        "subagent_instruction": subagent_instruction,
        "stages": result["stages"],
        "discovered_runs": result.get("discovered_runs", []),
    }
    return json.dumps(output, indent=2)


@mcp.tool()
async def start_stage(ctx: Context, stage: str, run_id: str | None = None) -> str:
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
        JSON object with keys:
          - ``scope``: the activated stage name.
          - ``tools``: list of tool names now visible.
          - ``sub_agent_prompt``: the stage system prompt body. The orchestrator
            MUST forward this field verbatim as the sub-agent's initial user
            message. This is the only correct prompt source — do not use
            ``subagent_instruction`` from ``get_pipeline_status`` for this purpose.
          - ``run_id``: the run identifier (may be None for ``input_report``).
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

    # Compute the stage system prompt to forward to the sub-agent.
    # We re-read pipeline status to get the current activate_prompt / algorithm
    # for Stage 4's dynamic prompt lookup.
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    outputs_dir = project_dir / "outputs"

    system_prompt: str | None = None
    try:
        if run_id is None:
            # input_report stage: no run yet, always Stage 1 prompt (pre-loaded)
            system_prompt = _STAGE_PROMPT_BODIES[1]
        else:
            status_result = _get_pipeline_status(outputs_dir=outputs_dir, run_id=run_id, project_dir=project_dir)
            current_stage = status_result.get("current_stage")
            activate_prompt = status_result.get("activate_prompt")
            algorithm = status_result.get("algorithm", "hill_climb")

            # Stage 4 uses activate_prompt name as lookup key; all others use stage number.
            lookup_key: int | str | None = activate_prompt if current_stage == 4 and activate_prompt else current_stage

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
            elif lookup_key in _STAGE_PROMPT_BODIES:
                system_prompt = _STAGE_PROMPT_BODIES[lookup_key]
    except FileNotFoundError as e:
        raise ToolError(f"Stage system prompt not found — MCP server installation may be broken: {e}") from e
    except ValueError as e:
        raise ToolError(f"Review Agent prompt assembly failed — unknown algorithm or phase: {e}") from e

    return json.dumps(
        {
            "scope": stage,
            "tools": list(tools),
            "sub_agent_prompt": system_prompt,
            "run_id": run_id,
        },
        indent=2,
    )


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
        status = review_fanout_status(run_id, algorithm=_BRANCH_ALGORITHM)
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
