# Scenario: Data Validation — Duplicate IDs Detected

## Setup
- Dataset: `tests/scenarios/data/duplicate_ids_dataset.jsonl`

## Scenario Description
The dataset has 5 rows but only 3 unique IDs — id "1" appears twice and id "2" appears twice. The Data Validation agent should detect the `unique_ids` schema violation, flagging the rows with duplicate IDs.

## User Simulator
You are a pipeline orchestrator triggering the data validation step.

**Your knowledge:**
- Dataset: `tests/scenarios/data/duplicate_ids_dataset.jsonl`
- Problem description: "Route queries to haiku, sonnet, or opus by complexity."

**Behavior:**
- Provide the dataset path and ask the data validation agent to validate it.

**Opening message:** "Please validate the dataset at `tests/scenarios/data/duplicate_ids_dataset.jsonl` for our routing optimization."

## Verification Criteria

### Tool output (structured JSON from `validate_dataset`)
- [ ] `validate_dataset` tool was called with the dataset path
- [ ] Schema finding `unique_ids` has status `fail` and severity `critical`
- [ ] The failing row indices include rows 2 and 4 (0-indexed — the second occurrence of ids "1" and "2")
- [ ] Other schema checks (required_keys, types, route_in_routes, non_empty_routes) pass

### Agent narrative (data quality report written by the agent)
- [ ] Agent's report explains that duplicate id values were found
- [ ] Agent's report flags this as a critical issue — IDs must be unique for deduplication and result tracking
