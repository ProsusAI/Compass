# Scenario: Persistent Clarification — Unhelpful Answers

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user gives vague, unhelpful, or off-topic answers for the first several turns. The agent should persist — rephrasing questions, approaching from different angles — without giving up or producing a premature report.

## User Simulator
You are a busy executive who wants results but doesn't want to spend time on details. You will eventually cooperate but need the agent to earn your engagement.

**Your knowledge:**
- Problem description (provide on turn 4+): "We route incoming API requests to haiku, sonnet, or opus based on how complex the query is. Simple stuff to haiku, hard stuff to opus."
- Dataset path (provide on turn 5+): `tests/scenarios/data/valid_dataset.jsonl`
- You have NO preferences for optional fields.

**Behavior:**
- Turn 1 (opening): Be vague — you want to optimize something.
- Turn 2: Deflect — "just make it work" or "I don't have time for this, can't you figure it out?"
- Turn 3: Give a slightly more useful but still insufficient answer — "it's about routing queries" without specifying tiers or trade-offs.
- Turn 4+: Start cooperating. Provide the problem description when the agent asks in a way that resonates.
- Turn 5+: Provide the dataset path when asked.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I need to optimize something. Can you help?"

## Verification Criteria
- [ ] Agent did not give up after unhelpful answers
- [ ] Agent did not produce a report without the required fields
- [ ] Agent rephrased or approached the question differently after each unhelpful answer
- [ ] Agent remained conversational and patient — not robotic or repetitive
- [ ] Final report was eventually produced with status `proceed_with_defaults`
- [ ] Conversation took at least 4 turns
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
