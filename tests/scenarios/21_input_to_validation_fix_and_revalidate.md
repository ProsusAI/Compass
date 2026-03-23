# Scenario: Input → Data Validation — Fix Dataset and Revalidate

## Setup
- Broken dataset: `tests/scenarios/data/type_errors_dataset.jsonl`
- Corrected dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides a dataset with type errors. The User Input agent collects the inputs and submits the report. The Data Validation agent runs and finds critical schema violations (wrong types, null values). The issue is surfaced to the user, who provides a corrected dataset path. The Data Validation agent re-validates the corrected dataset and it passes.

## User Simulator
You are a data analyst who accidentally provided a dataset with formatting issues from a broken export pipeline.

**Your knowledge:**
- Original (broken) dataset: `tests/scenarios/data/type_errors_dataset.jsonl`
- Corrected dataset (provide when told about the issue): `tests/scenarios/data/valid_dataset.jsonl`
- Problem description: "Route queries to haiku, sonnet, or opus based on complexity."

**Behavior:**
- Provide the broken dataset path and problem description in your opening message.
- When the agent explains the type/null issues, acknowledge the mistake and provide the corrected dataset path.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I'd like to optimize routing. My dataset is at `tests/scenarios/data/type_errors_dataset.jsonl` and the problem is routing queries to haiku, sonnet, or opus based on complexity."

## Verification Criteria
- [ ] `validate_dataset` was called on `type_errors_dataset.jsonl` (first attempt)
- [ ] First validation detected `types` schema finding with status `fail`
- [ ] First validation detected `null_fields` schema finding with status `fail`
- [ ] The type/null issues were explained to the user
- [ ] After the user provided the corrected path, `validate_dataset` was called on `valid_dataset.jsonl`
- [ ] Second validation shows all schema findings with status `pass`
- [ ] Final report references `valid_dataset.jsonl` as the dataset
- [ ] Agent called `submit_input_report` with the corrected dataset path
