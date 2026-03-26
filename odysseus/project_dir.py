"""Project directory resolution for the Odysseus MCP server.

All file I/O resolves against the current working directory.
"""

from pathlib import Path


def get_project_dir() -> Path:
    """Return the project directory for file I/O.

    Returns the current working directory (always absolute).
    """
    return Path.cwd()
