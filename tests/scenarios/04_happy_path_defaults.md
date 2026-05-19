# Scenario: Full Pipeline — Happy Path with All Defaults

## Setup
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- System prompts: `odysseus_routing_input`, `odysseus_data_validation`, `odysseus_backend_setup`, `odysseus_prompt_builder`, `odysseus_review_agent_iterative`, `odysseus_review_agent_cold_start`, `odysseus_final_report`
- MCP tools: `submit_input_report`, `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `stratified_split`, `get_default_pricing`, `init_search_state`, `register_candidate`, `run_batch_eval`, `record_eval_result`, `advance_step`, `get_search_state`, `save_prompt`, `build_review_briefing`, `record_directive_outcomes`, `filter_holdout_dataset`, `run_holdout_eval`, `build_final_report_briefing`, `save_final_report`, `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage`
- Backend profile: `tests/scenarios/data/backends/mock-echo.yaml`

## Scenario Description
Full pipeline where the user provides only the dataset path and a problem description. All optional fields — evaluation threshold, data split ratio, max iterations, and backend — are left unspecified and must default. Tests that each stage correctly applies and propagates defaults, and that no stage stalls requesting values the user did not provide.

Uses `rationale_test_dataset.jsonl` (10 rows, 3 tiers). The pipeline must complete all six stages using defaults throughout.

## User Simulator
You are a product manager who knows what they want to optimize but has no interest in tuning hyperparameters.

**Your knowledge:**
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl` — 10 labeled examples, 3 tiers (haiku, sonnet, opus)
- Problem description: "Route user questions to the cheapest model that can handle them correctly. Simple questions go to haiku, moderate to sonnet, hard ones to opus."
- You do NOT know or care about threshold, split ratio, max iterations, or backend — you expect the system to apply reasonable defaults.

**Behavior:** Open with just the dataset path and problem description. If the agent asks about optional parameters, say "use whatever default makes sense" or "I'll leave that to you." Do not volunteer specific values for any optional field.

**Opening message:** "Hi, I'd like to optimize a routing prompt. My dataset is at `tests/scenarios/data/rationale_test_dataset.jsonl` — 10 examples across haiku, sonnet, and opus. The goal is to route user questions to the cheapest model that can still answer correctly: simple questions to haiku, moderate ones to sonnet, hard ones to opus. Please use whatever defaults make sense for all the other settings."

## Verification Criteria

### Stage 1 — User Input
- [ ] `submit_input_report` called with status `proceed`
- [ ] Report applies defaults for threshold, split ratio, max iterations, and backend (no null/missing values)
- [ ] Report captures dataset path and problem description

### Stage 2 — Data Validation
- [ ] `validate_dataset` called; all findings pass
- [ ] `stratified_split` called using the default split ratio
- [ ] Routing context saved with 3 routes (haiku, sonnet, opus)

### Stage 3 — Backend Setup
- [ ] Backend resolved via default (not user-supplied)
- [ ] Stage completes without requesting input from user

### Stage 4 — Prompt Builder + Eval Runner
- [ ] `init_search_state` called with the default backend
- [ ] Prompt compiled; `run_batch_eval` called; scores recorded
- [ ] `advance_step` and `save_prompt` called

### Stage 5 — Holdout Validation
- [ ] `filter_holdout_dataset` and `run_holdout_eval` called

### Stage 6 — Final Report
- [ ] `build_final_report_briefing` and `save_final_report` called

### Defaults Propagation
- [ ] No stage stalled waiting for user to provide an optional parameter
- [ ] Default values used are internally consistent (e.g., default split ratio matches what stratified split used)
- [ ] All 6 stages completed
