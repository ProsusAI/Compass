# Scenario 26: Generate Routing Rationale — Ambiguous Boundary Examples

**Date:** 2026-03-23
**Verdict:** PASS (17/17 criteria)

---

## Transcript

```
=== SCENARIO 26: Generate Routing Rationale — Ambiguous Boundary Examples ===

--- Turn 1 (rt-4: summarize + draft questions → sonnet, gap sonnet-opus = 0.04) ---
User Simulator: [Provides rt-4 with classification, notes small quality gap]

Agent:

**Step 1 — Write route_exclusions**

Exclusion for haiku (straightforward):
- route: haiku
  reason: "Query demands a two-phase output — extractive summarization across three financial dimensions followed by generating three original follow-up questions — requiring sequential-dependency coordination."

Exclusion for opus (harder — small gap):
The agent explicitly stated: "This is harder. The quality scores show sonnet at 0.88 and opus at 0.92 — a gap of only 0.04."

After deliberation on observable properties:
- route: opus
  reason: "Query scopes both the summarization and question-generation phases to a single source document with explicitly stated dimensions, requiring no cross-source synthesis or open-ended analytical reasoning."

Agent acknowledged: "the argument is not fully decisive"

**Step 2 — Assess ambiguity**

- Haiku exclusion was clear and easy
- Opus exclusion "required considerable deliberation"
- Sequential-dependency + domain specificity could push toward opus
- Meets ambiguity criterion: "exclusions were difficult to write because the query sits near a routing boundary"

Proposed: **BOUNDARY_CASE**

**Output:**
route_exclusions:
  - route: haiku
    reason: "Query demands a two-phase output — extractive summarization across three financial dimensions followed by generating three original follow-up questions — requiring sequential-dependency coordination."
  - route: opus
    reason: "Query scopes both the summarization and question-generation phases to a single source document with explicitly stated dimensions, requiring no cross-source synthesis or open-ended analytical reasoning."
ambiguity_tags:
  - BOUNDARY_CASE

--- Turn 2 (rt-9: rewrite for conciseness → sonnet, gap sonnet-opus = 0.02) ---
User Simulator: [Provides rt-9, notes 0.02 gap and haiku arguability]

Agent:

**Step 1 — Write route_exclusions**

Exclusion for haiku (moderately confident):
- route: haiku
  reason: "Query requires editorial judgment to distinguish key points from expendable detail during the conciseness rewrite, not merely mechanical shortening."

Exclusion for opus (narrow structural argument):
- route: opus
  reason: "Query specifies a single-paragraph transformation with a bounded objective — conciseness — involving no multi-step reasoning or open-ended analytical judgment."

**Step 2 — Assess ambiguity**

Two sources of ambiguity detected:

1. **AMBIGUOUS_COMPLEXITY**: Complexity signals conflict — single-hop structure suggests simpler route, but editorial quality judgment exceeds mechanical rewriting. Tension between structural complexity (low) and output quality complexity (high).

2. **BOUNDARY_CASE**: Sonnet-opus gap of 0.02 is negligible. Opus exclusion relies on narrow structural observation.

**Output:**
route_exclusions:
  - route: haiku
    reason: "Query requires editorial judgment to distinguish key points from expendable detail during the conciseness rewrite, not merely mechanical shortening."
  - route: opus
    reason: "Query specifies a single-paragraph transformation with a bounded objective — conciseness — involving no multi-step reasoning or open-ended analytical judgment."
ambiguity_tags:
  - AMBIGUOUS_COMPLEXITY
  - BOUNDARY_CASE
```

---

## Verification Results

All 17 criteria PASS. Key highlights:
- Both examples have complete exclusion coverage
- No exclusions reference model capabilities
- rt-4 flagged with BOUNDARY_CASE (gap 0.04)
- rt-9 flagged with AMBIGUOUS_COMPLEXITY + BOUNDARY_CASE (gap 0.02, conflicting complexity signals)
- Agent reasoning traces ambiguity back to exclusion-writing difficulty
- Visible confidence differential: haiku exclusions "straightforward"/"moderately confident" vs opus exclusions "harder"/"narrow observation"
- Tag justifications substantive — not just "scores are close"
