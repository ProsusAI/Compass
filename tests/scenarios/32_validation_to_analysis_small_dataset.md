# Scenario: Validation → Routing Analysis — Small Dataset + Degenerate Split

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- System prompt (routing analysis): `odysseus/agents/prompts/routing_analysis_system.md`
- Skills: `odysseus/skills/classify-example/SKILL.md`, `odysseus/skills/generate-routing-rationale/SKILL.md`, `odysseus/skills/check-semantic-overlap/SKILL.md`
- MCP tools: `validate_dataset`, `create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`

## Scenario Description
Data Validation validates a 5-row dataset (2 haiku, 2 opus, 1 sonnet). Validation passes with a volume `fail` verdict (treated as warning — does not block). Routing Analysis proceeds and must handle stratified_split on 5 rows with 0.70 holdout (~3-4 holdout rows). Tests volume warning propagation and degenerate split handling.

## User Simulator
You are the pipeline orchestrator coordinating the Data Validation and Routing Analysis agents.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl` — 5 rows, 3 tiers (2 haiku, 2 opus, 1 sonnet)
- Problem description: "Route queries to haiku, sonnet, or opus based on complexity."
- A validated input report exists with: data_split_ratio 0.70, max_iterations 10.
- You expect volume warnings because tiers have fewer than 5 examples each.

**Behavior:**
1. Ask the Data Validation agent to validate `tests/scenarios/data/valid_dataset.jsonl`.
2. After validation completes (expect volume warnings), provide all four context dict keys to the Routing Analysis agent.
3. Let the Routing Analysis agent run through all four phases autonomously.

**Opening message:** "Please validate the dataset at `tests/scenarios/data/valid_dataset.jsonl` for our routing pipeline. The problem is routing queries to haiku, sonnet, or opus based on complexity."

## Verification Criteria
- [ ] `validate_dataset` was called with `tests/scenarios/data/valid_dataset.jsonl`
- [ ] Volume assessment overall_verdict is `fail` (treated as warning per data validation decision rules — does not block)
- [ ] Data quality report surfaces volume inadequacy but does not block the pipeline
- [ ] Routing Analysis received all 4 context dict keys and did not refuse to start
- [ ] Phase 1: All 5 examples classified
- [ ] Phase 4: `stratified_split` called and produced valid dev/holdout sets
- [ ] Holdout set has at least 1 row
- [ ] No tier is completely absent from the dev set (where possible given 5 rows)
- [ ] Output contract satisfied: all 7 context keys set
