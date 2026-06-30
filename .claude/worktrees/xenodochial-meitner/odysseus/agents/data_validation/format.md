# Routing Dataset Format Reference

This document defines the canonical target schema for routing datasets in Project Odysseus. It describes the format that the Data Validation Agent produces after ingesting and transforming user-provided data.

## File Format

JSONL — one JSON object per line. UTF-8 encoded. Blank lines and trailing newlines are tolerated.

## Required Fields

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Stable identifier for deduplication and result tracking |
| `input` | `string` | The user query to be routed |
| `expected` | `object` | Contains `route` and `routes` (see below) |
| `split` | `string` | `"dev"` or `"holdout"` — assigned during the dataset split step |

### `expected` sub-fields

| Field | Type | Description |
|---|---|---|
| `route` | `string` | The target routing tier for this query |
| `routes` | `object` | Per-model cost/quality data. Keys are model names. |

### `expected.routes.<model>` sub-fields

| Field | Type | Description |
|---|---|---|
| `cost` | `number` | Cost per call for that model |
| `quality_score` | `number` | Quality score for that model |

## Schema Constraints

1. **No null values** in required fields.
2. **Type correctness** — `input` must be a string, `expected` must be an object, `id` and `split` must be strings.
3. **Split values** — must be `"dev"` or `"holdout"`. Assigned during the dataset split step, not by the user.
4. **Route-in-routes (record-level)** — `expected.route` must be a key in `expected.routes`.
5. **Consistent model set (dataset-level)** — all records must have the same keys in `expected.routes`.
6. **Non-empty routes** — `expected.routes` must contain at least one entry.
7. **Unique IDs** — all `id` values must be unique within a dataset.
8. **Minimum record count** — each routing tier must meet thresholds defined in THP-69.
9. **Quality scores** — no range constraint imposed; normalization is handled conversationally (see THP-145).

## Informative Field Alias Table

Non-normative starting point for auto-mapping user field names to target fields.

| Target field | Common aliases |
|---|---|
| `input` | `query`, `question`, `prompt`, `text`, `message`, `user_input`, `request` |
| `expected.route` | `target`, `tier`, `model`, `label`, `class`, `category` |
| `id` | `example_id`, `row_id`, `uuid`, `index`, `idx` |
| `expected.routes.*.cost` | `price`, `cost_per_call`, `model_cost` |
| `expected.routes.*.quality_score` | `quality`, `score`, `accuracy`, `performance` |

## Examples

### Valid

```json
{"id": "ex-1", "input": "Explain quantum entanglement", "expected": {"route": "opus", "routes": {"opus": {"cost": 0.05, "quality_score": 0.98}, "sonnet": {"cost": 0.01, "quality_score": 0.88}, "haiku": {"cost": 0.002, "quality_score": 0.72}}}, "split": "dev"}
```

```json
{"id": "ex-2", "input": "What is my account balance?", "expected": {"route": "haiku", "routes": {"opus": {"cost": 0.05, "quality_score": 0.65}, "sonnet": {"cost": 0.01, "quality_score": 0.62}, "haiku": {"cost": 0.002, "quality_score": 0.60}}}, "split": "holdout"}
```

### Invalid

Missing `expected`:
```json
{"id": "ex-3", "input": "Help me reset my password", "split": "dev"}
```

`route` not in `routes` keys:
```json
{"id": "ex-4", "input": "Summarize this document", "expected": {"route": "gpt-4o", "routes": {"opus": {"cost": 0.05, "quality_score": 0.95}}}, "split": "dev"}
```

`input` is null:
```json
{"id": "ex-5", "input": null, "expected": {"route": "sonnet", "routes": {"sonnet": {"cost": 0.01, "quality_score": 0.8}}}, "split": "dev"}
```
