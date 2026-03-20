# THP-72: Validated Input Report Schema — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define the validated input report contract — a Markdown template, status constants, and a `read_status()` helper — consumed by downstream agents and `mcp.py`.

**Architecture:** Three deliverables: (1) a Python module with constants and a status-reading helper, (2) a Markdown template spec document, (3) tests. No Pydantic models — the report is a human-readable Markdown file parsed by LLM agents. The only programmatic consumer is `read_status()` used by `mcp.py`.

**Tech Stack:** Python 3.11+, pytest, `re` (stdlib) for status line parsing.

**Spec:** `docs/superpowers/specs/2026-03-20-thp72-validated-input-report-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `odysseus/agents/user_input_report.py` | `CONTEXT_KEY`, three status constants, `read_status(path) -> str` |
| `odysseus/agents/user_input_report_template.md` | Canonical Markdown template the User Input Agent must follow |
| `tests/test_user_input_report.py` | Tests for constants and `read_status()` |

| `odysseus/agents/__init__.py` | Re-export public API from `user_input_report` (modified) |

---

## Chunk 1: Constants, read_status(), template

### Task 1: Status constants and CONTEXT_KEY — tests first

**Files:**
- Create: `tests/test_user_input_report.py`
- Create: `odysseus/agents/user_input_report.py`

- [ ] **Step 1: Write failing tests for constants**

```python
# tests/test_user_input_report.py
"""Tests for the validated input report contract."""

from odysseus.agents.user_input_report import (
    CONTEXT_KEY,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_PROCEED,
    STATUS_PROCEED_WITH_DEFAULTS,
)


def test_context_key_is_non_empty_string():
    assert isinstance(CONTEXT_KEY, str)
    assert len(CONTEXT_KEY) > 0


def test_status_proceed_value():
    assert STATUS_PROCEED == "proceed"


def test_status_proceed_with_defaults_value():
    assert STATUS_PROCEED_WITH_DEFAULTS == "proceed_with_defaults"


def test_status_clarification_required_value():
    assert STATUS_CLARIFICATION_REQUIRED == "clarification_required"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_user_input_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'odysseus.agents.user_input_report'`

- [ ] **Step 3: Write minimal implementation**

```python
# odysseus/agents/user_input_report.py
"""Validated input report contract for the User Input Agent.

Defines the pipeline context key, status constants, and a helper
to read the status from a report file. The report itself is a
Markdown file produced by the User Input Agent following the
template in user_input_report_template.md.
"""

from __future__ import annotations

CONTEXT_KEY: str = "validated_input_report_path"
"""Pipeline context key. The User Input Agent sets this to the
file path of the generated report."""

STATUS_PROCEED: str = "proceed"
STATUS_PROCEED_WITH_DEFAULTS: str = "proceed_with_defaults"
STATUS_CLARIFICATION_REQUIRED: str = "clarification_required"

_VALID_STATUSES: frozenset[str] = frozenset({
    STATUS_PROCEED,
    STATUS_PROCEED_WITH_DEFAULTS,
    STATUS_CLARIFICATION_REQUIRED,
})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_user_input_report.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/user_input_report.py tests/test_user_input_report.py
git commit -m "feat(thp-72): add status constants and context key for validated input report"
```

---

### Task 2: read_status() — tests first

**Files:**
- Modify: `tests/test_user_input_report.py`
- Modify: `odysseus/agents/user_input_report.py`

- [ ] **Step 1: Write failing tests for read_status()**

Replace the full contents of `tests/test_user_input_report.py` with the complete file below (adds `Path`, `pytest`, `read_status` imports at the top and test functions + fixtures at the bottom):

```python
# tests/test_user_input_report.py
"""Tests for the validated input report contract."""

from pathlib import Path

import pytest

from odysseus.agents.user_input_report import (
    CONTEXT_KEY,
    STATUS_CLARIFICATION_REQUIRED,
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


def test_status_clarification_required_value():
    assert STATUS_CLARIFICATION_REQUIRED == "clarification_required"


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
- **Rationale:** Accuracy is a sensible baseline default.
- **Default Applied:** ["accuracy"]
- **Clarification Request:** N/A

## Assumed Defaults

| Field | Assumed Value | Note |
|---|---|---|
| `target_metrics` | ["accuracy"] | No target metrics provided — defaulting to accuracy. |
"""

SAMPLE_CLARIFICATION = """\
# Validated Input Report

**Status:** clarification_required

## Confirmed Inputs

### Problem Description
Route customer queries to the right model tier.

## Gap Report

### routing_dataset
- **Classification:** blocking
- **Rationale:** No default can substitute real labeled routing data.
- **Default Applied:** N/A
- **Clarification Request:** Please provide a routing dataset as a JSONL file.
"""


def test_read_status_proceed(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text(SAMPLE_PROCEED)
    assert read_status(report) == "proceed"


def test_read_status_proceed_with_defaults(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text(SAMPLE_PROCEED_WITH_DEFAULTS)
    assert read_status(report) == "proceed_with_defaults"


def test_read_status_clarification_required(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text(SAMPLE_CLARIFICATION)
    assert read_status(report) == "clarification_required"


def test_read_status_missing_status_line(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text("# Validated Input Report\n\nNo status here.\n")
    with pytest.raises(ValueError, match="No .\\*Status.\\* line found"):
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

Run: `uv run pytest tests/test_user_input_report.py -v -k "read_status"`
Expected: FAIL — `ImportError: cannot import name 'read_status'`

- [ ] **Step 3: Write minimal implementation**

Replace the full contents of `odysseus/agents/user_input_report.py` with the complete file below (adds `import re`, `from pathlib import Path` at the top after `from __future__ import annotations`, and `read_status()` at the bottom):

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
STATUS_CLARIFICATION_REQUIRED: str = "clarification_required"

_VALID_STATUSES: frozenset[str] = frozenset({
    STATUS_PROCEED,
    STATUS_PROCEED_WITH_DEFAULTS,
    STATUS_CLARIFICATION_REQUIRED,
})

_STATUS_PATTERN: re.Pattern[str] = re.compile(r"\*\*Status:\*\*\s+(\S+)")


def read_status(path: Path) -> str:
    """Read the status value from a validated input report file.

    Args:
        path: Path to the Markdown report file.

    Returns:
        One of STATUS_PROCEED, STATUS_PROCEED_WITH_DEFAULTS,
        or STATUS_CLARIFICATION_REQUIRED.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If no **Status:** line is found or the value
            is not one of the three recognized statuses.
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_user_input_report.py -v`
Expected: 10 PASSED

- [ ] **Step 5: Run linting and type checking**

Run: `uv run ruff check odysseus/agents/user_input_report.py tests/test_user_input_report.py && uv run pyright odysseus/agents/user_input_report.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add odysseus/agents/user_input_report.py tests/test_user_input_report.py
git commit -m "feat(thp-72): add read_status() helper for validated input report"
```

---

### Task 3: Markdown template document

**Files:**
- Create: `odysseus/agents/user_input_report_template.md`

- [ ] **Step 1: Write the template document**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add odysseus/agents/user_input_report_template.md
git commit -m "docs(thp-72): add validated input report Markdown template"
```

---

### Task 4: Export from agents package

**Files:**
- Modify: `odysseus/agents/__init__.py`

- [ ] **Step 1: Update the agents __init__.py to export the new module's public API**

Replace the full contents of `odysseus/agents/__init__.py` with:

```python
"""Agent implementations for the Odysseus pipeline."""

from odysseus.agents.eval_runner import EvalRunnerAgent
from odysseus.agents.user_input_report import (
    CONTEXT_KEY as USER_INPUT_REPORT_CONTEXT_KEY,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_PROCEED,
    STATUS_PROCEED_WITH_DEFAULTS,
    read_status as read_user_input_report_status,
)

__all__ = [
    "EvalRunnerAgent",
    "USER_INPUT_REPORT_CONTEXT_KEY",
    "STATUS_PROCEED",
    "STATUS_PROCEED_WITH_DEFAULTS",
    "STATUS_CLARIFICATION_REQUIRED",
    "read_user_input_report_status",
]
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS (no regressions)

- [ ] **Step 3: Run linting**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add odysseus/agents/__init__.py
git commit -m "feat(thp-72): export validated input report API from agents package"
```
