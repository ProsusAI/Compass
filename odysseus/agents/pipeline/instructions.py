"""Sub-agent HARD_STOP instruction templates for each pipeline stage.

These templates are embedded in ``get_pipeline_status`` responses so that the
orchestrator knows how to dispatch sub-agents.  Placeholders like ``{run_id}``
are filled at runtime by ``status.py``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Stage 1 — User Input
# ---------------------------------------------------------------------------

STAGE_1_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 1 tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(stage='input_report') BEFORE spawning the sub-agent.\n"
    "(No run_id yet — Stage 1 creates it via submit_input_report.)\n\n"
    "Sub-agent tools: get_pipeline_status, submit_input_report\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, extract the run_id from its output, "
    "then call complete_stage(run_id='<run_id_from_submit>'), "
    "then call get_pipeline_status.\n"
    "If Stage 1 is not complete, re-dispatch the sub-agent. Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

# ---------------------------------------------------------------------------
# Stage 2 — Data Validation
# ---------------------------------------------------------------------------

STAGE_2_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 2 tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='data_validation') "
    "BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, validate_dataset, "
    "detect_and_parse_dataset, transform_dataset, save_routing_context, "
    "stratified_split_tool, save_proposed_mapping\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 2 is not complete:\n"
    "  - Check the status detail field. If detail is 'mapping_confirmation_needed', read the\n"
    "    file at outputs/{run_id}/validation/proposed_mapping.json. Present the proposed\n"
    "    field mapping as a table to the user (source field → target field), include a few\n"
    "    sample rows for context, and list any unmapped fields. Ask the user to confirm the\n"
    "    mapping or provide corrections.\n"
    "    You MUST wait for the user's actual reply. Do NOT assume, guess, or auto-confirm.\n"
    "    Then call start_stage(run_id='{run_id}', stage='data_validation') again to re-activate\n"
    "    the stage scope, and re-dispatch the sub-agent with the confirmed (or corrected)\n"
    "    mapping in the conversation context. (Skipping start_stage will spawn the sub-agent\n"
    "    with orchestrator-scope tools and stage tools will be invisible.)\n"
    "  - Otherwise, call start_stage(run_id='{run_id}', stage='data_validation') again, then\n"
    "    re-dispatch the sub-agent. Do not call stage tools yourself.\n"
    "  - If Stage 2 remains incomplete after 2 re-dispatches, report the error to the\n"
    "    user and halt.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

# ---------------------------------------------------------------------------
# Stage 3 — Backend Setup
# ---------------------------------------------------------------------------

STAGE_3_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT perform backend setup from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='backend_setup') "
    "BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_default_pricing, save_backend_options\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 3 is not complete:\n"
    "  - Check the status detail field.\n"
    "  - If detail is 'backend_selection_needed', read the file at\n"
    "    outputs/{run_id}/backend_options.json. Present the available backends to the user.\n"
    "    If backends exist: ask 'Choose one of these existing backends, or create a new one.'\n"
    "    If no backends: ask 'No backends configured. Please provide: label, provider,\n"
    "    model, requests_per_minute, and tokens_per_minute.'\n"
    "    If the user chooses to create a new backend, collect: label, provider, model,\n"
    "    requests_per_minute, and tokens_per_minute.\n"
    "    You MUST wait for the user's actual reply. Do NOT assume, guess, or fabricate\n"
    "    the user's backend choice or configuration values.\n"
    "    Then call start_stage(run_id='{run_id}', stage='backend_setup') again to re-activate\n"
    "    the stage scope, and re-dispatch the sub-agent with the user's selection or config\n"
    "    in the conversation context. (Skipping start_stage will spawn the sub-agent with\n"
    "    orchestrator-scope tools and stage tools will be invisible.)\n"
    "  - If detail is 'pricing_missing', ask the user for input_cost_per_million_tokens,\n"
    "    cached_cost_per_million_tokens, and output_cost_per_million_tokens.\n"
    "    You MUST wait for the user's actual reply. Do NOT assume, guess, or fabricate values.\n"
    "    Then call start_stage(run_id='{run_id}', stage='backend_setup') again, and\n"
    "    re-dispatch the sub-agent with these pricing values in the conversation context.\n"
    "  - Otherwise, call start_stage(run_id='{run_id}', stage='backend_setup') again, then\n"
    "    re-dispatch the sub-agent. Do not perform backend setup yourself.\n"
    "  - If Stage 3 remains incomplete after 3 re-dispatches, report the error to the\n"
    "    user and halt.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

# ---------------------------------------------------------------------------
# Stage 4 — Refinement Loop (dynamic phases)
# ---------------------------------------------------------------------------

STAGE_4_COLD_START_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='review_cold') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, "
    "build_review_briefing_tool, record_directive_outcomes_tool\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

STAGE_4_BUILD_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, get_edit_directives_tool, "
    "init_search_state_tool, register_candidate_tool, record_eval_result_tool, "
    "advance_step_tool, run_eval\n"
    "Your tools: get_pipeline_status only\n\n"
    "NOTE: optimize_routing_prompt is the pipeline entry-point tool (orchestrator-level only). "
    "Do not call it from within the sub-agent.\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

STAGE_4_RERUN_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, get_edit_directives_tool, "
    "init_search_state_tool, register_candidate_tool, record_eval_result_tool, "
    "advance_step_tool, run_eval\n"
    "Your tools: get_pipeline_status only\n\n"
    "NOTE: This is a rerun — the Prompt Builder Rerun agent will restructure the existing prompt "
    "for the new backend. Source prompt version: '{source_prompt_version}'. "
    "New backend: '{new_backend}'.\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

STAGE_4_BUILD_RECOVERING_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, get_edit_directives_tool, "
    "init_search_state_tool, register_candidate_tool, record_eval_result_tool, "
    "advance_step_tool, run_eval, run_batch_eval\n"
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
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

STAGE_4_REVIEW_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 review-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='review') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, "
    "build_review_briefing_tool, record_directive_outcomes_tool\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

# ---------------------------------------------------------------------------
# Stage 5 — Final Report
# ---------------------------------------------------------------------------

STAGE_5_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 5 tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='final_report') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, filter_holdout_dataset_tool, "
    "list_pareto_candidates, run_holdout_eval, "
    "build_final_report_briefing_tool, save_final_report\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 5 is not complete:\n"
    "  - Check the status detail field. If detail is 'version_selection_needed', read the\n"
    "    file at outputs/{run_id}/pareto_candidates_listed.json. Present the candidates\n"
    "    to the user as a table (version, quality score, cost, round) and ask which\n"
    "    prompt_version they want to evaluate on the holdout set.\n"
    "    You MUST wait for the user's actual reply. Do NOT assume, guess, or fabricate values.\n"
    "    Then call start_stage(run_id='{run_id}', stage='final_report') again to re-activate\n"
    "    the stage scope, and re-dispatch the sub-agent with the chosen prompt_version in the\n"
    "    conversation context. (Skipping start_stage will spawn the sub-agent with\n"
    "    orchestrator-scope tools and stage tools will be invisible.)\n"
    "  - Otherwise, call start_stage(run_id='{run_id}', stage='final_report') again, then\n"
    "    re-dispatch the sub-agent. Do not call stage tools yourself.\n"
    "  - If Stage 5 remains incomplete after 2 re-dispatches, report the error to the\n"
    "    user and halt.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)
