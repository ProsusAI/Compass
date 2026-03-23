# THP-107 User Input System Prompt — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the self-contained system prompt for the User Input agent and deprecate the `clarification_required` status across the codebase.

**Architecture:** The system prompt (`prompts/user_input_system.md`) is a Markdown file loaded by MCP clients. It distills five dependency artifacts into actionable LLM instructions. Supporting code changes remove the deprecated `clarification_required` status and fix a stale default value.

**Tech Stack:** Python 3.11+, pytest, Markdown

**Spec:** `docs/superpowers/specs/2026-03-23-thp-107-user-input-system-prompt-design.md`

---

## File Structure

| Action | File | Responsibility |
|---|---|---|
| Create | `prompts/user_input_system.md` | Self-contained system prompt for the User Input agent |
| Modify | `odysseus/agents/user_input_report.py` | Remove `STATUS_CLARIFICATION_REQUIRED`, update `_VALID_STATUSES` and `read_status()` docstring |
| Modify | `odysseus/agents/__init__.py` | Remove `STATUS_CLARIFICATION_REQUIRED` from imports and `__all__` |
| Modify | `tests/test_user_input_report.py` | Remove clarification_required tests, add rejection test, update sample data |
| Modify | `odysseus/agents/user_input_report_template.md` | Remove `clarification_required` status, fix `target_metrics` default |
| Modify | `odysseus/agents/user_input_taxonomy.md` | Update Status Decision Logic section |
| Modify | `odysseus/agents/user_input_clarification_guide.md` | Remove two-attempt limit |
| Modify | `odysseus/agents/user_input_context.md` | Move `target_metrics` to Optional section |

---

## Chunk 1: Deprecate `clarification_required` status

### Task 1: Update tests for status deprecation

**Files:**
- Modify: `tests/test_user_input_report.py:1-125`

- [ ] **Step 1: Update the test file — remove clarification_required tests, add rejection test**

Replace the full contents of `tests/test_user_input_report.py` with:

```python
# tests/test_user_input_report.py
"""Tests for the validated input report contract."""

from pathlib import Path

import pytest

from odysseus.agents.user_input_report import (
    CONTEXT_KEY,
    STATUS_PROCEED,
    STATUS_PROCEED_WITH_DEFAULTS,
    read_status,
)


def test_context_key_is_non_empty_string():
    assert isinstance(CONTEXT_KEY, str)
    assert len(CONTEXT_KEY) > 0


def test_status_proceed_value():
    assert STATUS_PROCEED == "proceed"


def test_status_proceed_with_defaults_value():
    assert STATUS_PROCEED_WITH_DEFAULTS == "proceed_with_defaults"


SAMPLE_PROCEED = """\
# Validated Input Report

**Status:** proceed

## Confirmed Inputs

### Routing Dataset
data/routing.jsonl
"""

SAMPLE_PROCEED_WITH_DEFAULTS = """\
# Validated Input Report

**Status:** proceed_with_defaults

## Confirmed Inputs

### Routing Dataset
data/routing.jsonl

## Gap Report

### target_metrics
- **Classification:** non-blocking
- **Rationale:** F1 macro handles class imbalance well.
- **Default Applied:** ["f1/macro"]
- **Clarification Request:** N/A

## Assumed Defaults

| Field | Assumed Value | Note |
|---|---|---|
| `target_metrics` | ["f1/macro"] | No target metrics specified — defaulting to F1 macro average. |
"""


def test_read_status_proceed(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text(SAMPLE_PROCEED)
    assert read_status(report) == "proceed"


def test_read_status_proceed_with_defaults(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text(SAMPLE_PROCEED_WITH_DEFAULTS)
    assert read_status(report) == "proceed_with_defaults"


def test_read_status_rejects_clarification_required(tmp_path: Path):
    """clarification_required is deprecated — read_status must reject it."""
    report = tmp_path / "report.md"
    report.write_text("# Validated Input Report\n\n**Status:** clarification_required\n")
    with pytest.raises(ValueError, match="Unrecognized status"):
        read_status(report)


def test_read_status_missing_status_line(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text("# Validated Input Report\n\nNo status here.\n")
    with pytest.raises(ValueError, match="No \\*\\*Status:\\*\\* line found"):
        read_status(report)


def test_read_status_invalid_status_value(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text("# Validated Input Report\n\n**Status:** invalid_value\n")
    with pytest.raises(ValueError, match="Unrecognized status"):
        read_status(report)


def test_read_status_file_not_found():
    with pytest.raises(FileNotFoundError):
        read_status(Path("/nonexistent/report.md"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_user_input_report.py -v`

Expected: `test_read_status_rejects_clarification_required` FAILS (because `clarification_required` is still a valid status). The old `test_status_clarification_required_value` is gone. Other tests pass.

- [ ] **Step 3: Update `user_input_report.py` — remove `STATUS_CLARIFICATION_REQUIRED`**

Replace the full contents of `odysseus/agents/user_input_report.py` with:

```python
# odysseus/agents/user_input_report.py
"""Validated input report contract for the User Input Agent.

Defines the pipeline context key, status constants, and a helper
to read the status from a report file. The report itself is a
Markdown file produced by the User Input Agent following the
template in user_input_report_template.md.
"""

from __future__ import annotations

import re
from pathlib import Path

CONTEXT_KEY: str = "validated_input_report_path"
"""Pipeline context key. The User Input Agent sets this to the
file path of the generated report."""

STATUS_PROCEED: str = "proceed"
STATUS_PROCEED_WITH_DEFAULTS: str = "proceed_with_defaults"

_VALID_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_PROCEED,
        STATUS_PROCEED_WITH_DEFAULTS,
    }
)

_STATUS_PATTERN: re.Pattern[str] = re.compile(r"\*\*Status:\*\*\s+(\S+)")


def read_status(path: Path) -> str:
    """Read the status value from a validated input report file.

    Args:
        path: Path to the Markdown report file.

    Returns:
        One of STATUS_PROCEED or STATUS_PROCEED_WITH_DEFAULTS.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If no **Status:** line is found or the value
            is not one of the recognized statuses.
    """
    text = path.read_text()
    match = _STATUS_PATTERN.search(text)
    if match is None:
        raise ValueError(f"No **Status:** line found in {path}")
    status = match.group(1)
    if status not in _VALID_STATUSES:
        raise ValueError(f"Unrecognized status '{status}' in {path}")
    return status
```

- [ ] **Step 4: Update `__init__.py` — remove `STATUS_CLARIFICATION_REQUIRED` from exports**

Replace the full contents of `odysseus/agents/__init__.py` with:

```python
"""Agent implementations for the Odysseus pipeline."""

from odysseus.agents.eval_runner import EvalRunnerAgent
from odysseus.agents.user_input_report import (
    CONTEXT_KEY as USER_INPUT_REPORT_CONTEXT_KEY,
)
from odysseus.agents.user_input_report import (
    STATUS_PROCEED,
    STATUS_PROCEED_WITH_DEFAULTS,
)
from odysseus.agents.user_input_report import (
    read_status as read_user_input_report_status,
)

__all__ = [
    "EvalRunnerAgent",
    "USER_INPUT_REPORT_CONTEXT_KEY",
    "STATUS_PROCEED",
    "STATUS_PROCEED_WITH_DEFAULTS",
    "read_user_input_report_status",
]
```

- [ ] **Step 5: Run all tests to verify everything passes**

Run: `uv run pytest tests/test_user_input_report.py -v`

Expected: ALL PASS. Specifically:
- `test_read_status_rejects_clarification_required` — PASS (now rejected as unrecognized)
- `test_status_proceed_value` — PASS
- `test_status_proceed_with_defaults_value` — PASS
- All `read_status` tests — PASS

Then run full suite to check for import breakage:

Run: `uv run pytest -v`

Expected: No import errors for `STATUS_CLARIFICATION_REQUIRED` anywhere. If any test imports it, it will fail — fix those imports.

- [ ] **Step 6: Commit**

```bash
git add odysseus/agents/user_input_report.py odysseus/agents/__init__.py tests/test_user_input_report.py
git commit -m "refactor(thp-107): deprecate clarification_required status

Remove STATUS_CLARIFICATION_REQUIRED from user_input_report.py and
__init__.py. Update tests to verify the status is now rejected by
read_status(). The agent converses until gaps are resolved rather
than producing an incomplete report."
```

---

### Task 2: Update markdown artifacts

**Files:**
- Modify: `odysseus/agents/user_input_report_template.md:13,75,84`
- Modify: `odysseus/agents/user_input_taxonomy.md:23-28`
- Modify: `odysseus/agents/user_input_clarification_guide.md:42-43`
- Modify: `odysseus/agents/user_input_context.md:15-26`

- [ ] **Step 1: Update `user_input_report_template.md`**

Three changes in this file:

**Change 1 — Status line template (line 13):** Replace:
```
**Status:** proceed | proceed_with_defaults | clarification_required
```
with:
```
**Status:** proceed | proceed_with_defaults
```

**Change 2 — Status Values table (lines 69-76):** Replace:
```markdown
## Status Values

| Status | Condition |
|---|---|
| `proceed` | All required fields present; no defaults needed. |
| `proceed_with_defaults` | All required fields present; one or more optional fields defaulted. |
| `clarification_required` | At least one blocking gap detected. |
```
with:
```markdown
## Status Values

| Status | Condition |
|---|---|
| `proceed` | All required fields present; no defaults needed. |
| `proceed_with_defaults` | All required fields present; one or more optional fields defaulted. |
```

**Change 3 — Rule 2 (line 61):** Replace:
```
2. **Confirmed Inputs** is always present, even when `clarification_required` (partial inputs are still recorded).
```
with:
```
2. **Confirmed Inputs** is always present.
```

**Change 4 — Rule 5 (line 64):** Remove the line:
```
5. Blocking gap entries include the clarification request text from THP-109 templates.
```
And renumber rules 6-8 to 5-7.

**Change 5 — Gap Report classification (line 41):** Replace:
```
- **Classification:** blocking | non-blocking
```
with:
```
- **Classification:** non-blocking
```

**Change 6 — Field Reference `target_metrics` default (line 84):** Replace:
```
- `target_metrics` — default: `["accuracy"]` with no threshold
```
with:
```
- `target_metrics` — default: `["f1/macro"]`
```

- [ ] **Step 2: Update `user_input_taxonomy.md`**

Replace the Status Decision Logic section (lines 22-28):
```markdown
## Status Decision Logic

Based on the gaps identified, set the `status` field in the validated input report:

1. **Any blocking gap present** → `clarification_required` — halt pipeline, request missing fields.
2. **Only non-blocking gaps present** → `proceed_with_defaults` — apply defaults from table above, note them in the report.
3. **No gaps** → `proceed` — all fields present, continue pipeline.
```
with:
```markdown
## Status Decision Logic

Based on the gaps identified, set the `status` field in the validated input report:

1. **Any blocking gap present** → the agent continues conversing with the user until the gaps are resolved. No report is produced until all blocking gaps are filled.
2. **Only non-blocking gaps present** → `proceed_with_defaults` — apply defaults from table above, note them in the report.
3. **No gaps** → `proceed` — all fields present, continue pipeline.
```

- [ ] **Step 3: Update `user_input_clarification_guide.md`**

Replace lines 42-43:
```
If the user cannot provide a blocking field after two attempts, summarize what is still missing, explain the pipeline cannot proceed without it, and stop. Do not loop indefinitely.
```
with:
```
Keep asking until the user provides the required information. There is no attempt limit — the agent continues the conversation until all blocking gaps are resolved.
```

- [ ] **Step 4: Update `user_input_context.md`**

Move `target_metrics` from Required to Optional. Replace lines 15-26:
```markdown
**Required:**

- **Routing dataset** — labeled examples in JSONL format. Each record contains an input (the request to be routed) and the expected routing decision (the correct tier or tool label). This is used for both training the prompt and holdout evaluation.
- **Problem description** — free-text explaining the routing context: what types of requests are being routed, what the available tiers or tools are, and which trade-offs matter most (e.g. cost sensitivity, latency, quality floor).
- **Target metrics** — at least one target metric the user wants to optimize for, optionally with a numeric threshold (e.g. `accuracy >= 0.85`).

**Optional (defaults apply if omitted):**

- Evaluation threshold — the overall pass/fail threshold for the pipeline exit check.
- Data split ratio — fraction of data reserved for holdout evaluation.
- Max iterations — maximum number of refinement loop rounds.
```
with:
```markdown
**Required:**

- **Routing dataset** — labeled examples in JSONL format. Each record contains an input (the request to be routed) and the expected routing decision (the correct tier or tool label). This is used for both training the prompt and holdout evaluation.
- **Problem description** — free-text explaining the routing context: what types of requests are being routed, what the available tiers or tools are, and which trade-offs matter most (e.g. cost sensitivity, latency, quality floor).

**Optional (defaults apply if omitted):**

- **Target metrics** — at least one target metric the user wants to optimize for, optionally with a numeric threshold (e.g. `accuracy >= 0.85`). Default: `["f1/macro"]`.
- Evaluation threshold — the overall pass/fail threshold for the pipeline exit check.
- Data split ratio — fraction of data reserved for holdout evaluation.
- Max iterations — maximum number of refinement loop rounds.
```

- [ ] **Step 5: Run tests to verify nothing broke**

Run: `uv run pytest -v`

Expected: ALL PASS. The markdown changes don't break Python tests, but `tests/test_user_input_defaults.py` parses these files — confirm it still passes.

- [ ] **Step 6: Commit**

```bash
git add odysseus/agents/user_input_report_template.md odysseus/agents/user_input_taxonomy.md odysseus/agents/user_input_clarification_guide.md odysseus/agents/user_input_context.md
git commit -m "docs(thp-107): align artifacts with deprecated clarification_required status

- Remove clarification_required from report template and taxonomy
- Fix target_metrics default: accuracy → f1/macro in report template
- Remove two-attempt limit from clarification guide
- Move target_metrics from Required to Optional in context doc"
```

---

## Chunk 2: Create the system prompt

### Task 3: Write the User Input agent system prompt

**Files:**
- Create: `prompts/user_input_system.md`

**Reference files to distill from (do NOT copy-paste — distill into actionable instructions):**
- `odysseus/agents/user_input_context.md` — domain context, field definitions, metrics
- `odysseus/agents/user_input_defaults.md` — defaults table
- `odysseus/agents/user_input_taxonomy.md` — blocking/non-blocking classification
- `odysseus/agents/user_input_report_template.md` — output format
- `odysseus/agents/user_input_clarification_guide.md` — clarification protocol
- `prompts/eval_runner_system.md` — reference for prompt style/tone (follow this pattern)

**Reference for clarification protocol design:**
- The `superpowers:brainstorming` skill's conversational pattern: one question at a time, prefer multiple-choice when possible, comprehension before validation, incremental validation.

- [ ] **Step 1: Create `prompts/user_input_system.md`**

Write the system prompt with these sections in order:

```markdown
You are the User Input agent in the Odysseus routing-prompt optimization pipeline.

## Your job

You are the pipeline's entry gate. Your job is to validate the user's submission and produce a validated input report before any other agent runs. You do not proceed until the problem specification is complete and the data is sufficient.

You work conversationally with the user. If something is missing or unclear, you ask — one question at a time, building on what the user has already told you. Once everything is ready, you produce a structured report and hand off to the next stage.

## Domain context

Cost-quality routing is the problem of directing each incoming request to the cheapest model tier or tool that still meets quality requirements. A routing system selects among options — such as Haiku, Sonnet, or Opus model tiers, or different tools in an agentic pipeline — that produce the same type of output but differ in cost and quality.

## Problem specification

A complete routing problem has two required fields and four optional fields.

**Required (blocking — you must have these before producing a report):**

- `routing_dataset` — labeled examples in JSONL format. Each record has an input (the request to be routed) and the expected routing decision (the correct tier or tool label).
- `problem_description` — free-text describing the routing context: what types of requests are routed, what tiers or tools are available, and which trade-offs matter most.

**Optional (non-blocking — apply defaults if omitted):**

- `target_metrics` — metric(s) to optimize. Default: `["f1/macro"]`.
- `evaluation_threshold` — pass/fail threshold for the pipeline exit check. Default: `0.80`.
- `data_split_ratio` — fraction reserved for holdout evaluation. Default: `0.20`.
- `max_iterations` — maximum refinement loop rounds. Default: `10`.

## Available metrics

The evaluation framework supports four metrics. Use this section to guide users toward appropriate choices.

**accuracy** — Fraction of requests routed correctly. Simple and interpretable. Limitation: treats all misrouting errors equally. Example: `accuracy >= 0.85`.

**f1** — Per-class precision, recall, and F1 score, plus macro-averaged F1. Use when route classes are imbalanced. Example: `f1/macro >= 0.80`.

**confusion** — Full confusion matrix. Diagnostic only — not suitable as an optimization target.

**cost_quality_reduction** — Percentage change in cost and quality versus a baseline tier. Outputs `cost_reduction`, `quality_reduction`, `oracle_cost_reduction`, `oracle_quality_reduction`. Negative values mean savings (cost) or loss (quality). Example: `cost_reduction <= -0.30`.

## Validation logic

Classify each field as present or missing. Then apply this decision rule:

1. **Any blocking field missing** (`routing_dataset` or `problem_description`) → enter the clarification loop. Do not produce a report yet.
2. **Only non-blocking fields missing** → apply defaults, produce report with status `proceed_with_defaults`.
3. **All fields present** → produce report with status `proceed`.

## Defaults

When a non-blocking field is missing, apply the default and record it in the report.

| Field | Default | Rationale | User-facing note |
|---|---|---|---|
| `target_metrics` | `["f1/macro"]` | F1 macro handles class imbalance well and reveals per-class performance. | "No target metrics specified — defaulting to F1 macro average (`f1/macro`). You can specify metrics such as `accuracy >= 0.85` or `cost_reduction <= -0.30` in a follow-up." |
| `evaluation_threshold` | `0.80` | Conservative, achievable on most problems. | "No evaluation threshold specified — using 0.80 as the pass/fail threshold. You can adjust this in a follow-up." |
| `data_split_ratio` | `0.20` | Standard 80/20 train/holdout split. | "No data split ratio provided — reserving 20% of data for holdout evaluation." |
| `max_iterations` | `10` | Bounds cost while allowing convergence. | "No iteration limit provided — defaulting to 10 refinement rounds." |

## Clarification protocol

When blocking fields are missing, converse with the user to fill them. Follow these rules:

**Understand first, validate second.** Before checking fields, make sure you understand the user's routing problem. You should be able to answer: What types of requests are being routed? What are the available tiers or tools? What trade-offs matter most? If you cannot answer these, ask first. Information from this conversation counts toward resolving formal gaps.

**One question at a time.** Ask about the most important gap, wait for the answer, then move on. Priority order:
1. Problem description (priority 1)
2. Routing dataset (priority 2)

**Prefer multiple-choice when possible.** When the user's input is ambiguous and you can infer likely options, present them as choices. Always leave room for "none of these."

**Three question types:**
- **Provide** — field is entirely missing. Ask an open question, explain why it matters, offer an example.
- **Choose** — input is ambiguous. Present inferred options, let the user pick.
- **Fix** — field is present but malformed. Explain the issue, show a corrected example, accept the user's fix.

**No attempt limit.** Keep asking until all blocking gaps are resolved. The agent never gives up.

**Anti-patterns — do NOT:**
- Dump all gaps at once. One question at a time.
- Be robotic. Adapt your phrasing to the conversation. Use the user's terminology.
- Ask about non-blocking gaps. Apply defaults and mention what was assumed.
- Re-ask what was already answered. If a prior answer resolved a gap, move on.
- Reject natural language answers. If the user's answer contains the needed information in a non-standard format, accept it.

## Data Validation agent

When the user provides a dataset, dispatch the Data Validation agent to assess its quality. Incorporate its findings into your validation:

- If the Data Validation agent reports issues (insufficient examples, label imbalance, malformed records), treat them as potential blocking gaps.
- Surface data issues conversationally using the **fix** question type — explain what was found, what it means, and what the user can do.
- Data validation issues inherit the dataset's priority (priority 2).

> **Note:** The Data Validation agent is not yet implemented. When it becomes available, follow the protocol above. Until then, accept the dataset path as-is.

## Output format

Once all blocking gaps are resolved, produce the validated input report. Follow this template exactly:

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

### Evaluation Threshold
<value, if user-provided>

### Data Split Ratio
<value, if user-provided>

### Max Iterations
<value, if user-provided>

## Gap Report

### <field_identifier>
- **Classification:** non-blocking
- **Rationale:** <why this classification>
- **Default Applied:** <value>
- **Clarification Request:** N/A

## Assumed Defaults

| Field | Assumed Value | Note |
|---|---|---|
| `<field>` | <value> | <user-facing explanation> |

---

**Rules:**

1. **Status** is always the first bold field after the H1 heading.
2. **Confirmed Inputs** is always present. Optional field subsections (Evaluation Threshold, Data Split Ratio, Max Iterations) appear only if the user explicitly provided them. Defaulted fields go in Assumed Defaults instead.
3. **Gap Report** is omitted entirely if no gaps were detected.
4. **Assumed Defaults** is omitted entirely if status is `proceed`.
5. Gap Report headings use exact field identifiers (e.g. `### target_metrics`).
6. Confirmed Inputs headings use title-case display names (e.g. `### Routing Dataset`).

## Your workflow

**Phase 1 — Conversation:**
1. Receive user input.
2. Comprehension check — understand the routing problem before validating fields.
3. Validate all fields against the classification above.
4. If blocking gaps exist → clarification loop. One question at a time. No structured output.
5. Continue until all blocking gaps are resolved.

**Phase 2 — Report:**
1. Apply defaults for any missing optional fields.
2. Produce the validated input report in the exact template format above.
3. Alongside the report, conversationally mention any assumed defaults so the user knows what was assumed and can override in a follow-up.
```

- [ ] **Step 2: Run the full test suite to verify nothing is broken**

Run: `uv run pytest -v`

Expected: ALL PASS. Creating a new file should not break anything.

- [ ] **Step 3: Commit**

```bash
git add prompts/user_input_system.md
git commit -m "feat(thp-107): add User Input agent system prompt

Self-contained system prompt for the User Input agent. Distills
domain context, validation logic, defaults, clarification protocol,
and output format from the five THP-68 dependency artifacts.

Closes THP-107."
```

---

### Task 4: Final verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`

Expected: ALL PASS.

- [ ] **Step 2: Run linter**

Run: `uv run ruff check .`

Expected: No errors.

- [ ] **Step 3: Run type checker**

Run: `uv run pyright`

Expected: No errors related to the changed files.

- [ ] **Step 4: Verify prompt file exists and is non-empty**

Run: `wc -l prompts/user_input_system.md`

Expected: ~150-180 lines.

- [ ] **Step 5: Verify no references to `STATUS_CLARIFICATION_REQUIRED` remain**

Run: `grep -r "STATUS_CLARIFICATION_REQUIRED\|clarification_required" odysseus/ tests/ prompts/ --include="*.py" --include="*.md"`

Expected: No matches.
