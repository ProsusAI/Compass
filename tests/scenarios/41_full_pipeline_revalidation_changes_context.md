# Scenario: Full Pipeline — Re-Validation Changes Routing Context

## Setup
- First dataset: `tests/scenarios/data/two_route_dataset.jsonl`
- Second dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- System prompt (input): `odysseus/agents/prompts/user_input_system.md`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- MCP tools: `submit_input_report`, `validate_dataset`

## Scenario Description
The user initially provides a 2-route dataset (haiku + opus). Validation produces a 2-route routing_context. The user then says "actually, use this other dataset instead" and provides a 3-route dataset (haiku + sonnet + opus). Re-validation produces a different routing_context with 3 routes. Tests that context dict updates propagate correctly when the dataset changes mid-pipeline.

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

### Pipeline Integrity
- [ ] The final routing_context has 3 routes (haiku, sonnet, opus), not 2
- [ ] No references to the superseded 2-route context appear in the final output
