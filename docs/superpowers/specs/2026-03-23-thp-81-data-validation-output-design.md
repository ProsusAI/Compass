# THP-81 — Data Validation Output Format and Validation Checks

**Ticket:** [THP-81](https://prosus-thymo-thesis.atlassian.net/browse/THP-81)
**Epic:** [THP-73](https://prosus-thymo-thesis.atlassian.net/browse/THP-73) — Data Validation Agent
**Status:** Design approved
**Date:** 2026-03-23

## Overview

This spec defines two deliverables for the Data Validation agent:

1. The structure of the **data quality report** the agent produces after validating a user-submitted routing dataset.
2. Pre-written **validation check functions** (Python) that the agent executes to populate the report.

The Data Validation agent is a **format gate** — it ensures the dataset is structurally valid and meets volume requirements before passing it to downstream agents. It does not perform semantic analysis, missing signal detection, or data collection suggestions — those are downstream concerns (THP-74 Routing Analysis).

## Deliverables

### 1. Reference document — `odysseus/agents/data_validation_output.md`

Prose companion defining the report structure and referencing the Python module. Consumed by THP-106 (system prompt) to instruct the agent on what to produce.

### 2. Validation checks — `odysseus/agents/data_validation_checks.py`

Python module with three functions operating on raw parsed JSONL rows (list of dicts). Importable by THP-145 (validation logic). Uses only `pandas`, `json`, and `collections` from the standard library plus pandas.

## Report Structure

The data quality report has four sections, produced in this order.

### Section 1 — Dataset Summary

A natural-language paragraph written by the agent (not code-generated) summarizing:

- Total record count and number of routing tiers.
- Tier names and their distribution (e.g., "3 tiers: opus (42%), sonnet (35%), haiku (23%)").
- Any issues found — schema violations, volume gaps, imbalanced tiers.
- Overall verdict: ready for downstream processing or blocked on issues.

This section exists so downstream agents (THP-74) can read just this paragraph and understand what they are working with, without parsing the structured sections.

**Producer:** The agent writes this based on the outputs of the three check functions. Instructions for generating it are defined in THP-106 (system prompt).

### Section 2 — Schema Consistency Findings

A list of per-field validation results.

Each finding:

| Field | Type | Description |
|---|---|---|
| `field` | `str` | Field path checked (e.g., `"expected.route"`, `"input"`) |
| `status` | `"pass" \| "fail"` | Whether the check passed |
| `violation` | `str \| None` | Description of the violation if failed, `None` if passed |
| `row_indices` | `list[int]` | Indices of rows that failed (empty if passed) |

Checks performed:

1. Required keys present: `id`, `input`, `expected`, `expected.route`, `expected.routes`.
2. Correct types: `input` is `str`, `expected` is `dict`, `id` is `str`, `expected.route` is `str`, `expected.routes` values have numeric `cost` and `quality_score`.
3. Route-in-routes: `expected.route` is a key in `expected.routes` (per record).
4. Non-empty routes: `expected.routes` has at least one entry (per record).
5. Consistent model set: all records have the same keys in `expected.routes`.
6. Unique IDs: no duplicate `id` values across the dataset.

**Not checked:** `split` — assigned by the Routing Analysis Agent downstream per THP-80.

**Producer:** `check_schema_conformance()`.

### Section 3 — Label Distribution Stats

Per routing tier:

| Field | Type | Description |
|---|---|---|
| `tier` | `str` | Routing tier name (e.g., `"opus"`) |
| `count` | `int` | Number of records routed to this tier |
| `percentage` | `float` | Share of total dataset (0.0–1.0) |
| `imbalanced` | `bool` | `True` if below minimum threshold |

Dataset-level summary:

| Field | Type | Description |
|---|---|---|
| `total_records` | `int` | Total records in the dataset |
| `num_tiers` | `int` | Number of unique routing tiers |
| `imbalanced_tiers` | `list[str]` | Tier names flagged as imbalanced |

Imbalance threshold is sourced from THP-69's minimum tier percentage.

**Producer:** `check_label_distribution()`.

### Section 4 — Volume Adequacy Assessment

Per routing tier:

| Field | Type | Description |
|---|---|---|
| `tier` | `str` | Routing tier name |
| `verdict` | `"adequate" \| "insufficient" \| "absent"` | Volume verdict |
| `actual_count` | `int` | Records in this tier |
| `minimum_required` | `int` | Minimum required per THP-69 |

Dataset-level:

| Field | Type | Description |
|---|---|---|
| `overall_verdict` | `"pass" \| "fail"` | `"pass"` if all tiers adequate, `"fail"` otherwise |

**Producer:** `check_volume_adequacy()`.

## Validation Check Functions

All functions live in `odysseus/agents/data_validation_checks.py`.

### `check_schema_conformance(rows: list[dict]) -> list[SchemaFinding]`

Iterates all rows and checks each against the THP-80 schema. Returns one `SchemaFinding` per check type (not per row) — `row_indices` collects all failing rows for that check.

### `check_label_distribution(rows: list[dict]) -> LabelDistribution`

Counts records per `expected.route` value. Computes percentages and flags tiers below the imbalance threshold. Only operates on rows that passed schema conformance (i.e., have a valid `expected.route`).

### `check_volume_adequacy(rows: list[dict], min_per_tier: int) -> VolumeAssessment`

Compares per-tier counts against `min_per_tier`. Produces a verdict per tier and an overall dataset verdict. The `min_per_tier` parameter is passed in from THP-69's configuration, not hardcoded.

## Pydantic Models

Defined in `data_validation_checks.py` alongside the functions.

```python
class SchemaFinding(BaseModel):
    field: str
    status: Literal["pass", "fail"]
    violation: str | None = None
    row_indices: list[int] = Field(default_factory=list)

class TierDistribution(BaseModel):
    tier: str
    count: int
    percentage: float
    imbalanced: bool

class LabelDistribution(BaseModel):
    tiers: list[TierDistribution]
    total_records: int
    num_tiers: int
    imbalanced_tiers: list[str]

class TierVolume(BaseModel):
    tier: str
    verdict: Literal["adequate", "insufficient", "absent"]
    actual_count: int
    minimum_required: int

class VolumeAssessment(BaseModel):
    tiers: list[TierVolume]
    overall_verdict: Literal["pass", "fail"]
```

## Scope Boundaries

**In scope:**
- Report structure definition (four sections).
- Pre-written validation check functions (three functions).
- Pydantic models for structured output types.
- Reference document describing the report and referencing the Python module.

**Out of scope:**
- Missing signal detection — downstream (THP-74).
- Data collection suggestions — downstream (THP-74).
- `split` field validation — assigned downstream by Routing Analysis Agent.
- Query length distribution or semantic analysis.
- Dataset summary generation — agent responsibility, instructed by THP-106.
- Code generation by the agent — checks are pre-written, not generated per-run.

## Linkages

| Touch point | Detail |
|---|---|
| THP-80 | Schema constraints checked by `check_schema_conformance` are defined in the THP-80 data format spec. |
| THP-69 | Volume thresholds and imbalance minimums are sourced from THP-69's configuration. |
| THP-145 | Validation logic imports and calls the three check functions directly. |
| THP-106 | System prompt embeds the report structure and instructs the agent to write the dataset summary from check outputs. |
| THP-74 | Routing Analysis agent consumes the data quality report; the dataset summary gives it a quick overview. |
