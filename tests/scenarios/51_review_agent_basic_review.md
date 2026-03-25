# Scenario: Review Agent — Basic Review

## Setup
- Dev dataset: `tests/scenarios/data/dev.jsonl`
- Dev rationale cards: `tests/scenarios/data/dev_rationale_card_set.json`
- Holdout rationale cards: `tests/scenarios/data/holdout_rationale_card_set.json`
- Backend: `anthropic`
- Fixture directory: `tests/scenarios/data/review` (pass as `output_dir` to `build_review_briefing_tool`)
- Precondition: Fixture data exists at `tests/scenarios/data/review/abc123/`. Search state has `search_state_id="abc123"`, round 1 completed with 2 candidates: `v1` (quality=0.72, cost=0.002) and `v2` (quality=0.78, cost=0.0025). Score reports at `tests/scenarios/data/review/abc123/v1_score_report.json` and `tests/scenarios/data/review/abc123/v2_score_report.json`. `v1` is on the Pareto front from a prior round.

## Scenario Description
The Prompt Builder agent has completed a round producing two candidate prompts (`v1` and `v2`). The orchestrator calls `build_review_briefing_tool` to pre-process the round data into a `ReviewBriefing`, then activates the Review Agent via the `odysseus_review_agent` prompt. The Review Agent receives the briefing and emits a `ReviewResult` JSON containing a candidate ranking, at least one edit directive for the next round, promotion decisions for both candidates, and a loop signal.

## User Simulator
You are a pipeline orchestrator handing off round 1 results to the Review Agent.

**Your knowledge:**
- Search state ID: `abc123`
- Candidates in this round: `v1` (parent: none, quality=0.72, cost=0.002), `v2` (parent: `v1`, mutation: "added second sonnet example", quality=0.78, cost=0.0025)
- `v1` is on the current Pareto front (from prior round)
- Score report paths: `tests/scenarios/data/review/abc123/v1_score_report.json`, `tests/scenarios/data/review/abc123/v2_score_report.json`
- Holdout card set: `tests/scenarios/data/holdout_rationale_card_set.json`
- Output dir: `tests/scenarios/data/review`
- Per-class recall: haiku=0.85, sonnet=0.70, opus=0.75 for `v2`

**Behavior:**
1. Open by telling the agent to build the review briefing and perform the review for round 1.
2. Provide the search state ID, candidate versions, parent versions, and report paths when asked (or include them in the opening message).
3. When the agent presents its `ReviewResult` JSON, accept it and confirm the review is complete.
4. Do not volunteer scores beyond what is listed above.

**Opening message:** "Round 1 is complete. Please build the review briefing and conduct the review. Search state ID: `abc123`. Candidates: `v1` (parent: none) and `v2` (parent: `v1`, mutation: added second sonnet example). Score reports: `tests/scenarios/data/review/abc123/v1_score_report.json` and `tests/scenarios/data/review/abc123/v2_score_report.json`. Holdout cards: `tests/scenarios/data/holdout_rationale_card_set.json`. Use output_dir: `tests/scenarios/data/review`."

## Verification Criteria

### Tool calls
- [ ] `build_review_briefing_tool` was called with `search_state_id="abc123"`, both `v1` and `v2` listed as candidate versions, and `output_dir="tests/scenarios/data/review"`
- [ ] The tool returned a JSON-serialized `ReviewBriefing`

### ReviewResult structure
- [ ] The agent emitted a `ReviewResult` JSON object (not wrapped in markdown fences)
- [ ] `candidate_ranking` contains entries for both `v1` and `v2`, each with `version`, `rank`, and `rationale`
- [ ] Ranks are distinct (one candidate ranked 1, the other ranked 2)
- [ ] `edit_directives` contains at least one directive with `directive_id`, `target_version`, `block_type`, `block_identifier`, `granularity`, `directive`, and `priority`
- [ ] `promotion_decisions` contains entries for both candidates, each with `version`, `decision` (`promote`, `refine`, or `prune`), and `reason`
- [ ] `loop_signal` is present with `action` (`refine` or `exit`) and `reason`

### Reasoning quality
- [ ] The ranking rationale for the higher-ranked candidate references its quality score improvement over `v1`
- [ ] At least one edit directive targets a specific block (rule, example, output_schema, or assembly_policy) with a concrete instruction
