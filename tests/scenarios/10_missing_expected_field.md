# Scenario: Missing Required Field — No `expected` Column, Fix and Continue

## Setup
- Initial dataset: `tests/scenarios/data/no_expected_field.jsonl`
- Corrected dataset: `tests/scenarios/data/valid_dataset.jsonl`
- System prompts: `compass_routing_input`, `compass_data_validation`, `compass_backend_setup`, `compass_prompt_builder`, `compass_review_agent_iterative`, `compass_review_agent_cold_start`, `compass_final_report`
- MCP tools: `submit_input_report`, `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `stratified_split`, `get_default_pricing`, `init_search_state`, `register_candidate`, `run_batch_eval`, `record_eval_result`, `advance_step`, `get_search_state`, `save_prompt`, `build_review_briefing`, `record_directive_outcomes`, `filter_holdout_dataset`, `run_holdout_eval`, `build_final_report_briefing`, `save_final_report`, `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage`
- Backend profile: `tests/scenarios/data/backends/mock-echo.yaml`

## Scenario Description
The user provides a dataset that is missing the `expected` field — the required column that tells the evaluator which tier each example should be routed to. Without this field, evaluation is impossible. The Data Validation agent must detect this as a blocking schema error and stop, explaining clearly that the `expected` field is required and what it should contain.

The user then provides a corrected dataset (`valid_dataset.jsonl`) that has the `expected` field. Re-validation passes and the pipeline continues through all six stages.

Tests that the absence of a required schema field is caught as a blocking error (not a warning), and that the pipeline can recover cleanly by swapping the dataset.

## User Simulator
You are a data analyst who exported labels from a separate system and forgot to join them back into the main dataset file.

**Your knowledge:**
- Broken dataset: `tests/scenarios/data/no_expected_field.jsonl` — 5 rows missing the `expected` field
- Corrected dataset: `tests/scenarios/data/valid_dataset.jsonl` — 5 rows with `expected` field (haiku/sonnet/opus)
- Problem description: "Route customer support tickets to haiku for FAQs, sonnet for billing questions, opus for technical issues."
- Backend: `mock-echo`; all other optional fields: use defaults

**Behavior:**
1. Open with the broken dataset path and problem description.
2. When the agent reports the missing `expected` field as a blocking error, respond: "Ah right, I forgot to add the labels. Here is the corrected file: `tests/scenarios/data/valid_dataset.jsonl`."
3. Provide no additional explanation unless asked.

**Opening message:** "Hi, I want to optimize a routing prompt for customer support ticket routing. Dataset: `tests/scenarios/data/no_expected_field.jsonl`. Problem: route support tickets to haiku for FAQs, sonnet for billing, opus for technical issues. Mock-echo backend, default settings."

## Verification Criteria

### Stage 1 — User Input
- [ ] `submit_input_report` called with status `proceed`
- [ ] Report contains initial dataset path `tests/scenarios/data/no_expected_field.jsonl`

### Stage 2 — Data Validation (First Pass — Blocking Error)
- [ ] `validate_dataset` called with `tests/scenarios/data/no_expected_field.jsonl`
- [ ] Validation finding includes a blocking error for missing `expected` field
- [ ] Agent communicated the error to the user, specifically naming the missing `expected` field
- [ ] Pipeline did NOT proceed to Stage 3 without the corrected dataset

### Stage 2 — Data Validation (Second Pass — Recovery)
- [ ] Agent accepted `tests/scenarios/data/valid_dataset.jsonl` as the replacement
- [ ] `validate_dataset` called again with `tests/scenarios/data/valid_dataset.jsonl`
- [ ] All findings pass; `expected` field present and valid
- [ ] `stratified_split` called; routing context saved with 3 routes

### Stage 3 — Backend Setup
- [ ] Backend resolved as `mock-echo`; stage completes

### Stage 4 — Prompt Builder + Eval Runner
- [ ] `init_search_state`, `run_batch_eval`, `record_eval_result`, `advance_step`, `save_prompt` all called

### Stage 5 — Holdout Validation
- [ ] `filter_holdout_dataset` and `run_holdout_eval` called

### Stage 6 — Final Report
- [ ] `build_final_report_briefing` and `save_final_report` called

### Pipeline Integrity
- [ ] Corrected dataset path flows into all downstream stages (not the broken path)
- [ ] All 6 stages completed after fix
