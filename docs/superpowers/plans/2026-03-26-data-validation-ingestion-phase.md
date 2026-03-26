# Data Validation Ingestion Phase — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a data ingestion and transformation phase (Phase 1) to the Data Validation Agent so it can accept CSV, JSON, and non-canonical JSONL files, infer field mappings, confirm with the user, and transform into canonical JSONL before validation.

**Architecture:** Two new Python modules (`data_ingestion_detect.py` for format detection/parsing, `data_ingestion_transform.py` for mapping application and JSONL writing) registered as MCP tools. The Data Validation Agent system prompt gains a Phase 1 section. The User Input Agent prompt gets an updated handoff section.

**Tech Stack:** Python 3.11+, Pydantic for return models, csv stdlib module, pytest for testing.

**Spec:** [`docs/superpowers/specs/2026-03-26-data-validation-ingestion-phase-design.md`](../specs/2026-03-26-data-validation-ingestion-phase-design.md)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `odysseus/agents/data_ingestion_detect.py` | Create | Format detection, parsing, schema extraction. Returns `DetectionResult` model. |
| `odysseus/agents/data_ingestion_transform.py` | Create | Applies field mapping, writes canonical JSONL. Returns `TransformResult` model. |
| `odysseus/mcp.py` | Modify (add 2 tools) | Register `detect_and_parse_dataset` and `transform_dataset` MCP tools. |
| `odysseus/agents/prompts/data_validation_system.md` | Modify | Add Phase 1 section, update identity, update tool list, phase-specific interaction guidance. |
| `odysseus/agents/prompts/user_input_system.md` | Modify | Replace "Data Validation agent" section with "Pipeline handoff" section. |
| `docs/architecture.md` | Modify | Update Data Validation Agent description and context dict. |
| `tests/test_data_ingestion_detect.py` | Create | Unit tests for detection module. |
| `tests/test_data_ingestion_transform.py` | Create | Unit tests for transformation module. |

---

## Chunk 1: Detection Module

### Task 1: `detect_and_parse_dataset` — Pydantic models and CSV detection

**Files:**
- Create: `odysseus/agents/data_ingestion_detect.py`
- Create: `tests/test_data_ingestion_detect.py`

- [ ] **Step 1: Write failing test for DetectionResult model**

```python
# tests/test_data_ingestion_detect.py
"""Tests for odysseus.agents.data_ingestion_detect."""

from __future__ import annotations

import pytest

from odysseus.agents.data_ingestion_detect import DetectionResult


class TestDetectionResult:
    def test_minimal_valid(self) -> None:
        r = DetectionResult(
            source_format="csv",
            num_rows=3,
            columns=["a", "b"],
            sample_rows=[{"a": "1", "b": "2"}],
            nested_paths=[],
        )
        assert r.source_format == "csv"
        assert r.num_rows == 3

    def test_with_skipped_lines(self) -> None:
        r = DetectionResult(
            source_format="jsonl",
            num_rows=5,
            columns=["id"],
            sample_rows=[],
            nested_paths=[],
            skipped_lines=[2, 4],
        )
        assert r.skipped_lines == [2, 4]

    def test_with_warnings(self) -> None:
        r = DetectionResult(
            source_format="json",
            num_rows=1,
            columns=["x"],
            sample_rows=[],
            nested_paths=[],
            warnings=["Non-UTF-8 bytes replaced"],
        )
        assert len(r.warnings) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_ingestion_detect.py::TestDetectionResult -v`
Expected: FAIL — cannot import `DetectionResult`

- [ ] **Step 3: Implement DetectionResult model**

```python
# odysseus/agents/data_ingestion_detect.py
"""Format detection and raw parsing for the Data Validation agent.

Detects CSV, JSON, and JSONL formats, parses rows, and returns
schema information for LLM-driven field mapping inference.
"""

from __future__ import annotations

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_ingestion_detect.py::TestDetectionResult -v`
Expected: PASS

- [ ] **Step 5: Write failing test for CSV detection**

Add to `tests/test_data_ingestion_detect.py`:

```python
import tempfile
from pathlib import Path

from odysseus.agents.data_ingestion_detect import detect_and_parse


class TestDetectCSV:
    def _write_csv(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "data.csv"
        p.write_text(content, encoding="utf-8")
        return p

    def test_basic_csv(self, tmp_path: Path) -> None:
        path = self._write_csv(tmp_path, "name,age\nAlice,30\nBob,25\n")
        result = detect_and_parse(str(path))
        assert result.source_format == "csv"
        assert result.num_rows == 2
        assert result.columns == ["name", "age"]
        assert len(result.sample_rows) == 2
        assert result.sample_rows[0] == {"name": "Alice", "age": "30"}

    def test_csv_more_than_5_rows_samples_first_5(self, tmp_path: Path) -> None:
        lines = ["col\n"] + [f"row{i}\n" for i in range(10)]
        path = self._write_csv(tmp_path, "".join(lines))
        result = detect_and_parse(str(path))
        assert result.num_rows == 10
        assert len(result.sample_rows) == 5

    def test_csv_inconsistent_columns(self, tmp_path: Path) -> None:
        path = self._write_csv(tmp_path, "a,b\n1,2\n3\n4,5,6\n")
        result = detect_and_parse(str(path))
        assert result.num_rows == 3
        # Row with too few cols gets None for missing
        assert result.sample_rows[1]["b"] is None
        # Row with too many cols: extras dropped
        assert list(result.sample_rows[2].keys()) == ["a", "b"]
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_data_ingestion_detect.py::TestDetectCSV -v`
Expected: FAIL — cannot import `detect_and_parse`

- [ ] **Step 7: Implement CSV detection in `detect_and_parse`**

Add to `odysseus/agents/data_ingestion_detect.py`:

```python
import csv
import io
import json
from pathlib import Path


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
    """Recursively collect dot-paths for nested dicts."""
    paths: list[str] = []
    for key, value in obj.items():
        full_path = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            paths.append(full_path)
            paths.extend(_collect_dotpaths(value, full_path))
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

    # JSON and JSONL handled in next task
    raise ValueError(
        f"Unrecognizable format for {path.name} "
        f"(extension: {path.suffix!r}, first 200 chars: {text[:200]!r})"
    )
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/test_data_ingestion_detect.py::TestDetectCSV -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add odysseus/agents/data_ingestion_detect.py tests/test_data_ingestion_detect.py
git commit -m "feat: add detection module with CSV parsing for data ingestion"
```

### Task 2: `detect_and_parse_dataset` — JSON and JSONL detection

**Files:**
- Modify: `odysseus/agents/data_ingestion_detect.py`
- Modify: `tests/test_data_ingestion_detect.py`

- [ ] **Step 1: Write failing tests for JSON and JSONL**

Add to `tests/test_data_ingestion_detect.py`:

```python
class TestDetectJSON:
    def test_basic_json_array(self, tmp_path: Path) -> None:
        data = [{"id": "1", "text": "hello"}, {"id": "2", "text": "world"}]
        p = tmp_path / "data.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        result = detect_and_parse(str(p))
        assert result.source_format == "json"
        assert result.num_rows == 2
        assert result.columns == ["id", "text"]
        assert result.sample_rows[0] == {"id": "1", "text": "hello"}

    def test_json_nested_objects(self, tmp_path: Path) -> None:
        data = [{"id": "1", "expected": {"route": "opus", "routes": {"opus": {"cost": 0.05}}}}]
        p = tmp_path / "data.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        result = detect_and_parse(str(p))
        assert "expected" in result.columns
        assert "expected.route" in result.nested_paths
        assert "expected.routes" in result.nested_paths
        assert "expected.routes.opus" in result.nested_paths
        assert "expected.routes.opus.cost" in result.nested_paths

    def test_json_not_array(self, tmp_path: Path) -> None:
        p = tmp_path / "data.json"
        p.write_text('{"key": "value"}', encoding="utf-8")
        with pytest.raises(ValueError, match="expected a JSON array of objects"):
            detect_and_parse(str(p))


class TestDetectJSONL:
    def test_basic_jsonl(self, tmp_path: Path) -> None:
        lines = '{"id": "1", "input": "hi"}\n{"id": "2", "input": "bye"}\n'
        p = tmp_path / "data.jsonl"
        p.write_text(lines, encoding="utf-8")
        result = detect_and_parse(str(p))
        assert result.source_format == "jsonl"
        assert result.num_rows == 2
        assert set(result.columns) == {"id", "input"}

    def test_jsonl_skips_invalid_lines(self, tmp_path: Path) -> None:
        lines = '{"id": "1"}\nNOT JSON\n{"id": "2"}\n'
        p = tmp_path / "data.jsonl"
        p.write_text(lines, encoding="utf-8")
        result = detect_and_parse(str(p))
        assert result.num_rows == 2
        assert result.skipped_lines == [2]

    def test_jsonl_nested_paths(self, tmp_path: Path) -> None:
        lines = '{"expected": {"route": "opus", "routes": {"opus": {"cost": 0.05}}}}\n'
        p = tmp_path / "data.jsonl"
        p.write_text(lines, encoding="utf-8")
        result = detect_and_parse(str(p))
        assert "expected.route" in result.nested_paths
        assert "expected.routes.opus.cost" in result.nested_paths

    def test_jsonl_blank_lines_skipped(self, tmp_path: Path) -> None:
        lines = '{"id": "1"}\n\n{"id": "2"}\n'
        p = tmp_path / "data.jsonl"
        p.write_text(lines, encoding="utf-8")
        result = detect_and_parse(str(p))
        assert result.num_rows == 2
        assert result.skipped_lines == []


class TestDetectErrorCases:
    def test_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "data.csv"
        p.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="empty"):
            detect_and_parse(str(p))

    def test_unknown_format(self, tmp_path: Path) -> None:
        p = tmp_path / "data.parquet"
        p.write_bytes(b"\x00\x01\x02")
        with pytest.raises(ValueError, match="Unrecognizable format"):
            detect_and_parse(str(p))

    def test_non_utf8_produces_warning(self, tmp_path: Path) -> None:
        p = tmp_path / "data.jsonl"
        # Write bytes with invalid UTF-8 sequence
        p.write_bytes(b'{"id": "1", "input": "caf\xe9"}\n')
        result = detect_and_parse(str(p))
        assert any("UTF-8" in w for w in result.warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_ingestion_detect.py::TestDetectJSON tests/test_data_ingestion_detect.py::TestDetectJSONL -v`
Expected: FAIL — JSON/JSONL branches raise ValueError

- [ ] **Step 3: Implement JSON and JSONL parsing**

Add JSON and JSONL branches to `detect_and_parse` in `odysseus/agents/data_ingestion_detect.py`, replacing the final `raise ValueError`:

```python
    if fmt == "json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path.name}: {exc}") from exc
        if not isinstance(parsed, list):
            raise ValueError(
                f"File {path.name}: expected a JSON array of objects, "
                f"got {type(parsed).__name__}"
            )
        if parsed and not isinstance(parsed[0], dict):
            raise ValueError(
                f"File {path.name}: expected a JSON array of objects, "
                f"got array of {type(parsed[0]).__name__}"
            )
        rows = parsed
        columns = list(rows[0].keys()) if rows else []
        nested = []
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
        f"Unrecognizable format for {path.name} "
        f"(extension: {path.suffix!r}, first 200 chars: {text[:200]!r})"
    )
```

- [ ] **Step 4: Run all detection tests**

Run: `uv run pytest tests/test_data_ingestion_detect.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/data_ingestion_detect.py tests/test_data_ingestion_detect.py
git commit -m "feat: add JSON and JSONL parsing to detection module"
```

---

## Chunk 2: Transform Module

### Task 3: `transform_dataset` — Pydantic model and flat-to-flat mapping

**Files:**
- Create: `odysseus/agents/data_ingestion_transform.py`
- Create: `tests/test_data_ingestion_transform.py`

- [ ] **Step 1: Write failing test for TransformResult model and flat mapping**

```python
# tests/test_data_ingestion_transform.py
"""Tests for odysseus.agents.data_ingestion_transform."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odysseus.agents.data_ingestion_transform import TransformResult, transform_dataset


class TestTransformResult:
    def test_minimal(self) -> None:
        r = TransformResult(
            output_path="/tmp/out.jsonl",
            rows_written=3,
            fields_mapped={"a": "input"},
            fields_dropped=["b"],
        )
        assert r.rows_written == 3


class TestFlatToFlat:
    def _write_csv(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "source.csv"
        p.write_text(content, encoding="utf-8")
        return p

    def test_simple_rename(self, tmp_path: Path) -> None:
        src = self._write_csv(tmp_path, "prompt,tier\nhello,opus\nworld,haiku\n")
        out = tmp_path / "transformed.jsonl"
        mapping = {"prompt": "input", "tier": "expected.route"}
        result = transform_dataset(str(src), json.dumps(mapping), str(out))
        assert result.rows_written == 2
        assert result.fields_dropped == []
        lines = out.read_text().strip().splitlines()
        row0 = json.loads(lines[0])
        assert row0["input"] == "hello"
        assert row0["expected"]["route"] == "opus"

    def test_id_generated_when_missing(self, tmp_path: Path) -> None:
        src = self._write_csv(tmp_path, "prompt,tier\nhello,opus\n")
        out = tmp_path / "transformed.jsonl"
        mapping = {"prompt": "input", "tier": "expected.route"}
        result = transform_dataset(str(src), json.dumps(mapping), str(out))
        row = json.loads(out.read_text().strip().splitlines()[0])
        assert row["id"] == "row-0"

    def test_existing_id_preserved(self, tmp_path: Path) -> None:
        src = tmp_path / "source.jsonl"
        src.write_text('{"my_id": "abc", "prompt": "hi", "tier": "opus"}\n')
        out = tmp_path / "transformed.jsonl"
        mapping = {"my_id": "id", "prompt": "input", "tier": "expected.route"}
        result = transform_dataset(str(src), json.dumps(mapping), str(out))
        row = json.loads(out.read_text().strip().splitlines()[0])
        assert row["id"] == "abc"

    def test_unmapped_fields_dropped(self, tmp_path: Path) -> None:
        src = tmp_path / "source.jsonl"
        src.write_text('{"prompt": "hi", "tier": "opus", "extra": "ignored"}\n')
        out = tmp_path / "transformed.jsonl"
        mapping = {"prompt": "input", "tier": "expected.route"}
        result = transform_dataset(str(src), json.dumps(mapping), str(out))
        assert "extra" in result.fields_dropped
        row = json.loads(out.read_text().strip().splitlines()[0])
        assert "extra" not in row

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "source.jsonl"
        src.write_text('{"prompt": "hi"}\n')
        out = tmp_path / "transformed.jsonl"
        mapping = {"prompt": "input"}  # missing expected.route
        with pytest.raises(ValueError, match="required target fields"):
            transform_dataset(str(src), json.dumps(mapping), str(out))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_ingestion_transform.py -v`
Expected: FAIL — cannot import `transform_dataset`

- [ ] **Step 3: Implement TransformResult and basic transform_dataset**

```python
# odysseus/agents/data_ingestion_transform.py
"""Dataset transformation for the Data Validation agent.

Applies a confirmed field mapping to a parsed dataset and writes
canonical JSONL output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from odysseus.agents.data_ingestion_detect import detect_and_parse


class TransformResult(BaseModel):
    """Result of a dataset transformation."""

    output_path: str
    original_dataset_path: str
    rows_written: int
    fields_mapped: dict[str, str]
    fields_dropped: list[str] = Field(default_factory=list)


# Required target fields (or their parents for nested fields).
# The mapping must cover at least these targets.
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

    Coerces string values to numbers when the target path suggests
    a numeric field (cost, quality_score, or any numeric-looking string).
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

    # Detect format to know how to parse, then parse all rows in one pass
    detection = detect_and_parse(dataset_path)
    source_rows = _parse_all_rows(dataset_path, detection.source_format)

    # Determine dropped fields from detection columns
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

            # Generate id if not mapped
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


def _parse_all_rows(dataset_path: str, source_format: str) -> list[dict]:
    """Re-parse the full file for transformation (not just sample rows)."""
    from odysseus.agents.data_ingestion_detect import _parse_csv

    path = Path(dataset_path)
    text = path.read_text(encoding="utf-8", errors="replace")

    if source_format == "csv":
        _headers, rows = _parse_csv(text)
        return rows

    if source_format == "json":
        return json.loads(text)

    # jsonl
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_ingestion_transform.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/data_ingestion_transform.py tests/test_data_ingestion_transform.py
git commit -m "feat: add transform module with flat and nested field mapping"
```

### Task 4: `transform_dataset` — nested mapping and routes construction

**Files:**
- Modify: `tests/test_data_ingestion_transform.py`

- [ ] **Step 1: Write failing tests for nested and routes mapping**

Add to `tests/test_data_ingestion_transform.py`:

```python
class TestNestedMapping:
    def test_nested_source_to_nested_target(self, tmp_path: Path) -> None:
        src = tmp_path / "source.jsonl"
        src.write_text('{"result": {"tier": "opus"}, "text": "hi"}\n')
        out = tmp_path / "transformed.jsonl"
        mapping = {"text": "input", "result.tier": "expected.route", "result": "expected.routes"}
        result = transform_dataset(str(src), json.dumps(mapping), str(out))
        row = json.loads(out.read_text().strip().splitlines()[0])
        assert row["expected"]["route"] == "opus"

    def test_object_passthrough_for_routes(self, tmp_path: Path) -> None:
        routes = {"opus": {"cost": 0.05, "quality_score": 0.98}, "haiku": {"cost": 0.002, "quality_score": 0.72}}
        src = tmp_path / "source.jsonl"
        src.write_text(json.dumps({"text": "hi", "tier": "opus", "models": routes}) + "\n")
        out = tmp_path / "transformed.jsonl"
        mapping = {"text": "input", "tier": "expected.route", "models": "expected.routes"}
        result = transform_dataset(str(src), json.dumps(mapping), str(out))
        row = json.loads(out.read_text().strip().splitlines()[0])
        assert row["expected"]["routes"] == routes

    def test_column_expansion_for_routes(self, tmp_path: Path) -> None:
        """CSV values are strings. The transform preserves types as-is;
        numeric coercion happens during Phase 2 validation or is handled
        by the LLM agent when constructing the mapping for numeric fields."""
        src = tmp_path / "source.csv"
        src.write_text("text,tier,opus_cost,opus_quality,haiku_cost,haiku_quality\nhi,opus,0.05,0.98,0.002,0.72\n")
        out = tmp_path / "transformed.jsonl"
        mapping = {
            "text": "input",
            "tier": "expected.route",
            "opus_cost": "expected.routes.opus.cost",
            "opus_quality": "expected.routes.opus.quality_score",
            "haiku_cost": "expected.routes.haiku.cost",
            "haiku_quality": "expected.routes.haiku.quality_score",
        }
        result = transform_dataset(str(src), json.dumps(mapping), str(out))
        row = json.loads(out.read_text().strip().splitlines()[0])
        # CSV values are strings — numeric coercion is a known limitation.
        # The transform_dataset function attempts to coerce numeric-looking
        # strings when the target path contains "cost" or "quality_score".
        assert row["expected"]["routes"]["opus"]["cost"] == 0.05
        assert row["expected"]["routes"]["haiku"]["quality_score"] == 0.72

    def test_overwrite_existing_output(self, tmp_path: Path) -> None:
        out = tmp_path / "transformed.jsonl"
        out.write_text("old content\n")
        src = tmp_path / "source.jsonl"
        src.write_text('{"text": "hi", "tier": "opus", "routes": {"opus": {"cost": 0.05, "quality_score": 0.9}}}\n')
        mapping = {"text": "input", "tier": "expected.route", "routes": "expected.routes"}
        transform_dataset(str(src), json.dumps(mapping), str(out))
        assert "old content" not in out.read_text()
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `uv run pytest tests/test_data_ingestion_transform.py::TestNestedMapping -v`
Expected: Should PASS if the `_set_nested` / `_get_nested` logic handles these cases. If any fail, fix the transform logic.

- [ ] **Step 3: Fix any failures and run full test suite**

Run: `uv run pytest tests/test_data_ingestion_transform.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_data_ingestion_transform.py odysseus/agents/data_ingestion_transform.py
git commit -m "test: add nested mapping and routes construction tests"
```

---

## Chunk 3: MCP Tool Registration

### Task 5: Register both tools in `mcp.py`

**Files:**
- Modify: `odysseus/mcp.py:17` (add import)
- Modify: `odysseus/mcp.py:357-385` (add tools near `validate_dataset`)

- [ ] **Step 1: Write failing test that tools are registered**

Add to `tests/test_data_ingestion_detect.py`:

```python
class TestMCPToolRegistration:
    def test_detect_tool_exists(self) -> None:
        from odysseus.mcp import mcp
        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "detect_and_parse_dataset" in tool_names

    def test_transform_tool_exists(self) -> None:
        from odysseus.mcp import mcp
        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "transform_dataset" in tool_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_ingestion_detect.py::TestMCPToolRegistration -v`
Expected: FAIL — tools not registered

- [ ] **Step 3: Add tool registrations to `mcp.py`**

Add import at top of `odysseus/mcp.py`:

```python
from odysseus.agents.data_ingestion_detect import detect_and_parse
from odysseus.agents.data_ingestion_transform import transform_dataset as _do_transform
```

Add tools after the existing `validate_dataset` tool (around line 386):

```python
@mcp.tool()
async def detect_and_parse_dataset(dataset_path: str) -> str:
    """Detect the format of a dataset file and parse its schema.

    Supports CSV, JSON (array of objects), and JSONL formats.
    Returns column names, sample rows, and nested field paths
    for LLM-driven field mapping inference.

    Args:
        dataset_path: Absolute path to the dataset file.

    Returns:
        JSON-serialized DetectionResult with source_format, columns,
        sample_rows, nested_paths, and any warnings or skipped lines.
    """
    try:
        result = detect_and_parse(dataset_path)
    except (FileNotFoundError, ValueError) as exc:
        raise ToolError(str(exc)) from exc
    return result.model_dump_json(indent=2)


@mcp.tool()
async def transform_dataset(
    dataset_path: str,
    field_mapping: str,
    output_path: str,
) -> str:
    """Apply a confirmed field mapping and write canonical JSONL.

    Keys in field_mapping are source field names (or dot-paths for nested
    sources). Values are canonical target field names (e.g. "input",
    "expected.route", "expected.routes.opus.cost").

    Args:
        dataset_path: Absolute path to the original dataset file.
        field_mapping: JSON object mapping source fields to target fields.
        output_path: Absolute path for the transformed JSONL output.

    Returns:
        JSON-serialized TransformResult with output_path, rows_written,
        fields_mapped, and fields_dropped.
    """
    try:
        result = _do_transform(dataset_path, field_mapping, output_path)
    except (FileNotFoundError, ValueError) as exc:
        raise ToolError(str(exc)) from exc
    return result.model_dump_json(indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_ingestion_detect.py::TestMCPToolRegistration -v`
Expected: PASS

Note: The test may need adjustment depending on how `mcp._tool_manager` exposes tools. If `list_tools()` is not available, check `mcp._tools` or the FastMCP internals. Adapt the assertion to match the actual API.

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add odysseus/mcp.py tests/test_data_ingestion_detect.py
git commit -m "feat: register detect_and_parse_dataset and transform_dataset MCP tools"
```

---

## Chunk 4: System Prompt Updates

### Task 6: Update Data Validation Agent system prompt

**Files:**
- Modify: `odysseus/agents/prompts/data_validation_system.md`

- [ ] **Step 1: Rewrite the system prompt with Phase 1 + Phase 2 structure**

Replace the full contents of `odysseus/agents/prompts/data_validation_system.md` with:

```markdown
You are the Data Validation agent in the Odysseus routing-prompt optimization pipeline.

## Your job

You are the pipeline's format gate and data engineer. You accept datasets in any supported format (CSV, JSON, JSONL), transform them into canonical JSONL, validate the structural and statistical properties, and produce a complete data quality report.

You run after the User Input agent has collected and confirmed the problem specification. Your workflow has two phases:

1. **Phase 1 — Ingestion & Mapping** (conversational): detect the input format, infer field mappings, confirm with the user, and transform into canonical JSONL.
2. **Phase 2 — Validation & Reporting** (autonomous): validate the canonical dataset and produce the data quality report.

## Phase 1 — Ingestion & Mapping

In this phase you interact with the user to confirm field mappings.

1. Call `detect_and_parse_dataset` with the dataset path from the validated input report.
2. Examine the returned `columns`, `sample_rows`, and `nested_paths`.
3. Read the format spec resource (`odysseus://agents/data-validation/format-spec`) for the canonical target schema and alias table.
4. Infer which source fields map to each canonical target field:
   - `id` — stable identifier for deduplication
   - `input` — the user query to be routed
   - `expected.route` — the target routing tier
   - `expected.routes` — per-model cost/quality data (object with model keys)
   - `expected.routes.*.cost` — cost per call for each model
   - `expected.routes.*.quality_score` — quality score for each model
5. Present the proposed mapping as a table to the user. For each target field, briefly explain what it represents.
6. If all required fields (`input`, `expected.route`, `expected.routes`) are confidently mapped: ask the user to confirm. Unmapped source fields are dropped silently.
7. If any required field is ambiguous or unmapped: ask about each unresolved field one at a time.
8. Once confirmed, call `transform_dataset` with the mapping. The output is written to `data/transformed_<source_filestem>.jsonl`.
9. Proceed to Phase 2 with the transformed file path.

**Skip Phase 1** if `detect_and_parse_dataset` returns `source_format: "jsonl"` and the columns include `id`, `input`, `expected`, and the sample rows show the canonical nested structure (`expected.route`, `expected.routes`). Proceed directly to Phase 2 with the original file path.

## Phase 2 — Validation & Reporting

In this phase you work autonomously — produce the report without user interaction.

1. Call the `validate_dataset` tool with the dataset path (transformed or original).
2. Interpret the structured results returned by the tool.
3. Write a data quality report following the output format below.

You always produce a full report — even when critical issues are found. The report is consumed by the pipeline orchestrator and downstream agents.

## Output format

Your report has five sections plus a routing context block:

### 1. Dataset Summary

Write two paragraphs:

1. **Data description** — what the dataset contains: the routing problem domain, what kinds of queries are represented, and what the routing tiers correspond to. Base this on the user's problem description and the data you observed.
2. **Validation summary** — total record count, tier names and distribution, any issues found, and overall verdict (ready for downstream processing or blocked by critical issues).

### 2. Schema Consistency Findings

Present the `schema_findings` from the tool output. Each finding includes a `severity` field (`"critical"`, `"warning"`, or `"info"`). For each finding with status `"fail"`, state its severity, explain the violation, and list the affected row indices. Group passing checks into a single summary line.

### 3. Label Distribution Stats

Present the `label_distribution` from the tool output. Show per-tier counts and percentages. Flag any imbalanced tiers.

### 4. Volume Adequacy Assessment

Present the `volume_assessment` from the tool output. Show per-tier verdicts. State the overall verdict.

### 5. Query Length Distribution

Present the `query_length` stats from the tool output: min, max, mean, and p95 character lengths.

### 6. Routing Context

Synthesize a `routing_context` block for downstream annotation skills. Derive it from the dataset and the user's problem description:

- **`domain`**: Two sentences. First: what the routing system decides (from the problem description and dataset structure). Second: what topics and domains the queries cover (sample queries across routes and summarize the topic clusters you observe).
- **`routes`**: One entry per route found in the `consistent_model_set`. For each route, examine a few example queries assigned to it and write a one-sentence description of what that route typically handles.
- **`routing_dimensions`**: One entry per numeric field in `expected.routes` (e.g., `cost`, `quality_score`). Infer `direction` from the field semantics (`cost` → `lower_is_better`, `quality_score` → `higher_is_better`).
- **`route_ordering`**: If routes have a natural ordering along one dimension (e.g., capability tiers), include it. If routes are unordered (e.g., specialized tools), omit this field.
- **`seed_vocabulary`**: Leave all lists empty unless a prior annotation run's vocabulary is available.

Present the routing context as a fenced YAML code block. This block will be consumed verbatim by the routing analysis agent.

## Decision rules

Use the `severity` field on each schema finding to determine how to present it:

- **Critical** (`severity: "critical"`, checks: `required_keys`, `types`, `unique_ids`, `consistent_model_set`): the dataset is **blocked**. These must be fixed before evaluation can proceed.
- **Warning** (`severity: "warning"`, checks: `route_in_routes`, `non_empty_routes`, `null_fields`): flag in the report but do not block. The dataset can proceed with noted warnings.
- If volume adequacy overall verdict is `"fail"`: flag as a **warning** — the dataset can proceed but results may be unreliable for under-covered tiers.
- If label distribution has imbalanced tiers: flag as **informational** — note which tiers are underrepresented.
- If all checks pass and volume is adequate: the dataset is **ready** for downstream processing.
- The **Routing Context** section is always included, even when the dataset has critical issues. Downstream agents need the routing context to understand the domain even when re-validation is required.

## Available tools

- `detect_and_parse_dataset` — detects format (CSV/JSON/JSONL) and returns columns, sample rows, nested paths.
- `transform_dataset` — applies a confirmed field mapping and writes canonical JSONL.
- `validate_dataset` — runs all validation checks against a canonical JSONL dataset file.

## Available resources

- `odysseus://agents/data-validation/format-spec` — the data format specification with canonical schema and alias table.
- `odysseus://agents/data-validation/output-spec` — the output format specification.
```

- [ ] **Step 2: Review the prompt for accuracy against the spec**

Read the spec at `docs/superpowers/specs/2026-03-26-data-validation-ingestion-phase-design.md` and verify:
- Phase 1 workflow matches spec sections "Agent Workflow" and "System Prompt Changes"
- Phase 2 is unchanged from original (except interaction guidance)
- Tool list matches
- Decision rules unchanged

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/prompts/data_validation_system.md
git commit -m "feat: add Phase 1 ingestion workflow to data validation system prompt"
```

### Task 7: Update User Input Agent system prompt

**Files:**
- Modify: `odysseus/agents/prompts/user_input_system.md:63-73`

- [ ] **Step 1: Replace the "Data Validation agent" section**

In `odysseus/agents/prompts/user_input_system.md`, replace the section at lines 63-73 (starting with `## Data Validation agent` through the paragraph ending with "...routing context derived from the dataset."):

Old text to replace:
```markdown
## Data Validation agent

When the user provides a dataset, dispatch the Data Validation agent to assess its quality. Incorporate findings into your validation:

- If the Data Validation agent reports issues (insufficient examples, label imbalance, malformed records), treat them as potential blocking gaps.
- Surface data issues conversationally using the **fix** question type from the clarification skill.
- Data validation issues inherit the dataset's priority (priority 2).


The Data Validation agent produces a data quality report that includes a **Routing Context** section — a structured YAML block describing routes, routing dimensions, and domain context derived from the dataset.
```

New text:
```markdown
## Pipeline handoff

Once you have produced the validated input report and the user has confirmed it, call the `submit_input_report` tool with:
- `report`: the full report Markdown
- `dataset_path`: the absolute filesystem path to the routing dataset
- `problem_description`: the validated problem description

This triggers the next pipeline stage — the Data Validation Agent.

The pipeline flow after your handoff:
1. **Data Validation Agent** — ingests the dataset (CSV/JSON/JSONL), confirms field mappings with the user if needed, transforms to canonical format, then validates and produces a quality report.
2. **Routing Analysis Agent** — annotates and splits the validated dataset.

Your job is done after calling `submit_input_report`. The Data Validation Agent owns the conversation from that point — it will talk to the user directly if field mapping confirmation is needed. Do not attempt to mediate validation issues.
```

- [ ] **Step 2: Remove the redundant Handoff section at lines 129-136**

The existing "## Handoff" section at lines 129-136 is now redundant with the new "## Pipeline handoff" section (which includes the tool parameter guidance). Remove it.

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/prompts/user_input_system.md
git commit -m "feat: update user input agent with clean pipeline handoff"
```

---

## Chunk 5: Documentation and Final Verification

### Task 8: Update architecture docs

**Files:**
- Modify: `docs/architecture.md`

- [ ] **Step 1: Update the Data Validation Agent row in the Agent Registry table**

In the Agent Registry table (section 2), update the Data Validation row to mention the two-phase workflow and add the new tools to the module list.

- [ ] **Step 2: Add `original_dataset_path` to the Context Dict Reference**

In section 3, add a row:

| `original_dataset_path` | `str` | Data Validation Agent | (provenance tracking) | Path to the user's original dataset file before transformation |

- [ ] **Step 3: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: update architecture for data validation ingestion phase"
```

### Task 9: Run full test suite and lint

**Files:** None (verification only)

- [ ] **Step 1: Run all tests**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 2: Run linter**

Run: `uv run ruff check .`
Expected: No errors

- [ ] **Step 3: Run formatter**

Run: `uv run ruff format --check .`
Expected: No formatting issues (run `uv run ruff format .` to fix if needed)

- [ ] **Step 4: Run type checker**

Run: `uv run pyright`
Expected: No errors in new files

- [ ] **Step 5: Final commit if any formatting/lint fixes needed**

```bash
git add -A
git commit -m "style: fix lint and formatting in ingestion modules"
```
