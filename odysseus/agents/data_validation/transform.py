"""Dataset transformation for the Data Validation agent.

Applies a confirmed field mapping to a parsed dataset and writes
canonical JSONL output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from odysseus.agents.data_validation.detect import _parse_csv, detect_and_parse


class TransformResult(BaseModel):
    """Result of a dataset transformation."""

    output_path: str
    original_dataset_path: str
    rows_written: int
    fields_mapped: dict[str, str]
    fields_dropped: list[str] = Field(default_factory=list)


_REQUIRED_TARGETS = {"input", "expected.route", "expected.routes"}


def _maybe_coerce_numeric(value: Any) -> Any:
    """Coerce string values that look numeric to int or float."""
    if not isinstance(value, str):
        return value
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _set_nested(obj: dict, dot_path: str, value: Any) -> None:
    """Set a value in a nested dict using a dot-separated path.

    Coerces string values that look numeric to int or float.
    """
    parts = dot_path.split(".")
    current = obj
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    current[parts[-1]] = _maybe_coerce_numeric(value)


def _get_nested(obj: dict, dot_path: str) -> Any:
    """Get a value from a nested dict using a dot-separated path."""
    parts = dot_path.split(".")
    current = obj
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _check_required_targets(mapping: dict[str, str]) -> None:
    """Verify that all required target fields are covered by the mapping.

    A child mapping (e.g. expected.routes.opus.cost) satisfies the parent
    requirement (expected.routes).
    """
    target_values = set(mapping.values())
    for req in _REQUIRED_TARGETS:
        covered = any(t == req or t.startswith(req + ".") for t in target_values)
        if not covered:
            raise ValueError(
                f"Mapping does not cover required target fields. "
                f"Missing: {req}. Mapped targets: {sorted(target_values)}"
            )


def _parse_all_rows(dataset_path: str, source_format: str) -> list[dict]:
    """Parse the full file for transformation."""
    path = Path(dataset_path)
    text = path.read_text(encoding="utf-8", errors="replace")

    if source_format == "csv":
        _headers, rows = _parse_csv(text)
        return rows

    if source_format == "json":
        return json.loads(text)

    # jsonl
    rows: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return rows


def transform_dataset(
    dataset_path: str,
    field_mapping: str,
    output_path: str,
) -> TransformResult:
    """Apply a field mapping and write canonical JSONL.

    Args:
        dataset_path: Path to the original file (CSV/JSON/JSONL).
        field_mapping: JSON string mapping source field names to target field names.
        output_path: Path to write the transformed JSONL.

    Returns:
        TransformResult with output path, row count, and mapping details.
    """
    mapping: dict[str, str] = json.loads(field_mapping)
    _check_required_targets(mapping)

    detection = detect_and_parse(dataset_path)
    source_rows = _parse_all_rows(dataset_path, detection.source_format)

    all_source_fields = set(detection.columns)
    mapped_source_fields = set(mapping.keys())
    dropped = sorted(all_source_fields - mapped_source_fields)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    has_id_mapping = "id" in mapping.values()
    rows_written = 0

    with out_path.open("w", encoding="utf-8") as f:
        for idx, source_row in enumerate(source_rows):
            target_row: dict[str, Any] = {}

            for src_field, tgt_field in mapping.items():
                value = _get_nested(source_row, src_field)
                if value is not None:
                    _set_nested(target_row, tgt_field, value)

            if not has_id_mapping and "id" not in target_row:
                target_row["id"] = f"row-{idx}"

            f.write(json.dumps(target_row) + "\n")
            rows_written += 1

    return TransformResult(
        output_path=str(out_path),
        original_dataset_path=dataset_path,
        rows_written=rows_written,
        fields_mapped=mapping,
        fields_dropped=dropped,
    )
