# Scenario: Mixed Blocking and Non-Blocking Gaps

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides a clear problem description but no dataset and no optional fields. The agent should ask only about the blocking gap (dataset) and silently apply defaults for the non-blocking optional fields.

## User Simulator
You are a data scientist who has the routing problem well understood but forgot the dataset and hasn't specified any optional parameters.

**Your knowledge:**
- Problem description: "Our system routes API requests to haiku, sonnet, or opus based on task complexity. Straightforward lookups and translations go to haiku, summarization and moderate analysis to sonnet, and complex multi-step reasoning to opus. We want to optimize this routing for cost efficiency."
- Dataset path (provide when asked): `tests/scenarios/data/valid_dataset.jsonl`
- You have NO preferences for optional fields.

**Behavior:**
- Provide only the problem description in your opening message — no dataset, no optional fields.
- When the agent asks about the dataset, provide the path.
- Do NOT volunteer optional field preferences.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I need help optimizing our model routing. Our system routes API requests to haiku, sonnet, or opus based on task complexity. Straightforward lookups and translations go to haiku, summarization and moderate analysis to sonnet, and complex multi-step reasoning to opus. We want to optimize this routing for cost efficiency."

## Verification Criteria
- [ ] Agent asked about the dataset (blocking gap)
- [ ] Agent never asked about optional fields (non-blocking — defaults applied)
- [ ] Final report status is `proceed_with_defaults`
- [ ] Gap Report contains both blocking-resolved and non-blocking entries
- [ ] Assumed Defaults table lists all four optional field defaults
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description
