# Scenario: Data Validation Warnings — User Acknowledges and Proceeds

## Setup
- Dataset: `tests/scenarios/data/imbalanced_dataset.jsonl`
- System prompts: `odysseus_routing_input`, `odysseus_data_validation`, `odysseus_backend_setup`, `odysseus_prompt_builder`, `odysseus_review_agent`, `odysseus_final_report`
- MCP tools: `submit_input_report`, `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `stratified_split_tool`, `get_default_pricing`, `init_search_state_tool`, `register_candidate_tool`, `run_eval`, `record_eval_result_tool`, `advance_round_tool`, `get_search_state_tool`, `save_prompt_tool`, `build_review_briefing_tool`, `record_directive_outcomes_tool`, `filter_holdout_dataset_tool`, `run_holdout_eval`, `build_final_report_briefing_tool`, `save_final_report`, `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage`
- Backend profile: `tests/scenarios/data/backends/mock-echo.yaml`

## Scenario Description
The user provides an imbalanced dataset (`imbalanced_dataset.jsonl` — 10 rows, 9 haiku and 1 opus). Data validation detects the class imbalance as a warning (not a blocking error): the opus tier has too few examples for reliable evaluation, which may skew per-class metrics. The agent surfaces the warning and asks whether the user wants to proceed or provide a more balanced dataset. The user acknowledges the warning and explicitly chooses to proceed. The pipeline continues through all remaining stages.

Tests that non-blocking warnings are correctly distinguished from blocking errors, that the agent asks for user confirmation before proceeding with a warned dataset, and that the pipeline completes normally after confirmation.

## User Simulator
You are a data scientist who is aware of the imbalance but wants to see how the pipeline handles it.

**Your knowledge:**
- Dataset: `tests/scenarios/data/imbalanced_dataset.jsonl` — 10 rows: 9 haiku, 1 opus
- Problem description: "Route user queries to haiku for simple requests, sonnet for moderate, opus for complex reasoning."
- You know the dataset is imbalanced but want to proceed anyway — you're testing the system's behavior, not expecting perfect opus recall
- Backend: `mock-echo`; other fields: use defaults

**Behavior:**
1. Open with the dataset path and problem description.
2. When the agent surfaces the imbalance warning, acknowledge it: "Yes, I know it's imbalanced. Please proceed anyway."
3. Do not offer to fix the dataset. Confirm you want to continue.

**Opening message:** "Hi, I'd like to run routing optimization. Dataset: `tests/scenarios/data/imbalanced_dataset.jsonl` (10 examples, mostly haiku). Problem: route user queries to haiku for simple requests, sonnet for moderate, opus for complex reasoning. Use mock-echo backend and default settings."

## Verification Criteria

### Stage 1 — User Input
- [ ] `submit_input_report` called with status `proceed`
- [ ] Dataset path `tests/scenarios/data/imbalanced_dataset.jsonl` captured in report

### Stage 2 — Data Validation (Warnings)
- [ ] `validate_dataset` called with the imbalanced dataset
- [ ] Validation findings include at least one warning about class imbalance or insufficient opus examples
- [ ] No blocking errors raised — findings are warnings only
- [ ] Agent surfaced the warning to the user and asked whether to proceed or fix the data
- [ ] After user confirmed "proceed", pipeline continued — did NOT stall or ask again

### Stage 2 — Post-Warning Continuation
- [ ] `stratified_split_tool` called after user confirmation
- [ ] Routing context saved (with whatever routes are present in the dataset)

### Stage 3 — Backend Setup
- [ ] Backend resolved as `mock-echo`; stage completes

### Stage 4 — Prompt Builder + Eval Runner
- [ ] `init_search_state_tool`, `run_eval`, `record_eval_result_tool`, `advance_round_tool`, `save_prompt_tool` all called

### Stage 5 — Holdout Validation
- [ ] `filter_holdout_dataset_tool` and `run_holdout_eval` called

### Stage 6 — Final Report
- [ ] `build_final_report_briefing_tool` and `save_final_report` called

### Pipeline Integrity
- [ ] Agent asked for confirmation exactly once (did not re-ask after user confirmed)
- [ ] All 6 stages completed after user acknowledgment
