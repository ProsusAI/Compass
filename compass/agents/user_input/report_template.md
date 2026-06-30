# Validated Input Report — Template

> This document defines the canonical structure for the validated input report
> produced by the User Input Agent. The agent MUST follow this template exactly.
> Downstream LLM agents and `mcp.py` rely on this structure.

## Template

---

# Validated Input Report

**Status:** proceed | proceed_with_defaults

## Confirmed Inputs

### Routing Dataset
<path or description of the provided dataset>

### Problem Description
<the user's problem description, verbatim or lightly cleaned>

### Target Metrics
- <metric spec, e.g. `accuracy >= 0.85`>
- ...

### Evaluation Threshold
<value, if user-provided>

### Data Split Ratio
<value, if user-provided>

### Evaluation Budget
<value, if user-provided>

_(Optional field subsections — Evaluation Threshold, Data Split Ratio, Evaluation Budget — are only present when the user explicitly provided them. If an optional field was defaulted, it appears in Assumed Defaults instead, not here.)_

## Gap Report

### <field_identifier>
- **Classification:** non-blocking
- **Rationale:** <why this classification>
- **Default Applied:** <value, or "N/A" if blocking>
- **Clarification Request:** <template text if blocking, or "N/A">

_(One subsection per identified gap. Section omitted entirely if no gaps.)_

## Assumed Defaults

| Field | Assumed Value | Note |
|---|---|---|
| `<field_identifier>` | <value> | <user-facing explanation> |

_(Section omitted entirely if status is `proceed`.)_

---

## Rules

1. **Status line** is always the first bold field after the H1 heading.
2. **Confirmed Inputs** is always present.
3. **Gap Report** is omitted entirely if no gaps are detected.
4. **Assumed Defaults** is omitted entirely if no defaults were applied (i.e., status is `proceed`).
5. Non-blocking gap entries include the default value applied and a user-facing note.
6. Gap Report headings use the exact field identifier from the input taxonomy (e.g., `### evaluation_threshold`, not "Evaluation Threshold").
7. Confirmed Inputs headings use title-case display names (e.g., `### Routing Dataset`).

## Status Values

| Status | Condition |
|---|---|
| `proceed` | All required fields present; no defaults needed. |
| `proceed_with_defaults` | All required fields present; one or more optional fields defaulted. |

## Field Reference

**Required (blocking if absent):**
- `routing_dataset` — path or inline JSONL
- `problem_description` — free-text description

**Optional (non-blocking, defaulted if absent):**
- `target_metrics` — default: `["f1/macro"]`
- `evaluation_threshold` — default: `0.80`
- `data_split_ratio` — default: `0.80`
- `evaluation_budget` — total prompt versions to evaluate (default: 60)
