# Data Quality Report — Output Format Reference

This document defines the structure of the data quality report produced by the Data Validation agent. It is the primary input to THP-106 (system prompt assembly).

## Report Sections

The report has four sections, produced in this order.

### 1. Dataset Summary

Two natural-language paragraphs written by the agent:

1. **Data description** — what the dataset contains: the routing problem domain, what kinds of queries are represented, and what the routing tiers correspond to.
2. **Validation summary** — total record count, tier names and distribution, any issues found, and overall verdict (ready for downstream processing or blocked).

This section is agent-written, not code-generated. The agent bases it on the outputs of the three check functions below.

### 2. Schema Consistency Findings

Produced by `check_schema_conformance()` in `data_validation_checks.py`.

One finding per check type, each containing:
- `field` — field path checked (e.g., `"expected.route"`)
- `status` — `"pass"` or `"fail"`
- `violation` — description if failed, null if passed
- `row_indices` — indices of failing rows

Checks: required keys present and non-null, correct types, route-in-routes, non-empty routes, consistent model set, unique IDs. See the spec for full details.

### 3. Label Distribution Stats

Produced by `check_label_distribution()` in `data_validation_checks.py`.

Per tier: count, percentage, imbalance flag. Dataset-level: total records, number of tiers, imbalanced tier list, threshold used.

### 4. Volume Adequacy Assessment

Produced by `check_volume_adequacy()` in `data_validation_checks.py`.

Per tier: verdict (`adequate` / `insufficient` / `absent`), actual count, minimum required. Dataset-level: overall verdict (`pass` / `fail`), threshold used.

## Implementation

All check functions and Pydantic models live in `odysseus/agents/data_validation_checks.py`. The top-level `DataQualityReport` model wraps all four sections.

## Linkages

- **THP-80** — Schema constraints that `check_schema_conformance` validates against.
- **THP-69** — Volume thresholds and imbalance minimums passed as parameters.
- **THP-145** — Imports and calls the check functions directly.
- **THP-106** — Embeds this report structure into the agent system prompt.
- **THP-74** — Consumes the data quality report; reads the dataset summary for quick context.
