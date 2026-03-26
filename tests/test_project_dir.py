"""Tests for odysseus.project_dir."""

import os
from pathlib import Path

from odysseus.project_dir import get_project_dir


class TestGetProjectDir:
    def test_returns_cwd_by_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ODYSSEUS_PROJECT_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        assert get_project_dir() == tmp_path

    def test_env_var_overrides_cwd(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ODYSSEUS_PROJECT_DIR", str(tmp_path))
        assert get_project_dir() == tmp_path

    def test_env_var_resolved_to_absolute(self, monkeypatch, tmp_path):
        relative = "some/relative/path"
        monkeypatch.setenv("ODYSSEUS_PROJECT_DIR", relative)
        result = get_project_dir()
        assert result.is_absolute()
