# Scenario: Ambiguous Tiers — Choose Question Type

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user mentions "cheap and expensive models" without specifying concrete tier names. The agent should recognize the ambiguity and use the "choose" question type — presenting multiple-choice options for what the tiers might be, with an open-ended escape option.

## User Simulator
You are a developer who thinks in terms of "cheap model" and "expensive model" but hasn't mapped these to specific product names.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- When presented with options: you're using haiku as the cheap tier and opus as the expensive tier. Select that option.
- You have NO preferences for optional fields.

**Behavior:**
- Opening message mentions cheap/expensive models without naming them.
- When the agent presents options, pick the one that matches haiku/opus (or describe it if it's "none of these").
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I have a dataset at `tests/scenarios/data/valid_dataset.jsonl`. I need to route queries between my cheap and expensive models. Cheap for the easy stuff, expensive for the hard stuff."

## Verification Criteria
- [ ] Agent recognized the ambiguity in "cheap and expensive models"
- [ ] Agent presented multiple-choice options (e.g., "Are these tiers like Haiku/Sonnet/Opus, or custom endpoints, or something else?")
- [ ] Options included a "none of these" or open-ended escape
- [ ] Final problem description in the report includes the concrete tier names the user selected
- [ ] Final report status is `proceed_with_defaults`
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description
