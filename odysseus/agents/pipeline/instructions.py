"""Sub-agent HARD_STOP instruction templates for each pipeline stage.

These templates are embedded in ``get_pipeline_status`` responses so that the
orchestrator knows how to dispatch sub-agents.  Placeholders like ``{run_id}``
are filled at runtime by ``status.py``.
"""

from __future__ import annotations

_NO_WORKTREE_ISOLATION_LINE: str = (
    'Reminder: omit the Agent() `isolation` parameter (no isolation="worktree"); '
    "see the dispatch preamble for the full Agent() parameter contract.\n\n"
)

# ---------------------------------------------------------------------------
# Stage 1 — User Input
# ---------------------------------------------------------------------------

STAGE_1_INSTRUCTION: str = (
    "<HARD_STOP>\n" + _NO_WORKTREE_ISOLATION_LINE + "You MUST NOT call any Stage 1 tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(stage='input_report') BEFORE spawning the sub-agent.\n"
    "(No run_id yet — Stage 1 creates it via submit_input_report.)\n\n"
    "Sub-agent tools: get_pipeline_status, submit_input_report\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, extract the run_id from its output, "
    "then call complete_stage(run_id='<run_id_from_submit>'), "
    "then call get_pipeline_status.\n"
    "If Stage 1 is not complete, re-dispatch the sub-agent. Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)

# ---------------------------------------------------------------------------
# Stage 2 — Data Validation
# ---------------------------------------------------------------------------

STAGE_2_INSTRUCTION: str = (
    "<HARD_STOP>\n" + _NO_WORKTREE_ISOLATION_LINE + "You MUST NOT call any Stage 2 tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='data_validation') "
    "BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, validate_dataset, "
    "detect_and_parse_dataset, transform_dataset, save_routing_context, "
    "stratified_split_tool, save_proposed_mapping\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 2 is not complete with a non-empty detail field, follow the generic\n"
    "user-mediation flow: read detail.artifact_path, present detail.prompt_to_user\n"
    "to the user, wait for their real reply, call start_stage again, re-dispatch the\n"
    "sub-agent with the reply in context. If the detail kind is 'halt', do NOT proceed\n"
    "to downstream stages. If the detail's halt_on_failure_after limit is reached,\n"
    "report the error to the user and halt.\n"
    "If Stage 2 is incomplete with no detail, call start_stage again and re-dispatch.\n"
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)

# ---------------------------------------------------------------------------
# Stage 3 — Backend Setup
# ---------------------------------------------------------------------------

STAGE_3_INSTRUCTION: str = (
    "<HARD_STOP>\n" + _NO_WORKTREE_ISOLATION_LINE + "You MUST NOT perform backend setup from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='backend_setup') "
    "BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_default_pricing, save_backend_options\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 3 is not complete with a non-empty detail field, follow the generic\n"
    "user-mediation flow: read detail.artifact_path, present detail.prompt_to_user\n"
    "to the user, wait for their real reply, call start_stage again, re-dispatch the\n"
    "sub-agent with the reply in context. If the detail's halt_on_failure_after limit\n"
    "is reached, report the error to the user and halt.\n"
    "If Stage 3 is incomplete with no detail, call start_stage again and re-dispatch.\n"
    "Do not perform backend setup yourself.\n"
    "</HARD_STOP>"
)

# ---------------------------------------------------------------------------
# Stage 4 — Refinement Loop (dynamic phases)
# ---------------------------------------------------------------------------

STAGE_4_COLD_START_INSTRUCTION: str = (
    "<HARD_STOP>\n" + _NO_WORKTREE_ISOLATION_LINE + "You MUST NOT call any Stage 4 tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='review_cold') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, "
    "build_review_briefing_tool, record_directive_outcomes_tool\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)

_STAGE_4_BUILD_COMMON_BODY: str = (
    "<HARD_STOP>\n"
    + _NO_WORKTREE_ISOLATION_LINE
    + "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, get_routing_context_tool, "
    "get_child_variants_tool, get_edit_directives_tool, get_prompt_text_tool, get_score_report_tool, "
    "init_search_state_tool, register_candidate_tool, record_eval_result_tool, "
    "advance_step_tool, save_prompt_tool, run_eval"
)

_STAGE_4_BUILD_RECOVERY_EXTRA_TOOL: str = ", run_batch_eval"

_STAGE_4_BUILD_COMMON_TAIL: str = (
    "\n"
    "Your tools: get_pipeline_status only\n\n"
    "NOTE: optimize_routing_prompt is the pipeline entry-point tool (orchestrator-level only). "
    "Do not call it from within the sub-agent.\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)

_STAGE_4_BUILD_DISPATCH_CONTEXT: str = (
    "<DISPATCH_CONTEXT>\n"
    "This is an optimization round (round 2+ in the refinement loop). A search state already exists for this run.\n"
    "- Begin by calling get_search_state_tool (NOT init_search_state_tool).\n"
    "- Skip Phase 1 of your system prompt entirely. Proceed directly to Phase 2.\n"
    "- Calling init_search_state_tool now would clobber the optimization history.\n"
    "</DISPATCH_CONTEXT>\n\n"
)

_STAGE_4_BUILD_RECOVERY_PARAGRAPH: str = (
    "\n\n"
    "RECOVERY MODE: active_evals is non-empty. The sub-agent must call "
    "run_batch_eval(run_id='{run_id}', candidates=[]) to resume in-flight evaluations. "
    "Completed evals (eval_status='complete') are recovered from disk automatically; "
    "only missing or incomplete evals (eval_status='pending' or 'running') are re-run."
)


def STAGE_4_BUILD_INSTRUCTION(  # noqa: N802
    *,
    is_first_round: bool = False,
    recover_active_evals: bool = False,
) -> str:
    """Return the Stage-4 build sub-agent instruction for the given variant.

    Three output variants:
    - ``is_first_round=True``: first build after cold-start seeding (no DISPATCH_CONTEXT).
    - ``recover_active_evals=True``: recovery mode, includes ``run_batch_eval`` in toolbelt.
    - else (steady-state): optimisation round with leading DISPATCH_CONTEXT.
    """
    if recover_active_evals:
        tools_line = _STAGE_4_BUILD_COMMON_BODY + _STAGE_4_BUILD_RECOVERY_EXTRA_TOOL
        return tools_line + _STAGE_4_BUILD_RECOVERY_PARAGRAPH + _STAGE_4_BUILD_COMMON_TAIL
    if is_first_round:
        return _STAGE_4_BUILD_COMMON_BODY + _STAGE_4_BUILD_COMMON_TAIL
    return _STAGE_4_BUILD_DISPATCH_CONTEXT + _STAGE_4_BUILD_COMMON_BODY + _STAGE_4_BUILD_COMMON_TAIL


# Convenience pre-built strings for backward compatibility with tests that compare text.
# These are not public API — internal use only.
_STAGE_4_BUILD_OPTIMIZE_INSTRUCTION: str = STAGE_4_BUILD_INSTRUCTION()
_STAGE_4_BUILD_V1_INSTRUCTION: str = STAGE_4_BUILD_INSTRUCTION(is_first_round=True)
_STAGE_4_BUILD_RECOVERING_INSTRUCTION: str = STAGE_4_BUILD_INSTRUCTION(recover_active_evals=True)

STAGE_4_RERUN_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    + _NO_WORKTREE_ISOLATION_LINE
    + "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, get_routing_context_tool, "
    "get_prompt_text_tool, init_search_state_tool, register_candidate_tool, record_eval_result_tool, "
    "advance_step_tool, save_prompt_tool, run_eval\n"
    "Your tools: get_pipeline_status only\n\n"
    "NOTE: This is a rerun — the Prompt Builder Rerun agent will restructure the existing prompt "
    "for the new backend. Source prompt version: '{source_prompt_version}'. "
    "New backend: '{new_backend}'.\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)

STAGE_4_BUILD_RECOVERING_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    + _NO_WORKTREE_ISOLATION_LINE
    + "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, get_routing_context_tool, "
    "get_child_variants_tool, get_edit_directives_tool, get_prompt_text_tool, get_score_report_tool, "
    "init_search_state_tool, register_candidate_tool, record_eval_result_tool, "
    "advance_step_tool, save_prompt_tool, run_eval, run_batch_eval\n"
    "Your tools: get_pipeline_status only\n\n"
    "RECOVERY MODE: active_evals is non-empty. The sub-agent must call "
    "run_batch_eval(run_id='{run_id}', candidates=[]) to resume in-flight evaluations. "
    "Completed evals (eval_status='complete') are recovered from disk automatically; "
    "only missing or incomplete evals (eval_status='pending' or 'running') are re-run.\n\n"
    "NOTE: optimize_routing_prompt is the pipeline entry-point tool (orchestrator-level only). "
    "Do not call it from within the sub-agent.\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)

# Shared steady-review sub-agent toolbelt — used by STAGE_4_REVIEW_INSTRUCTION.
_STEADY_REVIEW_TOOLS_LINE: str = (
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, "
    "build_review_briefing_tool, record_directive_outcomes_tool, "
    "get_prompt_text_tool, query_holdout_examples_tool"
)

STAGE_4_REVIEW_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    + _NO_WORKTREE_ISOLATION_LINE
    + "You MUST NOT call any Stage 4 review-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='review') BEFORE spawning the sub-agent.\n\n"
    + _STEADY_REVIEW_TOOLS_LINE
    + "\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)

# ---------------------------------------------------------------------------
# Stage 5 — Final Report
# ---------------------------------------------------------------------------

STAGE_5_INSTRUCTION: str = (
    "<HARD_STOP>\n" + _NO_WORKTREE_ISOLATION_LINE + "You MUST NOT call any Stage 5 tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='final_report') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, filter_holdout_dataset_tool, "
    "list_pareto_candidates, run_holdout_eval, "
    "build_final_report_briefing_tool, save_final_report\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 5 is not complete with a non-empty detail field, follow the generic\n"
    "user-mediation flow: read detail.artifact_path, present detail.prompt_to_user\n"
    "to the user, wait for their real reply, call start_stage again, re-dispatch the\n"
    "sub-agent with the reply in context. If the detail's halt_on_failure_after limit\n"
    "is reached, report the error to the user and halt.\n"
    "If Stage 5 is incomplete with no detail, call start_stage again and re-dispatch.\n"
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)
