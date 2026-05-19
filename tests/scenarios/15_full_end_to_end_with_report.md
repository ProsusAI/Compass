# Scenario: Full End-to-End Pipeline with Final Report

## Setup
- Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl`
- System prompts: `odysseus_routing_input`, `odysseus_data_validation`, `odysseus_backend_setup`, `odysseus_prompt_builder`, `odysseus_review_agent_iterative`, `odysseus_review_agent_cold_start`, `odysseus_final_report`
- MCP tools: `submit_input_report`, `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `stratified_split`, `get_default_pricing`, `init_search_state`, `register_candidate`, `run_batch_eval`, `record_eval_result`, `advance_step`, `get_search_state`, `save_prompt`, `build_review_briefing`, `record_directive_outcomes`, `filter_holdout_dataset`, `run_holdout_eval`, `build_final_report_briefing`, `save_final_report`, `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage`
- Backend profile: `tests/scenarios/data/backends/mock-echo.yaml`

## Scenario Description
Complete end-to-end pipeline run with explicit verification of every stage including the holdout validation (Stage 5) and final report generation (Stage 6). Uses `full_pipeline_dataset.jsonl` (100 rows, 3 tiers, 70/30 dev/holdout split) with the mock-echo backend.

This scenario is the most comprehensive verification: it checks not just that all stages fire, but that the holdout dataset is correctly filtered (few-shot examples excluded), that holdout eval runs on the filtered set, that the final report briefing incorporates both dev and holdout results, and that the saved report contains the expected content sections. The user provides all fields upfront; no clarification or recovery needed.

## User Simulator
You are a senior ML engineer running a production-readiness check on the full optimization pipeline.

**Your knowledge:**
- Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl` — 100 labeled examples (50 haiku, 30 sonnet, 20 opus), 70/30 split
- Problem description: "Route customer support queries to haiku, sonnet, or opus by complexity. Simple factual questions go to haiku. Moderate multi-step tasks go to sonnet. Complex reasoning, edge cases, and escalations go to opus."
- Target metric: `accuracy >= 0.90`
- Evaluation threshold: `0.80`
- Data split ratio: `0.70`
- Max iterations: `5`
- Backend: `mock-echo`
- You care about seeing a complete final report with holdout results — mention this in your opening message

**Behavior:** Provide all required fields in your opening message. After the pipeline completes, ask to see the final report summary. Accept the report as-is.

**Opening message:** "Hi, I'm running a full pipeline validation. Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl` (100 examples — 50 haiku, 30 sonnet, 20 opus). Problem: route customer support queries to the right tier — simple questions to haiku, moderate tasks to sonnet, complex reasoning and escalations to opus. Target accuracy ≥ 0.90, threshold 0.80, split ratio 0.70, max 5 iterations, mock-echo backend. I want to see the complete final report including holdout eval results at the end."

## Verification Criteria

### Stage 1 — User Input
- [ ] `submit_input_report` called with status `proceed`
- [ ] All fields captured: dataset path, problem description, threshold (0.80), split ratio (0.70), max iterations (5), backend (mock-echo)

### Stage 2 — Data Validation
- [ ] `validate_dataset` called; all findings pass
- [ ] `stratified_split` called with the specified split ratio (0.70)
- [ ] Dev set and holdout set created
- [ ] Routing context saved with exactly 3 routes (haiku, sonnet, opus)

### Stage 3 — Backend Setup
- [ ] Backend resolved as `mock-echo`
- [ ] Stage completes without additional user interaction

### Stage 4 — Prompt Builder + Eval Runner
- [ ] `init_search_state` called with `backend="mock-echo"`
- [ ] At least one candidate compiled and registered
- [ ] `run_batch_eval` called with the dev split and mock-echo backend
- [ ] `record_eval_result` called with scores from the ScoreReport
- [ ] `advance_step` called at least once
- [ ] `build_review_briefing` called (Review Agent invoked between rounds)
- [ ] `save_prompt` called to persist the best candidate prompt

### Stage 5 — Holdout Validation
- [ ] `filter_holdout_dataset` called — few-shot examples from the best prompt are excluded from the holdout set
- [ ] Filtered holdout set is non-empty after exclusion
- [ ] `run_holdout_eval` called with the filtered holdout set and mock-echo backend
- [ ] Holdout ScoreReport received (accuracy and per-class metrics present)

### Stage 6 — Final Report
- [ ] `build_final_report_briefing` called — briefing incorporates both dev eval results and holdout eval results
- [ ] `save_final_report` called and returns a valid report path
- [ ] Final report content includes:
  - [ ] Summary of the best prompt candidate
  - [ ] Dev evaluation scores
  - [ ] Holdout evaluation scores
  - [ ] Comparison or commentary on dev vs holdout performance

### Pipeline Integrity
- [ ] All 6 stages executed in sequence without skipping
- [ ] Few-shot examples correctly excluded from holdout (filter step verified)
- [ ] Holdout set used in Stage 5 is distinct from the dev set used in Stage 4
- [ ] Total turn count is reasonable (no runaway loops)
- [ ] Final report is accessible at the returned path
