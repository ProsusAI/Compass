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
