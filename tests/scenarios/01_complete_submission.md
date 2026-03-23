# Scenario: Complete Submission

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides all required and optional fields in a single message. The agent should produce a validated input report immediately with status `proceed` — no clarification needed, no defaults applied.

## User Simulator
You are a data analyst at a tech company. You are setting up a routing optimization pipeline and have all the information ready.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl` — 5 labeled routing examples mapping queries to haiku/sonnet/opus tiers by complexity.
- Problem description: "Route customer queries to haiku/sonnet/opus tiers based on complexity — simple factual questions to haiku, moderate tasks to sonnet, complex reasoning to opus."
- Target metrics: `accuracy >= 0.90`
- Evaluation threshold: `0.85`
- Data split ratio: `0.25`
- Max iterations: `5`

**Behavior:** Provide all of the above in your opening message. Be clear and direct. Do not withhold any information.

**Opening message:** "Hi, I'd like to set up routing optimization. Here's what I have: my dataset is at `tests/scenarios/data/valid_dataset.jsonl` — it has 5 labeled examples mapping queries to haiku, sonnet, or opus tiers based on complexity. The problem is to route customer queries to the right tier: simple factual questions go to haiku, moderate tasks to sonnet, and complex reasoning to opus. I want to optimize for accuracy with a threshold of at least 90% (`accuracy >= 0.90`). Use an evaluation threshold of 0.85, a data split ratio of 0.25, and cap it at 5 iterations."

## Verification Criteria
- [ ] Report status is `proceed`
- [ ] Confirmed Inputs contains the dataset path `tests/scenarios/data/valid_dataset.jsonl`
- [ ] Confirmed Inputs contains the problem description about routing queries to haiku/sonnet/opus by complexity
- [ ] Confirmed Inputs lists `accuracy >= 0.90` as target metric
- [ ] Confirmed Inputs includes evaluation threshold (0.85), data split ratio (0.25), and max iterations (5)
- [ ] No `## Gap Report` heading appears in the report
- [ ] No `## Assumed Defaults` heading appears in the report
- [ ] Single turn — agent produced the report without asking clarification questions
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description
