# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Format detection and raw parsing for the Data Validation agent.

Detects CSV, JSON, and JSONL formats, parses rows, and returns
schema information for LLM-driven field mapping inference.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class DetectionResult(BaseModel):
    """Result of format detection and raw parsing."""

    source_format: Literal["csv", "json", "jsonl"]
    num_rows: int
    columns: list[str]
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)
    nested_paths: list[str] = Field(default_factory=list)
    skipped_lines: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


_MAX_SAMPLE_ROWS = 5


def _detect_format(path: Path) -> str:
    """Detect format from file extension."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    if suffix == ".jsonl":
        return "jsonl"
    return "unknown"


def _collect_dotpaths(obj: dict, prefix: str = "") -> list[str]:
    """Recursively collect dot-separated paths for all values inside nested dicts.

    For {"route": "opus", "routes": {"opus": {"cost": 0.05}}}, with prefix "expected",
    returns ["expected.route", "expected.routes", "expected.routes.opus", "expected.routes.opus.cost"].
    Includes both leaf values and intermediate dict nodes.
    """
    paths: list[str] = []
    for key, value in obj.items():
        full_path = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            paths.append(full_path)
            paths.extend(_collect_dotpaths(value, full_path))
        else:
            paths.append(full_path)
    return paths


def _parse_csv(text: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Parse CSV text into column names and row dicts.

    Handles inconsistent column counts: missing fields get None,
    extra fields are dropped.
    """
    reader = csv.reader(io.StringIO(text))
    try:
        headers = next(reader)
    except StopIteration:
        return [], []

    rows: list[dict[str, Any]] = []
    for row_values in reader:
        if not any(v.strip() for v in row_values):
            continue
        row_dict: dict[str, Any] = {}
        for i, header in enumerate(headers):
            if i < len(row_values):
                row_dict[header] = row_values[i]
            else:
                row_dict[header] = None
        rows.append(row_dict)
    return headers, rows


def detect_and_parse(dataset_path: str) -> DetectionResult:
    """Detect format and parse a dataset file.

    Supports CSV, JSON (array of objects), and JSONL formats.

    Args:
        dataset_path: Path to the dataset file.

    Returns:
        DetectionResult with schema and sample data.

    Raises:
        ValueError: If format is unrecognizable or file is empty.
    """
    path = Path(dataset_path)
    if not path.is_file():
        raise FileNotFoundError(f"Dataset file not found: {dataset_path}")

    warnings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
        warnings.append("Non-UTF-8 bytes replaced with U+FFFD")

    if not text.strip():
        raise ValueError(f"File is empty: {dataset_path}")

    fmt = _detect_format(path)

    if fmt == "csv":
        columns, rows = _parse_csv(text)
        return DetectionResult(
            source_format="csv",
            num_rows=len(rows),
            columns=columns,
            sample_rows=rows[:_MAX_SAMPLE_ROWS],
            nested_paths=[],
            warnings=warnings,
        )

    if fmt == "json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path.name}: {exc}") from exc
        if not isinstance(parsed, list):
            raise ValueError(f"File {path.name}: expected a JSON array of objects, got {type(parsed).__name__}")
        if parsed and not isinstance(parsed[0], dict):
            raise ValueError(
                f"File {path.name}: expected a JSON array of objects, got array of {type(parsed[0]).__name__}"
            )
        rows = parsed
        columns = list(rows[0].keys()) if rows else []
        nested: list[str] = []
        for row in rows[:_MAX_SAMPLE_ROWS]:
            for key, value in row.items():
                if isinstance(value, dict):
                    nested.extend(_collect_dotpaths(value, key))
        nested_deduped = list(dict.fromkeys(nested))
        return DetectionResult(
            source_format="json",
            num_rows=len(rows),
            columns=columns,
            sample_rows=rows[:_MAX_SAMPLE_ROWS],
            nested_paths=nested_deduped,
            warnings=warnings,
        )

    if fmt == "jsonl":
        rows = []
        skipped_lines: list[int] = []
        for line_num, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError:
                skipped_lines.append(line_num)
        columns = list(rows[0].keys()) if rows else []
        nested = []
        for row in rows[:_MAX_SAMPLE_ROWS]:
            for key, value in row.items():
                if isinstance(value, dict):
                    nested.extend(_collect_dotpaths(value, key))
        nested_deduped = list(dict.fromkeys(nested))
        return DetectionResult(
            source_format="jsonl",
            num_rows=len(rows),
            columns=columns,
            sample_rows=rows[:_MAX_SAMPLE_ROWS],
            nested_paths=nested_deduped,
            skipped_lines=skipped_lines,
            warnings=warnings,
        )

    raise ValueError(
        f"Unrecognizable format for {path.name} (extension: {path.suffix!r}, first 200 chars: {text[:200]!r})"
    )
