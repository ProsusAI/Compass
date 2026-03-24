# Scenario: Full Pipeline — Happy Path

## Setup
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- System prompt (input): `odysseus/agents/prompts/user_input_system.md`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- System prompt (routing analysis): `odysseus/agents/prompts/routing_analysis_system.md`
- Skills: `odysseus/skills/classify-example/SKILL.md`, `odysseus/skills/generate-routing-rationale/SKILL.md`, `odysseus/skills/check-semantic-overlap/SKILL.md`
- MCP tools: `submit_input_report`, `validate_dataset`, `create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`

## Scenario Description
End-to-end integration across all 3 implemented agents. The user provides all required fields upfront. The User Input agent collects inputs and produces a `proceed` report. The Data Validation agent validates the dataset. The Routing Analysis agent completes all 4 phases. Tests the complete pipeline chain with no friction.

## User Simulator
You are a data analyst with all information ready for the routing optimization pipeline.

**Your knowledge:**
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl` — 10 labeled routing examples mapping queries to haiku/sonnet/opus tiers by complexity.
- Problem description: "Route customer queries to haiku, sonnet, or opus tiers based on complexity — simple factual questions to haiku, moderate tasks to sonnet, complex reasoning to opus."
- Target metrics: `accuracy >= 0.90`
- Evaluation threshold: `0.80`
- Data split ratio: `0.20`
- Max iterations: `10`

**Behavior:** Provide all of the above in your opening message. Be clear and direct.

**Opening message:** "Hi, I'd like to set up routing optimization. My dataset is at `tests/scenarios/data/rationale_test_dataset.jsonl` with 10 labeled examples mapping queries to haiku, sonnet, or opus by complexity. The problem is to route customer queries to the right tier: simple factual questions go to haiku, moderate tasks to sonnet, and complex reasoning to opus. I want accuracy of at least 90%, evaluation threshold 0.80, data split ratio 0.20, and max 10 iterations."

## Verification Criteria

### Stage 1 — User Input
- [ ] Input agent collected all fields and produced a report with status `proceed`
- [ ] Agent called `submit_input_report` with the report, dataset path, and problem description

### Stage 2 — Data Validation
- [ ] `validate_dataset` was called with `tests/scenarios/data/rationale_test_dataset.jsonl`
- [ ] All schema findings have status `pass`
- [ ] routing_context produced with 3 routes (haiku, sonnet, opus)

### Stage 3 — Routing Analysis
- [ ] Routing Analysis received all 4 context dict keys
- [ ] routing_context from validation consumed verbatim by routing analysis
- [ ] dataset_path flows correctly through all 3 agents (`tests/scenarios/data/rationale_test_dataset.jsonl`)
- [ ] All 4 phases complete (classify, rationale, validate, split)
- [ ] Output contract satisfied: all 7 context keys set

### Pipeline Integrity
- [ ] All 3 agents operated in sequence — each stage completed before the next began
- [ ] Total turn count is reasonable (no unnecessary loops)
