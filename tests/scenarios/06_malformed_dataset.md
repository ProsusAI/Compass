# Scenario: Malformed Dataset — Data Validation Catches Missing Fields

## Setup
- Malformed dataset: `tests/scenarios/data/no_expected_field.jsonl`
- Corrected dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides all fields including a dataset, but the dataset is structurally invalid — records are missing the `expected` field. After the User Input agent collects the inputs and calls `submit_input_report`, the Data Validation agent runs `validate_dataset` on the dataset. The validation report shows critical schema failures (missing required keys). The User Input agent surfaces the issue to the user and guides them to provide a corrected dataset. After receiving the corrected path, the Data Validation agent re-validates the new dataset successfully.

## User Simulator
You are a data analyst who accidentally exported the dataset without the label column.

**Your knowledge:**
- Original (broken) dataset: `tests/scenarios/data/no_expected_field.jsonl`
- Corrected dataset path (provide when told about the issue): `tests/scenarios/data/valid_dataset.jsonl`
- Problem description: "Route queries to haiku, sonnet, or opus based on complexity."

**Behavior:**
- Provide the broken dataset path and problem description in your opening message.
- When the agent explains the structural issue, acknowledge the mistake and provide the corrected dataset path.

**Opening message:** "Hi, I'd like to optimize my routing. My dataset is at `tests/scenarios/data/no_expected_field.jsonl` and the problem is routing queries to haiku, sonnet, or opus based on complexity."

## Verification Criteria
- [ ] `validate_dataset` was called on the original dataset (`no_expected_field.jsonl`)
- [ ] Data validation report identified `required_keys` schema finding with status `fail`
- [ ] Agent surfaced the missing `expected` field issue to the user — explained what's needed
- [ ] Agent did not reject the submission outright — guided the user to fix it
- [ ] After the user provided the corrected path, `validate_dataset` was called on `valid_dataset.jsonl`
- [ ] Second validation returned all schema findings with status `pass`
- [ ] Final report references the corrected dataset path `tests/scenarios/data/valid_dataset.jsonl`
- [ ] Final report status is `proceed_with_defaults`
- [ ] Agent called `submit_input_report` tool with the report, corrected dataset path, and problem description
