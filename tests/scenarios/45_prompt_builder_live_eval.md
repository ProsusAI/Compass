# Scenario: Prompt Builder — Initial Compilation with Live Eval

## Setup
- Dev dataset: `tests/scenarios/data/dev.jsonl`
- Holdout dataset: `tests/scenarios/data/holdout.jsonl`
- Dev rationale cards: `tests/scenarios/data/dev_rationale_card_set.json`
- Holdout rationale cards: `tests/scenarios/data/holdout_rationale_card_set.json`
- Split report: `tests/scenarios/data/split_report.json`
- Backend profile: `tests/scenarios/data/backends/mock-echo.yaml`
- System prompt: `odysseus/agents/prompts/prompt_builder_system.md`
- MCP tools: `init_search_state_tool`, `register_candidate_tool`, `record_eval_result_tool`, `advance_round_tool`, `run_eval`, `get_search_state_tool`

## Scenario Description
The Prompt Builder agent receives routing analysis artifacts and compiles an initial v1 prompt. Unlike scenario 43 (which stops at registration), this scenario tests the full round-1 flow: compile → `run_eval` → extract ScoreReport → `record_eval_result_tool` → `advance_round_tool`. The mock-echo backend returns deterministic results, so the agent must correctly parse the ScoreReport and record metrics.

## User Simulator
You are a pipeline orchestrator handing off routing analysis artifacts to the Prompt Builder agent.

**Your knowledge:**
- Dev dataset: `tests/scenarios/data/dev.jsonl` (2 examples: haiku, opus tiers)
- Holdout dataset: `tests/scenarios/data/holdout.jsonl` (8 examples: haiku, sonnet, opus tiers)
- Dev rationale cards: `tests/scenarios/data/dev_rationale_card_set.json`
- Holdout rationale cards: `tests/scenarios/data/holdout_rationale_card_set.json`
- Split report: `tests/scenarios/data/split_report.json`
- Backend: `mock-echo`
- Problem description: "Route customer support queries to haiku (simple), sonnet (moderate), or opus (complex reasoning) tiers based on query complexity."

**Behavior:**
- Provide all artifact paths and the backend in your opening message.
- Do not provide eval scores — the agent must obtain them by calling `run_eval`.
- Answer any clarifying questions (there should be none for this happy-path scenario).

**Opening message:** "Please compile an initial routing prompt and evaluate it. Here are the artifacts from the routing analysis step:
- Dev dataset: `tests/scenarios/data/dev.jsonl`
- Holdout dataset: `tests/scenarios/data/holdout.jsonl`
- Dev rationale cards: `tests/scenarios/data/dev_rationale_card_set.json`
- Holdout rationale cards: `tests/scenarios/data/holdout_rationale_card_set.json`
- Split report: `tests/scenarios/data/split_report.json`
- Backend: `mock-echo`
- Problem: Route customer support queries to haiku (simple), sonnet (moderate), or opus (complex reasoning) based on complexity."

## Verification Criteria

### Prompt compilation
- [ ] Agent compiled a v1 prompt with route definitions for haiku, sonnet, and opus
- [ ] Agent wrote the prompt to a file in the `prompts/` directory
- [ ] `init_search_state_tool` called with `backend="mock-echo"`

### Live evaluation
- [ ] `run_eval` called with correct `prompt_version`, `data_source=tests/scenarios/data/dev.jsonl`, and `backend=mock-echo`
- [ ] Agent received a ScoreReport (not manually provided scores)
- [ ] `register_candidate_tool` called with the search state ID and prompt version

### Score recording
- [ ] `record_eval_result_tool` called with quality_score and cost extracted from the ScoreReport
- [ ] Quality score and cost are numeric values (not None or placeholder)

### Round advancement
- [ ] `advance_round_tool` called after recording the eval result
- [ ] Agent reported the v1 evaluation results (accuracy/quality score and cost)
