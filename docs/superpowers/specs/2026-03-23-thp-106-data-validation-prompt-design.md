# THP-106 — Data Validation Agent Final Prompt Design

**Ticket:** [THP-106](https://prosus-thymo-thesis.atlassian.net/browse/THP-106)
**Epic:** [THP-73](https://prosus-thymo-thesis.atlassian.net/browse/THP-73) — Data Validation Agent
**Status:** Design approved
**Date:** 2026-03-23

## Overview

Incremental edit to the existing Data Validation system prompt (`prompts/data_validation_system.md`) to finalize it as the THP-106 deliverable. The prompt assembles the agent's instructions into a self-contained instruction set for any MCP-connected LLM.

## Design Decisions

### Scope: format gate only

The Data Validation agent is a structural and statistical format gate. It does not perform semantic analysis, missing signal detection, or data collection suggestions — those are downstream concerns owned by the Routing Analysis agent (THP-74).

THP-82 (routing rationale schema) and THP-84 (routing dataset quality context) are **not incorporated** into this prompt. They belong to THP-74's epic.

### Context artifacts: MCP resources, not inlined

THP-80 (data format spec) and THP-81 (output format) are referenced as MCP resources that the agent can fetch at runtime, not inlined into the prompt text. This keeps the prompt concise and avoids duplication.

### Report completeness: always produce a full report

The agent always produces a complete `DataQualityReport` regardless of issues found. There is no early termination or partial report. The report's structured fields (schema findings, volume verdict) signal severity to the orchestrator.

### No direct user interaction

The Data Validation agent does not interact with the user. The report is consumed by the pipeline orchestrator and the User Input agent, which owns all user-facing conversation including clarification and fix requests.

### No top-level status field

A single status keyword (e.g., `"blocked"` / `"ready"`) does not provide the User Input agent with enough context to ask targeted clarification questions. The orchestrator derives status from the structured report fields (`schema_findings`, `volume_assessment.overall_verdict`).

### Query length distribution: in scope

`QueryLengthDistribution` (Section 5) is retained. It is an informative structural statistic, not semantic analysis, and is already implemented in `data_validation_checks.py`.

## Changes to Existing Prompt

The existing prompt at `prompts/data_validation_system.md` (54 lines, added in THP-145) is the starting point. Changes are minimal:

### Change 1 — Role & Mission (rewrite opening)

**Before:**
```
You are the Data Validation agent in the Odysseus routing-prompt optimization pipeline.

## Your job

You validate the user's routing dataset and produce a data quality report. You run after the User Input agent has collected and confirmed the problem specification.
```

**After:**
```
You are the Data Validation agent in the Odysseus routing-prompt optimization pipeline.

## Your job

You are the pipeline's format gate. You validate the structural and statistical properties of the user's routing dataset and produce a complete data quality report. You run after the User Input agent has collected the problem specification.

You always produce a full report — even when critical issues are found. The report is consumed by the pipeline orchestrator and the User Input agent, which owns all user-facing conversation. You do not interact with the user directly.
```

### Change 2 — Decision rules (remove user-facing language)

**Before:**
```
- If any schema finding has status `"fail"` with violation on required keys or types: the dataset is **blocked** — report the issues and ask the user to fix them.
```

**After:**
```
- If any schema finding has status `"fail"` with violation on required keys or types: the dataset is **blocked**. Flag these as critical issues in the report.
```

### Unchanged sections

- **Workflow** (call tool, interpret results, write report) — no changes.
- **Output format sections 1-5** (Dataset Summary, Schema Findings, Label Distribution, Volume Adequacy, Query Length) — no changes.
- **Available tools** (`validate_dataset`) — no changes.
- **Available resources** (format-spec, output-spec URIs) — no changes.

## Deliverable

Updated file: `prompts/data_validation_system.md`

## Linkages

| Touch point | Detail |
|---|---|
| THP-80 | Referenced as MCP resource `odysseus://agents/data-validation/format-spec`. |
| THP-81 | Referenced as MCP resource `odysseus://agents/data-validation/output-spec`. |
| THP-145 | Validation logic implements the checks the prompt instructs the agent to call via `validate_dataset`. |
| `prompts/user_input_system.md` | User Input agent dispatches this agent and consumes its report. |
| THP-74 | Routing Analysis agent consumes the data quality report downstream. |
