# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Project directory resolution for the Compass MCP server.

Resolution order:
1. MCP roots — when the client (e.g. Cursor) declares workspace roots, the
   first ``file://`` root is used automatically; no user configuration needed.
2. ``COMPASS_PROJECT_DIR`` env var — explicit override for environments where
   roots are not supported (e.g. when using uvx and cwd is not propagated).
3. Current working directory — last resort fallback.

The resolved path is cached after the first successful resolution because
each server process serves exactly one client (stdio transport).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context

_cached: Path | None = None


def get_project_dir() -> Path:
    """Return the project directory for file I/O (sync, uses cache).

    Checks the module-level cache first, then ``COMPASS_PROJECT_DIR``,
    then falls back to the current working directory.  Call
    ``resolve_project_dir`` from an async tool to populate the cache via
    MCP roots before this is needed.
    """
    if _cached is not None:
        return _cached
    env = os.environ.get("COMPASS_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    return Path.cwd()


async def resolve_project_dir(ctx: Context) -> Path:  # type: ignore[type-arg]
    """Return the project directory, populating the cache if needed.

    Tries MCP roots first so that IDE clients (Cursor, VS Code) that declare
    their open workspace folder are handled automatically.
    """
    global _cached
    if _cached is not None:
        return _cached

    # 1. Try MCP roots
    try:
        result = await ctx.request_context.session.list_roots()
        if result.roots:
            uri = str(result.roots[0].uri)
            path = Path(uri.removeprefix("file://"))
            _cached = path
            return _cached
    except Exception:
        pass

    # 2. Env var override
    env = os.environ.get("COMPASS_PROJECT_DIR")
    if env:
        _cached = Path(env).resolve()
        return _cached

    # 3. Current working directory
    _cached = Path.cwd()
    return _cached
