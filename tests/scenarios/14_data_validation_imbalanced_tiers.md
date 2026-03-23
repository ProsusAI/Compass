# Scenario: Data Validation — Imbalanced Tier Distribution

## Setup
- Dataset: `tests/scenarios/data/imbalanced_dataset.jsonl`

## Scenario Description
The dataset has 10 rows: 9 routed to haiku and 1 to opus. The Data Validation agent should detect the volume inadequacy for opus (1 row < minimum 5) and flag it. The schema itself is valid so all schema findings pass, but the volume assessment fails because opus has insufficient examples.

## User Simulator
You are a pipeline orchestrator triggering the data validation step.

**Your knowledge:**
- Dataset: `tests/scenarios/data/imbalanced_dataset.jsonl`
- Problem description: "Route queries to haiku or opus based on complexity."

**Behavior:**
- Provide the dataset path and ask the data validation agent to validate it.

**Opening message:** "Please validate the dataset at `tests/scenarios/data/imbalanced_dataset.jsonl`. We're routing queries to haiku or opus based on complexity."

## Verification Criteria
- [ ] `validate_dataset` tool was called with the dataset path
- [ ] All schema findings have status `pass`
- [ ] Label distribution shows 2 tiers (haiku, opus)
- [ ] Label distribution total_records = 10
- [ ] Volume assessment overall_verdict = `fail`
- [ ] Volume assessment shows haiku as `adequate` (9 >= 5) and opus as `insufficient` (1 < 5)
- [ ] Report flags the volume inadequacy as a warning — opus tier lacks sufficient examples
- [ ] Report does NOT block the dataset as critically broken — schema is valid
