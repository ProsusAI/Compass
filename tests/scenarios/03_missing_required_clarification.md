# Scenario: Missing Required Field — Clarification Loop

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides a clear problem description but forgets to include the dataset. The agent should detect the missing required field, ask for it (without dumping all gaps at once), and produce the report after the user provides it.

## User Simulator
You are a data analyst who has been thinking about the routing problem but forgot to attach the dataset.

**Your knowledge:**
- Problem description: "We have a three-tier model routing system — haiku for cheap/fast queries, sonnet for moderate complexity, opus for deep reasoning tasks. We want to optimize the routing decisions to minimize cost while maintaining quality."
- Dataset path (provide when asked): `tests/scenarios/data/valid_dataset.jsonl`
- You have NO preferences for optional fields (metrics, threshold, split ratio, iterations).

**Behavior:**
- In your opening message, describe the routing problem clearly but do NOT mention any dataset.
- When the agent asks about the dataset, provide the path.
- Do NOT volunteer optional field values at any point.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I'm working on a routing optimization project. We have a three-tier model routing system — haiku for cheap/fast queries, sonnet for moderate complexity, and opus for deep reasoning tasks. We want to optimize the routing decisions to minimize cost while maintaining quality."

## Verification Criteria
- [ ] Agent asked about the dataset (not all gaps at once)
- [ ] Agent did not ask about optional fields
- [ ] Conversation took at least 2 turns before the report was produced
- [ ] Final report status is `proceed_with_defaults`
- [ ] Confirmed Inputs contains the dataset path provided in the follow-up
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description
