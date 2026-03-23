# Scenario: Vague Problem Description — Needs Refinement

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides a dataset but only a vague problem description. The agent should recognize that "route stuff to the right place" is insufficient, engage in comprehension-first questioning to understand the routing problem, and produce a report with a refined description.

## User Simulator
You are a product manager who knows the routing system well but described it vaguely because you assumed the tool would figure it out.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- Actual routing context (share when asked): You route customer support queries to three Claude model tiers — haiku for simple FAQ-style questions, sonnet for moderately complex troubleshooting, and opus for deep technical investigations. Cost matters more than perfect accuracy for simple queries — you'd rather occasionally misroute a simple query to sonnet than pay opus prices for everything.
- You have NO preferences for optional fields.

**Behavior:**
- Opening message is deliberately vague about the problem.
- When the agent asks clarifying questions about tiers, request types, or trade-offs, share the details from your knowledge.
- Respond naturally and conversationally — don't recite a spec.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "Hey, I've got a dataset at `tests/scenarios/data/valid_dataset.jsonl` and I want to route stuff to the right place. Can you help me optimize this?"

## Verification Criteria
- [ ] Agent did not accept "route stuff to the right place" as a valid problem description
- [ ] Agent asked at least one clarifying question about the routing context (what types of requests, what tiers, what trade-offs)
- [ ] Final report contains a refined, specific problem description — not the original vague input
- [ ] The refined description mentions concrete tiers or tools (haiku, sonnet, opus)
- [ ] The refined description reflects the information the user provided during clarification
- [ ] Final report status is `proceed_with_defaults`
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description
