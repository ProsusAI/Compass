# Scenario: Input Clarification Then Full Pipeline Success

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- System prompts: `odysseus_routing_input`, `odysseus_data_validation`, `odysseus_backend_setup`, `odysseus_prompt_builder`, `odysseus_review_agent_iterative`, `odysseus_review_agent_cold_start`, `odysseus_final_report`
- MCP tools: `submit_input_report`, `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `stratified_split`, `get_default_pricing`, `init_search_state`, `register_candidate`, `run_batch_eval`, `record_eval_result`, `advance_step`, `get_search_state`, `save_prompt`, `build_review_briefing`, `record_directive_outcomes`, `filter_holdout_dataset`, `run_holdout_eval`, `build_final_report_briefing`, `save_final_report`, `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage`
- Backend profile: `tests/scenarios/data/backends/mock-echo.yaml`

## Scenario Description
The user opens with a problem description and some preferences but omits the required dataset path. The User Input agent detects the missing required field and asks for clarification. The user provides the dataset path in their next message. The pipeline then continues through all six stages without further issues.

Tests that the clarification loop in Stage 1 works correctly for a single missing required field, that the pipeline proceeds once the field is supplied, and that no context is lost between the clarification exchange and downstream stages.

## User Simulator
You are a data scientist who got ahead of themselves and forgot to include the dataset path in their opening message.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl` — 5 labeled routing examples, 3 tiers (haiku, sonnet, opus)
- Problem description: "Route API requests to the right model tier based on estimated complexity."
- Target metric: `accuracy >= 0.90`
- Backend: `mock-echo`
- All other optional fields: use defaults

**Behavior:**
1. Open with the problem description and preferences, but do NOT include the dataset path.
2. When the agent asks for the dataset path, respond with `tests/scenarios/data/valid_dataset.jsonl`.
3. Answer any further questions directly and concisely.

**Opening message:** "Hi, I want to optimize a routing prompt for API request routing. The goal is to route API requests to the right model tier based on estimated complexity — haiku for simple, sonnet for moderate, opus for complex. I'd like accuracy ≥ 0.90. Please use the mock-echo backend and default settings for everything else."

## Verification Criteria

### Stage 1 — User Input (Clarification)
- [ ] Agent detected missing dataset path and asked the user to provide it (did not call `submit_input_report` before receiving the path)
- [ ] After the user provided the dataset path, `submit_input_report` was called with status `proceed`
- [ ] Report contains `tests/scenarios/data/valid_dataset.jsonl` as the dataset path
- [ ] All other fields (threshold, split ratio, backend) present in the report with appropriate defaults or user-supplied values

### Stage 2 — Data Validation
- [ ] `validate_dataset` called with `tests/scenarios/data/valid_dataset.jsonl`
- [ ] All schema findings pass
- [ ] Routing context saved with 3 routes (haiku, sonnet, opus)
- [ ] `stratified_split` called

### Stage 3 — Backend Setup
- [ ] Backend resolved as `mock-echo`
- [ ] Stage completes without additional user input

### Stage 4 — Prompt Builder + Eval Runner
- [ ] `init_search_state`, `run_batch_eval`, `record_eval_result`, `advance_step`, `save_prompt` all called

### Stage 5 — Holdout Validation
- [ ] `filter_holdout_dataset` and `run_holdout_eval` called

### Stage 6 — Final Report
- [ ] `build_final_report_briefing` and `save_final_report` called

### Pipeline Integrity
- [ ] Only one clarification exchange occurred (agent asked once, user answered, pipeline proceeded)
- [ ] No context from the opening message was lost after clarification
- [ ] All 6 stages completed in sequence
