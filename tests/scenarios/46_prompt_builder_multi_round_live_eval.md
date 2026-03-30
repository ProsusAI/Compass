# Scenario: Prompt Builder — Multi-Round Optimization with Live Eval

## Setup
- Dev dataset: `tests/scenarios/data/dev.jsonl`
- Split report: `tests/scenarios/data/split_report.json`
- Backend profile: `tests/scenarios/data/backends/mock-echo.yaml`
- System prompt: `odysseus/agents/prompts/prompt_builder_system.md`
- MCP tools: `init_search_state_tool`, `register_candidate_tool`, `record_eval_result_tool`, `advance_round_tool`, `run_eval`, `get_search_state_tool`
- Precondition: None — the User Simulator bootstraps the search state context in its opening message.

## Scenario Description
The Prompt Builder agent is mid-optimization. The orchestrator provides review directives and the current search state. The agent generates variant prompts, calls `run_eval` for each (no oracle — real eval via mock-echo), records results, and advances the round. The orchestrator then provides a second set of review directives, and the agent runs another optimization round. Tests that the agent correctly drives a multi-round optimization loop using live eval results.

**Note on mock-echo scoring:** Since mock-echo returns perfect scores (quality_score=1.0, cost=0.0), all variants will tie the existing Pareto front. The agent should still complete both rounds as directed by the orchestrator, even though no Pareto improvement occurs. This scenario tests the mechanical flow (generate → eval → record → advance), not score-driven optimization decisions.

## User Simulator
You are a pipeline orchestrator running the prompt builder optimization loop.

**Your knowledge:**
- Backend: `mock-echo`
- Search state ID: use a placeholder like `"test-46"`
- v1 scored quality_score=1.0, cost=0.0 (mock-echo returns perfect scores)
- Round 1 review directives: "Tighten the system instruction to be more concise. Reorder routes by expected frequency."
- Round 2 review directives: "Add explicit handling for ambiguous queries that could go to either sonnet or opus."

**Behavior:**
1. Open by providing the search state context and round 1 review directives.
2. After the agent completes round 1 (calls `advance_round_tool`), provide round 2 review directives.
3. Do NOT provide eval scores — the agent must call `run_eval` for each variant.
4. Answer only what is asked.

**Opening message:** "Continuing optimization. Search state ID: `test-46`. Current Pareto front: `v1` at quality_score=1.0, cost=0.0. Round 1 review directives: (1) tighten the system instruction to be more concise, (2) reorder routes by expected frequency. Please generate variants and evaluate them using `run_eval`."

## Verification Criteria

### Round 1
- [ ] Agent generated at least 2 child variants from v1
- [ ] `run_eval` called for each variant (not oracle scores)
- [ ] `register_candidate_tool` called for each variant
- [ ] `record_eval_result_tool` called for each variant with scores from ScoreReport
- [ ] `advance_round_tool` called to close round 1

### Round 2
- [ ] Agent generated new variants after receiving round 2 directives
- [ ] `run_eval` called for each round 2 variant
- [ ] `record_eval_result_tool` and `advance_round_tool` called for round 2
- [ ] Agent reported Pareto front state after each round

### Search state integrity
- [ ] `get_search_state_tool` called at least once to read current state
- [ ] Version numbers are sequential and unique across both rounds
- [ ] Agent correctly tracked parent-child relationships in `register_candidate_tool` calls
