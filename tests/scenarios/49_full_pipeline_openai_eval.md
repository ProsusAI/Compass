# Scenario: Full Pipeline — OpenAI Backend

## Setup
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- System prompt (input): `odysseus/agents/prompts/user_input_system.md`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- System prompt (routing analysis): `odysseus/agents/prompts/routing_analysis_system.md`
- System prompt (prompt builder): `odysseus/agents/prompts/prompt_builder_system.md`
- Eval Runner: code-driven agent (no system prompt — `odysseus/agents/eval_runner.py`)
- Skills: `odysseus/skills/classify-example/SKILL.md`, `odysseus/skills/generate-routing-rationale/SKILL.md`, `odysseus/skills/check-semantic-overlap/SKILL.md`
- MCP tools: `submit_input_report`, `validate_dataset`, `create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`, `init_search_state_tool`, `register_candidate_tool`, `record_eval_result_tool`, `advance_round_tool`, `run_eval`
- Backend profile: `tests/scenarios/data/backends/openai.yaml`
- Requires environment variable: `OPENAI_API_KEY`

## Scenario Description
Same end-to-end pipeline as scenario 48, but using the OpenAI backend (`gpt-4o-mini`) for real LLM evaluation. This smoke test validates that the entire system works against a live API — real prompts produce real routing decisions that are scored by real metrics. The prompt builder should detect the OpenAI provider and apply Markdown/JSON conventions.

## User Simulator
You are a data analyst with all information ready for the routing optimization pipeline.

**Your knowledge:**
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl` — 10 labeled routing examples.
- Problem description: "Route customer queries to haiku, sonnet, or opus tiers based on complexity — simple factual questions to haiku, moderate tasks to sonnet, complex reasoning to opus."
- Target metrics: `accuracy >= 0.90`
- Evaluation threshold: `0.80`
- Data split ratio: `0.20`
- Max iterations: `10`
- Backend: `openai`

**Behavior:** Provide all of the above in your opening message. Be clear and direct.

**Opening message:** "Hi, I'd like to set up routing optimization. My dataset is at `tests/scenarios/data/rationale_test_dataset.jsonl` with 10 labeled examples mapping queries to haiku, sonnet, or opus by complexity. The problem is to route customer queries to the right tier: simple factual questions go to haiku, moderate tasks to sonnet, and complex reasoning to opus. I want accuracy of at least 90%, evaluation threshold 0.80, data split ratio 0.20, max 10 iterations, and please use the `openai` backend."

## Verification Criteria

### Stage 1–3 (same progression as scenario 48)
- [ ] Input agent produced `proceed` report
- [ ] Data validation produced routing_context with 3 routes
- [ ] Routing analysis completed all 4 phases with 7 context keys

### Stage 4 — Prompt Builder + Eval (OpenAI)
- [ ] Agent detected OpenAI provider and applied Markdown/JSON conventions (not XML)
- [ ] `run_eval` called with `backend=openai`
- [ ] ScoreReport received with real accuracy metrics
- [ ] Cost in ScoreReport summary is non-zero (real API usage)
- [ ] No API errors in eval results (all examples evaluated successfully)
- [ ] `record_eval_result_tool` and `advance_round_tool` called

### Pipeline Integrity
- [ ] All 5 stages in sequence
- [ ] Total turn count is reasonable
