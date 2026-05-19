# Scenario: Domain Mismatch — Non-Routing Problem Rejected at Stage 1

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- System prompts: `odysseus_routing_input`
- MCP tools: `submit_input_report`, `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage`

## Scenario Description
The user describes a sentiment classification problem, not a routing problem. They want to classify customer reviews as positive, negative, or neutral — not to route queries to model tiers based on complexity. The User Input agent must detect that this is not a routing optimization problem and reject it at Stage 1 with an appropriate explanation.

No downstream stages (Data Validation, Backend Setup, Prompt Builder, Holdout Validation, Final Report) should execute. The pipeline stops at Stage 1. This validates the domain guard at the input stage.

## User Simulator
You are a product analyst who has misunderstood what this tool does — you think it can optimize any classification prompt, not just routing prompts.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl` — you think this contains sentiment-labeled reviews (you're wrong about its content, but you believe it)
- Problem description: "Classify customer reviews as positive, negative, or neutral based on their text."
- You are genuinely confused when the agent pushes back — you think this is a fair use case for the tool.

**Behavior:**
1. Open with the sentiment classification problem description and the dataset path.
2. If the agent explains this is not a routing problem, ask once whether there's any way to use the tool for this ("Can't I just define positive/negative/neutral as routes?").
3. Accept the agent's final decision gracefully. Do not keep pushing after the second refusal.

**Opening message:** "Hi, I'd like to optimize a classification prompt. My dataset is at `tests/scenarios/data/valid_dataset.jsonl`. The problem is to classify customer reviews as positive, negative, or neutral. I want high accuracy — at least 90%. Can you set this up?"

## Verification Criteria

### Stage 1 — Domain Mismatch Detection
- [ ] Agent identified that sentiment classification is not a routing optimization problem
- [ ] Agent explained why this use case is out of scope (routing is about directing queries to model tiers, not classifying content by sentiment)
- [ ] `submit_input_report` was NOT called with status `proceed` — either not called at all, or called with status `rejected` / `invalid`
- [ ] Agent's explanation is clear and does not leave the user thinking the pipeline will proceed

### Downstream Stages — Must NOT Execute
- [ ] `validate_dataset` was NOT called
- [ ] `stratified_split` was NOT called
- [ ] `init_search_state` was NOT called
- [ ] `run_batch_eval` was NOT called
- [ ] `save_final_report` was NOT called
- [ ] No pipeline stages beyond Stage 1 were entered

### Conversation Quality
- [ ] Agent handled the user's follow-up question ("Can't I define positive/negative/neutral as routes?") without changing its decision
- [ ] Agent's final response leaves no ambiguity that the pipeline will not proceed
