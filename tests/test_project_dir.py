"""Tests for compass.project_dir."""

import compass.project_dir
from compass.project_dir import get_project_dir


class TestGetProjectDir:
    def test_returns_cwd(self, monkeypatch, tmp_path):
        monkeypatch.setattr(compass.project_dir, "_cached", None)
        monkeypatch.chdir(tmp_path)
        assert get_project_dir() == tmp_path
