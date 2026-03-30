# Scenario: Full Pipeline — Dataset Fix Mid-Pipeline, Then Full Validation

## Setup
- Broken dataset: `tests/scenarios/data/type_errors_dataset.jsonl`
- Corrected dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- System prompt (input): `odysseus/agents/prompts/user_input_system.md`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- MCP tools: `submit_input_report`, `validate_dataset`

## Scenario Description
The user provides a dataset with type errors. The User Input agent collects inputs and submits. Data Validation catches critical type errors. The user provides a corrected dataset path. Re-validation passes. Tests mid-pipeline recovery and that validation receives the final corrected dataset with no residual state from the failed validation.

## User Simulator
You are a data analyst who accidentally provided a dataset from a broken export pipeline.

**Your knowledge:**
- Original (broken) dataset: `tests/scenarios/data/type_errors_dataset.jsonl`
- Corrected dataset (provide when told about issues): `tests/scenarios/data/rationale_test_dataset.jsonl`
- Problem description: "Route queries to haiku, sonnet, or opus based on complexity."

**Behavior:**
- Provide the broken dataset path and problem description in your opening message.
- When the agent explains the type/null issues, acknowledge the mistake and provide the corrected dataset path.
- When the agent mentions assumed defaults, confirm they are fine.

**Opening message:** "I'd like to optimize routing. My dataset is at `tests/scenarios/data/type_errors_dataset.jsonl` and the problem is routing queries to haiku, sonnet, or opus based on complexity."

## Verification Criteria

### Stage 1 — User Input
- [ ] Input agent collected inputs and called `submit_input_report`

### Stage 2 — Data Validation (first attempt)
- [ ] First `validate_dataset` call was on `tests/scenarios/data/type_errors_dataset.jsonl`
- [ ] First validation detected critical failures (types and/or null_fields)
- [ ] Issues were explained to the user

### Stage 2 — Data Validation (second attempt)
- [ ] After user provided corrected path, `validate_dataset` was called on `tests/scenarios/data/rationale_test_dataset.jsonl`
- [ ] Second validation shows all schema findings with status `pass`
- [ ] routing_context is derived from the corrected dataset

### Pipeline Integrity
- [ ] No residual state from the failed first validation leaks into subsequent processing
- [ ] routing_context is derived from the corrected dataset (not the broken one)
