# Scenario: Multiple Blocking Gaps

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides a vague opening with neither a real problem description nor a dataset. Both required fields are missing. The agent should ask one question at a time in priority order: problem description first (priority 1), then dataset (priority 2).

## User Simulator
You are a manager who heard about the routing optimizer and wants to try it, but hasn't prepared any details yet.

**Your knowledge:**
- Problem description (provide when asked): "We route user requests to different Claude model tiers — haiku, sonnet, and opus — based on the complexity of the task. Simple questions go to haiku, moderate analysis to sonnet, and complex creative or reasoning tasks to opus."
- Dataset path (provide when asked): `tests/scenarios/data/valid_dataset.jsonl`
- You have NO preferences for optional fields.

**Behavior:**
- Your opening message is vague — you want to optimize routing but don't provide specifics.
- When the agent asks about the problem, describe the model-tier routing setup.
- When the agent asks about the dataset, provide the path.
- Do NOT volunteer information before being asked.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I want to optimize my routing."

## Verification Criteria
- [ ] Agent did NOT dump both gaps in a single message
- [ ] Agent asked about the problem description before the dataset (priority order)
- [ ] Each turn focused on a single gap (not multiple unrelated questions)
- [ ] Final report status is `proceed_with_defaults`
- [ ] Confirmed Inputs contains both the problem description and dataset path
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
