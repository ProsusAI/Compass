# Scenario: Malformed Dataset

> **DEFERRED:** This scenario depends on the Data Validation agent (THP-73), which is not yet implemented. The system prompt currently says "accept the dataset path as-is," so this test would not produce meaningful results. Un-defer when THP-73 lands.

## Setup
- Malformed dataset: `tests/scenarios/data/no_expected_field.jsonl`
- Corrected dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides all fields including a dataset, but the dataset is structurally invalid — records are missing the `expected` field. The agent should detect the structural issue (via the Data Validation agent), surface it using the "fix" question type, and guide the user to provide a corrected dataset.

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
- [ ] Agent identified that the dataset is missing the `expected` field
- [ ] Agent used a "fix" style question — explained the issue, showed what's needed
- [ ] Agent did not reject the submission outright — guided the user to fix it
- [ ] Final report references the corrected dataset path `tests/scenarios/data/valid_dataset.jsonl`
- [ ] Final report status is `proceed_with_defaults`
- [ ] Agent called `submit_input_report` tool with the report, corrected dataset path, and problem description
