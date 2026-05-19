"""Tests for the build_pipeline_config helper."""

from pathlib import Path

from odysseus.agents.prompt_builder.search import SearchState
from odysseus.mcp.prompt_building_tools import build_pipeline_config


class TestBuildPipelineConfig:
    def test_default_metric_when_no_primary(self, tmp_path: Path) -> None:
        """No primary_metric_name -> accuracy + confusion + f1 + cost_quality_change."""
        state = SearchState(search_state_id="r1", backend="anthropic", primary_metric_name=None)
        config = build_pipeline_config(
            state=state,
            prompt_version="v1",
            data_source="d.jsonl",
            run_id="r1",
            project_dir=tmp_path,
        )
        names = [m.name for m in config.metrics]
        assert names == ["accuracy", "confusion", "f1", "cost_quality_change"]

    def test_primary_metric_with_slash(self, tmp_path: Path) -> None:
        """primary_metric_name='f1/macro' keeps the default metric set."""
        state = SearchState(search_state_id="r1", backend="anthropic", primary_metric_name="f1/macro")
        config = build_pipeline_config(
            state=state,
            prompt_version="v1",
            data_source="d.jsonl",
            run_id="r1",
            project_dir=tmp_path,
        )
        assert len(config.metrics) == 4
        names = [m.name for m in config.metrics]
        assert "accuracy" in names
        assert "confusion" in names
        assert "f1" in names
        assert "cost_quality_change" in names

    def test_primary_metric_accuracy_no_duplicate(self, tmp_path: Path) -> None:
        """primary_metric_name='accuracy' does not duplicate the default accuracy metric."""
        state = SearchState(search_state_id="r1", backend="anthropic", primary_metric_name="accuracy")
        config = build_pipeline_config(
            state=state,
            prompt_version="v1",
            data_source="d.jsonl",
            run_id="r1",
            project_dir=tmp_path,
        )
        names = [m.name for m in config.metrics]
        assert names == ["accuracy", "confusion", "f1", "cost_quality_change"]

    def test_output_paths_scoped_to_run(self, tmp_path: Path) -> None:
        """Output paths are under outputs/<run_id>/eval/."""
        state = SearchState(search_state_id="r1", backend="anthropic")
        config = build_pipeline_config(
            state=state,
            prompt_version="v1",
            data_source="d.jsonl",
            run_id="r1",
            project_dir=tmp_path,
        )
        assert "r1/eval/v1/results.jsonl" in config.output.results_path
        assert "r1/eval/v1/report.json" in config.output.report_path

    def test_backend_from_state(self, tmp_path: Path) -> None:
        """Backend comes from search state."""
        state = SearchState(search_state_id="r1", backend="openai")
        config = build_pipeline_config(
            state=state,
            prompt_version="v1",
            data_source="d.jsonl",
            run_id="r1",
            project_dir=tmp_path,
        )
        assert config.backend == "openai"
