# Scenario 25: Generate Routing Rationale — Clear-Cut Examples

**Date:** 2026-03-23
**Verdict:** PASS (18/18 criteria)

---

## Transcript

```
=== SCENARIO 25: Generate Routing Rationale — Clear-Cut Examples ===

--- Turn 1 (rt-1: "What is the capital of France?" → haiku) ---
User Simulator: [Provides rt-1 with classification intent_pattern=factual-lookup, complexity_structure=single-hop]

Agent:

**Step 1 — Write route_exclusions**

Routes are tiered (haiku < sonnet < opus). Writing from lowest to highest non-assigned.

Exclusion for sonnet:
- route: sonnet
  reason: "Query requests a single well-known fact with no synthesis or elaboration required."

Exclusion for opus:
- route: opus
  reason: "Query contains no multi-step reasoning, comparative analysis, or argument construction."

**Step 2 — Assess ambiguity**

- Sonnet exclusion: straightforward to write
- Opus exclusion: equally easy
- Classification signals fully aligned
- No plausible case for multiple routes

No ambiguity conditions apply.

**Output:**
route_exclusions:
  - route: sonnet
    reason: "Query requests a single well-known fact with no synthesis or elaboration required."
  - route: opus
    reason: "Query contains no multi-step reasoning, comparative analysis, or argument construction."
ambiguity_tags: []

--- Turn 2 (rt-2: economic policy comparison → opus) ---
User Simulator: [Provides rt-2 with classification intent_pattern=comparative-analysis, complexity_structure=sequential-dependency]

Agent:

**Step 1 — Write route_exclusions**

Exclusion for haiku:
- route: haiku
  reason: "Query requires comparing two distinct economic frameworks across multiple policy dimensions."
- route: haiku
  reason: "Query's evaluation step depends on the output of the preceding comparison of Keynesianism and monetarism."

Exclusion for sonnet:
- route: sonnet
  reason: "Query demands an evaluative judgement of explanatory power against the multi-phase 2008 financial crisis and its aftermath."

**Step 2 — Assess ambiguity**

- Haiku exclusion: easy — clearly too complex for lowest tier
- Sonnet exclusion: noted evaluative judgment layer, but clearly warranted
- Classification signals fully aligned

No ambiguity conditions apply.

**Output:**
route_exclusions:
  - route: haiku
    reason: "Query requires comparing two distinct economic frameworks across multiple policy dimensions."
  - route: haiku
    reason: "Query's evaluation step depends on the output of the preceding comparison of Keynesianism and monetarism."
  - route: sonnet
    reason: "Query demands an evaluative judgement of explanatory power against the multi-phase 2008 financial crisis and its aftermath."
ambiguity_tags: []
```

---

## Verification Results

All 18 criteria PASS. Key highlights:
- Both examples have complete exclusion coverage for all non-assigned routes
- Route values exactly match dataset values
- All reasons reference observable query properties, none reference model capabilities
- All reasons are single sentences
- Neither example tagged with ambiguity (correct — both are clear-cut)
- Ordering follows lowest-to-highest for tiered routes
- Clear language distinction between simple (rt-1) and complex (rt-2) disqualifiers
