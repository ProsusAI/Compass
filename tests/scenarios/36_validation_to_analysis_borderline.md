# Scenario: Validation → Routing Analysis — Borderline Examples Trigger Validation Loop

## Setup
- Dataset: `tests/scenarios/data/borderline_dataset.jsonl`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- System prompt (routing analysis): `odysseus/agents/prompts/routing_analysis_system.md`
- Skills: `odysseus/skills/classify-example/SKILL.md`, `odysseus/skills/generate-routing-rationale/SKILL.md`, `odysseus/skills/check-semantic-overlap/SKILL.md`
- MCP tools: `validate_dataset`, `create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`

## Scenario Description
Data Validation validates a 10-row dataset with deliberately ambiguous queries at tier boundaries (e.g., "explain X briefly" vs "give a short explanation of X"). Validation passes clean — the problem is query ambiguity, not data quality. During Phase 1 classification, the ambiguous queries are likely to produce semantically overlapping vocabulary entries. Phase 3's `check-semantic-overlap` skill should detect overlaps, triggering the auto-fix → re-validate loop.

**Non-determinism note:** LLM classification is non-deterministic. The dataset maximizes overlap likelihood but overlap is not guaranteed. This scenario has two valid pass conditions (see Verification Criteria).

## User Simulator
You are the pipeline orchestrator coordinating the Data Validation and Routing Analysis agents.

**Your knowledge:**
- Dataset: `tests/scenarios/data/borderline_dataset.jsonl` — 10 rows, 3 tiers, with deliberately ambiguous near-duplicate query intents
- Problem description: "Route queries to haiku, sonnet, or opus based on complexity and depth required."
- A validated input report exists with: data_split_ratio 0.20, max_iterations 10.

**Behavior:**
1. Ask the Data Validation agent to validate `tests/scenarios/data/borderline_dataset.jsonl`.
2. After validation completes, provide all four context dict keys to the Routing Analysis agent.
3. Let the Routing Analysis agent run through all four phases autonomously.

**Opening message:** "Please validate the dataset at `tests/scenarios/data/borderline_dataset.jsonl` for our routing pipeline. The problem is routing queries to haiku, sonnet, or opus based on complexity and depth required."

## Verification Criteria
- [ ] `validate_dataset` was called with `tests/scenarios/data/borderline_dataset.jsonl`
- [ ] All schema findings have status `pass` (no data quality issues)
- [ ] Routing Analysis received all 4 context dict keys
- [ ] Phase 1: All 10 examples classified with intent_pattern and complexity_structure
- [ ] Phase 2: All 10 examples have route_exclusions and ambiguity_tags
- [ ] Phase 3: `check-semantic-overlap` skill activated (this always runs regardless of overlap)
- [ ] **If overlap detected:** auto-fix merges overlapping entries, reassigns affected cards, re-validation passes within 5 attempts
- [ ] **If no overlap detected:** Phase 3 passes on first attempt — scenario passes vacuously for the overlap path, but pipeline still completes with borderline data
- [ ] If validation loop exhausts 5 attempts, error report is surfaced (not silently dropped)
- [ ] Phase 4: `stratified_split` called, output artifacts produced
- [ ] Output contract satisfied: all 7 context keys set
