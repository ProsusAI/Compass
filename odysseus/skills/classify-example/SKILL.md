---
name: classify-example
description: >
  Use when annotating a routing dataset example with intent_pattern and
  complexity_structure fields. Triggers during routing rationale card
  generation, dataset annotation loops, or when a new example needs
  classification against the vocabulary registry. Requires a routing_context
  preamble describing the domain, routes, and routing dimensions.
---

# classify-example

## Overview

Jointly determine `intent_pattern` and `complexity_structure` for a routing example. The core principle: **complexity informs intent, not the other way around** — always analyse reasoning topology before assigning task-type labels.

## When to Use

- Annotating dataset examples with routing rationale cards
- Running the annotation loop on new or updated dataset entries
- Re-classifying examples after vocabulary registry changes

**Do NOT use** for writing `route_exclusions` or `ambiguity_tags` — use `generate-routing-rationale` for those fields after this skill completes.

## Quick Reference

| Field | Convention | Determine | Based on |
|---|---|---|---|
| `complexity_structure` | kebab-case | First | Reasoning topology: step count, dependencies, constraints |
| `intent_pattern` | kebab-case | Second | Primary goal, informed by complexity |
| `proposed_entries` | kebab-case | If needed | Cluster threshold from `references/vocabulary-registry-rules.md` |

## Inputs

- **query**: the raw query text from the dataset example
- **ground_truth_route**: the expected route value from the dataset
- **vocabulary_registry**: current entries for `intent_pattern` and `complexity_structure`
- **routing_context**: structured preamble describing the routing domain, routes, dimensions, and optional seed vocabulary

## Procedure

### Step 1 — Determine complexity_structure first

Analyse the query against `routing_context.routing_dimensions` before assigning any intent label. For each dimension, assess the degree to which the query demands it. Ask:

- Which routing dimensions are relevant to this query?
- How much does the query demand along each relevant dimension?
- Does the query require capabilities at the upper end of any dimension, or is it well within the lower range?

For example, if a "capability" or "complexity" dimension is present, consider: how many distinct reasoning steps does a correct response require? Are steps independent (parallel) or does each depend on prior output (sequential)? Does the query contain multiple constraints that must all be satisfied?

Parallel constraints do not imply sequential dependencies. Count only genuine dependencies, not surface verbosity.

Assign `complexity_structure` to the best-matching registry entry. If no entry fits, note a candidate for proposal (see Step 3).

### Step 2 — Classify intent_pattern

With `complexity_structure` established, classify the task type within the domain described by `routing_context.domain`. Use complexity to break ties when the query could map to multiple intent categories. Ask:

- What is the primary goal of the query (transformation, retrieval, generation, analysis, etc.)?
- Does the complexity level shift the likely intent category?
- Does the domain context suggest specific intent categories that are relevant?

Assign `intent_pattern` to the best-matching registry entry. If no entry fits, note a candidate for proposal.

### Step 3 — Vocabulary registry matching

For each field, confirm the chosen entry satisfies the cluster threshold rule (see `references/vocabulary-registry-rules.md`).

If no existing entry fits, propose a new entry with:
- `name`: kebab-case identifier
- `definition`: one-sentence description
- `example_ids`: IDs of dataset examples that would use this entry
- `justification`: why no existing entry is sufficient

### Output

```
intent_pattern: <registry-entry-name>
complexity_structure: <registry-entry-name>
proposed_entries:          # omit if empty
  - field: intent_pattern | complexity_structure
    name: <kebab-case>
    definition: <one sentence>
    example_ids: [<id>, ...]
    justification: <why existing entries are insufficient>
```

## Common Mistakes

- **Verbosity is not complexity.** A long query with parallel constraints is not the same as a query requiring sequential dependencies.
- **Do not assume domain-specific categories exist.** Vocabulary entries must emerge from the data; do not invent categories for specific domains.
- **Always determine complexity before intent.** Classifying intent first locks in assumptions that complexity reasoning should inform.
- **Both fields inform each other.** If the complexity assignment feels wrong after classifying intent, revisit Step 1 before finalising.
