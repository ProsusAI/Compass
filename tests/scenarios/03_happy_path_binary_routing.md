# Scenario: Full Pipeline — Happy Path with Binary Routing

## Setup
- Dataset: `tests/scenarios/data/two_route_dataset.jsonl`
- System prompts: `odysseus_routing_input`, `odysseus_data_validation`, `odysseus_backend_setup`, `odysseus_prompt_builder`, `odysseus_review_agent`, `odysseus_final_report`
- MCP tools: `submit_input_report`, `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `stratified_split_tool`, `get_default_pricing`, `init_search_state_tool`, `register_candidate_tool`, `run_eval`, `record_eval_result_tool`, `advance_step_tool`, `get_search_state_tool`, `save_prompt_tool`, `build_review_briefing_tool`, `record_directive_outcomes_tool`, `filter_holdout_dataset_tool`, `run_holdout_eval`, `build_final_report_briefing_tool`, `save_final_report`, `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage`
- Backend profile: `tests/scenarios/data/backends/mock-echo.yaml`

## Scenario Description
Full pipeline with a simpler binary routing problem: only two tiers (haiku and opus), no intermediate sonnet tier. Uses `two_route_dataset.jsonl` (8 rows). Tests that the pipeline correctly handles a 2-route routing context throughout all stages — prompt compilation, eval scoring, Review Agent, and final report must all reflect exactly 2 routes without errors or assumptions about a 3-tier structure.

This validates that no stage hardcodes a 3-tier assumption and that the pipeline is genuinely tier-count agnostic.

## User Simulator
You are a data engineer running a binary routing optimization: simple queries go to haiku, all others go to opus.

**Your knowledge:**
- Dataset: `tests/scenarios/data/two_route_dataset.jsonl` — 8 labeled examples, 2 tiers (haiku and opus)
- Problem description: "Route user queries to either haiku (fast, simple questions) or opus (complex, multi-step reasoning). No middle tier."
- Target metric: `accuracy >= 0.90`
- Evaluation threshold: `0.80`
- Data split ratio: `0.70`
- Max iterations: `3`
- Backend: `mock-echo`

**Behavior:** Provide all fields in your opening message. If the agent asks about tiers, confirm there are exactly two (haiku and opus). Do not introduce a third tier.

**Opening message:** "Hi, I need routing optimization for a binary routing problem. Dataset: `tests/scenarios/data/two_route_dataset.jsonl` (8 examples, 2 tiers: haiku and opus). Problem: route user queries to either haiku for simple questions or opus for complex reasoning — no middle tier. Target accuracy ≥ 0.90, evaluation threshold 0.80, split ratio 0.70, max 3 iterations. Backend: `mock-echo`."

## Verification Criteria

### Stage 1 — User Input
- [ ] `submit_input_report` called with status `proceed`
- [ ] Report references exactly 2 tiers (haiku, opus) — no sonnet mentioned
- [ ] Dataset path `tests/scenarios/data/two_route_dataset.jsonl` captured correctly

### Stage 2 — Data Validation
- [ ] `validate_dataset` called with the two-route dataset
- [ ] Schema findings all pass
- [ ] Routing context saved with exactly 2 routes (haiku, opus)
- [ ] `stratified_split_tool` called; dev and holdout splits respect the 2-route structure

### Stage 3 — Backend Setup
- [ ] Backend resolved as `mock-echo`
- [ ] Stage completes without requesting additional input

### Stage 4 — Prompt Builder + Eval Runner
- [ ] `init_search_state_tool` called with `backend="mock-echo"`
- [ ] Compiled prompt contains route definitions for exactly 2 tiers (haiku, opus) — no sonnet route generated
- [ ] `run_eval` called with dev dataset
- [ ] ScoreReport received with per-class scores for haiku and opus (no sonnet class)
- [ ] `record_eval_result_tool`, `advance_step_tool` called
- [ ] `save_prompt_tool` called

### Stage 5 — Holdout Validation
- [ ] `filter_holdout_dataset_tool` called
- [ ] `run_holdout_eval` called; holdout report reflects 2-class scoring

### Stage 6 — Final Report
- [ ] `build_final_report_briefing_tool` and `save_final_report` called
- [ ] Report reflects 2-route structure throughout

### Pipeline Integrity
- [ ] No stage introduces a third tier or fails due to 2-route input
- [ ] All 6 stages completed in sequence
