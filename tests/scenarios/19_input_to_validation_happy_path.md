# Scenario: Input → Data Validation — Full Happy Path

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
End-to-end integration: the user provides all required fields, the User Input agent collects inputs and produces a validated input report with status `proceed`, then the Data Validation agent validates the referenced dataset. Both stages succeed with no issues. This tests the complete handoff between the two agents.

## User Simulator
You are a data analyst with all information ready for the routing optimization pipeline.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl` — 5 labeled routing examples mapping queries to haiku/sonnet/opus tiers by complexity.
- Problem description: "Route customer queries to haiku, sonnet, or opus tiers based on complexity — simple factual questions to haiku, moderate tasks to sonnet, complex reasoning to opus."
- Target metrics: `accuracy >= 0.90`
- Evaluation threshold: `0.85`
- Data split ratio: `0.25`
- Max iterations: `5`

**Behavior:** Provide all of the above in your opening message. Be clear and direct.

**Opening message:** "Hi, I'd like to set up routing optimization. My dataset is at `tests/scenarios/data/valid_dataset.jsonl` with 5 labeled examples mapping queries to haiku, sonnet, or opus by complexity. The problem is to route customer queries to the right tier: simple factual questions go to haiku, moderate tasks to sonnet, and complex reasoning to opus. I want accuracy of at least 90%, evaluation threshold 0.85, data split ratio 0.25, and max 5 iterations."

## Verification Criteria
- [ ] User Input agent collected all fields and produced a report with status `proceed`
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description
- [ ] `validate_dataset` tool was called with `tests/scenarios/data/valid_dataset.jsonl`
- [ ] Data validation report shows all 7 schema findings with status `pass`
- [ ] Label distribution shows 3 tiers with total_records = 5
- [ ] Volume assessment overall_verdict = `fail` (some tiers have < 5 examples — only 5 total rows across 3 tiers)
- [ ] Volume warning is surfaced but does not block the pipeline
- [ ] Query length stats are present and count = 5
- [ ] Both agents operated in sequence — input collection completed before validation ran
