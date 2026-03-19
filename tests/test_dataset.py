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
        _write_jsonl(
            path,
            [
                {"id": "1", "input": {"text": "a"}, "expected": {"label": "b"}, "split": "holdout"},
            ],
        )

        manager = JsonlDatasetManager()
        examples = manager.load(str(path), "dev")

        assert examples == []


class TestJsonlDatasetManagerHoldoutGuard:
    def test_holdout_blocked_by_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "data.jsonl"
        _write_jsonl(path, SAMPLE_RECORDS)

        monkeypatch.delenv("ALLOW_HOLDOUT", raising=False)
        manager = JsonlDatasetManager()

        with pytest.raises(PermissionError, match="Holdout access denied"):
            manager.load(str(path), "holdout")

    def test_holdout_allowed_with_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "data.jsonl"
        _write_jsonl(path, SAMPLE_RECORDS)

        monkeypatch.setenv("ALLOW_HOLDOUT", "1")
        manager = JsonlDatasetManager()
        examples = manager.load(str(path), "holdout")

        assert len(examples) == 1
        assert examples[0].id == "3"

    def test_holdout_blocked_with_wrong_env_value(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "data.jsonl"
        _write_jsonl(path, SAMPLE_RECORDS)

        monkeypatch.setenv("ALLOW_HOLDOUT", "true")
        manager = JsonlDatasetManager()

        with pytest.raises(PermissionError):
            manager.load(str(path), "holdout")


class TestJsonlDatasetManagerErrors:
    def test_file_not_found(self):
        from odysseus.eval.dataset import JsonlDatasetManager

        manager = JsonlDatasetManager()
        with pytest.raises(FileNotFoundError):
            manager.load("/nonexistent/path.jsonl", "dev")

    def test_malformed_json_line(self, tmp_path: Path):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "bad.jsonl"
        path.write_text('{"id":"1","input":{},"expected":{},"split":"dev"}\nNOT JSON\n')

        manager = JsonlDatasetManager()
        with pytest.raises(ValueError, match="Line 2: invalid JSON"):
            manager.load(str(path), "dev")

    def test_missing_required_field(self, tmp_path: Path):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "incomplete.jsonl"
        # Missing "expected" field
        path.write_text('{"id":"1","input":{"text":"hi"},"split":"dev"}\n')

        manager = JsonlDatasetManager()
        with pytest.raises(ValueError, match="Line 1: failed to construct Example"):
            manager.load(str(path), "dev")

    def test_blank_lines_are_skipped(self, tmp_path: Path):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "blanks.jsonl"
        path.write_text(
            '{"id":"1","input":{"text":"a"},"expected":{"label":"b"},"split":"dev"}\n'
            "\n"
            '{"id":"2","input":{"text":"c"},"expected":{"label":"d"},"split":"dev"}\n'
        )

        manager = JsonlDatasetManager()
        examples = manager.load(str(path), "dev")
        assert len(examples) == 2


class TestJsonlDatasetManagerLogging:
    def test_logs_example_count_at_info(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        from odysseus.eval.dataset import JsonlDatasetManager

        path = tmp_path / "data.jsonl"
        _write_jsonl(path, SAMPLE_RECORDS)

        manager = JsonlDatasetManager()
        with caplog.at_level(logging.INFO, logger="odysseus.eval.dataset"):
            manager.load(str(path), "dev")

        assert any("Loaded 2 dev examples" in msg for msg in caplog.messages)


class TestJsonlDatasetManagerProtocol:
    def test_conforms_to_dataset_manager_protocol(self):
        from odysseus.eval.dataset import JsonlDatasetManager
        from odysseus.eval.protocols import DatasetManager

        manager = JsonlDatasetManager()
        assert isinstance(manager, DatasetManager)
