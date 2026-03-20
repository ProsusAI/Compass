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
