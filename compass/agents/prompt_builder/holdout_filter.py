# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Holdout dataset filter for the Prompt Builder agent.

Removes few-shot examples from the holdout evaluation set to prevent data
contamination — few-shot examples drawn from the holdout set must be excluded
before final evaluation.
"""

from __future__ import annotations

import json
from pathlib import Path


def filter_holdout_dataset(
    holdout_jsonl_path: str,
    exclude_ids: list[str],
) -> str:
    """Filter a holdout JSONL dataset by removing rows with specified IDs.

    Reads the JSONL file at *holdout_jsonl_path*, removes any rows whose
    ``id`` field appears in *exclude_ids*, and writes the result to a new
    file named ``{stem}_filtered{suffix}`` in the same directory.

    Args:
        holdout_jsonl_path: Path to the input JSONL file.
        exclude_ids: List of row IDs to exclude from the output.

    Returns:
        Path to the filtered output file as a string.

    Raises:
        FileNotFoundError: If *holdout_jsonl_path* does not exist.
    """
    input_path = Path(holdout_jsonl_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Holdout dataset not found: {holdout_jsonl_path}")

    exclude_set = set(exclude_ids)

    output_path = input_path.with_name(f"{input_path.stem}_filtered{input_path.suffix}")

    with input_path.open("r", encoding="utf-8") as fh_in, output_path.open("w", encoding="utf-8") as fh_out:
        for line in fh_in:
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            if row.get("id") in exclude_set:
                continue
            fh_out.write(stripped + "\n")

    return str(output_path)
