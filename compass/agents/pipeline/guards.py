# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Precondition guards for MCP tools."""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp.exceptions import ToolError


def _check_missing(paths: list[Path | str]) -> list[str]:
    return [str(p) for p in paths if not Path(p).is_file()]


def _make_error(missing: list[str], stage: int, stage_name: str, hint: str) -> ToolError:
    return ToolError(
        f"Pipeline precondition not met: missing {', '.join(missing)}. "
        f"You are at stage {stage} ({stage_name}). {hint} "
        f"Call get_pipeline_status for the full checklist."
    )


def check_artifacts(
    *paths: Path | str,
    stage: int,
    stage_name: str,
    hint: str,
) -> None:
    """Inline guard — call at the top of a tool function."""
    missing = _check_missing(list(paths))
    if missing:
        raise _make_error(missing, stage, stage_name, hint)
