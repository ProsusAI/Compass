# Scenario: Full Pipeline — Re-Validation Changes Routing Context

## Setup
- First dataset: `tests/scenarios/data/two_route_dataset.jsonl`
- Second dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- System prompt (input): `odysseus/agents/prompts/user_input_system.md`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- System prompt (routing analysis): `odysseus/agents/prompts/routing_analysis_system.md`
- Skills: `odysseus/skills/classify-example/SKILL.md`, `odysseus/skills/generate-routing-rationale/SKILL.md`, `odysseus/skills/check-semantic-overlap/SKILL.md`
- MCP tools: `submit_input_report`, `validate_dataset`, `create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`

## Scenario Description
The user initially provides a 2-route dataset (haiku + opus). Validation produces a 2-route routing_context. The user then says "actually, use this other dataset instead" and provides a 3-route dataset (haiku + sonnet + opus). Re-validation produces a different routing_context with 3 routes. Routing Analysis must use the final 3-route context, not the superseded 2-route one. Tests that context dict updates propagate correctly when the dataset changes mid-pipeline.

## User Simulator
You are a data analyst who realizes they provided the wrong dataset version.

**Your knowledge:**
- First (wrong) dataset: `tests/scenarios/data/two_route_dataset.jsonl` — 8 rows, 2 routes (haiku + opus)
- Second (correct) dataset: `tests/scenarios/data/rationale_test_dataset.jsonl` — 10 rows, 3 routes (haiku + sonnet + opus)
- Problem description: "Route queries to appropriate model tiers based on complexity."

**Behavior:**
- Provide the first (2-route) dataset in your opening message.
- After validation completes, say "Actually, I gave you the wrong dataset. Please use `tests/scenarios/data/rationale_test_dataset.jsonl` instead — it has the full 3-tier routing."
- When the agent mentions assumed defaults, confirm they are fine.

**Opening message:** "I'd like to optimize routing. My dataset is at `tests/scenarios/data/two_route_dataset.jsonl` and the problem is routing queries to model tiers based on complexity."

## Verification Criteria

### Stage 1 — User Input
- [ ] Input agent collected inputs and called `submit_input_report`

### Stage 2 — First Validation
- [ ] First `validate_dataset` call was on `tests/scenarios/data/two_route_dataset.jsonl`
- [ ] First routing_context has 2 routes (haiku, opus)

### Stage 2 — Second Validation
- [ ] After user switched datasets, `validate_dataset` was called on `tests/scenarios/data/rationale_test_dataset.jsonl`
- [ ] Second routing_context has 3 routes (haiku, sonnet, opus)

### Stage 3 — Routing Analysis
- [ ] Routing Analysis receives the 3-route routing_context (not the 2-route one)
- [ ] route_exclusions per card have 2 entries (not 1, which would indicate stale 2-route context)
- [ ] `stratified_split` strata cover 3 tiers
- [ ] No references to the 2-route context appear in routing analysis output
- [ ] All 4 phases complete
- [ ] Output contract satisfied: all 7 context keys set
