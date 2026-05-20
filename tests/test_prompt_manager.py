"""Tests for the FilePromptManager."""

import logging
from pathlib import Path

import pytest

from compass.prompts.manager import FilePromptManager


@pytest.fixture()
def prompts_dir(tmp_path: Path) -> Path:
    """Create a temporary prompts directory with sample files."""
    d = tmp_path / "prompts"
    d.mkdir()
    return d


def _write_prompt(prompts_dir: Path, name: str, content: str) -> Path:
    """Helper to write a prompt file and return its path."""
    p = prompts_dir / name
    p.write_text(content)
    return p


class TestLoad:
    def test_load_yaml_by_version(self, prompts_dir: Path) -> None:
        _write_prompt(prompts_dir, "v1.yaml", "prompt: You are a router.")
        mgr = FilePromptManager(prompts_dir)
        result = mgr.load("v1")
        assert result == "prompt: You are a router."

    def test_load_txt_by_version(self, prompts_dir: Path) -> None:
        _write_prompt(prompts_dir, "v2.txt", "Route this request.")
        mgr = FilePromptManager(prompts_dir)
        result = mgr.load("v2")
        assert result == "Route this request."

    def test_load_prefers_yaml_over_txt(self, prompts_dir: Path) -> None:
        _write_prompt(prompts_dir, "v1.yaml", "yaml content")
        _write_prompt(prompts_dir, "v1.txt", "txt content")
        mgr = FilePromptManager(prompts_dir)
        assert mgr.load("v1") == "yaml content"

    def test_load_unknown_version_raises(self, prompts_dir: Path) -> None:
        mgr = FilePromptManager(prompts_dir)
        with pytest.raises(FileNotFoundError, match="no-such-version"):
            mgr.load("no-such-version")

    def test_load_empty_directory_raises_for_latest(self, prompts_dir: Path) -> None:
        mgr = FilePromptManager(prompts_dir)
        with pytest.raises(FileNotFoundError, match="latest"):
            mgr.load("latest")


class TestLatestResolution:
    def test_latest_returns_most_recently_modified(self, prompts_dir: Path) -> None:
        import time

        _write_prompt(prompts_dir, "v1.yaml", "old prompt")
        time.sleep(0.05)
        _write_prompt(prompts_dir, "v2.yaml", "new prompt")
        mgr = FilePromptManager(prompts_dir)
        assert mgr.load("latest") == "new prompt"

    def test_latest_ignores_non_prompt_files(self, prompts_dir: Path) -> None:
        _write_prompt(prompts_dir, ".gitkeep", "")
        _write_prompt(prompts_dir, "v1.yaml", "the prompt")
        mgr = FilePromptManager(prompts_dir)
        assert mgr.load("latest") == "the prompt"


class TestLogging:
    def test_load_logs_version_at_info(self, prompts_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
        _write_prompt(prompts_dir, "v3.yaml", "some prompt")
        mgr = FilePromptManager(prompts_dir)

        with caplog.at_level(logging.INFO, logger="compass.prompts.manager"):
            mgr.load("v3")

        assert any("v3" in record.message for record in caplog.records)

    def test_load_latest_logs_resolved_version(self, prompts_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
        _write_prompt(prompts_dir, "v1.yaml", "prompt")
        mgr = FilePromptManager(prompts_dir)

        with caplog.at_level(logging.INFO, logger="compass.prompts.manager"):
            mgr.load("latest")

        assert any("latest" in record.message or "v1" in record.message for record in caplog.records)
