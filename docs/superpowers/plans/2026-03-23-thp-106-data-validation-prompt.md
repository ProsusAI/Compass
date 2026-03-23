# THP-106 Data Validation Agent Final Prompt Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finalize the Data Validation agent system prompt with three targeted edits: role clarification, section count fix, and decision rule adjustment.

**Architecture:** Incremental edit to `prompts/data_validation_system.md`. No new files. No code changes — prompt text only.

**Tech Stack:** Markdown (system prompt file)

**Spec:** `docs/superpowers/specs/2026-03-23-thp-106-data-validation-prompt-design.md`

---

## Chunk 1: Prompt Edits

### Task 1: Update Role & Mission

**Files:**
- Modify: `prompts/data_validation_system.md:1-5`

- [ ] **Step 1: Apply Change 1 — rewrite opening**

Replace lines 1-5:

```
You are the Data Validation agent in the Odysseus routing-prompt optimization pipeline.

## Your job

You validate the user's routing dataset and produce a data quality report. You run after the User Input agent has collected and confirmed the problem specification.
```

With:

```
You are the Data Validation agent in the Odysseus routing-prompt optimization pipeline.

## Your job

You are the pipeline's format gate. You validate the structural and statistical properties of the user's routing dataset and produce a complete data quality report. You run after the User Input agent has collected and confirmed the problem specification.

You always produce a full report — even when critical issues are found. The report is consumed by the pipeline orchestrator and the User Input agent, which owns all user-facing conversation. You do not interact with the user directly.
```

- [ ] **Step 2: Apply Change 2 — fix section count**

Replace on line 14:

```
Your report has four sections:
```

With:

```
Your report has five sections:
```

- [ ] **Step 3: Apply Change 3 — update decision rule**

Replace on line 41:

```
- If any schema finding has status `"fail"` with violation on required keys or types: the dataset is **blocked** — report the issues and ask the user to fix them.
```

With:

```
- If any schema finding has status `"fail"` with violation on required keys or types: the dataset is **blocked**. Flag these as critical issues in the report.
```

- [ ] **Step 4: Verify the final prompt reads correctly**

Run: `cat prompts/data_validation_system.md`

Verify:
- Opening mentions "format gate" and "complete data quality report"
- Second paragraph about always producing full report and no direct user interaction is present
- "five sections" not "four sections"
- Blocked rule says "Flag these as critical issues in the report" not "ask the user to fix them"
- All other sections (workflow, output format 1-5, tools, resources) unchanged

- [ ] **Step 5: Commit**

```bash
git add prompts/data_validation_system.md
git commit -m "feat(thp-106): finalize data validation agent system prompt"
```
