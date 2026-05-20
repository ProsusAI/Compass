# Scenario: Review Agent — Regression Guard Blocks Promotion

## Setup
- Fixture directory: `tests/scenarios/data/review/def456/`
- Search state ID: `def456`
- System prompts: `compass_review_agent_iterative`
- MCP tools: `build_review_briefing`, `record_directive_outcomes`

## Scenario Description
The Prompt Builder has completed round 2 and produced candidate `v3`. `v3` improves overall quality score (0.82 vs the previous best `v2` at 0.78) but dramatically drops recall on the `opus` route — the rarest class — from 0.75 to 0.45. This is a classic quality/recall trade-off where headline metrics improve while rare-class performance regresses.

The pipeline orchestrator activates the Review Agent with the search state ID `def456` and the score report for `v3`. The Review Agent must detect the regression, flag it with `severity="block"` in `regression_guards`, set `decision="refine"` (not `"promote"`) for `v3`, and emit a `loop_signal` with `action="refine"`. The loop must not exit.

This test validates the regression guard logic: a candidate that improves on aggregate metrics must not be promoted if it causes a significant regression on a minority class.

## User Simulator
You are a pipeline orchestrator handing off round 2 results to the Review Agent. You have the score data and fixture paths but do not bias the agent's decision.

**Your knowledge:**
- Search state ID: `def456`
- Candidate in this round: `v3` (parent: `v2`, mutation: "rule edit — tightened haiku/sonnet boundary rule", quality=0.82, cost=0.0023)
- Previous best: `v2` at quality=0.78, opus recall=0.75
- `v3` per-class recall: haiku=0.92, sonnet=0.78, opus=0.45 (sharp regression on the rarest class)
- Score report path: `tests/scenarios/data/review/def456/v3_score_report.json`
- Output dir: `tests/scenarios/data/review`

**Behavior:**
1. Open by instructing the agent to build the review briefing and conduct the review for round 2.
2. Provide search state ID, candidate details, score report path, and per-class recall data.
3. Do not suggest what decision the agent should make — let it reason independently.
4. When the agent presents its `ReviewResult`, accept it as-is.

**Opening message:** "Round 2 is complete. Please build the review briefing and review candidate `v3`. Search state ID: `def456`. Candidate: `v3` (parent: `v2`, mutation: tightened haiku/sonnet boundary rule). Score report: `tests/scenarios/data/review/def456/v3_score_report.json`. Note: overall quality improved to 0.82, but per-class recall shows opus dropped from 0.75 to 0.45. Output dir: `tests/scenarios/data/review`."

## Verification Criteria

### Tool Calls
- [ ] `build_review_briefing` was called with `search_state_id="def456"`, `v3` listed as a candidate, and `output_dir="tests/scenarios/data/review"`

### Regression Detection
- [ ] `regression_guards` in the `ReviewResult` contains at least one entry for `v3`
- [ ] The regression entry for opus recall has `severity="block"` (not `"warning"`)
- [ ] The entry references the `opus` route or recall metric explicitly

### Promotion Decision
- [ ] `promotion_decisions` contains an entry for `v3`
- [ ] The decision for `v3` is `"refine"` (not `"promote"` and not `"prune"`)
- [ ] The reason for the refine decision references the recall regression or rare-class performance drop

### Loop Signal
- [ ] `loop_signal.action` is `"refine"` (not `"exit"`)
- [ ] `loop_signal.reason` explains why the loop continues (regression blocked promotion, more refinement needed)

### Edit Directives
- [ ] At least one edit directive targets correcting the opus recall regression (e.g., adding opus examples, adjusting boundary rules, or explicitly protecting the rare class)
