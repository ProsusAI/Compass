# Scenario: Data Validation — Insufficient Volume Per Tier

## Setup
- Dataset: `tests/scenarios/data/small_dataset.jsonl`

## Scenario Description
The dataset has only 2 rows — 1 haiku and 1 opus. Both tiers are below the minimum of 5 per tier. The schema is valid, but the volume assessment should fail for both tiers. The Data Validation agent should warn that results will be unreliable with so few examples.

## User Simulator
You are a pipeline orchestrator triggering the data validation step.

**Your knowledge:**
- Dataset: `tests/scenarios/data/small_dataset.jsonl`
- Problem description: "Route queries to haiku or opus by complexity."

**Behavior:**
- Provide the dataset path and ask the data validation agent to validate it.

**Opening message:** "Please validate the dataset at `tests/scenarios/data/small_dataset.jsonl`. We're routing queries to haiku or opus."

## Verification Criteria

### Tool output (structured JSON from `validate_dataset`)
- [ ] `validate_dataset` tool was called with the dataset path
- [ ] All schema findings have status `pass` — the data is structurally valid
- [ ] Volume assessment overall_verdict = `fail`
- [ ] Both tiers show verdict `insufficient` (1 < minimum 5)
- [ ] Label distribution total_records = 2
- [ ] Query length count = 2

### Agent narrative (data quality report written by the agent)
- [ ] Agent's report warns that the dataset is too small for reliable evaluation
- [ ] Agent's report does NOT flag any schema-level critical issues
