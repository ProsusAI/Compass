"""Tests for JSONL dataset manager."""

import json
import logging
from pathlib import Path

import pytest

from odysseus.eval.models import Example


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """Helper: write records as JSONL to path."""
    with open(path, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


SAMPLE_RECORDS = [
    {
        "id": "1",
        "input": "hello",
        "expected": {
            "route": "greeting",
            "routes": {
                "greeting": {"cost": 0.01, "quality_score": 0.9},
                "farewell": {"cost": 0.01, "quality_score": 0.5},
            },
        },
    },
    {
        "id": "2",
        "input": "bye",
        "expected": {
            "route": "farewell",
            "routes": {
                "greeting": {"cost": 0.01, "quality_score": 0.4},
                "farewell": {"cost": 0.01, "quality_score": 0.95},
            },
        },
    },
    {
        "id": "3",
        "input": "secret",
        "expected": {"route": "hidden", "routes": {"hidden": {"cost": 0.02, "quality_score": 0.8}}},
    },
]


class TestJsonlDatasetManagerLoad:
    def test_load_returns_all_examples(self, tmp_path: Path):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "data.jsonl"
        _write_jsonl(path, SAMPLE_RECORDS)

        manager = JsonlDatasetManager()
        examples = manager.load(str(path))

        assert len(examples) == 3
        assert all(isinstance(e, Example) for e in examples)
        assert [e.id for e in examples] == ["1", "2", "3"]

    def test_load_parses_fields_correctly(self, tmp_path: Path):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "data.jsonl"
        _write_jsonl(path, SAMPLE_RECORDS)

        manager = JsonlDatasetManager()
        examples = manager.load(str(path))

        assert examples[0].input == "hello"
        assert examples[0].expected.route == "greeting"


class TestJsonlDatasetManagerErrors:
    def test_file_not_found(self):
        from odysseus.eval.dataset import JsonlDatasetManager

        manager = JsonlDatasetManager()
        with pytest.raises(FileNotFoundError):
            manager.load("/nonexistent/path.jsonl")

    def test_malformed_json_line(self, tmp_path: Path):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "bad.jsonl"
        valid = '{"id":"1","input":"hi","expected":{"route":"a","routes":{"a":{"cost":0.01,"quality_score":0.9}}}}'
        path.write_text(f"{valid}\nNOT JSON\n")

        manager = JsonlDatasetManager()
        with pytest.raises(ValueError, match="Line 2: invalid JSON"):
            manager.load(str(path))

    def test_missing_required_field(self, tmp_path: Path):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "incomplete.jsonl"
        # Missing "expected" field
        path.write_text('{"id":"1","input":"hi"}\n')

        manager = JsonlDatasetManager()
        with pytest.raises(ValueError, match="Line 1: failed to construct Example"):
            manager.load(str(path))

    def test_blank_lines_are_skipped(self, tmp_path: Path):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "blanks.jsonl"
        path.write_text(
            '{"id":"1","input":"a","expected":{"route":"b","routes":{"b":{"cost":0.01,"quality_score":0.9}}}}\n'
            "\n"
            '{"id":"2","input":"c","expected":{"route":"d","routes":{"d":{"cost":0.01,"quality_score":0.9}}}}\n'
        )

        manager = JsonlDatasetManager()
        examples = manager.load(str(path))
        assert len(examples) == 2


class TestJsonlDatasetManagerLogging:
    def test_logs_example_count_at_info(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "data.jsonl"
        _write_jsonl(path, SAMPLE_RECORDS)

        manager = JsonlDatasetManager()
        with caplog.at_level(logging.INFO, logger="odysseus.eval.dataset"):
            manager.load(str(path))

        assert any("Loaded 3" in msg for msg in caplog.messages)


class TestJsonlDatasetManagerProtocol:
    def test_conforms_to_dataset_manager_protocol(self):
        from odysseus.eval.dataset import JsonlDatasetManager
        from odysseus.eval.protocols import DatasetManager

        manager = JsonlDatasetManager()
        assert isinstance(manager, DatasetManager)
