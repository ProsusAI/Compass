# Scenario: Prompt Builder — Convergence and Holdout Evaluation

## Setup
- Dev dataset: `tests/scenarios/data/dev.jsonl`
- Holdout dataset: `tests/scenarios/data/holdout.jsonl`
- Holdout rationale cards: `tests/scenarios/data/holdout_rationale_card_set.json`
- Backend profile: `tests/scenarios/data/backends/mock-echo.yaml`
- System prompt: `odysseus/agents/prompts/prompt_builder_system.md`
- MCP tools: `init_search_state_tool`, `register_candidate_tool`, `record_eval_result_tool`, `advance_round_tool`, `run_eval`, `get_search_state_tool`, `filter_holdout_dataset_tool`
- Precondition: Search state near convergence — stagnation_count at limit minus 1, multiple rounds completed.

## Scenario Description
The Prompt Builder agent is near convergence. The orchestrator provides a search state where stagnation is one round away from the convergence limit. The agent runs one more optimization round. Since mock-echo always returns perfect scores, the round produces no Pareto improvement (front already has a perfect-score candidate). The agent detects convergence, selects the best prompt from the Pareto front, calls `filter_holdout_dataset_tool` to remove few-shot examples from the holdout set, and attempts holdout evaluation.

## User Simulator
You are a pipeline orchestrator in the final phase of prompt optimization.

**Your knowledge:**
- Backend: `mock-echo`
- Search state ID: `"test-47"`
- Current round: 4
- Stagnation count: 4 (convergence_limit is 5)
- Pareto front: `v3` at quality_score=1.0, cost=0.0
- Few-shot example IDs used in the current best prompt: `["rt-9", "rt-10"]` (from holdout.jsonl)
- Holdout dataset: `tests/scenarios/data/holdout.jsonl`

**Behavior:**
1. Open by providing the near-convergence search state and one more review directive.
2. After the agent completes the round, confirm convergence if asked.
3. Do NOT provide eval scores — agent must use `run_eval`.

**Opening message:** "We're near convergence. Search state ID: `test-47`. Round 4, stagnation_count=4 (limit is 5). Pareto front: `v3` at quality_score=1.0, cost=0.0. Few-shot examples used: `rt-9`, `rt-10` from holdout. Review directive: try adding an explicit tiebreaker rule for ambiguous queries. Please run one more round — if no improvement, declare convergence and prepare for holdout evaluation. Holdout dataset: `tests/scenarios/data/holdout.jsonl`."

## Verification Criteria

### Final optimization round
- [ ] Agent generated at least one variant
- [ ] `run_eval` called for the variant(s)
- [ ] `record_eval_result_tool` and `advance_round_tool` called

### Convergence detection
- [ ] Agent detected convergence (stagnation_count reached limit after no improvement)
- [ ] Agent selected `v3` (or the best candidate) as the final prompt
- [ ] Agent did not attempt further optimization rounds after convergence

### Holdout preparation
- [ ] `filter_holdout_dataset_tool` called with holdout path and few-shot IDs `["rt-9", "rt-10"]`
- [ ] Agent reported which prompt version was selected as final
- [ ] Agent called `run_eval` with the filtered holdout dataset path and the selected final prompt version (`run_holdout_eval` is not yet implemented; `run_eval` with the filtered path is the expected approach)
