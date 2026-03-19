"""JSONL dataset manager for the evaluation engine."""

from __future__ import annotations

import json
import logging
import os
from typing import Literal

from pydantic import ValidationError

from odysseus.eval.models import Example

logger = logging.getLogger(__name__)


class JsonlDatasetManager:
    """Loads evaluation datasets from JSONL files with dev/holdout split filtering.

    Each JSONL line must be a JSON object with fields: id, input, expected, split.
    """

    def load(self, path: str, split: Literal["dev", "holdout"]) -> list[Example]:
        """Load examples from a JSONL file, filtered by split.

        Args:
            path: Path to the JSONL file.
            split: Which partition to load ("dev" or "holdout").

        Returns:
            List of Example objects matching the requested split.

        Raises:
            FileNotFoundError: If the JSONL file does not exist.
            ValueError: If a line contains invalid JSON or fails validation.
            PermissionError: If split="holdout" and ALLOW_HOLDOUT != "1".
        """
        if split == "holdout":
            self._check_holdout_access()

        examples: list[Example] = []
        with open(path) as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Line {line_num}: invalid JSON — {e}") from e

                record_split = record.get("split")
                if record_split != split:
                    continue

                try:
                    example = Example(
                        id=record["id"],
                        input=record["input"],
                        expected=record["expected"],
                    )
                except (KeyError, ValidationError) as e:
                    raise ValueError(f"Line {line_num}: failed to construct Example — {e}") from e

                examples.append(example)

        logger.info("Loaded %d %s examples from %s", len(examples), split, path)
        return examples

    @staticmethod
    def _check_holdout_access() -> None:
        """Raise PermissionError if holdout access is not explicitly allowed."""
        if os.environ.get("ALLOW_HOLDOUT") != "1":
            raise PermissionError("Holdout access denied. Set ALLOW_HOLDOUT=1 to access holdout data.")
