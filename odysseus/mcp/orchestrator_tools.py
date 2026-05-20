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
    Call `start_stage(run_id=...)` in a loop to dispatch sub-agents.
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
        f"2. ALL OTHER STAGES — Dispatcher: When start_stage returns a non-null\n"
        f"   `subagent_instruction`, you MUST spawn a sub-agent using it. Never call stage tools yourself.\n\n"
        f"DISPATCH PROTOCOL (for all stages after Stage 1):\n"
        f"  a. Call start_stage(run_id=...) — NO stage argument. The server decides the next stage.\n"
        f"  b. If the response has `pipeline_complete: true` → stop. The pipeline is finished.\n"
        f"  c. Read `subagent_instruction` for your dispatch checklist and `sub_agent_prompt` for\n"
        f"     the sub-agent's initial user message.\n"
        f"  d. Spawn a sub-agent. The sub-agent's INITIAL USER MESSAGE MUST be the `sub_agent_prompt`\n"
        f"     field from `start_stage`'s response, VERBATIM. Do NOT include `subagent_instruction`\n"
        f"     text — that brief is for you, not the sub-agent. Do not paraphrase, summarise, or\n"
        f"     rewrite. Each dispatch is for ONE phase only.\n"
        f"     Use `recommended_model` from the response for the sub-agent's `model` parameter.\n"
        f"  e. After the sub-agent returns → call complete_stage(run_id=...)\n"
        f"  f. Loop back to (a)\n\n"
        f"USER INPUT MEDIATION (for stages that need user decisions):\n"
        f"  Sub-agents CANNOT interact with users directly. When a sub-agent needs user input,\n"
        f"  it writes partial artifacts and exits. You detect this via start_stage:\n\n"
        f"  a. Call start_stage(run_id=...) after the sub-agent returns\n"
        f"  b. If the response has a non-null `detail` object:\n"
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
        f"  Each start_stage response carries a `recommended_model` field with the correct\n"
        f"  value for the current dispatch. If your Claude Code installation does not have\n"
        f"  access to one of these aliases, fall back to the closest available\n"
        f"  tier and report it in the run summary.\n\n"
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
    """Read-only inspector for pipeline progress.

    Returns the raw pipeline status without any dispatch wrapping. Use this
    for debugging, auditing, or reading stage detail fields (e.g. to surface
    a ``detail.prompt_to_user`` message to the user). Not part of the dispatch
    loop — orchestrators use ``start_stage`` directly to advance the pipeline.

    Args:
        run_id: Pipeline run identifier; uses most recent run if omitted.

    Returns:
        JSON object with current stage, subagent_instruction (raw, from status.py),
        stages array, and discovered_runs.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    outputs_dir = project_dir / "outputs"
    result = _get_pipeline_status(outputs_dir=outputs_dir, run_id=run_id, project_dir=project_dir)

    output = {
        "run_id": result["run_id"],
        "current_stage": result["current_stage"],
        "current_stage_name": result["current_stage_name"],
        "subagent_instruction": result.get("subagent_instruction"),
        "stages": result["stages"],
        "discovered_runs": result.get("discovered_runs", []),
    }
    return json.dumps(output, indent=2)


@mcp.tool()
async def start_stage(ctx: Context, run_id: str | None = None) -> str:
    """Single dispatch verb — inspect artifacts, choose the next stage, and activate it.

    The orchestrator calls this in a loop (no ``stage`` argument needed). The
    server reads the current artifact state to determine which stage to dispatch,
    activates it, and returns everything the orchestrator needs to spawn a
    sub-agent: the stage system prompt, the dispatch checklist, and the
    recommended model.

    After the sub-agent finishes, call ``complete_stage`` to return to
    orchestrator scope, then call ``start_stage`` again to advance.

    Sends a ``notifications/tools/list_changed`` notification so the client
    refreshes its cached tool list with the newly visible stage tools.

    Args:
        run_id: Pipeline run identifier. Optional on the very first call (which
            lands on Stage 1 / ``input_report``); required for all subsequent
            calls.

    Returns:
        JSON object with keys:
          - ``scope``: the activated stage name (STAGE_REGISTRY key).
          - ``tools``: list of tool names now visible to the sub-agent.
          - ``sub_agent_prompt``: the stage system prompt body. The orchestrator
            MUST forward this verbatim as the sub-agent's initial user message.
          - ``run_id``: the resolved run identifier (may be None on Stage 1 entry).
          - ``recommended_model``: ``"sonnet"`` for review phases, ``"haiku"``
            for all other stages. Pass this as the ``model`` parameter to
            ``Agent()``.
          - ``subagent_instruction``: dispatch checklist for the orchestrator
            (⚠️ DISPATCH REQUIRED header + stage-specific HARD_STOP body).
          - ``pipeline_complete``: ``True`` when the pipeline is finished (stage
            6). When this is ``True``, no stage is activated and the orchestrator
            should stop.
          - ``current_stage``: integer stage number (1–6).
          - ``current_stage_name``: human-readable stage name.
          - ``activate_prompt``: the activate_prompt key used for Stage 4 routing.
          - ``detail``: the current stage's detail dict (user-mediation info),
            or ``null`` if none.
          - ``discovered_runs``: list of known runs (populated when
            ``run_id=None`` is passed on the entry-point call).
    """
    current = get_active_stage()
    if current != "orchestrator":
        raise ToolError(
            f"start_stage can only be called from orchestrator scope "
            f"(current scope: '{current}'). Call complete_stage first."
        )

    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    outputs_dir = project_dir / "outputs"

    # Read pipeline status to determine which stage to dispatch next.
    try:
        status_result = _get_pipeline_status(outputs_dir=outputs_dir, run_id=run_id, project_dir=project_dir)
    except Exception as e:
        raise ToolError(f"Failed to read pipeline status from {outputs_dir}: {e}") from e

    current_stage_num = status_result.get("current_stage", 1)
    activate_prompt = status_result.get("activate_prompt")
    algorithm = status_result.get("algorithm", "hill_climb")
    resolved_run_id = status_result.get("run_id")
    subagent_instruction_raw: str | None = status_result.get("subagent_instruction")
    discovered_runs = status_result.get("discovered_runs", [])

    # Stage 6 = pipeline complete — do NOT activate any stage.
    if current_stage_num == 6:
        return json.dumps(
            {
                "pipeline_complete": True,
                "run_id": resolved_run_id,
                "next_action": status_result.get("next_action"),
                "current_stage": current_stage_num,
                "current_stage_name": status_result.get("current_stage_name"),
            },
            indent=2,
        )

    # Validate: non-entry-point calls must have a run_id.
    if run_id is None and current_stage_num != 1:
        raise ToolError(
            f"run_id is required when the pipeline is at stage {current_stage_num}. "
            "Only the first call (Stage 1 / input_report) may omit run_id."
        )

    # Map (current_stage, activate_prompt) → STAGE_REGISTRY key.
    if current_stage_num == 1:
        stage = "input_report"
    elif current_stage_num == 2:
        stage = "data_validation"
    elif current_stage_num == 3:
        stage = "backend_setup"
    elif current_stage_num == 4:
        if activate_prompt == "odysseus_review_agent_cold_start":
            stage = "review_cold"
        elif activate_prompt == "odysseus_review_agent_iterative":
            stage = "review"
        else:
            # prompt_builder / prompt_builder_rerun / any other build phase
            stage = "prompt_building"
    else:
        # stage 5
        stage = "final_report"

    if stage not in STAGE_REGISTRY:
        valid = ", ".join(sorted(STAGE_REGISTRY))
        raise ToolError(f"Computed stage '{stage}' is not in STAGE_REGISTRY. Valid stages: {valid}")

    set_active_stage(stage)
    try:
        await ctx.session.send_tool_list_changed()
    except Exception:
        logger.warning("Failed to send tool list notification for stage '%s'", stage)
    tools = STAGE_REGISTRY[stage]

    # Compute the stage system prompt to forward to the sub-agent.
    system_prompt: str | None = None
    try:
        if run_id is None:
            # input_report stage: no run yet, always Stage 1 prompt (pre-loaded)
            system_prompt = _STAGE_PROMPT_BODIES[1]
        else:
            # Stage 4 uses activate_prompt name as lookup key; all others use stage number.
            lookup_key: int | str | None = (
                activate_prompt if current_stage_num == 4 and activate_prompt else current_stage_num
            )

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

    # Compute recommended model and build the dispatch checklist.
    recommended_model = recommended_model_for(activate_prompt)
    tier = "strong" if recommended_model == "sonnet" else "fast"
    model_alias = '"sonnet"' if recommended_model == "sonnet" else '"haiku"'
    wrapped_instruction: str | None = None
    if subagent_instruction_raw:
        wrapped_instruction = (
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
            f"      directories.)\n\n" + subagent_instruction_raw
        )

    # Extract current stage detail for user-mediation surfacing.
    stage_detail: dict | None = None
    stages = status_result.get("stages", [])
    if stages and current_stage_num >= 1 and current_stage_num <= len(stages):
        stage_detail = stages[current_stage_num - 1].get("detail")

    return json.dumps(
        {
            "scope": stage,
            "tools": list(tools),
            "sub_agent_prompt": system_prompt,
            "run_id": resolved_run_id,
            "recommended_model": recommended_model,
            "subagent_instruction": wrapped_instruction,
            "pipeline_complete": False,
            "current_stage": current_stage_num,
            "current_stage_name": status_result.get("current_stage_name"),
            "activate_prompt": activate_prompt,
            "detail": stage_detail,
            "discovered_runs": discovered_runs,
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
    """Initiate a rerun of a completed pipeline run against a different backend.

    Args:
        run_id: Pipeline run identifier with a converged Stage 4.
        source_prompt_version: Prompt version to rerun; auto-selected from Pareto front if omitted.

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
