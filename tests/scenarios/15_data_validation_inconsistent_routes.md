# Scenario: Data Validation — Inconsistent Model Sets Across Rows

## Setup
- Dataset: `tests/scenarios/data/inconsistent_routes_dataset.jsonl`

## Scenario Description
The dataset mixes two different route key sets: rows 1, 2, 5 use haiku/sonnet/opus while rows 3, 4 use gpt4/gpt35. The Data Validation agent should detect the `consistent_model_set` schema violation, flagging the rows that deviate from the reference set established by the first row.

## User Simulator
You are a pipeline orchestrator triggering the data validation step.

**Your knowledge:**
- Dataset: `tests/scenarios/data/inconsistent_routes_dataset.jsonl`
- Problem description: "Route queries to the appropriate model tier."

**Behavior:**
- Provide the dataset path and ask the data validation agent to validate it.

**Opening message:** "Please validate the dataset at `tests/scenarios/data/inconsistent_routes_dataset.jsonl`. We're setting up a routing optimization pipeline."

## Verification Criteria

### Tool output (structured JSON from `validate_dataset`)
- [ ] `validate_dataset` tool was called with the dataset path
- [ ] Schema finding `consistent_model_set` has status `fail` and severity `critical`
- [ ] The failing row indices include rows 2 and 3 (0-indexed — the gpt4/gpt35 rows)
- [ ] Other schema checks (required_keys, types, unique_ids) pass for all rows

### Agent narrative (data quality report written by the agent)
- [ ] Agent's report explains the inconsistency: some rows use haiku/sonnet/opus, others use gpt4/gpt35
- [ ] Agent's report flags this as a critical schema issue — the dataset has mixed model definitions
