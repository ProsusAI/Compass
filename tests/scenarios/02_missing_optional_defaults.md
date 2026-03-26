# Scenario: Missing Optional Fields — Proceed with Defaults

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides both required fields (dataset and problem description) but omits all optional fields (target metrics, evaluation threshold, data split ratio, max iterations). The agent should apply defaults for the missing optional fields, mention them conversationally, and ask the user if the defaults are acceptable before finalizing.

## User Simulator
You are a data analyst who knows the routing problem well but hasn't thought about metrics or thresholds yet.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- Problem description: "We route incoming customer queries to either haiku, sonnet, or opus depending on how complex the query is. Simple lookups go to haiku, multi-step tasks go to sonnet, and open-ended reasoning goes to opus."
- You have NO preferences for metrics, thresholds, split ratios, or iteration limits.

**Behavior:**
- Provide the dataset and problem description in your opening message.
- Do NOT mention metrics, thresholds, split ratios, or iterations.
- If the agent mentions assumed defaults and asks whether they are acceptable, confirm that they are fine.

**Opening message:** "Hi, I want to optimize my routing setup. My dataset is at `tests/scenarios/data/valid_dataset.jsonl` — it has labeled examples of queries routed to haiku, sonnet, or opus tiers. The routing logic is based on complexity: simple lookups go to haiku, multi-step tasks to sonnet, and open-ended reasoning to opus."

## Verification Criteria
- [ ] Report status is `proceed_with_defaults`
- [ ] Confirmed Inputs contains dataset path and problem description
- [ ] Confirmed Inputs does NOT have subsections for Target Metrics, Evaluation Threshold, Data Split Ratio, or Max Iterations (these were all defaulted, so they belong in Assumed Defaults)
- [ ] Gap Report lists `target_metrics` as `non-blocking` with default `["f1/macro"]`
- [ ] Gap Report lists `evaluation_threshold` as `non-blocking` with default `0.80`
- [ ] Gap Report lists `data_split_ratio` as `non-blocking` with default `0.70`
- [ ] Gap Report lists `max_iterations` as `non-blocking` with default `10`
- [ ] Assumed Defaults table contains all four defaults with correct values
- [ ] Agent did NOT ask about optional fields before producing the report — applied defaults rather than treating them as blocking
- [ ] Agent conversationally mentioned the assumed defaults alongside the report
- [ ] Agent asked whether the assumed defaults are acceptable or if the user wants to adjust them
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description
