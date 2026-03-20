# THP-72: Validated Input Report Schema — Design Spec

**Jira:** [THP-72](https://prosus-thymo-thesis.atlassian.net/browse/THP-72)
**Epic:** THP-68 — User Input Agent
**Date:** 2026-03-20

## Goal

Define the structure and contract of the validated input report — a Markdown file produced by the User Input Agent and consumed by all downstream agents and the MCP server.

## Approach

**Pure MD template spec.** The report is a human-readable Markdown file. Downstream LLM agents read it natively. The only programmatic consumer is `mcp.py`, which checks the status line to decide whether to continue the pipeline or surface clarifications.

No Pydantic model, no JSON Schema. A small Python module provides the context key constant, status constants, and a status-reading helper.

### Design Decisions — Deviations from Ticket

- **Markdown instead of JSON.** The ticket specifies a JSON object schema. We chose Markdown because: (1) the report must be human-reviewable by the user, (2) all downstream consumers are LLM agents that parse Markdown natively via their prompts — no programmatic extraction is needed beyond `read_status()`, and (3) the MCP server only needs the status value, not structured field access. This makes the Markdown file the authoritative format; the ticket's JSON examples informed the section structure.
- **File paths renamed accordingly.** The ticket suggests `odysseus/agents/user_input_schema.json`. Since the deliverable is now a Markdown template + Python helpers (not a JSON Schema), the files are `user_input_report_template.md` and `user_input_report.py`.
- **`target_metrics` classification.** THP-108 classifies `target_metrics` as blocking, while THP-71 lists a default for it. This spec follows THP-108 (blocking). The THP-71 default for `target_metrics` is a known cross-ticket inconsistency to be resolved in THP-71.

## Report Template

```markdown
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

_(Optional field subsections are only present when the user explicitly provided them. If an optional field was defaulted, it appears in Assumed Defaults instead, not here.)_

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
| `evaluation_threshold` | 0.80 | No evaluation threshold specified — using 0.80 as default. |
| ... | ... | ... |

_(Section omitted entirely if status is `proceed`.)_
```

### Template Rules

- Status line is always the first bold field after the H1 heading.
- `## Confirmed Inputs` is always present, even when `clarification_required` (partial inputs are still recorded).
- `## Gap Report` is omitted entirely if no gaps are detected.
- `## Assumed Defaults` is omitted entirely if no defaults were applied (i.e., status is `proceed`).
- Blocking gap entries in the Gap Report include the clarification request text from THP-109 templates.
- Non-blocking gap entries include the default value applied and a user-facing note.
- Gap Report headings use the exact field identifier from THP-69 (e.g., `### evaluation_threshold`, not "Evaluation Threshold"). This ensures consistency across reports.
- Confirmed Inputs headings use title-case display names (e.g., `### Routing Dataset`) since they are user-facing. The mapping from display name to field identifier is fixed and unambiguous.

## Status Semantics

| Status | Condition | Pipeline behavior |
|---|---|---|
| `proceed` | All required fields present, no defaults needed. | Pipeline continues. Gap Report and Assumed Defaults absent. |
| `proceed_with_defaults` | All required fields present, one or more optional fields defaulted. | Pipeline continues. Gap Report lists non-blocking entries. Assumed Defaults table present. |
| `clarification_required` | At least one blocking gap detected. | Pipeline halts. MCP server surfaces clarification request text to user. Non-blocking gaps may coexist with blocking ones. |

### How `mcp.py` uses the status

1. Read the report file at the path from the pipeline context.
2. Extract the status value from the `**Status:**` line (simple string match).
3. If `proceed` or `proceed_with_defaults` — pass the report file path into the pipeline context dict, continue to the next agent.
4. If `clarification_required` — return the Gap Report content to the user via MCP, wait for re-submission.

## Pipeline Context Contract

```python
CONTEXT_KEY = "validated_input_report_path"
```

The User Input Agent writes the report to disk and sets `context[CONTEXT_KEY]` to the file path. Downstream agents receive this path via the context dict and read the Markdown file to extract the sections they need. This follows the existing `ScoreReport.CONTEXT_KEY` pattern.

**Downstream parsing model:** All downstream consumers (THP-73 Data Validation, THP-74 Routing Analysis, etc.) are LLM agents. They receive the report content as part of their prompt context and extract relevant information via natural language understanding — no programmatic Markdown parsing is needed. The only programmatic extraction is `read_status()` used by `mcp.py`.

## Deliverables

### 1. `odysseus/agents/user_input_report.py`

Small Python module:
- `CONTEXT_KEY = "validated_input_report_path"` — pipeline context key.
- `STATUS_PROCEED = "proceed"` — status constant.
- `STATUS_PROCEED_WITH_DEFAULTS = "proceed_with_defaults"` — status constant.
- `STATUS_CLARIFICATION_REQUIRED = "clarification_required"` — status constant.
- `read_status(path: Path) -> str` — reads a report file and returns the status value. Raises `ValueError` if the status line is missing or contains an unrecognized value. Lets `FileNotFoundError` propagate naturally if the file does not exist. Uses the first `**Status:**` match in the file.

### 2. `odysseus/agents/user_input_report_template.md`

The canonical template spec document. This is the reference the User Input Agent (THP-107) will be instructed to follow when producing reports. It is a contract document, not executable code.

### 3. `tests/test_user_input_report.py`

Tests for:
- `read_status()` correctly extracts each of the three status values from sample report files.
- `read_status()` raises `ValueError` on missing or invalid status lines.
- Status constants match expected string values.
- `CONTEXT_KEY` is defined and non-empty.

## What This Task Does NOT Cover

- The User Input Agent implementation (THP-107).
- Gap taxonomy logic (THP-108).
- Default values table (THP-71).
- Clarification request template content (THP-109).

Those tasks define the *content* that populates reports. THP-72 defines the *shape*.

## Dependencies

- **Blocked by:** THP-69 (field definitions — merged from THP-70), THP-71 (defaults table), THP-108 (gap taxonomy).
- **Blocks:** THP-107 (system prompt needs this schema finalized).
- **Parallel with:** THP-109 (clarification templates).

## Runtime Output Location

Reports are written to the `outputs/` directory at runtime (alongside existing eval outputs). Exact naming convention is THP-107's concern; expected pattern: `outputs/validated_input_report.md`.
