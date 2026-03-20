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

_VALID_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_PROCEED,
        STATUS_PROCEED_WITH_DEFAULTS,
        STATUS_CLARIFICATION_REQUIRED,
    }
)

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
