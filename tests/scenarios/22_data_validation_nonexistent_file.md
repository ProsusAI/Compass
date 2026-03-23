# Scenario: Data Validation — Nonexistent Dataset File

## Setup
- No dataset file (path does not exist)

## Scenario Description
The Data Validation agent is asked to validate a dataset file that does not exist on disk. The `validate_dataset` tool should return a clear error. The agent should report the failure and indicate that the dataset path needs to be corrected.

## User Simulator
You are a pipeline orchestrator triggering the data validation step with a bad path.

**Your knowledge:**
- Dataset path: `tests/scenarios/data/this_file_does_not_exist.jsonl`
- Problem description: "Route queries to model tiers."

**Behavior:**
- Provide the nonexistent dataset path and ask for validation.

**Opening message:** "Please validate the dataset at `tests/scenarios/data/this_file_does_not_exist.jsonl` for our routing pipeline."

## Verification Criteria
- [ ] `validate_dataset` tool was called with the nonexistent path
- [ ] Tool returned an error containing "Dataset file not found"
- [ ] Agent reported the failure clearly — the file does not exist
- [ ] Agent did NOT produce a data quality report (no data to validate)
- [ ] Agent indicated the dataset path needs to be corrected
