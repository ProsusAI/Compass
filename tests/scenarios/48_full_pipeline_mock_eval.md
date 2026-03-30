# Scenario: Full Pipeline — Happy Path with Mock Eval

## Setup
- Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl`
- System prompt (input): `odysseus/agents/prompts/user_input_system.md`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- System prompt (prompt builder): `odysseus/agents/prompts/prompt_builder_system.md`
- Eval Runner: code-driven agent (no system prompt — `odysseus/agents/eval_runner.py`)
- MCP tools: `submit_input_report`, `validate_dataset`, `stratified_split`, `init_search_state_tool`, `register_candidate_tool`, `record_eval_result_tool`, `advance_round_tool`, `run_eval`
- Backend profile: `tests/scenarios/data/backends/mock-echo.yaml`

## Scenario Description
End-to-end integration across all 4 pipeline stages: User Input → Data Validation → Prompt Builder → Eval Runner. The user provides all required fields upfront. Each stage completes and hands off context to the next. The Prompt Builder compiles v1, calls `run_eval` with mock-echo, records the ScoreReport, and advances the round. Tests complete context flow from the first user message through to a scored prompt candidate.

## User Simulator
You are a data analyst with all information ready for the routing optimization pipeline.

**Your knowledge:**
- Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl` — 100 labeled routing examples mapping queries to haiku/sonnet/opus tiers by complexity (50 haiku, 30 sonnet, 20 opus).
- Problem description: "Route customer queries to haiku, sonnet, or opus tiers based on complexity — simple factual questions to haiku, moderate tasks to sonnet, complex reasoning to opus."
- Target metrics: `accuracy >= 0.90`
- Evaluation threshold: `0.80`
- Data split ratio: `0.70`
- Max iterations: `10`
- Backend: `mock-echo`

**Behavior:** Provide all of the above in your opening message. Be clear and direct.

**Opening message:** "Hi, I'd like to set up routing optimization. My dataset is at `tests/scenarios/data/full_pipeline_dataset.jsonl` with 100 labeled examples mapping queries to haiku, sonnet, or opus by complexity. The problem is to route customer queries to the right tier: simple factual questions go to haiku, moderate tasks to sonnet, and complex reasoning to opus. I want accuracy of at least 90%, evaluation threshold 0.80, data split ratio 0.70, max 10 iterations, and please use the `mock-echo` backend."

## Verification Criteria

### Stage 1 — User Input
- [ ] Input agent collected all fields and produced a report with status `proceed`
- [ ] Agent called `submit_input_report` with the report, dataset path, and problem description

### Stage 2 — Data Validation
- [ ] `validate_dataset` was called with `tests/scenarios/data/full_pipeline_dataset.jsonl`
- [ ] All schema findings have status `pass`
- [ ] routing_context produced with 3 routes (haiku, sonnet, opus)

### Stage 3 — Prompt Builder + Eval (includes Eval Runner, which is invoked as a tool, not a separate agent handoff)
- [ ] `init_search_state_tool` called with `backend="mock-echo"`
- [ ] Prompt compiled with route definitions for haiku, sonnet, opus
- [ ] `run_eval` called with dev dataset and mock-echo backend
- [ ] ScoreReport received and `record_eval_result_tool` called with extracted scores
- [ ] `advance_round_tool` called

### Pipeline Integrity
- [ ] All 4 stages operated in sequence — each stage completed before the next began
- [ ] Dataset path flows correctly through all agents
- [ ] Total turn count is reasonable (no unnecessary loops)
