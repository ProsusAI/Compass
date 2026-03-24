# Scenario: Full Pipeline — Defaults Cascade to Routing Analysis

## Setup
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- System prompt (input): `odysseus/agents/prompts/user_input_system.md`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- System prompt (routing analysis): `odysseus/agents/prompts/routing_analysis_system.md`
- Skills: `odysseus/skills/classify-example/SKILL.md`, `odysseus/skills/generate-routing-rationale/SKILL.md`, `odysseus/skills/check-semantic-overlap/SKILL.md`
- MCP tools: `submit_input_report`, `validate_dataset`, `create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`

## Scenario Description
The user provides only a dataset path and a one-line problem description — no metrics, thresholds, split ratios, or iteration limits. The User Input agent applies all defaults (data_split_ratio 0.20, evaluation_threshold 0.80, max_iterations 10). Data Validation runs normally. Routing Analysis inherits the defaulted split ratio for Phase 4. Tests that defaults propagate correctly across all 3 agents.

## User Simulator
You are a data analyst who knows the routing problem but hasn't thought about optional parameters.

**Your knowledge:**
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- Problem description: "Route queries to haiku, sonnet, or opus based on complexity."
- You have NO preferences for metrics, thresholds, split ratios, or iterations.

**Behavior:**
- Provide the dataset and problem description in your opening message.
- Do NOT mention metrics, thresholds, split ratios, or iterations.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I want to optimize my routing. My dataset is at `tests/scenarios/data/rationale_test_dataset.jsonl`. The routing logic is: simple lookups go to haiku, moderate tasks to sonnet, and complex reasoning to opus."

## Verification Criteria

### Stage 1 — User Input
- [ ] Input agent detected missing optional fields and applied defaults
- [ ] `submit_input_report` shows default values: data_split_ratio 0.20, evaluation_threshold 0.80, max_iterations 10

### Stage 2 — Data Validation
- [ ] `validate_dataset` called, all schema findings pass
- [ ] Defaults did not affect validation results

### Stage 3 — Routing Analysis
- [ ] Routing Analysis reads the split ratio from the validated input report
- [ ] Phase 4 `stratified_split` uses the defaulted dev_ratio (0.80 dev / 0.20 holdout) from the input report — this matches the routing analysis agent's internal default, confirming the input report value flows through correctly
- [ ] Dev/holdout split proportions match the defaulted ratio (8 dev, 2 holdout for 10 rows)
- [ ] All 4 phases complete
- [ ] Output contract satisfied: all 7 context keys set
