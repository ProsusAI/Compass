# Scenario 27: Classify Example — Mid-Tier Sonnet Queries

**Date:** 2026-03-23
**Verdict:** PASS (16/16 criteria)

---

## Transcript

```
=== SCENARIO 27: Classify Example — Mid-Tier Sonnet Queries ===

--- Turn 1 (rt-4: summarize + draft questions → sonnet) ---
User Simulator: [Provides rt-4 with full registry containing 5 intent_pattern entries and 2 complexity_structure entries]

Agent:

**Step 1 — Determine complexity_structure first**

Two distinct phases:
1. Summarize the earnings report across three dimensions
2. Draft three follow-up questions for the CFO

Step 2 depends on step 1 — questions should target areas surfaced by the summary. Genuine sequential dependency.

Compared to existing sequential-dependency examples (rt-2, rt-6, rt-8), rt-4 is "on the lighter end" — shorter dependency chain, less analytically demanding. But clearly exceeds single-hop.

**complexity_structure: sequential-dependency** (existing entry fits)

**Step 2 — Classify intent_pattern**

Checked all 5 existing entries:
- factual-lookup: Not a single factual answer ✗
- arithmetic-computation: No calculation ✗
- comparative-analysis: Not comparing frameworks ✗
- persuasive-generation: Not persuasive argumentation ✗
- pattern-analysis: Not identifying patterns in data ✗

Core task: structured summarization + derivative content generation.

**Proposing: summarization-generation**

**Output:**
intent_pattern: summarization-generation
complexity_structure: sequential-dependency
proposed_entries:
  - field: intent_pattern
    name: summarization-generation
    definition: "Query asks for condensed extraction from a source document followed by generation of derivative content"
    example_ids: ["rt-4"]
    justification: "Existing entries cover retrieval, computation, comparison, persuasion, and pattern analysis, but none cover the summarize-then-generate pattern."

--- Turn 2 (rt-9: rewrite for conciseness → sonnet) ---
User Simulator: [Provides rt-9 with same registry]

Agent:

**Step 1 — Determine complexity_structure first**

A skilled writer performs "rewrite for conciseness while keeping key points" as a single integrated transformation — not two sequential steps. Fundamentally a single transformation operation.

Contrasted with rt-4: "in rt-4, the second task (questions) is a genuinely separate deliverable. In rt-9, there is only one deliverable."

Acknowledged rt-9 is harder than simple factual lookups (requires comprehension and judgment) but complexity_structure describes reasoning topology, not difficulty.

**complexity_structure: single-hop** (existing entry fits)

**Step 2 — Classify intent_pattern**

Checked all existing entries + proposed summarization-generation:
- factual-lookup: Not retrieving facts ✗
- arithmetic-computation: No calculation ✗
- summarization-generation: Close but distinct — "summarization extracts meaning into new form; rewriting edits the existing form" ✗
- Others: clearly don't fit ✗

**Proposing: text-transformation**

**Output:**
intent_pattern: text-transformation
complexity_structure: single-hop
proposed_entries:
  - field: intent_pattern
    name: text-transformation
    definition: "Query asks for rewriting or editing existing text to meet a specific quality criterion such as conciseness, tone, or clarity"
    example_ids: ["rt-9"]
    justification: "Existing entries cover retrieval, computation, comparison, persuasion, pattern analysis, and summarization-generation, but none cover direct text editing/rewriting."
```

---

## Verification Results

All 16 criteria PASS. Key highlights:
- rt-4: sequential-dependency (multi-step) with new `summarization-generation` intent
- rt-9: single-hop (single transformation) with new `text-transformation` intent
- Agent correctly placed these on the complexity spectrum — neither lumped with simple lookups nor complex analysis
- Existing registry checked systematically before proposals
- No overlapping entries created
- Complexity before intent in all reasoning
