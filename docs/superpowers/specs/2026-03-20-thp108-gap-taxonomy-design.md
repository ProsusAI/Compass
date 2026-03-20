# THP-108: Blocking vs Non-Blocking Gap Taxonomy — Design

## Overview

A single Markdown file (`odysseus/agents/user_input_taxonomy.md`) that classifies every input field from THP-70 as blocking or non-blocking, provides sensible defaults for non-blocking fields, and defines the decision logic the User Input agent uses to determine pipeline status.

This file is a reference document — it will be embedded into the agent's system prompt by THP-107. No code or Pydantic models are needed; the LLM agent applies the taxonomy at runtime and produces the `ValidatedInputReport` (THP-72) directly.

## Deliverable

**File:** `odysseus/agents/user_input_taxonomy.md`

### Section 1: Taxonomy Table

A flat table covering all 6 fields from THP-70:

| Field | Classification | Rationale | Default |
|---|---|---|---|
| `routing_dataset` | Blocking | No default can substitute real labeled routing data | — |
| `problem_description` | Blocking | Analysis agent cannot extract patterns without it | — |
| `target_metrics` | Non-blocking | Metrics are fixed in THP-69 context; F1 is a strong general-purpose default | F1 score |
| `evaluation_threshold` | Non-blocking | Conservative threshold consistent with routing literature | 0.80 |
| `data_split_ratio` | Non-blocking | 80/20 is a well-established standard | 0.20 |
| `max_iterations` | Non-blocking | Bounds cost while allowing convergence | 10 |

### Section 2: Classification Criteria

Two definitions:

- **Blocking**: Cannot be reasonably defaulted; no surrogate exists; downstream agents fail without it.
- **Non-blocking**: A principled domain default exists; the user can override the assumed value later.

### Section 3: Status Decision Logic

The rule the agent uses to set the `status` field in the `ValidatedInputReport`:

- Any blocking gap present → `clarification_required`
- Only non-blocking gaps present → `proceed_with_defaults`
- No gaps → `proceed`

## Out of Scope

- **Partial data handling** — Malformed or insufficient data is the data analysis agent's responsibility. Errors found by that agent are labeled as blocking or given a default/warning independently.
- **Code implementation** — No Pydantic models or classifier functions. The taxonomy is purely a reference document for the system prompt.

## Dependencies

| Dependency | Relationship |
|---|---|
| THP-70 | Field list this taxonomy classifies |
| THP-69 | Metrics context (fixed set; informs `target_metrics` default) |
| THP-71 | Default values align with this taxonomy's non-blocking defaults |
| THP-72 | Output schema the agent produces using this taxonomy |
| THP-107 | System prompt embeds this taxonomy |
| THP-109 | Clarification templates triggered only for blocking gaps |
