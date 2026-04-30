"""Dataset transformation for the Data Validation agent.

Applies a confirmed field mapping to a parsed dataset and writes
canonical JSONL output.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from odysseus.agents.data_validation.detect import _parse_csv, detect_and_parse

logger = logging.getLogger(__name__)


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


def _get_nested_wildcard(obj: dict, dot_path: str) -> list[tuple[list[str], Any]]:
    """Get values from a nested dict, expanding ``*`` segments over all keys.

    Returns a list of ``(key_sequence, leaf_value)`` pairs where
    *key_sequence* records which concrete keys replaced each ``*``.
    """
    parts = dot_path.split(".")
    results: list[tuple[list[str], Any]] = []

    def _recurse(current: Any, depth: int, keys: list[str]) -> None:
        if depth == len(parts):
            results.append((list(keys), current))
            return
        segment = parts[depth]
        if segment == "*":
            if not isinstance(current, dict):
                return
            for key in current:
                keys.append(key)
                _recurse(current[key], depth + 1, keys)
                keys.pop()
        else:
            if not isinstance(current, dict) or segment not in current:
                return
            _recurse(current[segment], depth + 1, keys)

    _recurse(obj, 0, [])
    return results


def _set_nested_wildcard(
    obj: dict, dot_path: str, key_sequence: list[str], value: Any
) -> None:
    """Set a value in a nested dict, substituting ``*`` with keys from *key_sequence*."""
    parts = dot_path.split(".")
    ki = 0
    resolved: list[str] = []
    for part in parts:
        if part == "*":
            resolved.append(key_sequence[ki])
            ki += 1
        else:
            resolved.append(part)
    _set_nested(obj, ".".join(resolved), value)


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

    rows_written = 0

    with out_path.open("w", encoding="utf-8") as f:
        for idx, source_row in enumerate(source_rows):
            target_row: dict[str, Any] = {}

            for src_field, tgt_field in mapping.items():
                if "*" in src_field or "*" in tgt_field:
                    matches = _get_nested_wildcard(source_row, src_field)
                    for key_seq, val in matches:
                        _set_nested_wildcard(target_row, tgt_field, key_seq, val)
                    if not matches and idx == 0:
                        logger.warning(
                            "Wildcard mapping key %r matched nothing in source row (target: %r)",
                            src_field,
                            tgt_field,
                        )
                else:
                    value = _get_nested(source_row, src_field)
                    if value is not None:
                        _set_nested(target_row, tgt_field, value)
                    elif idx == 0:
                        logger.warning(
                            "Mapping key %r not found in source row (target: %r)",
                            src_field,
                            tgt_field,
                        )

            if "id" not in target_row:
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


class AddIdsResult(BaseModel):
    """Result of adding IDs to a dataset."""

    dataset_path: str
    total_rows: int
    ids_added: int
    ids_already_present: int


def add_ids_to_dataset(
    dataset_path: str,
    prefix: str = "row",
    start_index: int = 0,
) -> AddIdsResult:
    """Add sequential IDs to JSONL rows that are missing them.

    Reads the file, adds IDs where missing (skipping values that
    would collide with existing IDs), and writes back in-place.

    Args:
        dataset_path: Path to the JSONL file.
        prefix: Prefix for generated IDs. Default ``"row"``.
        start_index: Starting index for generated IDs. Default ``0``.

    Returns:
        AddIdsResult with counts.

    Raises:
        FileNotFoundError: If *dataset_path* does not exist.
    """
    path = Path(dataset_path)
    if not path.is_file():
        raise FileNotFoundError(f"Dataset file not found: {dataset_path}")

    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        rows.append(json.loads(stripped))

    existing_ids: set[str] = set()
    missing_indices: list[int] = []
    for i, row in enumerate(rows):
        row_id = row.get("id")
        if isinstance(row_id, str) and row_id:
            existing_ids.add(row_id)
        else:
            missing_indices.append(i)

    gen_idx = start_index
    for i in missing_indices:
        candidate = f"{prefix}-{gen_idx}"
        while candidate in existing_ids:
            gen_idx += 1
            candidate = f"{prefix}-{gen_idx}"
        rows[i]["id"] = candidate
        existing_ids.add(candidate)
        gen_idx += 1

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    return AddIdsResult(
        dataset_path=dataset_path,
        total_rows=len(rows),
        ids_added=len(missing_indices),
        ids_already_present=len(rows) - len(missing_indices),
    )
