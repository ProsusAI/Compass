"""Tests for JSONL dataset manager."""

import json
from pathlib import Path

import pytest

from odysseus.eval.models import Example


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """Helper: write records as JSONL to path."""
    with open(path, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


SAMPLE_RECORDS = [
    {"id": "1", "input": {"text": "hello"}, "expected": {"label": "greeting"}, "split": "dev"},
    {"id": "2", "input": {"text": "bye"}, "expected": {"label": "farewell"}, "split": "dev"},
    {"id": "3", "input": {"text": "secret"}, "expected": {"label": "hidden"}, "split": "holdout"},
]


class TestJsonlDatasetManagerDevSplit:
    def test_load_dev_returns_only_dev_examples(self, tmp_path: Path):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "data.jsonl"
        _write_jsonl(path, SAMPLE_RECORDS)

        manager = JsonlDatasetManager()
        examples = manager.load(str(path), "dev")

        assert len(examples) == 2
        assert all(isinstance(e, Example) for e in examples)
        assert [e.id for e in examples] == ["1", "2"]

    def test_load_dev_parses_fields_correctly(self, tmp_path: Path):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "data.jsonl"
        _write_jsonl(path, SAMPLE_RECORDS)

        manager = JsonlDatasetManager()
        examples = manager.load(str(path), "dev")

        assert examples[0].input == {"text": "hello"}
        assert examples[0].expected == {"label": "greeting"}

    def test_load_returns_empty_list_when_no_matching_split(self, tmp_path: Path):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "data.jsonl"
        _write_jsonl(path, [
            {"id": "1", "input": {"text": "a"}, "expected": {"label": "b"}, "split": "holdout"},
        ])

        manager = JsonlDatasetManager()
        examples = manager.load(str(path), "dev")

        assert examples == []
