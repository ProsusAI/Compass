# THP-80 — Routing Dataset Format Specification

**Ticket:** [THP-80](https://prosus-thymo-thesis.atlassian.net/browse/THP-80)
**Epic:** [THP-73](https://prosus-thymo-thesis.atlassian.net/browse/THP-73) — Data Validation Agent
**Status:** Design approved
**Date:** 2026-03-23

## Overview

This spec defines the canonical target schema for routing datasets in Project Odysseus. It describes what a fully valid, pipeline-ready dataset looks like — the format that the Data Validation Agent produces after ingesting and transforming user-provided data.

The spec does not cover transformation logic or conversational flows for gap-filling — those are defined in THP-145 (validation logic) and THP-106 (system prompt).

## File Format

JSONL — one JSON object per line. Blank lines and trailing newlines are tolerated. UTF-8 encoded. Each line is parsed independently.

Users may provide data in other formats (CSV, JSON array). Format conversion is out of scope for this spec and is handled by the agent's transformation logic (THP-145).

## Target Schema

### Required Fields

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Stable identifier for deduplication and result tracking |
| `input` | `string` | The user query to be routed |
| `expected` | `object` | Routing expectation — contains `route` and `routes` |
| `split` | `string` | Either `"dev"` or `"holdout"` — assigned by the Data Validation Agent, not provided by the user |

The `expected` object must contain:

| Field | Type | Description |
|---|---|---|
| `expected.route` | `string` | The target routing tier for this query |
| `expected.routes` | `object` | Per-model cost/quality data. Keys are model names, values are objects with `cost` and `quality_score` |

Each entry in `expected.routes` must contain:

| Field | Type | Description |
|---|---|---|
| `cost` | `number` | Cost per call for that model |
| `quality_score` | `number` | Quality score for that model |

### Optional Fields

| Field | Type | Description |
|---|---|---|
| `metadata` | `object` | Arbitrary additional context (e.g., source, domain, difficulty tag). Not validated beyond being a JSON object. |

## Schema Constraints

1. **No null values** in required fields — `id`, `input`, `expected`, `split` must all be present and non-null.
2. **Type correctness** — `input` must be a string, `expected` must be an object, `id` and `split` must be strings, `expected.route` must be a string, `expected.routes` values must have numeric `cost` and `quality_score`.
3. **Split values** — `split` must be exactly `"dev"` or `"holdout"`. This field is assigned by the Data Validation Agent, not provided by the user.
4. **Consistent routing tiers** — the set of unique `expected.route` values defines the routing tiers; `expected.route` must be a key present in `expected.routes`.
5. **Consistent model set** — all records should have the same set of keys in `expected.routes` (same models across the dataset).
6. **Minimum record count** — at least one record per unique routing tier (exact thresholds defined in THP-69).

## Informative Field Alias Table

This table provides common field name variations that users may use in their submitted data. It is **non-normative** — a starting point for auto-mapping, not an exhaustive list.

| Target field | Common aliases |
|---|---|
| `input` | `query`, `question`, `prompt`, `text`, `message`, `user_input`, `request` |
| `expected.route` | `target`, `tier`, `model`, `label`, `class`, `category` |
| `id` | `example_id`, `row_id`, `uuid`, `index`, `idx` |
| `expected.routes.*.cost` | `price`, `cost_per_call`, `model_cost` |
| `expected.routes.*.quality_score` | `quality`, `score`, `accuracy`, `performance` |

The Data Validation Agent may use this table as a heuristic for auto-mapping. When ambiguous, it should ask the user to confirm the mapping. Mapping logic is defined in THP-145.

## Examples

### Valid Records

**Complete record:**
```json
{"id": "ex-1", "input": "Explain quantum entanglement", "expected": {"route": "opus", "routes": {"opus": {"cost": 0.05, "quality_score": 0.98}, "sonnet": {"cost": 0.01, "quality_score": 0.88}, "haiku": {"cost": 0.002, "quality_score": 0.72}}}, "split": "dev"}
```

**With optional metadata:**
```json
{"id": "ex-2", "input": "What is my account balance?", "expected": {"route": "haiku", "routes": {"opus": {"cost": 0.05, "quality_score": 0.65}, "sonnet": {"cost": 0.01, "quality_score": 0.62}, "haiku": {"cost": 0.002, "quality_score": 0.60}}}, "split": "holdout", "metadata": {"source": "production_logs", "domain": "billing"}}
```

### Invalid Records

**Missing `expected`:**
```json
{"id": "ex-3", "input": "Help me reset my password", "split": "dev"}
```

**`route` not present in `routes` keys:**
```json
{"id": "ex-4", "input": "Summarize this document", "expected": {"route": "gpt-4o", "routes": {"opus": {"cost": 0.05, "quality_score": 0.95}}}, "split": "dev"}
```

**`input` is null:**
```json
{"id": "ex-5", "input": null, "expected": {"route": "sonnet", "routes": {"sonnet": {"cost": 0.01, "quality_score": 0.8}}}, "split": "dev"}
```

## Notes for Downstream Tickets

### THP-145 (Validation Logic)

- The agent should support **field auto-mapping** using the alias table as a heuristic, asking the user to confirm when ambiguous.
- When cost/quality data is missing, the agent should **ask the user** to provide it rather than guessing or using defaults.
- Quality scores outside 0.0–1.0 are not rejected — the agent asks the user how to normalize them.
- The `split` field is **assigned by the agent**, not expected from the user.
- The agent should handle non-JSONL input formats (CSV, JSON array) via conversion.

### THP-106 (System Prompt)

- The conversational flow for gap-filling (missing fields, ambiguous mappings, normalization) should be defined in the system prompt.

## Linkages

| Touch point | Detail |
|---|---|
| THP-145 | Validation logic implements the schema constraints and transformation rules referenced here. |
| THP-81 | Code generation context references this schema so generated analysis code targets the correct fields. |
| THP-106 | Final system prompt embeds this spec so the agent knows what to validate against. |
| THP-69 | Volume thresholds defined there align with the minimum record count constraint. |
