# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Tests for add_ids_to_dataset."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compass.agents.data_validation.transform import AddIdsResult, add_ids_to_dataset


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().strip().splitlines()]


class TestAddIdsToDataset:
    def test_all_rows_missing_ids(self, tmp_path: Path) -> None:
        ds = tmp_path / "data.jsonl"
        _write_jsonl(ds, [{"input": "a"}, {"input": "b"}, {"input": "c"}])
        result = add_ids_to_dataset(str(ds))
        assert result.total_rows == 3
        assert result.ids_added == 3
        assert result.ids_already_present == 0
        rows = _read_jsonl(ds)
        assert [r["id"] for r in rows] == ["row-0", "row-1", "row-2"]

    def test_some_rows_have_ids(self, tmp_path: Path) -> None:
        ds = tmp_path / "data.jsonl"
        _write_jsonl(ds, [{"id": "existing", "input": "a"}, {"input": "b"}])
        result = add_ids_to_dataset(str(ds))
        assert result.ids_added == 1
        assert result.ids_already_present == 1
        rows = _read_jsonl(ds)
        assert rows[0]["id"] == "existing"
        assert rows[1]["id"] == "row-0"

    def test_custom_prefix_and_start_index(self, tmp_path: Path) -> None:
        ds = tmp_path / "data.jsonl"
        _write_jsonl(ds, [{"input": "a"}, {"input": "b"}])
        result = add_ids_to_dataset(str(ds), prefix="ex", start_index=10)
        rows = _read_jsonl(ds)
        assert [r["id"] for r in rows] == ["ex-10", "ex-11"]
        assert result.ids_added == 2

    def test_collision_avoidance(self, tmp_path: Path) -> None:
        ds = tmp_path / "data.jsonl"
        _write_jsonl(ds, [{"id": "row-0", "input": "a"}, {"input": "b"}])
        result = add_ids_to_dataset(str(ds))
        rows = _read_jsonl(ds)
        assert rows[0]["id"] == "row-0"
        assert rows[1]["id"] == "row-1"
        assert result.ids_added == 1

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            add_ids_to_dataset("/nonexistent/path.jsonl")

    def test_all_rows_already_have_ids(self, tmp_path: Path) -> None:
        ds = tmp_path / "data.jsonl"
        _write_jsonl(ds, [{"id": "a", "input": "x"}, {"id": "b", "input": "y"}])
        result = add_ids_to_dataset(str(ds))
        assert result.ids_added == 0
        assert result.ids_already_present == 2
        rows = _read_jsonl(ds)
        assert [r["id"] for r in rows] == ["a", "b"]

    def test_returns_correct_model(self, tmp_path: Path) -> None:
        ds = tmp_path / "data.jsonl"
        _write_jsonl(ds, [{"input": "a"}])
        result = add_ids_to_dataset(str(ds))
        assert isinstance(result, AddIdsResult)
        assert result.dataset_path == str(ds)
