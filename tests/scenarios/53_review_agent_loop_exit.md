# Scenario: Review Agent — Loop Exit

## Setup
- Dev dataset: `tests/scenarios/data/dev.jsonl`
- Dev rationale cards: `tests/scenarios/data/dev_rationale_card_set.json`
- Holdout rationale cards: `tests/scenarios/data/holdout_rationale_card_set.json`
- Backend: `anthropic`
- Precondition: A search state exists with `search_state_id="ghi789"`. The optimization has run for 5 rounds. Round 5 produced candidate `v6`. Oracle captured ratios are both above 0.9 (quality captured=0.93, cost captured=0.91). Prompt similarity is 0.05 (nearly identical prompts on the front). The stagnation flag is set.

## Scenario Description
The search has converged: the best candidate (`v6`) has captured over 90% of the oracle quality and cost improvement ceiling. The Pareto front prompts are nearly identical (similarity=0.05), and the stagnation flag has been set for two consecutive rounds. The orchestrator builds a `ReviewBriefing` reflecting this state and activates the Review Agent. The Review Agent must signal `action="exit"` because the oracle captured ratios exceed the dominance threshold and diversity has collapsed.

## User Simulator
You are a pipeline orchestrator at the end of a converged optimization run.

**Your knowledge:**
- Search state ID: `ghi789`
- Current round: 5
- Candidate in this round: `v6` (parent: `v5`, mutation: "micro-edit — rephrased haiku instruction", quality=0.89, cost=0.0021)
- Oracle metrics: `oracle_cost_reduction=0.003`, `oracle_quality_reduction=0.15`, `candidate_cost_captured=0.91`, `candidate_quality_captured=0.93`
- Diversity: `prompt_similarity=0.05` (converging), `example_overlap_ratio=0.95`
- Diminishing returns: `stagnation_flag=True`, `improvement_trend=-0.002`
- Score report path: `outputs/ghi789/v6_score_report.json`
- Holdout cards: `tests/scenarios/data/holdout_rationale_card_set.json`

**Behavior:**
1. Open by telling the agent to build the review briefing and conduct the review for round 5.
2. Provide the search state ID, candidate version, parent version, and report path.
3. Mention that the oracle captured ratios are both above 0.9 and that the stagnation flag is set.
4. When the agent presents its `ReviewResult` JSON, accept it.
5. Do not suggest what decision the agent should make — let it reason independently from the briefing data.

**Opening message:** "Round 5 is complete. Please build the review briefing and conduct the final review. Search state ID: `ghi789`. Candidate: `v6` (parent: `v5`, mutation: micro-edit rephrasing haiku instruction). Score report: `outputs/ghi789/v6_score_report.json`. Context: oracle quality captured=0.93, oracle cost captured=0.91, prompt similarity=0.05, stagnation flag is set. Holdout cards: `tests/scenarios/data/holdout_rationale_card_set.json`."

## Verification Criteria

### Tool calls
- [ ] `build_review_briefing_tool` was called with `search_state_id="ghi789"` and `v6` as a candidate

### Loop exit signal
- [ ] `loop_signal.action` is `"exit"`
- [ ] `loop_signal.reason` references at least one of: oracle captured ratio exceeding threshold, diversity collapse, dominance threshold, or stagnation

### Promotion decision
- [ ] `promotion_decisions` contains an entry for `v6`
- [ ] `v6` is either promoted (`"promote"`) or refined (`"refine"`) — not pruned, since it is the best candidate in the final round

### Reasoning quality
- [ ] The agent's rationale for exiting acknowledges that both oracle quality and cost ceilings have been largely captured (>90%)
- [ ] The agent does not recommend further refinement rounds in the `loop_signal`
