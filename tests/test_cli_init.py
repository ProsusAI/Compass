"""Tests for odysseus.cli — init command."""

from odysseus.cli import run_init


class TestRunInit:
    def test_creates_directories(self, tmp_path):
        run_init(tmp_path)
        assert (tmp_path / "outputs").is_dir()
        assert (tmp_path / "prompts").is_dir()
        assert (tmp_path / "backends").is_dir()

    def test_creates_mock_backend(self, tmp_path):
        run_init(tmp_path)
        mock_yaml = tmp_path / "backends" / "mock-echo.yaml"
        assert mock_yaml.is_file()
        assert "mock-echo" in mock_yaml.read_text()

    def test_creates_run_config(self, tmp_path):
        run_init(tmp_path)
        config = tmp_path / "outputs" / "run_config.yaml"
        assert config.is_file()

    def test_idempotent(self, tmp_path):
        run_init(tmp_path)
        custom = tmp_path / "prompts" / "v1.txt"
        custom.write_text("my prompt")
        run_init(tmp_path)
        assert custom.read_text() == "my prompt"

    def test_does_not_overwrite_existing_files(self, tmp_path):
        (tmp_path / "backends").mkdir()
        existing = tmp_path / "backends" / "mock-echo.yaml"
        existing.write_text("custom content")
        run_init(tmp_path)
        assert existing.read_text() == "custom content"
