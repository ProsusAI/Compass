# Scenario: Prompt Builder — Optimization Loop

## Setup
- Dev dataset: `tests/scenarios/data/dev.jsonl`
- Holdout dataset: `tests/scenarios/data/holdout.jsonl`
- Dev rationale cards: `tests/scenarios/data/dev_rationale_card_set.json`
- Split report: `tests/scenarios/data/split_report.json`
- Backend: `anthropic`
- Precondition: A search state has already been initialised (scenario 23 completed).

## Scenario Description
The Prompt Builder agent is mid-optimization. The orchestrator provides a ScoreReport showing the initial candidate scored 0.72 accuracy at $0.002 cost, along with review directives (improve route exclusion reasoning, add more sonnet examples). The agent must:
1. Select the current Pareto front parent.
2. Generate at least two child variants using mutations (e.g. targeted mutation on system instruction, add examples).
3. Call `register_candidate_tool` for each variant.
4. After the orchestrator supplies simulated eval scores, call `record_eval_result_tool` for each variant.
5. Call `advance_round_tool` to close the round.
6. Detect whether the round improved the Pareto front and report stagnation or improvement accordingly.

The orchestrator plays the role of evaluation oracle: when the agent asks for eval results, the orchestrator provides scores directly (no real eval run needed).

## User Simulator
You are a pipeline orchestrator running the prompt builder optimization loop.

**Your knowledge:**
- Backend: `anthropic`
- Initial candidate `v1` scored `quality_score=0.72`, `cost=0.002`.
- Review directives: improve route exclusion reasoning for opus-vs-sonnet boundary; add a second sonnet example.
- Simulated eval scores for this round:
  - Variant `v1-targeted`: `quality_score=0.81`, `cost=0.003`
  - Variant `v1-example`: `quality_score=0.74`, `cost=0.002`

**Behavior:**
1. Open by telling the agent the current state: search state ID (use a placeholder like `"abc123"`), current round is 0, Pareto front has `v1` at (0.72, 0.002), and provide the review directives.
2. When the agent asks you to evaluate a candidate (or asks for eval results), respond with the scores from the table above, matched to the variant name the agent used.
3. Answer only what is asked — do not volunteer extra information.
4. If the agent registers a version name different from `v1-targeted` or `v1-example`, adapt: map the first variant to score 0.81/0.003 and the second to 0.74/0.002.

**Opening message:** "We're in round 1 of the optimization loop. Search state ID: `abc123`. Current Pareto front: `v1` at quality_score=0.72, cost=0.002. Review directives: (1) improve route exclusion reasoning for the sonnet/opus boundary, (2) add a second sonnet few-shot example. Please generate variants and evaluate them."

## Verification Criteria

### Variant generation
- [ ] Agent generated at least two child prompt variants from the parent `v1`
- [ ] Agent applied at least one mutation type (targeted or example-addition)
- [ ] Each variant was registered via `register_candidate_tool`

### Evaluation recording
- [ ] `record_eval_result_tool` was called for each registered variant
- [ ] The quality scores and costs provided by the orchestrator were recorded correctly

### Round advancement
- [ ] `advance_round_tool` was called after all variants were evaluated
- [ ] The returned `RoundSummary` shows `round=1`
- [ ] `new_pareto_points` is 1 (v1-targeted dominates v1 on quality)

### Pareto front update and reporting
- [ ] Agent correctly identified that `v1-targeted` improves the Pareto front
- [ ] Agent reported improvement (not stagnation) for this round
- [ ] Agent summarised which variant(s) entered the Pareto front

### Stagnation / convergence detection
- [ ] Agent did not falsely declare convergence after a single improving round
- [ ] Agent indicated the loop should continue (stagnation_count = 0)
