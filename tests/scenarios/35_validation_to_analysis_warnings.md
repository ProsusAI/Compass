# Scenario: Validation → Routing Analysis — Warnings Don't Block Analysis

## Setup
- Dataset: `tests/scenarios/data/warnings_dataset.jsonl`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- System prompt (routing analysis): `odysseus/agents/prompts/routing_analysis_system.md`
- Skills: `odysseus/skills/classify-example/SKILL.md`, `odysseus/skills/generate-routing-rationale/SKILL.md`, `odysseus/skills/check-semantic-overlap/SKILL.md`
- MCP tools: `validate_dataset`, `create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`

## Scenario Description
Data Validation validates a 10-row dataset that passes all critical checks but triggers warning-severity findings (null values in non-required fields). The data quality report contains warnings alongside passing checks. Routing Analysis must proceed without being blocked by the warnings, treating them as informational. Tests that non-critical warnings propagate correctly and don't halt the pipeline.

## User Simulator
You are the pipeline orchestrator coordinating the Data Validation and Routing Analysis agents.

**Your knowledge:**
- Dataset: `tests/scenarios/data/warnings_dataset.jsonl` — 10 rows, 3 tiers, some null values in route cost/quality_score fields
- Problem description: "Route queries to haiku, sonnet, or opus based on complexity."
- A validated input report exists with: data_split_ratio 0.20, max_iterations 10.
- You expect some null_fields warnings but no critical failures.

**Behavior:**
1. Ask the Data Validation agent to validate `tests/scenarios/data/warnings_dataset.jsonl`.
2. After validation completes (expect warnings but no blockers), provide all four context dict keys to the Routing Analysis agent.
3. Let the Routing Analysis agent run through all four phases autonomously.

**Opening message:** "Please validate the dataset at `tests/scenarios/data/warnings_dataset.jsonl` for our routing pipeline. The problem is routing queries to haiku, sonnet, or opus based on complexity. I know there might be some null values in the data but the structure should be valid."

## Verification Criteria
- [ ] `validate_dataset` was called with `tests/scenarios/data/warnings_dataset.jsonl`
- [ ] All critical schema findings (required_keys, types, unique_ids, consistent_model_set) have status `pass`
- [ ] At least one warning-severity finding (null_fields) has status `fail` (rows w-8, w-9, w-10)
- [ ] At least one warning-severity finding (route_in_routes) has status `fail` (row w-7 has route `fast` not in routes)
- [ ] data_quality_report contains warnings alongside passing checks
- [ ] Routing Analysis received all 4 context dict keys and did not refuse to start based on warnings
- [ ] Phase 1: All 10 examples classified (null values in route metrics don't affect classification)
- [ ] All 4 phases complete
- [ ] Final output artifacts are structurally complete
- [ ] Output contract satisfied: all 7 context keys set
