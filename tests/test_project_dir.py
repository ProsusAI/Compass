"""Tests for odysseus.project_dir."""

from odysseus.project_dir import get_project_dir


class TestGetProjectDir:
    def test_returns_cwd(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        assert get_project_dir() == tmp_path
