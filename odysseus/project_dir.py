"""Project directory resolution for the Odysseus MCP server.

When installed as a remote MCP server (e.g. via ``uvx --from git+...``),
file I/O must resolve against the *user's* project directory, not the
package install location.

Resolution order:
    1. ``ODYSSEUS_PROJECT_DIR`` environment variable (if set)
    2. Current working directory
"""

import os
from pathlib import Path


def get_project_dir() -> Path:
    """Return the project directory for file I/O.

    Returns the value of ``ODYSSEUS_PROJECT_DIR`` if set,
    otherwise the current working directory. Always absolute.
    """
    env = os.environ.get("ODYSSEUS_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    return Path.cwd()
