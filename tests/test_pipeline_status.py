import time
from pathlib import Path

from odysseus.agents.pipeline_status import discover_runs, get_pipeline_status


class TestDiscoverRuns:
    def test_no_runs(self, tmp_path: Path) -> None:
        assert discover_runs(tmp_path) == []

    def test_finds_run(self, tmp_path: Path) -> None:
        (tmp_path / "abc12345" / "input").mkdir(parents=True)
        (tmp_path / "abc12345" / "input" / "input_report.md").write_text("# Report")
        assert discover_runs(tmp_path) == ["abc12345"]

    def test_most_recent_first(self, tmp_path: Path) -> None:
        for rid in ["run_old", "run_new"]:
            d = tmp_path / rid / "input"
            d.mkdir(parents=True)
            (d / "input_report.md").write_text("# Report")
            time.sleep(0.05)
        assert discover_runs(tmp_path)[0] == "run_new"


class TestGetPipelineStatus:
    def test_empty_run(self, tmp_path: Path) -> None:
        (tmp_path / "abc12345" / "input").mkdir(parents=True)
        (tmp_path / "abc12345" / "input" / "input_report.md").write_text("# Report")
        result = get_pipeline_status(tmp_path, "abc12345")
        assert result["stages"][0]["status"] == "complete"
        assert result["current_stage"] == 2

    def test_validation_complete(self, tmp_path: Path) -> None:
        _setup_through_validation(tmp_path, "abc12345")
        result = get_pipeline_status(tmp_path, "abc12345")
        assert result["stages"][1]["status"] == "complete"
        assert result["current_stage"] == 3

    def test_analysis_complete(self, tmp_path: Path) -> None:
        _setup_through_validation(tmp_path, "abc12345")
        analysis = tmp_path / "abc12345" / "analysis"
        analysis.mkdir(parents=True)
        for f in ["validation_report.json", "dev.jsonl", "holdout.jsonl",
                   "dev_rationale_card_set.json", "holdout_rationale_card_set.json",
                   "vocabulary_registry.json"]:
            (analysis / f).write_text("{}")
        result = get_pipeline_status(tmp_path, "abc12345")
        assert result["stages"][2]["status"] == "complete"

    def test_blocked_stages(self, tmp_path: Path) -> None:
        (tmp_path / "abc12345" / "input").mkdir(parents=True)
        (tmp_path / "abc12345" / "input" / "input_report.md").write_text("# Report")
        result = get_pipeline_status(tmp_path, "abc12345")
        assert result["stages"][2]["status"] == "blocked"  # routing analysis
        assert result["stages"][4]["status"] == "blocked"  # prompt v1

    def test_no_runs_returns_empty(self, tmp_path: Path) -> None:
        result = get_pipeline_status(tmp_path, run_id=None)
        assert result["run_id"] is None
        assert result["current_stage"] == 1
        assert "submit_input_report" in result["available_tools"]

    def test_run_id_none_uses_most_recent(self, tmp_path: Path) -> None:
        for rid in ["old_run", "new_run"]:
            d = tmp_path / rid / "input"
            d.mkdir(parents=True)
            (d / "input_report.md").write_text("# Report")
            time.sleep(0.05)
        result = get_pipeline_status(tmp_path, run_id=None)
        assert result["run_id"] == "new_run"

    def test_prompt_v1_glob(self, tmp_path: Path) -> None:
        """Stage 5 should detect v1.yaml, not just v1.txt."""
        _setup_through_validation(tmp_path, "r1")
        _setup_analysis(tmp_path, "r1")
        prompts = tmp_path / "r1" / "prompts"
        prompts.mkdir(parents=True)
        (prompts / "v1.yaml").write_text("prompt: test")
        result = get_pipeline_status(tmp_path, "r1")
        assert result["stages"][4]["status"] == "complete"


def _setup_through_validation(base: Path, run_id: str) -> None:
    (base / run_id / "input").mkdir(parents=True, exist_ok=True)
    (base / run_id / "input" / "input_report.md").write_text("# Report")
    (base / run_id / "validation").mkdir(parents=True, exist_ok=True)
    for f in ["transformed.jsonl", "data_quality_report.json", "routing_context.json"]:
        (base / run_id / "validation" / f).write_text("{}")


def _setup_analysis(base: Path, run_id: str) -> None:
    analysis = base / run_id / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    for f in ["validation_report.json", "dev.jsonl", "holdout.jsonl",
               "dev_rationale_card_set.json", "holdout_rationale_card_set.json",
               "vocabulary_registry.json"]:
        (analysis / f).write_text("{}")
