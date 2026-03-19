"""Tests for the FilePromptManager."""

import asyncio  # noqa: F401 — used in Tasks 4-5 (hot-reload tests)
import contextlib  # noqa: F401 — used in Tasks 4-5 (hot-reload tests)
import logging  # noqa: F401 — used in Task 6 (logging tests)
from pathlib import Path

import pytest

from odysseus.prompts.manager import FilePromptManager


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


class TestHotReload:
    async def test_cache_updates_on_new_file(self, prompts_dir: Path) -> None:
        _write_prompt(prompts_dir, "v1.yaml", "original")
        mgr = FilePromptManager(prompts_dir)
        assert mgr.load("v1") == "original"

        # Start watcher
        task = asyncio.create_task(mgr.watch())
        try:
            # Add a new file
            _write_prompt(prompts_dir, "v2.yaml", "new version")
            # Give watcher time to detect
            await asyncio.sleep(0.5)
            assert mgr.load("v2") == "new version"
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def test_cache_updates_on_modified_file(self, prompts_dir: Path) -> None:
        _write_prompt(prompts_dir, "v1.yaml", "before")
        mgr = FilePromptManager(prompts_dir)
        assert mgr.load("v1") == "before"

        task = asyncio.create_task(mgr.watch())
        try:
            _write_prompt(prompts_dir, "v1.yaml", "after")
            await asyncio.sleep(0.5)
            assert mgr.load("v1") == "after"
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def test_cache_updates_on_deleted_file(self, prompts_dir: Path) -> None:
        p = _write_prompt(prompts_dir, "v1.yaml", "content")
        mgr = FilePromptManager(prompts_dir)
        assert mgr.load("v1") == "content"

        task = asyncio.create_task(mgr.watch())
        try:
            p.unlink()
            await asyncio.sleep(0.5)
            with pytest.raises(FileNotFoundError):
                mgr.load("v1")
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
