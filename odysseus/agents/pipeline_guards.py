"""Precondition guards for MCP tools."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.fastmcp.exceptions import ToolError


def _check_missing(paths: list[Path | str]) -> list[str]:
    return [str(p) for p in paths if not Path(p).is_file()]


def _make_error(missing: list[str], stage: int, stage_name: str, hint: str) -> ToolError:
    return ToolError(
        f"Pipeline precondition not met: missing {', '.join(missing)}. "
        f"You are at stage {stage} ({stage_name}). {hint} "
        f"Call get_pipeline_status for the full checklist."
    )


def require_artifacts(
    *paths: Path | str,
    stage: int,
    stage_name: str,
    hint: str,
) -> Callable:
    """Decorator that checks file existence before tool execution.
    Works with both sync and async functions.
    """

    def decorator(fn: Callable) -> Callable:
        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                missing = _check_missing(list(paths))
                if missing:
                    raise _make_error(missing, stage, stage_name, hint)
                return await fn(*args, **kwargs)

            return async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                missing = _check_missing(list(paths))
                if missing:
                    raise _make_error(missing, stage, stage_name, hint)
                return fn(*args, **kwargs)

            return sync_wrapper

    return decorator


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
