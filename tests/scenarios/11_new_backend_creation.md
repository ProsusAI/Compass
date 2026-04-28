# Scenario: Backend Setup — Create New Backend During Stage 3

## Setup
- Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl`
- System prompts: `odysseus_routing_input`, `odysseus_data_validation`, `odysseus_backend_setup`, `odysseus_prompt_builder`, `odysseus_review_agent`, `odysseus_final_report`
- MCP tools: `submit_input_report`, `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `stratified_split_tool`, `get_default_pricing`, `init_search_state_tool`, `register_candidate_tool`, `run_eval`, `record_eval_result_tool`, `advance_step_tool`, `get_search_state_tool`, `save_prompt_tool`, `build_review_briefing_tool`, `record_directive_outcomes_tool`, `filter_holdout_dataset_tool`, `run_holdout_eval`, `build_final_report_briefing_tool`, `save_final_report`, `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage`
- Backend profile: Created during scenario (label: `openai-mini`)
- Eval backend for actual runs: `tests/scenarios/data/backends/mock-echo.yaml`

## Scenario Description
During Stage 3 (Backend Setup), the user creates a new backend rather than selecting an existing one. The user specifies all backend details: label `openai-mini`, provider `openai`, model `gpt-4.1-mini`, RPM 200, TPM 150000. The Backend Setup agent resolves default pricing via `get_default_pricing`, assembles the backend profile, and writes the YAML. The pipeline then continues with prompt building and eval using the mock-echo backend for actual eval runs (to avoid requiring a live API key for the new backend in this test).

Tests that the Backend Setup stage correctly handles new backend creation — gathering spec from the user, calling `get_default_pricing`, and persisting the profile — before handing off to Stage 4.

## User Simulator
You are an ML engineer setting up a new cost-optimized backend for routing evaluation.

**Your knowledge:**
- Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl`
- Problem description: "Route customer queries to haiku, sonnet, or opus tiers by complexity."
- New backend spec:
  - Label: `openai-mini`
  - Provider: `openai`
  - Model: `gpt-4.1-mini`
  - RPM: 200
  - TPM: 150000
- For actual eval runs in Stage 4: you're fine using mock-echo (the new backend is just registered, not used for live evals in this test)
- Optional fields: use defaults

**Behavior:**
1. Open with the dataset path and problem description. Do not mention the backend yet — let Stage 3 prompt you.
2. When the Backend Setup agent asks about backend configuration, say you want to create a new one with the above spec.
3. Provide the label, provider, model, RPM, and TPM when asked.
4. For eval backend in Stage 4, confirm `mock-echo` is fine.

**Opening message:** "Hi, I'd like to optimize routing for customer queries — haiku for simple, sonnet for moderate, opus for complex. Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl` (100 examples, 3 tiers). Default settings for threshold, split, and iterations please."

## Verification Criteria

### Stage 1 — User Input
- [ ] `submit_input_report` called with status `proceed`
- [ ] Dataset path and problem description captured correctly

### Stage 2 — Data Validation
- [ ] `validate_dataset` called; all findings pass
- [ ] Routing context saved with 3 routes; `stratified_split_tool` called

### Stage 3 — Backend Setup (New Backend Creation)
- [ ] Backend Setup agent presented the user with backend options (new vs existing)
- [ ] Agent collected all required fields from the user: label (`openai-mini`), provider (`openai`), model (`gpt-4.1-mini`), RPM (200), TPM (150000)
- [ ] `get_default_pricing` called to resolve pricing for the new backend
- [ ] New backend profile YAML written/saved with label `openai-mini`
- [ ] Stage completed successfully

### Stage 4 — Prompt Builder + Eval Runner
- [ ] `init_search_state_tool` called (with mock-echo for actual eval)
- [ ] `run_eval`, `record_eval_result_tool`, `advance_step_tool`, `save_prompt_tool` all called

### Stage 5 — Holdout Validation
- [ ] `filter_holdout_dataset_tool` and `run_holdout_eval` called

### Stage 6 — Final Report
- [ ] `build_final_report_briefing_tool` and `save_final_report` called

### Pipeline Integrity
- [ ] New backend `openai-mini` was registered without error
- [ ] All 6 stages completed in sequence
