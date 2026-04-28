# Scenario: Malformed Dataset — Type Errors, Fix, and Revalidate

## Setup
- Initial dataset: `tests/scenarios/data/type_errors_dataset.jsonl`
- Corrected dataset: `tests/scenarios/data/valid_dataset.jsonl`
- System prompts: `odysseus_routing_input`, `odysseus_data_validation`, `odysseus_backend_setup`, `odysseus_prompt_builder`, `odysseus_review_agent_iterative`, `odysseus_review_agent_cold_start`, `odysseus_final_report`
- MCP tools: `submit_input_report`, `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `stratified_split_tool`, `get_default_pricing`, `init_search_state_tool`, `register_candidate_tool`, `run_eval`, `record_eval_result_tool`, `advance_step_tool`, `get_search_state_tool`, `save_prompt_tool`, `build_review_briefing_tool`, `record_directive_outcomes_tool`, `filter_holdout_dataset_tool`, `run_holdout_eval`, `build_final_report_briefing_tool`, `save_final_report`, `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage`
- Backend profile: `tests/scenarios/data/backends/mock-echo.yaml`

## Scenario Description
The user initially provides a dataset with type errors and null values (`type_errors_dataset.jsonl` — numeric IDs, numeric input fields, string costs, null values). The Data Validation agent detects these as blocking schema errors and surfaces them to the user. The user acknowledges the errors, then provides a corrected dataset (`valid_dataset.jsonl`). Validation runs again on the corrected dataset, passes, and the pipeline continues through all remaining stages.

Tests the complete error-detection and recovery cycle for malformed data: blocking validation failure, user-initiated fix, re-validation success, and pipeline continuation.

## User Simulator
You are a data engineer who exported a dataset from a database and didn't notice the schema got mangled in the process.

**Your knowledge:**
- First dataset (broken): `tests/scenarios/data/type_errors_dataset.jsonl` — has numeric IDs instead of strings, numeric inputs instead of strings, string-formatted costs instead of floats, and some null values
- Corrected dataset: `tests/scenarios/data/valid_dataset.jsonl` — 5 clean rows, 3 tiers (haiku, sonnet, opus)
- Problem description: "Route API calls to haiku, sonnet, or opus based on query complexity."
- Backend: `mock-echo`; all other optional fields: use defaults

**Behavior:**
1. Open with the broken dataset path and problem description.
2. When the agent reports type errors or blocking validation failures, respond: "Oh no, that's the wrong export. Here's the fixed file: `tests/scenarios/data/valid_dataset.jsonl`."
3. After providing the corrected dataset, do not add further explanations unless asked.

**Opening message:** "Hi, I want to optimize routing for API calls. Dataset: `tests/scenarios/data/type_errors_dataset.jsonl`. Problem: route API calls to haiku for simple queries, sonnet for moderate, opus for complex. Please use mock-echo backend and default settings."

## Verification Criteria

### Stage 1 — User Input
- [ ] `submit_input_report` called with status `proceed` (after initial dataset path provided)
- [ ] Report contains initial dataset path `tests/scenarios/data/type_errors_dataset.jsonl`

### Stage 2 — Data Validation (First Pass — Blocking Failure)
- [ ] `validate_dataset` called with `tests/scenarios/data/type_errors_dataset.jsonl`
- [ ] Validation findings include at least one blocking error (type mismatch, null value, or schema violation)
- [ ] Agent surfaced the blocking errors to the user clearly, explaining which fields/rows are affected
- [ ] Pipeline did NOT proceed to Stage 3 on the broken dataset

### Stage 2 — Data Validation (Second Pass — Recovery)
- [ ] Agent accepted the corrected dataset path `tests/scenarios/data/valid_dataset.jsonl`
- [ ] `validate_dataset` called again with `tests/scenarios/data/valid_dataset.jsonl`
- [ ] All findings pass on the corrected dataset
- [ ] `stratified_split_tool` called; routing context saved with 3 routes

### Stage 3 — Backend Setup
- [ ] Backend resolved as `mock-echo`; stage completes

### Stage 4 — Prompt Builder + Eval Runner
- [ ] `init_search_state_tool`, `run_eval`, `record_eval_result_tool`, `advance_step_tool`, `save_prompt_tool` all called using the corrected dataset

### Stage 5 — Holdout Validation
- [ ] `filter_holdout_dataset_tool` and `run_holdout_eval` called

### Stage 6 — Final Report
- [ ] `build_final_report_briefing_tool` and `save_final_report` called

### Pipeline Integrity
- [ ] Corrected dataset path flows correctly into all downstream stages (not the original broken path)
- [ ] All 6 stages completed after recovery
