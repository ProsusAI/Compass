# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Tests for compass.agents.data_ingestion_detect."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compass.agents.data_validation.detect import (
    DetectionResult,
    detect_and_parse,
)

# ---------------------------------------------------------------------------
# TestDetectionResult — model construction
# ---------------------------------------------------------------------------


class TestDetectionResult:
    def test_minimal_construction(self) -> None:
        result = DetectionResult(source_format="csv", num_rows=3, columns=["a", "b"])
        assert result.source_format == "csv"
        assert result.num_rows == 3
        assert result.columns == ["a", "b"]
        assert result.sample_rows == []
        assert result.nested_paths == []
        assert result.skipped_lines == []
        assert result.warnings == []

    def test_with_skipped_lines(self) -> None:
        result = DetectionResult(
            source_format="jsonl",
            num_rows=2,
            columns=["id", "input"],
            skipped_lines=[3, 7],
        )
        assert result.skipped_lines == [3, 7]

    def test_with_warnings(self) -> None:
        result = DetectionResult(
            source_format="json",
            num_rows=1,
            columns=["id"],
            warnings=["Non-UTF-8 bytes replaced with U+FFFD"],
        )
        assert len(result.warnings) == 1
        assert "U+FFFD" in result.warnings[0]

    def test_all_formats_accepted(self) -> None:
        for fmt in ("csv", "json", "jsonl"):
            result = DetectionResult(source_format=fmt, num_rows=0, columns=[])  # type: ignore[arg-type]
            assert result.source_format == fmt


# ---------------------------------------------------------------------------
# TestDetectCSV
# ---------------------------------------------------------------------------


class TestDetectCSV:
    def test_basic_csv(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("id,input,label\n1,hello,opus\n2,world,haiku\n")
        result = detect_and_parse(str(f))
        assert result.source_format == "csv"
        assert result.num_rows == 2
        assert result.columns == ["id", "input", "label"]
        assert len(result.sample_rows) == 2
        assert result.sample_rows[0] == {"id": "1", "input": "hello", "label": "opus"}
        assert result.nested_paths == []

    def test_more_than_five_rows_samples_first_five(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        lines = ["id,value"] + [f"{i},{i * 10}" for i in range(8)]
        f.write_text("\n".join(lines) + "\n")
        result = detect_and_parse(str(f))
        assert result.num_rows == 8
        assert len(result.sample_rows) == 5
        assert result.sample_rows[0]["id"] == "0"
        assert result.sample_rows[4]["id"] == "4"

    def test_inconsistent_columns_missing_gets_none(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        # Row 2 is missing the third column
        f.write_text("a,b,c\n1,2,3\n4,5\n")
        result = detect_and_parse(str(f))
        assert result.num_rows == 2
        assert result.sample_rows[1]["a"] == "4"
        assert result.sample_rows[1]["b"] == "5"
        assert result.sample_rows[1]["c"] is None

    def test_inconsistent_columns_extra_dropped(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        # Row 1 has an extra column beyond the header
        f.write_text("a,b\n1,2,EXTRA\n3,4\n")
        result = detect_and_parse(str(f))
        assert result.num_rows == 2
        assert result.sample_rows[0] == {"a": "1", "b": "2"}
        assert "EXTRA" not in result.sample_rows[0]

    def test_blank_lines_skipped(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("x,y\n1,2\n\n3,4\n")
        result = detect_and_parse(str(f))
        assert result.num_rows == 2


# ---------------------------------------------------------------------------
# TestDetectJSON
# ---------------------------------------------------------------------------


class TestDetectJSON:
    def test_basic_json_array(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        rows = [{"id": "1", "input": "hello"}, {"id": "2", "input": "world"}]
        f.write_text(json.dumps(rows))
        result = detect_and_parse(str(f))
        assert result.source_format == "json"
        assert result.num_rows == 2
        assert result.columns == ["id", "input"]
        assert len(result.sample_rows) == 2

    def test_nested_objects_produce_correct_nested_paths(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        rows = [
            {
                "id": "ex-1",
                "input": "query",
                "expected": {
                    "route": "opus",
                    "routes": {
                        "opus": {"cost": 0.05, "quality_score": 0.98},
                        "haiku": {"cost": 0.002, "quality_score": 0.72},
                    },
                },
            }
        ]
        f.write_text(json.dumps(rows))
        result = detect_and_parse(str(f))
        assert "expected.route" in result.nested_paths
        assert "expected.routes" in result.nested_paths
        assert "expected.routes.opus" in result.nested_paths
        assert "expected.routes.opus.cost" in result.nested_paths
        assert "expected.routes.haiku" in result.nested_paths
        assert "expected.routes.haiku.quality_score" in result.nested_paths

    def test_nested_paths_deduped_across_sample_rows(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        rows = [{"id": str(i), "meta": {"key": "value"}} for i in range(6)]
        f.write_text(json.dumps(rows))
        result = detect_and_parse(str(f))
        # "meta.key" should appear only once despite 5 sample rows
        assert result.nested_paths.count("meta.key") == 1

    def test_more_than_five_rows_samples_first_five(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        rows = [{"id": str(i)} for i in range(10)]
        f.write_text(json.dumps(rows))
        result = detect_and_parse(str(f))
        assert result.num_rows == 10
        assert len(result.sample_rows) == 5

    def test_non_array_raises_value_error(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text(json.dumps({"key": "value"}))
        with pytest.raises(ValueError, match="expected a JSON array"):
            detect_and_parse(str(f))

    def test_array_of_non_dicts_raises_value_error(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text(json.dumps(["a", "b", "c"]))
        with pytest.raises(ValueError, match="expected a JSON array of objects"):
            detect_and_parse(str(f))

    def test_empty_json_array(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text("[]")
        result = detect_and_parse(str(f))
        assert result.num_rows == 0
        assert result.columns == []
        assert result.sample_rows == []


# ---------------------------------------------------------------------------
# TestDetectJSONL
# ---------------------------------------------------------------------------


class TestDetectJSONL:
    def test_basic_jsonl(self, tmp_path: Path) -> None:
        f = tmp_path / "data.jsonl"
        f.write_text('{"id": "1", "input": "hello"}\n{"id": "2", "input": "world"}\n')
        result = detect_and_parse(str(f))
        assert result.source_format == "jsonl"
        assert result.num_rows == 2
        assert result.columns == ["id", "input"]
        assert result.skipped_lines == []

    def test_invalid_lines_recorded_in_skipped_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "data.jsonl"
        f.write_text('{"id": "1"}\nnot valid json\n{"id": "3"}\n{also bad}\n{"id": "5"}\n')
        result = detect_and_parse(str(f))
        assert result.num_rows == 3
        assert 2 in result.skipped_lines
        assert 4 in result.skipped_lines
        assert 1 not in result.skipped_lines

    def test_blank_lines_skipped_not_counted_as_errors(self, tmp_path: Path) -> None:
        f = tmp_path / "data.jsonl"
        f.write_text('{"id": "1"}\n\n{"id": "2"}\n')
        result = detect_and_parse(str(f))
        assert result.num_rows == 2
        assert result.skipped_lines == []

    def test_nested_paths(self, tmp_path: Path) -> None:
        f = tmp_path / "data.jsonl"
        f.write_text('{"id": "1", "expected": {"route": "opus", "routes": {"opus": {"cost": 0.05}}}}\n')
        result = detect_and_parse(str(f))
        assert "expected.route" in result.nested_paths
        assert "expected.routes.opus.cost" in result.nested_paths

    def test_more_than_five_rows_samples_first_five(self, tmp_path: Path) -> None:
        f = tmp_path / "data.jsonl"
        lines = [json.dumps({"id": str(i)}) for i in range(8)]
        f.write_text("\n".join(lines) + "\n")
        result = detect_and_parse(str(f))
        assert result.num_rows == 8
        assert len(result.sample_rows) == 5

    def test_nested_paths_deduped(self, tmp_path: Path) -> None:
        f = tmp_path / "data.jsonl"
        lines = [json.dumps({"id": str(i), "meta": {"x": 1}}) for i in range(4)]
        f.write_text("\n".join(lines) + "\n")
        result = detect_and_parse(str(f))
        assert result.nested_paths.count("meta.x") == 1


# ---------------------------------------------------------------------------
# TestDetectErrorCases
# ---------------------------------------------------------------------------


class TestDetectErrorCases:
    def test_empty_file_raises_value_error(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.csv"
        f.write_text("")
        with pytest.raises(ValueError, match="empty"):
            detect_and_parse(str(f))

    def test_whitespace_only_file_raises_value_error(self, tmp_path: Path) -> None:
        f = tmp_path / "blank.jsonl"
        f.write_text("   \n  \n")
        with pytest.raises(ValueError, match="empty"):
            detect_and_parse(str(f))

    def test_unknown_format_raises_value_error(self, tmp_path: Path) -> None:
        f = tmp_path / "data.parquet"
        f.write_text("some binary content here")
        with pytest.raises(ValueError, match="Unrecognizable format"):
            detect_and_parse(str(f))

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            detect_and_parse(str(tmp_path / "nonexistent.csv"))

    def test_non_utf8_produces_warning(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        # Write valid header + row with a latin-1 byte sequence not valid in UTF-8
        content = b"id,label\n1,caf\xe9\n"
        f.write_bytes(content)
        result = detect_and_parse(str(f))
        assert any("U+FFFD" in w for w in result.warnings)
        assert result.num_rows == 1

    def test_invalid_json_in_json_file_raises_value_error(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text("{not valid json}")
        with pytest.raises(ValueError, match="Invalid JSON"):
            detect_and_parse(str(f))
