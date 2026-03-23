# Scenario: Data Validation — Clean Dataset Passes All Checks

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The User Input agent has already collected the problem specification and produced a validated input report. The Data Validation agent now runs against a structurally valid dataset. All schema findings should pass, label distribution should show three balanced tiers, and the overall report should indicate the dataset is ready for downstream processing.

## User Simulator
You are a pipeline orchestrator triggering the data validation step.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- Problem description: "Route customer queries to haiku, sonnet, or opus tiers based on complexity."

**Behavior:**
- Provide the dataset path and ask the data validation agent to validate it.

**Opening message:** "Please validate the dataset at `tests/scenarios/data/valid_dataset.jsonl` for our routing optimization pipeline. The problem is routing customer queries to haiku, sonnet, or opus based on complexity."

## Verification Criteria

### Tool output (structured JSON from `validate_dataset`)
- [ ] `validate_dataset` tool was called with the dataset path
- [ ] All 7 schema findings have status `pass` (required_keys, types, route_in_routes, non_empty_routes, consistent_model_set, unique_ids, null_fields)
- [ ] Label distribution shows 3 tiers (haiku, sonnet, opus)
- [ ] Label distribution total_records = 5
- [ ] Query length count = 5

### Agent narrative (data quality report written by the agent)
- [ ] Agent's report describes the dataset as ready for downstream processing
- [ ] Agent's report does not flag any critical issues or blocking warnings
