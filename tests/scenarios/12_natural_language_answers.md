# Scenario: Natural Language Answers — Non-Standard Format

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides all required information in a single rambling, conversational message rather than in structured field-value format. The agent should extract the relevant information without asking the user to reformat or re-provide anything.

## User Simulator
You are a chatty colleague who explains everything in a stream-of-consciousness style.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- Problem: routing queries to haiku/opus by complexity
- Metric: accuracy, at least 90%
- No preferences for other optional fields.

**Behavior:**
- Provide everything in one big rambling message.
- If the agent asks you to reformat or re-provide information, push back: "I already told you all of that."
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "So basically we have this JSONL file at `tests/scenarios/data/valid_dataset.jsonl` and what we're trying to do is figure out which queries should go to the cheap model and which ones need the expensive one, you know? Like simple stuff goes to haiku and the hard questions go to opus. Oh and we care about accuracy, like at least 90%."

## Verification Criteria
- [ ] Agent extracted the dataset path from the conversational message
- [ ] Agent extracted the problem description from the natural language
- [ ] Agent extracted the metric spec (`accuracy >= 0.90`) from informal phrasing
- [ ] Agent did not ask the user to reformat or re-provide information already given
- [ ] Final report contains the extracted information in clean, structured form
- [ ] Final report status is `proceed_with_defaults` (user provided dataset, problem description, and target metric, but not threshold, split ratio, or iterations — those get defaults)
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
