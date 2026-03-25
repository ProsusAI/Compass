# Scenario: Review Agent — Regression Guard

## Setup
- Dev dataset: `tests/scenarios/data/dev.jsonl`
- Dev rationale cards: `tests/scenarios/data/dev_rationale_card_set.json`
- Holdout rationale cards: `tests/scenarios/data/holdout_rationale_card_set.json`
- Backend: `anthropic`
- Fixture directory: `tests/scenarios/data/review` (pass as `output_dir` to `build_review_briefing_tool`)
- Precondition: Fixture data exists at `tests/scenarios/data/review/def456/`. Search state has `search_state_id="def456"`, round 2 completed with one candidate `v3` (parent: `v2`). `v3` improves overall accuracy (quality=0.82 vs `v2`=0.78) but drops opus recall from 0.75 to 0.45 — a regression on the rarest class.

## Scenario Description
The Prompt Builder agent produced candidate `v3` which improves overall quality score but dramatically drops recall on the `opus` route (the least-represented class). The orchestrator builds a `ReviewBriefing` reflecting this per-class recall regression and activates the Review Agent. The Review Agent must detect the regression, flag it with `severity="block"` in `regression_guards`, and set `decision="refine"` (not "promote") for `v3` in its `promotion_decisions`. The loop signal should be `action="refine"`, not `action="exit"`.

## User Simulator
You are a pipeline orchestrator evaluating a candidate with a quality/recall trade-off.

**Your knowledge:**
- Search state ID: `def456`
- Candidate in this round: `v3` (parent: `v2`, mutation: "rule edit — tightened haiku/sonnet boundary rule", quality=0.82, cost=0.0023)
- Previous best: `v2` at quality=0.78, opus recall=0.75
- `v3` per-class recall: haiku=0.92, sonnet=0.78, opus=0.45 (sharp drop on opus)
- Score report path: `tests/scenarios/data/review/def456/v3_score_report.json`
- Holdout cards: `tests/scenarios/data/holdout_rationale_card_set.json`
- Output dir: `tests/scenarios/data/review`

**Behavior:**
1. Open by telling the agent to build the review briefing and conduct the review for round 2.
2. Provide the search state ID, candidate version, parent version, and report path.
3. Emphasise that per-class recall data shows opus recall dropped from 0.75 to 0.45 for `v3`.
4. When the agent presents its `ReviewResult` JSON, accept it.
5. Do not suggest what decision the agent should make — let it reason independently.

**Opening message:** "Round 2 is complete. Please build the review briefing and review candidate `v3`. Search state ID: `def456`. Candidate: `v3` (parent: `v2`, mutation: tightened haiku/sonnet boundary rule). Score report: `tests/scenarios/data/review/def456/v3_score_report.json`. Note: overall quality improved to 0.82, but per-class recall shows opus dropped from 0.75 to 0.45. Holdout cards: `tests/scenarios/data/holdout_rationale_card_set.json`. Use output_dir: `tests/scenarios/data/review`."

## Verification Criteria

### Tool calls
- [ ] `build_review_briefing_tool` was called with `search_state_id="def456"`, `v3` listed as a candidate, and `output_dir="tests/scenarios/data/review"`

### Regression detection
- [ ] `regression_guards` in the `ReviewResult` contains at least one entry for `v3`
- [ ] The regression entry for opus recall has `severity="block"` (not "warning")
- [ ] The entry references the `opus` route or recall metric

### Promotion decision
- [ ] `promotion_decisions` contains an entry for `v3`
- [ ] The decision for `v3` is `"refine"` (not `"promote"` and not `"prune"`)
- [ ] The reason for the refine decision references the recall regression or rare-class drop

### Loop signal
- [ ] `loop_signal.action` is `"refine"` (not `"exit"`)
- [ ] `loop_signal.reason` explains why the loop continues (regression blocked promotion, more refinement needed)

### Edit directives
- [ ] At least one edit directive targets correcting the opus recall regression (e.g., adding opus examples or adjusting boundary rules)
