# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""JSONL dataset manager for the evaluation engine."""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from compass.eval.models import Example

logger = logging.getLogger(__name__)


class JsonlDatasetManager:
    """Loads evaluation datasets from JSONL files.

    Each JSONL line must be a JSON object with fields: id, input, expected.
    """

    def load(self, path: str) -> list[Example]:
        """Load examples from a JSONL file.

        Args:
            path: Path to the JSONL file.

        Returns:
            List of Example objects.

        Raises:
            FileNotFoundError: If the JSONL file does not exist.
            ValueError: If a line contains invalid JSON or fails validation.
        """
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

                try:
                    example = Example(
                        id=record["id"],
                        input=record["input"],
                        expected=record["expected"],
                    )
                except (KeyError, ValidationError) as e:
                    raise ValueError(f"Line {line_num}: failed to construct Example — {e}") from e

                examples.append(example)

        logger.info("Loaded %d examples from %s", len(examples), path)
        return examples
