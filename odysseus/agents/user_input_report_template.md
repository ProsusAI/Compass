# Validated Input Report — Template

> This document defines the canonical structure for the validated input report
> produced by the User Input Agent. The agent MUST follow this template exactly.
> Downstream LLM agents and `mcp.py` rely on this structure.

## Template

---

# Validated Input Report

**Status:** proceed | proceed_with_defaults | clarification_required

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

### Max Iterations
<value, if user-provided>

_(Optional field subsections — Evaluation Threshold, Data Split Ratio, Max Iterations — are only present when the user explicitly provided them. If an optional field was defaulted, it appears in Assumed Defaults instead, not here.)_

## Gap Report

### <field_identifier>
- **Classification:** blocking | non-blocking
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
2. **Confirmed Inputs** is always present, even when `clarification_required` (partial inputs are still recorded).
3. **Gap Report** is omitted entirely if no gaps are detected.
4. **Assumed Defaults** is omitted entirely if no defaults were applied (i.e., status is `proceed`).
5. Blocking gap entries include the clarification request text from THP-109 templates.
6. Non-blocking gap entries include the default value applied and a user-facing note.
7. Gap Report headings use the exact field identifier from THP-69 (e.g., `### evaluation_threshold`, not "Evaluation Threshold").
8. Confirmed Inputs headings use title-case display names (e.g., `### Routing Dataset`).

## Status Values

| Status | Condition |
|---|---|
| `proceed` | All required fields present; no defaults needed. |
| `proceed_with_defaults` | All required fields present; one or more optional fields defaulted. |
| `clarification_required` | At least one blocking gap detected. |

## Field Reference

**Required (blocking if absent):**
- `routing_dataset` — path or inline JSONL
- `problem_description` — free-text description

**Optional (non-blocking, defaulted if absent):**
- `target_metrics` — default: `["accuracy"]` with no threshold
- `evaluation_threshold` — default: `0.80`
- `data_split_ratio` — default: `0.20`
- `max_iterations` — default: `10`
