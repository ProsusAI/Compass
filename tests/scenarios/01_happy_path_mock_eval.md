# Scenario: Full Pipeline — Happy Path with Mock Eval

## Setup
- Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl`
- System prompts: `odysseus_routing_input`, `odysseus_data_validation`, `odysseus_backend_setup`, `odysseus_prompt_builder`, `odysseus_review_agent_iterative`, `odysseus_review_agent_cold_start`, `odysseus_final_report`
- MCP tools: `submit_input_report`, `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `stratified_split_tool`, `get_default_pricing`, `init_search_state_tool`, `register_candidate_tool`, `run_eval`, `record_eval_result_tool`, `advance_step_tool`, `get_search_state_tool`, `save_prompt_tool`, `build_review_briefing_tool`, `record_directive_outcomes_tool`, `filter_holdout_dataset_tool`, `run_holdout_eval`, `build_final_report_briefing_tool`, `save_final_report`, `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage`
- Backend profile: `tests/scenarios/data/backends/mock-echo.yaml`

## Scenario Description
Full end-to-end pipeline happy path using a deterministic mock-echo backend. The user provides all required fields upfront in their opening message. All six pipeline stages execute in sequence: User Input, Data Validation, Backend Setup, Prompt Builder + Eval Runner (with Review Agent between rounds), Holdout Validation, and Final Report. No errors, clarifications, or recoveries are required.

This scenario validates that the complete pipeline orchestrates correctly when given well-formed input: all stages complete, context flows correctly between stages, and the final report is generated and saved.

## User Simulator
You are an ML engineer who has already assembled all required information for a routing optimization run.

**Your knowledge:**
- Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl` — 100 labeled routing examples (50 haiku, 30 sonnet, 20 opus)
- Problem description: "Route customer support queries to haiku, sonnet, or opus tiers based on complexity — simple factual questions go to haiku, moderate multi-step tasks go to sonnet, and complex reasoning or ambiguous edge cases go to opus."
- Target metric: `accuracy >= 0.90`
- Evaluation threshold: `0.80`
- Data split ratio: `0.70`
- Max iterations: `5`
- Backend: `mock-echo`

**Behavior:** Provide all of the above in your opening message. Answer any follow-up questions concisely and directly. Do not volunteer extra information beyond what is asked.

**Opening message:** "Hi, I want to run the full routing optimization pipeline. Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl` (100 labeled examples — 50 haiku, 30 sonnet, 20 opus). Problem: route customer support queries to haiku, sonnet, or opus by complexity; simple factual questions go to haiku, moderate multi-step tasks to sonnet, complex reasoning or edge cases to opus. Target accuracy ≥ 0.90, evaluation threshold 0.80, split ratio 0.70, max 5 iterations. Use the `mock-echo` backend."

## Verification Criteria

### Stage 1 — User Input
- [ ] `submit_input_report` was called with status `proceed`
- [ ] Report contains dataset path `tests/scenarios/data/full_pipeline_dataset.jsonl`
- [ ] Report captures problem description referencing haiku/sonnet/opus tiers
- [ ] All provided fields (threshold, split ratio, max iterations, backend) are present in the report

### Stage 2 — Data Validation
- [ ] `detect_and_parse_dataset` or `validate_dataset` was called with the correct dataset path
- [ ] All schema findings have status `pass` (no blocking errors)
- [ ] `stratified_split_tool` was called, producing dev and holdout splits
- [ ] `save_routing_context` was called with a routing context containing 3 routes (haiku, sonnet, opus)

### Stage 3 — Backend Setup
- [ ] `get_default_pricing` was called (or backend resolved via provided profile)
- [ ] Backend confirmed as `mock-echo`
- [ ] Stage completes without requesting additional user input

### Stage 4 — Prompt Builder + Eval Runner
- [ ] `init_search_state_tool` was called with `backend="mock-echo"`
- [ ] At least one candidate compiled with route definitions for haiku, sonnet, and opus
- [ ] `run_eval` was called with the dev dataset and mock-echo backend
- [ ] `record_eval_result_tool` was called with scores from the ScoreReport
- [ ] `advance_step_tool` was called at least once
- [ ] Review Agent (`build_review_briefing_tool`) was called between rounds
- [ ] `save_prompt_tool` called to persist the best candidate

### Stage 5 — Holdout Validation
- [ ] `filter_holdout_dataset_tool` was called to exclude few-shot examples
- [ ] `run_holdout_eval` was called with the filtered holdout set and mock-echo backend

### Stage 6 — Final Report
- [ ] `build_final_report_briefing_tool` was called
- [ ] `save_final_report` was called and returned a report path
- [ ] Final report includes holdout evaluation results

### Pipeline Integrity
- [ ] All 6 stages executed in sequence without skipping
- [ ] Total turn count is reasonable (no runaway loops)
- [ ] Dataset path flowed correctly through all stages
