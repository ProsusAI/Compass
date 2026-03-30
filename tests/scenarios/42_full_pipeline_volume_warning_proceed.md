# Scenario: Full Pipeline — Volume Warning, User Proceeds, Analysis Copes

## Setup
- Dataset: `tests/scenarios/data/small_dataset.jsonl`
- System prompt (input): `odysseus/agents/prompts/user_input_system.md`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- MCP tools: `submit_input_report`, `validate_dataset`

## Scenario Description
The user provides an intentionally tiny dataset (2 rows, 2 tiers). Data Validation produces a volume `fail` verdict. The user is warned but insists on proceeding. Tests graceful handling of extreme edge cases and that volume failures are surfaced as warnings rather than hard blockers.

## User Simulator
You are a data analyst who wants to test the pipeline with minimal data despite warnings.

**Your knowledge:**
- Dataset: `tests/scenarios/data/small_dataset.jsonl` — 2 rows (1 haiku, 1 opus)
- Problem description: "Route queries to haiku or opus based on complexity."
- You are aware the dataset is tiny and want to proceed anyway.

**Behavior:**
- Provide the dataset and problem description in your opening message.
- When warned about volume inadequacy, insist on proceeding: "I know it's small, but I want to test the pipeline anyway. Please proceed."
- When the agent mentions assumed defaults, confirm they are fine.

**Opening message:** "I'd like to optimize routing. My dataset is at `tests/scenarios/data/small_dataset.jsonl` — just 2 examples. The problem is routing queries to haiku or opus based on complexity."

## Verification Criteria

### Stage 1 — User Input
- [ ] Input agent collected inputs and called `submit_input_report`

### Stage 2 — Data Validation
- [ ] `validate_dataset` called with `tests/scenarios/data/small_dataset.jsonl`
- [ ] Volume assessment overall_verdict is `fail`
- [ ] Volume failure surfaced clearly to the user
- [ ] User acknowledged and requested to proceed

### Pipeline Integrity
- [ ] Volume failure is surfaced clearly to the user (not silently swallowed)
- [ ] Pipeline does not hard-block on volume warning — user can acknowledge and continue
