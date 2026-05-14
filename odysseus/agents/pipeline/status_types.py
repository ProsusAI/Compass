"""Shared response types for the pipeline status module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# StageDetail — structured user-mediation payload
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageDetail:
    """Structured payload for stages that require user interaction or signal a hard halt.

    Serialise via ``dataclasses.asdict(detail)`` when embedding in JSON responses.
    """

    kind: Literal["user_input_needed", "halt"]
    code: str
    artifact_path: str
    prompt_to_user: str
    expected_response: str
    halt_on_failure_after: int | None = 2
