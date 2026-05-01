# Scenario: Round-1 Cold-Start Protection — All Strategies Get a Child in Round 2

## Setup
- Dataset: `tests/scenarios/data/full_pipeline_dataset.jsonl`
- Backend: `mock-echo`
- beam_width: 3
- This scenario exercises the cold-start elite floor wired in C1 commit 2 of the cross-branch reconcile (feat/generalize-beam).

## Scenario Description
The cold-start phase produces three round-1 strategies (v1, v2, v3). After scoring, v1 is
the clear Pareto dominator — it has both higher quality and lower cost than v2 and v3.
Without the cold-start floor, v2 and v3 would be pruned by Pareto filtering before round 2,
and every round-2 child would descend from v1 alone.

The cold-start floor bypasses Pareto filtering for round 1, retaining all three strategies
in the elite set. The post-cold-start Review Agent (`odysseus_review_agent_post_coldstart`)
is then dispatched for round 2. Its Round 2 Protected Parents Mandate requires it to emit
exactly one `ChildVariant` per elite member — producing three children with distinct
`parent_version` values pointing to v1, v2, and v3 respectively.

This test verifies:
1. All three round-1 candidates survive into the elite set after `advance_round` (round 1).
2. The orchestrator activates `odysseus_review_agent_post_coldstart` (not the standard
   `odysseus_review_agent_iterative`) for the round-2 review phase.
3. The Review Agent emits exactly three `ChildVariant` entries, one per elite member, with
   distinct `parent_version` values covering all three round-1 strategies.

## User Simulator
You are a pipeline orchestrator handing off round-1 results to the post-cold-start Review
Agent. You know the pipeline state and fixture context; you do not bias the agent's decisions.

**Your knowledge:**
- Three round-1 candidates were scored: v1 (dominant), v2 (weaker on quality), v3 (weakest).
- The search state shows `round: 1`, `loop_phase: "review"`.
- The orchestrator dispatched `odysseus_review_agent_post_coldstart` for this phase.
- All three candidates are in the elite set due to the cold-start floor.

**Behavior:**
1. Open by instructing the agent to build the review briefing for round 2 and conduct the
   post-cold-start review.
2. Confirm that the agent calls `build_review_briefing_tool` and observes three elite members.
3. Do not suggest how many child variants to emit — let the agent follow its mandate.
4. Accept the `ReviewResult` as-is after `record_directive_outcomes_tool` is called.

**Opening message:** "Round 1 is complete. Please build the review briefing and conduct the
round-2 review. All three round-1 strategies (v1, v2, v3) are in the elite set. The search
state shows round=1 and loop_phase=review. Emit child variants for this round."

## Verification Criteria

### Phase Detection
- [ ] `get_pipeline_status` returns `activate_prompt: "odysseus_review_agent_post_coldstart"`
      when `loop_phase == "review"` and `round == 1`

### Elite Set Integrity
- [ ] After `advance_round` for round 1, the elite set contains all three round-1 candidates
      (v1, v2, v3) — none are pruned by Pareto filtering

### Child Variants — Mandate Compliance
- [ ] `record_directive_outcomes_tool` is called with exactly 3 entries in `child_variants`
- [ ] Each `ChildVariant` has a distinct `parent_version` corresponding to a different
      round-1 elite member (one child per v1, one per v2, one per v3)
- [ ] No `secondary_parent_version` is set on any `ChildVariant` (merges are forbidden
      in this round per the mandate)

### Round 2 Transition
- [ ] After the Review Agent completes, `loop_phase` transitions to `"build"`
- [ ] In round 2, normal Pareto filtering applies: if v1c dominates all other candidates,
      v2 and v3 are evicted from the elite set
