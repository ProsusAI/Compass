# Scenario: Validation → Routing Analysis — Two-Route Dataset

## Setup
- Dataset: `tests/scenarios/data/two_route_dataset.jsonl`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- System prompt (routing analysis): `odysseus/agents/prompts/routing_analysis_system.md`
- Skills: `odysseus/skills/classify-example/SKILL.md`, `odysseus/skills/generate-routing-rationale/SKILL.md`, `odysseus/skills/check-semantic-overlap/SKILL.md`
- MCP tools: `validate_dataset`, `create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`

## Scenario Description
Data Validation validates an 8-row dataset with only 2 routes (haiku + opus, no sonnet). Validation produces a routing_context with exactly 2 routes. Routing Analysis must produce route_exclusions with exactly 1 entry per card (the single non-assigned route) and stratified_split strata have only 2 buckets. Tests that the pipeline adapts to a reduced route count without assuming a middle tier.

## User Simulator
You are the pipeline orchestrator coordinating the Data Validation and Routing Analysis agents.

**Your knowledge:**
- Dataset: `tests/scenarios/data/two_route_dataset.jsonl` — 8 rows, 2 tiers (4 haiku, 4 opus)
- Problem description: "Binary routing — route simple factual queries to haiku and complex analytical queries to opus. No middle tier."
- A validated input report exists with: data_split_ratio 0.20, max_iterations 10.

**Behavior:**
1. Ask the Data Validation agent to validate `tests/scenarios/data/two_route_dataset.jsonl`.
2. After validation completes, provide all four context dict keys to the Routing Analysis agent.
3. Let the Routing Analysis agent run through all four phases autonomously.

**Opening message:** "Please validate the dataset at `tests/scenarios/data/two_route_dataset.jsonl` for our routing pipeline. This is a binary routing problem — simple factual queries go to haiku, complex analytical queries go to opus. No middle tier."

## Verification Criteria
- [ ] `validate_dataset` was called with `tests/scenarios/data/two_route_dataset.jsonl`
- [ ] routing_context has exactly 2 routes (haiku, opus)
- [ ] Routing Analysis received all 4 context dict keys
- [ ] Phase 1: All 8 examples classified with intent_pattern and complexity_structure
- [ ] Phase 2: Each card's route_exclusions has exactly 1 entry (the non-assigned route)
- [ ] Vocabulary does not assume or reference a middle tier (no "sonnet" in any artifact)
- [ ] Phase 4: `stratified_split` produces dev/holdout across 2 strata
- [ ] All output artifacts reference only 2 routes (haiku, opus)
- [ ] Output contract satisfied: all 7 context keys set
