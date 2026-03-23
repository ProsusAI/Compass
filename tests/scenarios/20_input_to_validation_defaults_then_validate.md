# Scenario: Input → Data Validation — Defaults Applied Then Validated

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides only the required fields (dataset and problem description), omitting all optional fields. The User Input agent applies defaults and produces a report with status `proceed_with_defaults`. The Data Validation agent then validates the dataset. This tests that the defaulting mechanism does not interfere with validation.

## User Simulator
You are a data analyst who knows the routing problem but hasn't specified any optional parameters.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- Problem description: "Route queries to haiku, sonnet, or opus based on complexity — simple lookups to haiku, moderate tasks to sonnet, complex reasoning to opus."
- You have NO preferences for metrics, thresholds, split ratios, or iteration limits.

**Behavior:**
- Provide the dataset and problem description in your opening message.
- Do NOT mention metrics, thresholds, split ratios, or iterations.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I want to optimize my routing. My dataset is at `tests/scenarios/data/valid_dataset.jsonl`. The routing logic is: simple lookups go to haiku, moderate tasks to sonnet, and complex reasoning to opus."

## Verification Criteria
- [ ] User Input agent produced a report with status `proceed_with_defaults`
- [ ] Assumed Defaults table includes target_metrics, evaluation_threshold, data_split_ratio, and max_iterations
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description
- [ ] `validate_dataset` tool was called with `tests/scenarios/data/valid_dataset.jsonl`
- [ ] Data validation report shows all schema findings with status `pass`
- [ ] Defaulted optional fields (metrics, thresholds, etc.) did not affect validation results
- [ ] Both agents ran in sequence — input report finalized before validation started
