"""Tests for odysseus.agents.prompt_builder_holdout_filter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odysseus.agents.prompt_builder.holdout_filter import filter_holdout_dataset


def _make_example(id_: str) -> dict:
    """Return a valid Odysseus Example dict for *id_*."""
    return {
        "id": id_,
        "input": f"query {id_}",
        "expected": {
            "route": "a",
            "routes": {"a": {"cost": 0.01, "quality_score": 0.9}},
        },
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class TestFilterHoldoutDataset:
    def test_filters_excluded_ids(self, tmp_path: Path) -> None:
        """3 examples, exclude 2, verify 1 remains."""
        rows = [_make_example("ex1"), _make_example("ex2"), _make_example("ex3")]
        input_file = tmp_path / "holdout.jsonl"
        _write_jsonl(input_file, rows)

        output_path = filter_holdout_dataset(str(input_file), ["ex1", "ex3"])

        result = _read_jsonl(Path(output_path))
        assert len(result) == 1
        assert result[0]["id"] == "ex2"
        assert output_path == str(tmp_path / "holdout_filtered.jsonl")

    def test_no_exclusions_copies_all(self, tmp_path: Path) -> None:
        """Empty exclude list — all rows are preserved."""
        rows = [_make_example("ex1"), _make_example("ex2")]
        input_file = tmp_path / "dataset.jsonl"
        _write_jsonl(input_file, rows)

        output_path = filter_holdout_dataset(str(input_file), [])

        result = _read_jsonl(Path(output_path))
        assert len(result) == 2
        assert [r["id"] for r in result] == ["ex1", "ex2"]

    def test_missing_file_raises(self) -> None:
        """FileNotFoundError is raised when the input file does not exist."""
        with pytest.raises(FileNotFoundError):
            filter_holdout_dataset("/nonexistent/path/holdout.jsonl", [])
