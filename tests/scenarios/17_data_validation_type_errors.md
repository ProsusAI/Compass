# Scenario: Data Validation — Type Errors and Null Values

## Setup
- Dataset: `tests/scenarios/data/type_errors_dataset.jsonl`

## Scenario Description
The dataset has multiple type violations: a numeric id (row 1), a numeric input (row 2), string cost/quality values (row 3), and null cost/quality values (row 4). The Data Validation agent should detect the `types` and `null_fields` schema violations.

## User Simulator
You are a pipeline orchestrator triggering the data validation step.

**Your knowledge:**
- Dataset: `tests/scenarios/data/type_errors_dataset.jsonl`
- Problem description: "Route queries to haiku, sonnet, or opus by complexity."

**Behavior:**
- Provide the dataset path and ask the data validation agent to validate it.

**Opening message:** "Please validate the dataset at `tests/scenarios/data/type_errors_dataset.jsonl` for routing optimization."

## Verification Criteria

### Tool output (structured JSON from `validate_dataset`)
- [ ] `validate_dataset` tool was called with the dataset path
- [ ] Schema finding `types` has status `fail` and severity `critical`, with multiple row indices
- [ ] Type errors detected for: numeric id (row 1), numeric input (row 2), string cost/quality_score (row 3)
- [ ] Schema finding `null_fields` has status `fail` and severity `warning` — null values in cost/quality_score (row 4)

### Agent narrative (data quality report written by the agent)
- [ ] Agent's report explains the specific type violations found
- [ ] Agent's report flags the type errors as critical schema issues — types must match the format spec
