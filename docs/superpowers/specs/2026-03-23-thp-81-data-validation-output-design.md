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

Python module with three functions operating on raw parsed JSONL rows (list of dicts). Importable by THP-145 (validation logic). Uses only the Python standard library (`collections.Counter`) — no external dependencies.

## Report Structure

The data quality report has four sections, produced in this order.

### Section 1 — Dataset Summary

Natural-language text written by the agent (not code-generated) covering two paragraphs:

1. **Data description** — what the dataset contains: the routing problem domain, what kinds of queries are represented, and what the routing tiers correspond to (e.g., "a customer support routing dataset mapping user queries to three model tiers — opus for complex reasoning, sonnet for moderate tasks, haiku for simple lookups").
2. **Validation summary** — total record count, number of routing tiers, tier names and their distribution (e.g., "3 tiers: opus (42%), sonnet (35%), haiku (23%)"), any issues found (schema violations, volume gaps, imbalanced tiers), and overall verdict: ready for downstream processing or blocked on issues.

This section exists so downstream agents (THP-74) can read just these paragraphs and understand both *what* they are working with and *whether* the data is ready, without parsing the structured sections.

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

1. Required keys present and non-null: `id`, `input`, `expected`, `expected.route`, `expected.routes`. A key that exists but has a `null` value is treated as missing.
2. Correct types: `input` is `str`, `expected` is `dict`, `id` is `str`, `expected.route` is `str`, `expected.routes` values have numeric `cost` and `quality_score`.
3. Route-in-routes: `expected.route` is a key in `expected.routes` (per record).
4. Non-empty routes: `expected.routes` has at least one entry (per record).
5. Consistent model set: all records have the same keys in `expected.routes`.
6. Unique IDs: no duplicate `id` values across the dataset.

**Not checked:** `split` — this field is assigned by the Routing Analysis Agent downstream and is not present in user-submitted data. THP-80 defines `split` as required in the *final* pipeline schema; this agent validates the *pre-split* dataset.

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
| `min_tier_percentage` | `float` | Imbalance threshold used (from THP-69) |

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
| `min_per_tier` | `int` | Minimum threshold used (from THP-69) |

**Producer:** `check_volume_adequacy()`.

## Validation Check Functions

All functions live in `odysseus/agents/data_validation_checks.py`.

**Execution order:** Functions must be called in this order because `check_label_distribution` and `check_volume_adequacy` depend on schema-valid rows:

1. `check_schema_conformance` — runs first on all rows.
2. `check_label_distribution` — runs on schema-valid rows only.
3. `check_volume_adequacy` — runs on schema-valid rows only.

**Filtering:** Each function internally skips rows that lack a valid `expected.route` (i.e., rows that would fail schema conformance). The caller passes all rows to every function — no pre-filtering required. Functions that need tier counts compute them independently from valid rows.

**Edge cases:** An empty `rows` list produces empty findings, zero counts, and `overall_verdict: "fail"`. If all rows fail schema conformance, distribution and volume functions report zero records per tier.

### `check_schema_conformance(rows: list[dict]) -> list[SchemaFinding]`

Iterates all rows and checks each against the THP-80 schema. Returns one `SchemaFinding` per check type (not per row) — `row_indices` collects all failing rows for that check.

### `check_label_distribution(rows: list[dict], min_tier_percentage: float) -> LabelDistribution`

Counts records per `expected.route` value. Computes percentages and flags tiers below the imbalance threshold. Internally skips rows without a valid `expected.route`. The `min_tier_percentage` parameter is passed in from THP-69's configuration.

### `check_volume_adequacy(rows: list[dict], min_per_tier: int) -> VolumeAssessment`

Compares per-tier counts against `min_per_tier`. Produces a verdict per tier and an overall dataset verdict. Internally skips rows without a valid `expected.route`. The `min_per_tier` parameter is passed in from THP-69's configuration, not hardcoded.

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
    min_tier_percentage: float  # threshold used, for auditability

class TierVolume(BaseModel):
    tier: str
    verdict: Literal["adequate", "insufficient", "absent"]
    actual_count: int
    minimum_required: int

class VolumeAssessment(BaseModel):
    tiers: list[TierVolume]
    overall_verdict: Literal["pass", "fail"]
    min_per_tier: int  # threshold used, for auditability

class DataQualityReport(BaseModel):
    """Top-level report wrapping all four sections."""
    summary: str  # agent-written natural-language paragraph
    schema_findings: list[SchemaFinding]
    label_distribution: LabelDistribution
    volume_assessment: VolumeAssessment
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
