# Scenario: Validation → Routing Analysis — Imbalanced Tiers + Split Constraints

## Setup
- Dataset: `tests/scenarios/data/imbalanced_dataset.jsonl`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- System prompt (routing analysis): `odysseus/agents/prompts/routing_analysis_system.md`
- Skills: `odysseus/skills/classify-example/SKILL.md`, `odysseus/skills/generate-routing-rationale/SKILL.md`, `odysseus/skills/check-semantic-overlap/SKILL.md`
- MCP tools: `validate_dataset`, `create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`

## Scenario Description
Data Validation validates a heavily imbalanced dataset (9 haiku + 1 opus, no sonnet). Validation flags the imbalance. Routing Analysis must classify 9 very similar haiku queries without over-fragmenting vocabulary, handle the single opus example, and deal with stratified_split where the sole opus example can only appear in one split. Tests imbalanced distribution handling across both agents.

## User Simulator
You are the pipeline orchestrator coordinating the Data Validation and Routing Analysis agents.

**Your knowledge:**
- Dataset: `tests/scenarios/data/imbalanced_dataset.jsonl` — 10 rows, 9 haiku + 1 opus, no sonnet
- Problem description: "Route queries to haiku or opus based on complexity — simple lookups to haiku, complex reasoning to opus."
- A validated input report exists with: data_split_ratio 0.70, max_iterations 10.
- You expect imbalance warnings.

**Behavior:**
1. Ask the Data Validation agent to validate `tests/scenarios/data/imbalanced_dataset.jsonl`.
2. After validation completes (expect imbalance flags), provide all four context dict keys to the Routing Analysis agent.
3. Let the Routing Analysis agent run through all four phases autonomously.

**Opening message:** "Please validate the dataset at `tests/scenarios/data/imbalanced_dataset.jsonl` for our routing pipeline. The problem is routing queries to haiku or opus based on complexity."

## Verification Criteria
- [ ] `validate_dataset` was called with `tests/scenarios/data/imbalanced_dataset.jsonl`
- [ ] Label distribution shows 9 haiku + 1 opus, imbalance flagged
- [ ] routing_context reflects the dataset (may have 2 or 3 routes depending on what validation derives from the data)
- [ ] Routing Analysis received all 4 context dict keys
- [ ] Phase 1: All 10 examples classified — haiku vocabulary entries don't over-fragment (pruning consolidates)
- [ ] Phase 2: route_exclusions generated for all 10 examples
- [ ] Phase 3: Validation completes (pruning likely merges thin haiku clusters)
- [ ] Phase 4: `stratified_split` called — the single opus example appears in exactly one split (dev or holdout, not both)
- [ ] Output artifacts are structurally complete despite degenerate distribution
