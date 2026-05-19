"""File-based prompt manager with versioned loading."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Extensions recognized as prompt files, in priority order.
PROMPT_EXTENSIONS = (".yaml", ".yml", ".txt", ".md")


class FilePromptManager:
    """Loads versioned prompts from a directory on disk.

    Satisfies the ``PromptManager`` protocol defined in
    ``odysseus/eval/protocols.py``.
    """

    def __init__(self, prompts_dir: str | Path) -> None:
        self._dir = Path(prompts_dir)
        self._cache: dict[str, str] = {}
        self._mtimes: dict[str, float] = {}  # version -> mtime for latest resolution
        self._scan()

    # -- Protocol method -------------------------------------------------------

    def load(self, version: str) -> str:
        """Return the raw prompt text for *version*.

        If *version* is ``"latest"``, the most recently modified prompt file is
        returned.  Raises ``FileNotFoundError`` when the version cannot be
        resolved.
        """
        if version == "latest":
            return self._load_latest()

        if version in self._cache:
            logger.info("Loaded prompt version '%s'", version)
            return self._cache[version]

        raise FileNotFoundError(f"Prompt version '{version}' not found in {self._dir}")

    # -- Internal helpers ------------------------------------------------------

    def _scan(self) -> None:
        """(Re-)scan the prompts directory and populate the cache."""
        new_cache: dict[str, str] = {}
        new_mtimes: dict[str, float] = {}
        for ext in PROMPT_EXTENSIONS:
            for path in self._dir.glob(f"*{ext}"):
                version = path.stem
                if version not in new_cache:  # first extension wins (priority)
                    new_cache[version] = path.read_text()
                    new_mtimes[version] = path.stat().st_mtime
        self._cache = new_cache
        self._mtimes = new_mtimes
        logger.debug("Prompt cache refreshed: %s", list(self._cache.keys()))

    def _load_latest(self) -> str:
        """Resolve 'latest' to the most recently modified prompt file from cache."""
        if not self._cache:
            raise FileNotFoundError(f"No prompt files found for 'latest' in {self._dir}")

        version = max(self._mtimes, key=self._mtimes.__getitem__)
        content = self._cache[version]
        logger.info("Loaded prompt version '%s' (resolved from 'latest')", version)
        return content
