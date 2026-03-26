# Scenario: Full Pipeline — Two-Route Edge Case

## Setup
- Dataset: `tests/scenarios/data/two_route_dataset.jsonl`
- System prompt (input): `odysseus/agents/prompts/user_input_system.md`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- System prompt (routing analysis): `odysseus/agents/prompts/routing_analysis_system.md`
- System prompt (prompt builder): `odysseus/agents/prompts/prompt_builder_system.md`
- Eval Runner: code-driven agent (no system prompt — `odysseus/agents/eval_runner.py`)
- Skills: `odysseus/skills/classify-example/SKILL.md`, `odysseus/skills/generate-routing-rationale/SKILL.md`, `odysseus/skills/check-semantic-overlap/SKILL.md`
- MCP tools: `submit_input_report`, `validate_dataset`, `create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`, `init_search_state_tool`, `register_candidate_tool`, `record_eval_result_tool`, `advance_round_tool`, `run_eval`
- Backend profile: `tests/scenarios/data/backends/mock-echo.yaml`

## Scenario Description
End-to-end pipeline with a simpler two-route routing problem (haiku + opus only). Tests that the entire pipeline — from data validation through prompt compilation and evaluation — correctly handles a binary routing problem. Fewer routes affect split stratification, prompt structure, and eval metrics. The compiled prompt should only reference two routes, not three.

## User Simulator
You are a data analyst setting up a binary routing problem.

**Your knowledge:**
- Dataset: `tests/scenarios/data/two_route_dataset.jsonl` — 8 labeled examples with haiku and opus tiers only.
- Problem description: "Route customer queries to either haiku or opus — simple questions go to haiku, complex reasoning goes to opus."
- Target metrics: `accuracy >= 0.90`
- Evaluation threshold: `0.80`
- Data split ratio: `0.70`
- Max iterations: `10`
- Backend: `mock-echo`

**Behavior:** Provide all of the above in your opening message. Be clear and direct.

**Opening message:** "Hi, I'd like to set up routing optimization for a two-tier system. My dataset is at `tests/scenarios/data/two_route_dataset.jsonl` with 8 labeled examples using only haiku and opus tiers. The problem is to route customer queries to either haiku (simple questions) or opus (complex reasoning). I want accuracy of at least 90%, evaluation threshold 0.80, data split ratio 0.70, max 10 iterations, and please use the `mock-echo` backend."

## Verification Criteria

### Stage 1 — User Input
- [ ] Input agent produced `proceed` report

### Stage 2 — Data Validation
- [ ] `validate_dataset` called with `tests/scenarios/data/two_route_dataset.jsonl`
- [ ] routing_context produced with exactly 2 routes (haiku, opus)
- [ ] No reference to sonnet in routing_context

### Stage 3 — Routing Analysis
- [ ] All 4 phases complete
- [ ] Rationale cards and vocabulary registry reflect only haiku and opus routes

### Stage 4 — Prompt Builder + Eval
- [ ] Compiled prompt has route definitions for only haiku and opus
- [ ] No references to sonnet in the compiled prompt
- [ ] `run_eval` called and ScoreReport received
- [ ] `record_eval_result_tool` and `advance_round_tool` called

### Pipeline Integrity
- [ ] All 5 stages in sequence
- [ ] Two-route context flows correctly through all agents (no phantom third route)
- [ ] Total turn count is reasonable
