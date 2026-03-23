---
name: classify-example
description: >
  Jointly determine intent_pattern and complexity_structure for a routing
  example. Use when annotating dataset examples with routing rationale cards.
  Takes query text, ground-truth route, and vocabulary registry as input.
  Outputs field values and optionally proposes new vocabulary entries when
  no existing entry fits.
---

# classify-example

Annotate a routing example with `intent_pattern` and `complexity_structure` by following the procedure below. These two fields are jointly determined — use combined reasoning rather than classifying each field in isolation.

## Inputs

- **query**: the raw query text from the dataset example
- **ground_truth_route**: the expected route value from the dataset
- **vocabulary_registry**: current entries for `intent_pattern` and `complexity_structure`

## Procedure

### Step 1 — Determine complexity_structure first

Analyse the query's reasoning topology before assigning any intent label. Ask:

- How many distinct reasoning steps does a correct response require?
- Are steps independent (parallel) or does each step depend on prior output (sequential)?
- Does the query contain multiple disconnected constraints that must all be satisfied?

Parallel constraints do not imply sequential dependencies. Count only genuine dependencies, not surface verbosity.

Assign `complexity_structure` to the best-matching registry entry. If no entry fits, note a candidate for proposal (see Step 3).

### Step 2 — Classify intent_pattern

With `complexity_structure` established, classify the task type. Use complexity to break ties when the query could map to multiple intent categories. Ask:

- What is the primary goal of the query (transformation, retrieval, generation, analysis, etc.)?
- Does the complexity level shift the likely intent category?

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
