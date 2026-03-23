# Scenario 28: Full Annotation Pipeline — Classify Then Generate Rationale

**Date:** 2026-03-23
**Verdict:** PASS (18/18 criteria)

---

## Transcript

```
=== SCENARIO 28: Full Annotation Pipeline — Classify Then Generate Rationale ===

--- Turn 1 (classify-example on rt-3: "Translate good morning to Spanish" → haiku) ---
User Simulator: [Provides rt-3 with partial registry: factual-lookup, single-hop, 2 ambiguity seeds]

Agent:

**Step 1 — Determine complexity_structure first**

- One step: recall or produce the Spanish translation
- No dependencies, no multiple constraints
- Existing `single-hop` fits precisely

**complexity_structure: single-hop**

**Step 2 — Classify intent_pattern**

Translation of a common greeting is arguably retrievable from common knowledge. However, the primary goal is transformation (converting text between languages), not retrieval of a standalone fact.

Considered: `factual-lookup` partially fits since simple translation could be viewed as factual recall. But before proposing a new entry, checked cluster threshold — a new `direct-translation` entry would have only 1 example (below threshold of 3). Given that common-phrase translation is reasonably within "factual-lookup" scope, used `factual-lookup` as best available match while noting marginal fit.

**intent_pattern: factual-lookup** (with proposed `direct-translation` for future collection)

**Output:**
intent_pattern: factual-lookup
complexity_structure: single-hop
proposed_entries:
  - field: intent_pattern
    name: direct-translation
    definition: "Query asks for a straightforward translation of a word or phrase into a specified target language"
    example_ids: ["rt-3"]
    justification: "factual-lookup covers knowledge retrieval but does not capture the transformation nature of translation; however, this proposal has only 1 example (below threshold of 3)"

--- Turn 2 (generate-routing-rationale on rt-3, using classification from Turn 1) ---
User Simulator: [Provides rt-3 with classification from Turn 1: intent_pattern=factual-lookup, complexity_structure=single-hop]

Agent:

**Step 1 — Write tier_disqualifiers**

Using classification: intent_pattern = factual-lookup, complexity_structure = single-hop (from Turn 1 output).

Disqualifier for sonnet:
- route: sonnet
  reason: "The query asks for a single common-phrase translation requiring no multi-step reasoning or elaboration."

Disqualifier for opus:
- route: opus
  reason: "The query contains one short phrase with an unambiguous target language and no constraints requiring synthesis or extended analysis."

**Step 2 — Assess ambiguity**

- Disqualifiers straightforward to write
- Classification signals (factual-lookup + single-hop) consistently point to simplest route
- Quality scores (haiku=0.96, sonnet=0.95, opus=0.94) — all similar but task is definitively simple

No ambiguity conditions apply.

**Output:**
tier_disqualifiers:
  - route: sonnet
    reason: "The query asks for a single common-phrase translation requiring no multi-step reasoning or elaboration."
  - route: opus
    reason: "The query contains one short phrase with an unambiguous target language and no constraints requiring synthesis or extended analysis."
ambiguity_tags: []

**Combined RationaleCard for rt-3:**
intent_pattern: factual-lookup
complexity_structure: single-hop
tier_disqualifiers:
  - route: sonnet
    reason: "The query asks for a single common-phrase translation requiring no multi-step reasoning or elaboration."
  - route: opus
    reason: "The query contains one short phrase with an unambiguous target language and no constraints requiring synthesis or extended analysis."
ambiguity_tags: []
```

---

## Verification Results

All 18 criteria PASS. Key highlights:
- **Pipeline handoff correct**: Classification values (factual-lookup, single-hop) from Turn 1 used verbatim in Turn 2
- **No drift**: Same values in both turns
- **Full RationaleCard assembled**: All 4 fields present, parseable into valid model
- **Disqualifiers reference observable properties**: single phrase, no multi-step reasoning, unambiguous target
- **No model capability references**
- **Clear-cut assessment correct**: No ambiguity tags (quality scores close but task definitively simple)
- **Full reasoning chain traceable**: complexity → intent → disqualifiers → ambiguity
