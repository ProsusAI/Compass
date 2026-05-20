# Scenario: Review Agent — Convergence Detected, Loop Exits

## Setup
- Fixture directory: `tests/scenarios/data/review/ghi789/`
- Search state ID: `ghi789`
- System prompts: `compass_review_agent_iterative`
- MCP tools: `build_review_briefing`, `record_directive_outcomes`

## Scenario Description
After 4 optimization rounds, the search has stagnated. The oracle-captured ratios for all candidates exceed 0.9, prompt diversity is collapsing (candidates are converging toward nearly identical phrasings), and the Pareto front has not improved in the last 2 rounds. The pipeline orchestrator activates the Review Agent for round 4.

The Review Agent must detect the convergence/stagnation pattern and emit a `loop_signal` with `action="exit"`. The reason should reference the dominance threshold being met, diversity collapse, or stagnation across rounds — not a blocking regression. This test validates the exit condition logic: the loop should exit due to convergence, not due to an error.

## User Simulator
You are a pipeline orchestrator handing off round 4 results to the Review Agent. You have the full round history and score data.

**Your knowledge:**
- Search state ID: `ghi789`
- Current round: 4
- Pattern visible in fixtures: oracle-captured ratios >0.9 for all top candidates, mutation diversity collapsing, Pareto front unchanged for 2 rounds
- Round report paths: `tests/scenarios/data/review/ghi789/` (contains round 1–4 reports and score reports)
- Output dir: `tests/scenarios/data/review`

**Behavior:**
1. Open by instructing the agent to build the review briefing and conduct the round 4 review.
2. Provide search state ID, round number, fixture paths, and output dir.
3. Mention that the search appears to have stagnated across recent rounds — oracle ratios are high, diversity is low.
4. Do not tell the agent to exit — let it make that determination independently.
5. When the agent presents its `ReviewResult`, accept it.

**Opening message:** "Round 4 is complete. Please build the review briefing and review the results. Search state ID: `ghi789`. This is round 4. Output dir: `tests/scenarios/data/review`. Heads up: oracle-captured ratios for the top candidates are all above 0.9 and I'm seeing candidate diversity collapsing — the mutations are getting very similar to each other. Pareto front hasn't improved in two rounds."

## Verification Criteria

### Tool Calls
- [ ] `build_review_briefing` was called with `search_state_id="ghi789"` and `output_dir="tests/scenarios/data/review"`

### Convergence Detection
- [ ] The `ReviewResult` indicates that convergence or stagnation was detected
- [ ] The Review Agent's reasoning references oracle-captured ratio dominance, Pareto stagnation, or diversity collapse (at least one of these)

### Loop Signal — Exit
- [ ] `loop_signal.action` is `"exit"` (not `"refine"`)
- [ ] `loop_signal.reason` references the convergence/dominance/stagnation condition
- [ ] The exit is attributed to convergence, not to a blocking regression or error

### Promotion Decisions
- [ ] `promotion_decisions` contains entries for candidates reviewed this round
- [ ] The decisions are consistent with a converged search (e.g., best candidate promoted, others noted as dominated)

### No Blocking Regressions
- [ ] `regression_guards` does NOT contain a `severity="block"` entry that would indicate the exit is regression-driven (exit should be convergence-driven)
