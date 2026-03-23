---
name: generate-routing-rationale
description: >
  Produce tier_disqualifiers and propose ambiguity_tags for a routing example.
  Use after classify-example has determined intent and complexity. Takes query
  text, ground-truth route, classification output, and vocabulary registry.
  Outputs disqualifier list covering all non-assigned routes and candidate
  ambiguity tags.
---

# generate-routing-rationale

Write `tier_disqualifiers` and propose `ambiguity_tags` for a routing example. Run this skill after `classify-example` has produced `intent_pattern` and `complexity_structure`.

## Inputs

- **query**: the raw query text from the dataset example
- **ground_truth_route**: the expected route value from the dataset
- **classification_output**: `intent_pattern` and `complexity_structure` from `classify-example`
- **vocabulary_registry**: current entries for `ambiguity_tags`
- **all_routes**: the complete list of valid route values in the dataset

## Procedure

### Step 1 — Write tier_disqualifiers

For each route in `all_routes` that is not the `ground_truth_route`, write at least one disqualifier sentence.

**Ordering:**
- If routes are numerically ordered (e.g., tiered), write disqualifiers from lowest to highest.
- If routes are unordered, write them in alphabetical order.

**What each disqualifier must do:**
- Reference a specific, observable property of the query that rules out that route.
- Be expressed as a single, non-empty sentence.
- Stand alone — it must not rely on knowledge of what the assigned route can or cannot do.

See `references/disqualifier-guidelines.md` for DO/DON'T examples.

### Step 2 — Assess ambiguity

Review the disqualifiers written in Step 1. Flag the example for an `ambiguity_tag` if any of the following apply:

- One or more disqualifiers were difficult to write because the query sits near a routing boundary.
- The query could plausibly belong to multiple routes and the classification required a judgement call.
- The classification output from `classify-example` contained conflicting signals between `intent_pattern` and `complexity_structure`.

If none of the above apply, output an empty `ambiguity_tags` list.

If ambiguity is detected, propose one or more tags from the vocabulary registry. If no existing tag fits, propose a new SCREAMING_SNAKE_CASE candidate. Tags proposed here are candidates — cluster threshold enforcement happens during post-loop validation.

### Output

```
tier_disqualifiers:
  - route: <route-value>
    reason: <single sentence referencing an observable query property>
  # one entry per non-assigned route (multiple entries allowed per route)
ambiguity_tags:       # omit or leave empty if no ambiguity
  - <TAG_NAME>
```

## Notes

- The `route` field in each disqualifier must exactly match a value from `all_routes` — these are opaque strings; do not paraphrase or abbreviate them.
- Every non-assigned route must have at least one disqualifier. Missing coverage is an annotation error.
- Disqualifiers should be written from the query's perspective, not from any route target's perspective.
