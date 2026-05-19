# Scenario: Full Pipeline — Happy Path with OpenAI Backend

## Setup
- Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl`
- System prompts: `odysseus_routing_input`, `odysseus_data_validation`, `odysseus_backend_setup`, `odysseus_prompt_builder`, `odysseus_review_agent_iterative`, `odysseus_review_agent_cold_start`, `odysseus_final_report`
- MCP tools: `submit_input_report`, `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `stratified_split`, `get_default_pricing`, `init_search_state`, `register_candidate`, `run_batch_eval`, `record_eval_result`, `advance_step`, `get_search_state`, `save_prompt`, `build_review_briefing`, `record_directive_outcomes`, `filter_holdout_dataset`, `run_holdout_eval`, `build_final_report_briefing`, `save_final_report`, `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage`
- Backend profile: `tests/scenarios/data/backends/openai.yaml`
- **Prerequisite:** `OPENAI_API_KEY` must be set in the environment

## Scenario Description
Full end-to-end pipeline happy path using a live OpenAI backend (gpt-5.2). Structurally identical to scenario 01, but exercises the real OpenAI API path through the eval runner. This smoke-tests that the pipeline handles a live provider correctly: auth, rate limiting, response parsing, and ScoreReport extraction all work against the real API.

The user provides all required fields upfront. All six stages execute in sequence. This test is expected to be slower than mock-eval scenarios due to real API latency.

## User Simulator
You are an ML engineer running a live API smoke test of the full routing optimization pipeline.

**Your knowledge:**
- Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl` — 100 labeled routing examples (50 haiku, 30 sonnet, 20 opus)
- Problem description: "Route customer support queries to haiku, sonnet, or opus tiers based on complexity — simple factual questions go to haiku, moderate multi-step tasks go to sonnet, and complex reasoning or ambiguous edge cases go to opus."
- Target metric: `accuracy >= 0.85`
- Evaluation threshold: `0.75`
- Data split ratio: `0.70`
- Max iterations: `3`
- Backend: `openai` (gpt-5.2)

**Behavior:** Provide all of the above in your opening message. Answer follow-up questions concisely. Accept any minor latency-related delays without complaint.

**Opening message:** "Hi, I want to run the full routing optimization pipeline with the OpenAI backend. Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl` (100 labeled examples — 50 haiku, 30 sonnet, 20 opus). Problem: route customer support queries to haiku, sonnet, or opus by complexity; simple factual questions go to haiku, moderate multi-step tasks to sonnet, complex reasoning or edge cases to opus. Target accuracy ≥ 0.85, evaluation threshold 0.75, split ratio 0.70, max 3 iterations. Use the `openai` backend (gpt-5.2)."

## Verification Criteria

### Stage 1 — User Input
- [ ] `submit_input_report` called with status `proceed`
- [ ] Report contains backend `openai`
- [ ] Report captures dataset path and problem description correctly

### Stage 2 — Data Validation
- [ ] `validate_dataset` called with the correct dataset path
- [ ] All schema findings pass; 3-route routing context saved
- [ ] `stratified_split` produces dev and holdout splits

### Stage 3 — Backend Setup
- [ ] Backend resolved as `openai` (gpt-5.2)
- [ ] `get_default_pricing` called or pricing confirmed from profile
- [ ] Stage completes without error

### Stage 4 — Prompt Builder + Eval Runner
- [ ] `init_search_state` called with `backend="openai"`
- [ ] `run_batch_eval` called against the live OpenAI API
- [ ] ScoreReport received and `record_eval_result` called with valid scores
- [ ] `advance_step` called; search state updated
- [ ] `save_prompt` called

### Stage 5 — Holdout Validation
- [ ] `filter_holdout_dataset` called
- [ ] `run_holdout_eval` called against OpenAI API
- [ ] Holdout ScoreReport recorded

### Stage 6 — Final Report
- [ ] `build_final_report_briefing` called
- [ ] `save_final_report` called and report path returned

### Pipeline Integrity
- [ ] All 6 stages executed in sequence
- [ ] No API auth errors propagated to user as pipeline failures
- [ ] ScoreReport fields (accuracy, per-class metrics) are non-null and within valid range [0, 1]
