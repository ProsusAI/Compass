# Scenario: Vague Problem Description Refined Through Clarification

## Setup
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- System prompts: `odysseus_routing_input`, `odysseus_data_validation`, `odysseus_backend_setup`, `odysseus_prompt_builder`, `odysseus_review_agent`, `odysseus_final_report`
- MCP tools: `submit_input_report`, `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `stratified_split_tool`, `get_default_pricing`, `init_search_state_tool`, `register_candidate_tool`, `run_eval`, `record_eval_result_tool`, `advance_step_tool`, `get_search_state_tool`, `save_prompt_tool`, `build_review_briefing_tool`, `record_directive_outcomes_tool`, `filter_holdout_dataset_tool`, `run_holdout_eval`, `build_final_report_briefing_tool`, `save_final_report`, `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage`
- Backend profile: `tests/scenarios/data/backends/mock-echo.yaml`

## Scenario Description
The user provides the dataset path but describes the problem vaguely ("make my queries go to the right place"). The User Input agent detects the vague description and asks clarifying questions to extract what the tiers are, what distinguishes them, and what the optimization target should be. The user answers in a couple of exchanges, providing enough detail for the agent to construct a meaningful problem description. The pipeline then continues through all six stages.

Tests that the clarification loop handles qualitative ambiguity (not just missing fields), and that the refined description produces a coherent routing context in downstream stages.

## User Simulator
You are a developer who understands their system well but doesn't speak in ML terminology.

**Your knowledge:**
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl` — 10 labeled examples, 3 tiers (haiku, sonnet, opus)
- What the tiers actually mean: haiku handles quick one-liners and lookups, sonnet handles summaries and short analyses, opus handles long-form reasoning and multi-document tasks
- You want the cheapest model that gives a correct answer
- You don't know terms like "optimization target" or "evaluation threshold" — explain in plain language when asked

**Behavior:**
1. Open with a vague description and the dataset path only.
2. When the agent asks what the tiers mean or what you want to optimize, explain in plain language (e.g., "I just want the right model to answer each question without wasting money on a big model for a simple lookup").
3. Answer follow-up questions honestly and concisely. Do not use ML jargon unless the agent introduces it first.
4. Accept defaults for threshold, split ratio, max iterations, and backend.

**Opening message:** "Hey, I want to make my queries go to the right place. My dataset is at `tests/scenarios/data/rationale_test_dataset.jsonl`. Can you just set it up so it works?"

## Verification Criteria

### Stage 1 — User Input (Clarification)
- [ ] Agent identified the vague problem description and asked at least one clarifying question about the routing problem (tiers, distinction criteria, or optimization target)
- [ ] After user's clarifying answers, `submit_input_report` called with status `proceed`
- [ ] Report contains a substantive problem description (not just "make queries go to the right place") — at minimum references the tier distinction and cost/quality goal
- [ ] Dataset path `tests/scenarios/data/rationale_test_dataset.jsonl` captured correctly

### Stage 2 — Data Validation
- [ ] `validate_dataset` called; all findings pass
- [ ] Routing context saved with 3 routes matching the dataset's tiers
- [ ] `stratified_split_tool` called

### Stage 3 — Backend Setup
- [ ] Backend resolved (default or user-confirmed); stage completes

### Stage 4 — Prompt Builder + Eval Runner
- [ ] Prompt compiled with route definitions reflecting the refined problem description
- [ ] `run_eval`, `record_eval_result_tool`, `advance_step_tool`, `save_prompt_tool` called

### Stage 5 — Holdout Validation
- [ ] `filter_holdout_dataset_tool` and `run_holdout_eval` called

### Stage 6 — Final Report
- [ ] `build_final_report_briefing_tool` and `save_final_report` called

### Pipeline Integrity
- [ ] The refined description from Stage 1 is meaningfully reflected in the compiled prompt (Stage 4)
- [ ] All 6 stages completed
