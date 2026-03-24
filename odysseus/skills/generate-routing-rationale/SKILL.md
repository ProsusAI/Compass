---
name: generate-routing-rationale
description: >
  Use when a routing example already has intent_pattern and complexity_structure
  assigned and needs route_exclusions and ambiguity_tags. Triggers after
  classify-example completes, during annotation loops, or when exclusion
  coverage is missing or incomplete. Requires a routing_context preamble.
---

# generate-routing-rationale

## Overview

Write `route_exclusions` and propose `ambiguity_tags` for a routing example. The core principle: **exclusions must reference observable query properties, never route capabilities** — explain why the query rules out a route, not why a route fails the query.

**REQUIRED:** Run `classify-example` first to produce `intent_pattern` and `complexity_structure`.

## When to Use

- After `classify-example` has classified an example and disqualifiers are needed
- When disqualifier coverage is incomplete (missing routes)
- During annotation loops that produce full routing rationale cards

**Do NOT use** for classifying `intent_pattern` or `complexity_structure` — use `classify-example` for those fields first.

## Quick Reference

| Field | Convention | Coverage | Key rule |
|---|---|---|---|
| `route_exclusions` | One entry per non-assigned route | Every non-assigned route must have ≥1 | Reference query properties, not route capabilities |
| `ambiguity_tags` | SCREAMING_SNAKE_CASE | Only if ambiguity detected | Propose from registry; new tags are candidates until cluster threshold met |

## Inputs

- **query**: the raw query text from the dataset example
- **ground_truth_route**: the expected route value from the dataset
- **classification_output**: `intent_pattern` and `complexity_structure` from `classify-example`
- **vocabulary_registry**: current entries for `ambiguity_tags`
- **routing_context**: structured preamble describing the routing domain, routes, dimensions, and optional ordering

## Procedure

### Step 1 — Write route_exclusions

For each route in `routing_context.routes` that is not the `ground_truth_route`, write at least one exclusion sentence.

**Ordering:**
- If `routing_context.route_ordering` is present, write exclusions from lowest to highest along the declared dimension.
- If `routing_context.route_ordering` is absent, write them in alphabetical order by route name.

**What each exclusion must do:**
- Reference a specific, observable property of the query that rules out that route.
- Be expressed as a single, non-empty sentence.
- Stand alone — it must not rely on knowledge of what the assigned route can or cannot do.

See `references/exclusion-guidelines.md` for DO/DON'T examples.

### Step 2 — Assess ambiguity

Review the disqualifiers written in Step 1. Flag the example for an `ambiguity_tag` if any of the following apply:

- One or more disqualifiers were difficult to write because the query sits near a routing boundary.
- The query could plausibly belong to multiple routes and the classification required a judgement call.
- The classification output from `classify-example` contained conflicting signals between `intent_pattern` and `complexity_structure`.

If none of the above apply, output an empty `ambiguity_tags` list.

If ambiguity is detected, propose one or more tags from the vocabulary registry. If no existing tag fits, propose a new SCREAMING_SNAKE_CASE candidate. Tags proposed here are candidates — cluster threshold enforcement happens during post-loop validation.

### Output

```
route_exclusions:
  - route: <route-value>
    reason: <single sentence referencing an observable query property>
  # one entry per non-assigned route (multiple entries allowed per route)
ambiguity_tags:       # omit or leave empty if no ambiguity
  - <TAG_NAME>
```

## Common Mistakes

- **Paraphrasing route values.** The `route` field must exactly match a route name from `routing_context.routes` — these are opaque strings. Do not abbreviate, re-case, or translate them.
- **Missing coverage.** Every non-assigned route must have at least one exclusion. Missing routes are annotation errors caught during validation.
- **Writing from the route's perspective.** "This route lacks web access" describes the route. "Query requires real-time retrieval from external sources" describes the query. Always write from the query's perspective.
- **Compound sentences.** Each `reason` must be a single sentence. Split compound claims into separate exclusion entries for the same route.
