# Scenario: Backend Setup — Select Existing Backend

## Setup
- Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl`
- System prompts: `odysseus_routing_input`, `odysseus_data_validation`, `odysseus_backend_setup`, `odysseus_prompt_builder`, `odysseus_review_agent_iterative`, `odysseus_review_agent_cold_start`, `odysseus_final_report`
- MCP tools: `submit_input_report`, `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `stratified_split`, `get_default_pricing`, `init_search_state`, `register_candidate`, `run_batch_eval`, `record_eval_result`, `advance_step`, `get_search_state`, `save_prompt`, `build_review_briefing`, `record_directive_outcomes`, `filter_holdout_dataset`, `run_holdout_eval`, `build_final_report_briefing`, `save_final_report`, `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage`
- Backend profile: `tests/scenarios/data/backends/anthropic.yaml`

## Scenario Description
During Stage 3 (Backend Setup), the user selects an existing backend (`anthropic`, claude-haiku) from the available profiles rather than creating a new one. This tests the straightforward backend selection flow — the agent presents available options, the user picks `anthropic`, and the stage completes without any new YAML being created.

The pipeline then continues through all remaining stages using the selected anthropic backend configuration. This verifies that backend selection integrates cleanly with the rest of the pipeline and that no spurious YAML creation or `get_default_pricing` calls occur when selecting an existing profile.

## User Simulator
You are a data scientist who already has a registered Anthropic backend and wants to use it.

**Your knowledge:**
- Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl`
- Problem description: "Route customer support queries to haiku, sonnet, or opus by estimated query complexity."
- Existing backend: `anthropic` (claude-haiku) — already registered, no new backend needed
- Optional fields: use defaults

**Behavior:**
1. Open with the dataset path and problem description. Do not mention the backend explicitly yet.
2. When the Backend Setup agent presents backend options, select the existing `anthropic` backend.
3. If asked to confirm the selection, confirm it without adding extra parameters.
4. Do not request creation of a new backend.

**Opening message:** "Hi, I want to optimize a routing prompt for customer support. Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl` (100 examples, 3 tiers). Problem: route queries to haiku for simple support questions, sonnet for moderate, opus for complex or escalated cases. Default settings for everything else."

## Verification Criteria

### Stage 1 — User Input
- [ ] `submit_input_report` called with status `proceed`
- [ ] Dataset path and problem description captured

### Stage 2 — Data Validation
- [ ] `validate_dataset` called; all findings pass
- [ ] Routing context saved with 3 routes; `stratified_split` called

### Stage 3 — Backend Setup (Existing Selection)
- [ ] Agent presented existing backend options to the user
- [ ] User selected `anthropic`; agent confirmed the selection
- [ ] No new backend YAML was created (no new file written)
- [ ] `get_default_pricing` was NOT called for a new backend (pricing already in existing profile)
- [ ] Stage completed with `anthropic` backend confirmed

### Stage 4 — Prompt Builder + Eval Runner
- [ ] `init_search_state` called with backend referencing `anthropic` or the mock-echo backend for eval
- [ ] `run_batch_eval`, `record_eval_result`, `advance_step`, `save_prompt` called

### Stage 5 — Holdout Validation
- [ ] `filter_holdout_dataset` and `run_holdout_eval` called

### Stage 6 — Final Report
- [ ] `build_final_report_briefing` and `save_final_report` called

### Pipeline Integrity
- [ ] No new backend was created — existing `anthropic` profile was used as-is
- [ ] All 6 stages completed in sequence
