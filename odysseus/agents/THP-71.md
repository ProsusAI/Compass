# THP-71 — Define default values for non-blocking gaps

**Type:** Task  
**Status:** To Do  
**Epic:** [THP-68](https://prosus-thymo-thesis.atlassian.net/browse/THP-68) — User input agent  
**Jira:** [THP-71](https://prosus-thymo-thesis.atlassian.net/browse/THP-71)

## Description

Define the table of default values the agent applies when non-blocking gaps are detected in the user's submission — for example, default target metrics, default evaluation thresholds, and default data split ratios. Each default should include a value, a rationale, and a note that it was assumed rather than user-specified.

## What to build

Produce a defaults table covering every non-blocking field from THP-108. For each entry, specify:

1. **Field name** — matching the field identifiers in THP-70.
2. **Default value** — the concrete value or rule applied when the field is absent.
3. **Rationale** — why this value is a sensible domain default.
4. **User-facing note** — the phrasing used in the gap report to inform the user that this value was assumed (must be transparent and overrideable).

Example structure:

| Field | Default value | Rationale | User-facing note |
|---|---|---|---|
| `target_metrics` | `["accuracy"]` with no threshold | Accuracy is the most interpretable baseline metric | "No target metrics provided — defaulting to accuracy. You can specify metrics such as `f1_macro >= 0.85` in a follow-up." |
| `evaluation_threshold` | `0.80` | Conservative pass threshold consistent with routing literature | "No evaluation threshold specified — using 0.80 as default." |
| `data_split_ratio` | `0.20` holdout | 80/20 is standard for supervised evaluation | "No data split ratio provided — reserving 20% for holdout." |
| `max_iterations` | `10` | Bounds cost; sufficient for convergence on most routing problems | "No iteration limit provided — defaulting to 10 refinement rounds." |

Also document:

- **Override mechanism** — how the user can provide corrected values after seeing the assumed defaults (e.g. via follow-up clarification in the same MCP session).
- **Propagation** — how assumed defaults are flagged in the validated input report (THP-72) so downstream agents know which values were user-specified vs. assumed.

## How it links with the rest of the codebase

| Touch point | Detail |
|---|---|
| THP-70 | Optional field definitions this defaults table covers. |
| THP-108 | Non-blocking gap taxonomy identifies which fields this table applies to. |
| THP-72 | Assumed defaults are recorded in the validated input report with their rationale. |
| THP-107 | Default values are embedded in the system prompt as lookup rules. |

## Dependencies between tasks

- Blocked by THP-70 (optional field list) and THP-108 (non-blocking classification).
- THP-72 (output schema) depends on this being settled.
- Can be written in parallel with THP-109.
