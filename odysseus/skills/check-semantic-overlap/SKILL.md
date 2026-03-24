---
name: check-semantic-overlap
description: >
  Pairwise semantic overlap detection across vocabulary registry entries.
  Use during validation of a RationaleCardSet to check that no two entries
  within the same dimension (intent_pattern, complexity_structure,
  ambiguity_tags) are semantically redundant.
---

# check-semantic-overlap

## Overview

Detect semantic redundancy in vocabulary registry entries by comparing definitions pairwise within each dimension. The core principle: **two entries are overlapping if their definitions describe the same concept under different labels** — surface framing differences do not justify separate entries.

## When to Use

- During Phase 3 validation of the Routing Analysis pipeline, after deterministic checks pass
- When the vocabulary registry has been modified (entries added, merged, or re-defined)
- When re-validating after auto-fix of cluster threshold or pruning issues

**Do NOT use** for classification (`classify-example`) or rationale generation (`generate-routing-rationale`).

## Quick Reference

| Dimension | Convention | Comparison scope |
|---|---|---|
| `intent_pattern` | kebab-case entries | All pairs within dimension |
| `complexity_structure` | kebab-case entries | All pairs within dimension |
| `ambiguity_tags` | SCREAMING_SNAKE_CASE entries | All pairs within dimension |

Cross-dimension comparisons (e.g., an intent vs. a complexity entry) are never performed — entries in different dimensions describe fundamentally different aspects.

## Inputs

- **vocabulary_registry**: the `VocabularyRegistry` to check, containing three lists of `VocabularyEntry`
  - Each `VocabularyEntry` has: `name`, `definition`, `example_ids`, `justification`

## Procedure

### Step 1 — Enumerate pairs

For each dimension (`intent_pattern`, `complexity_structure`, `ambiguity_tags`), enumerate all unique pairs of entries. Skip dimensions with fewer than 2 entries.

### Step 2 — Compare definitions

For each pair, compare the `definition` fields. Determine whether:

1. **One definition substantially subsumes the other** — entry A's definition covers everything entry B describes, making B redundant. Subsumption requires that B adds no meaningful distinction beyond what A already captures.
2. **Both describe the same concept with different wording** — the definitions are paraphrases or near-synonyms, differing only in surface framing (e.g., "document-summarisation" vs "text-condensation").
3. **They are genuinely distinct** — the definitions describe different concepts, even if the entries sometimes co-occur on the same examples.

Only flag cases (1) and (2) as overlapping.

### Step 3 — Report findings

Collect all overlapping pairs with a one-sentence explanation of the overlap. If no overlap is found, report a clean verdict.

See `references/vocabulary-registry-rules.md` for the semantic overlap policy.

### Output

```yaml
overlapping_pairs:    # omit section if no overlap found
  - dimension: intent_pattern | complexity_structure | ambiguity_tags
    entry_a: <name>
    entry_b: <name>
    reasoning: <one sentence explaining the overlap>
verdict: overlap_detected | no_overlap
```

## Common Mistakes

- **Co-occurrence is not overlap.** Two entries appearing on the same examples does not make them semantically redundant — they may describe different aspects of those examples.
- **Names are not definitions.** Similar-sounding names (e.g., "data-lookup" and "data-retrieval") may have genuinely distinct definitions. Always compare definitions, not names.
- **Cross-dimension comparison is invalid.** Never flag entries from different dimensions as overlapping — `intent_pattern` and `complexity_structure` describe fundamentally different things.
- **Partial overlap is not subsumption.** If entry A covers 80% of what entry B describes but B captures a meaningful distinction, they are not overlapping. Subsumption requires that B adds nothing A doesn't already cover.
