# tests/test_user_input_report.py
"""Tests for the validated input report contract."""

from pathlib import Path

import pytest

from compass.agents.user_input.report import (
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
