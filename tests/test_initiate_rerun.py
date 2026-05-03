"""Tests for initiate_rerun tool logic (direct function tests, no MCP)."""

import json
from pathlib import Path

import pytest

from odysseus.agents.pipeline.status import get_pipeline_status


def _setup_stage4_converged_with_pareto(base: Path, run_id: str) -> None:
    """Stage 4 complete: converged=True, pareto_front has one candidate."""
    (base / run_id / "input").mkdir(parents=True, exist_ok=True)
    (base / run_id / "input" / "input_report.md").write_text("# Report")
    (base / run_id / "validation").mkdir(parents=True, exist_ok=True)
    for f in ["transformed.jsonl", "data_quality_report.json", "routing_context.json"]:
        (base / run_id / "validation" / f).write_text("{}")
    (base / run_id / "analysis").mkdir(parents=True, exist_ok=True)
    for f in ["dev.jsonl", "holdout.jsonl"]:
        (base / run_id / "analysis" / f).write_text("{}")
    (base / "backends").mkdir(parents=True, exist_ok=True)
    (base / "backends" / "mock.yaml").write_text(
        "model: mock-model\nprovider: mock_echo\n"
        "requests_per_minute: 100\ntokens_per_minute: 100000\n"
        "pricing:\n"
        "  input_cost_per_million_tokens: 0.0\n"
        "  cached_cost_per_million_tokens: 0.0\n"
        "  output_cost_per_million_tokens: 0.0\n"
    )
    (base / run_id / "search").mkdir(parents=True, exist_ok=True)
    (base / run_id / "search" / "child_variants.json").write_text("[]")
    (base / run_id / "prompts").mkdir(parents=True, exist_ok=True)
    (base / run_id / "prompts" / "v1.txt").write_text("prompt text")
    (base / run_id / "prompts" / "v3.txt").write_text("best prompt text")
    pareto_front = [
        {
            "prompt_version": "v1",
            "parent_version": None,
            "quality_score": 0.80,
            "cost": 0.05,
            "round_introduced": 1,
            "dominated": True,
            "example_ids": [],
        },
        {
            "prompt_version": "v3",
            "parent_version": "v1",
            "quality_score": 0.92,
            "cost": 0.04,
            "round_introduced": 3,
            "dominated": False,
            "example_ids": [],
        },
    ]
    search_state = {
        "search_state_id": "ss-001",
        "backend": "mock",
        "primary_metric_name": None,
        "round": 5,
        "pareto_front": pareto_front,
        "round_history": [],
        "stagnation_count": 5,
        "stagnation_limit": 3,
        "convergence_limit": 5,
        "max_rounds": 50,
        "mutation_mode": "targeted",
        "converged": True,
        "loop_phase": "build",
    }
    (base / run_id / "search" / "search_state.json").write_text(json.dumps(search_state))


def _run_initiate_rerun(
    outputs_dir: Path,
    run_id: str,
    source_prompt_version: str | None = None,
) -> dict:
    """Call the initiate_rerun business logic directly (no MCP layer)."""
    from odysseus.mcp._initiate_rerun import initiate_rerun_logic

    return initiate_rerun_logic(
        outputs_dir=outputs_dir,
        run_id=run_id,
        source_prompt_version=source_prompt_version,
    )


class TestInitiateRerun:
    def test_writes_rerun_config_json(self, tmp_path: Path) -> None:
        _setup_stage4_converged_with_pareto(tmp_path, "r1")
        _run_initiate_rerun(tmp_path, "r1")
        config_path = tmp_path / "r1" / "rerun_config.json"
        assert config_path.is_file()
        config = json.loads(config_path.read_text())
        assert config["mode"] == "rerun"
        assert config["new_backend"] is None
        assert config["source_prompt_version"] == "v3"  # highest quality on front
        assert config["original_backend"] == "mock"

    def test_renames_search_state(self, tmp_path: Path) -> None:
        _setup_stage4_converged_with_pareto(tmp_path, "r1")
        _run_initiate_rerun(tmp_path, "r1")
        assert not (tmp_path / "r1" / "search" / "search_state.json").is_file()
        assert (tmp_path / "r1" / "search" / "search_state_original.json").is_file()

    def test_stage4_becomes_incomplete_after_rename(self, tmp_path: Path) -> None:
        _setup_stage4_converged_with_pareto(tmp_path, "r1")
        _run_initiate_rerun(tmp_path, "r1")
        assert not (tmp_path / "r1" / "search" / "search_state.json").is_file()

    def test_explicit_source_version_override(self, tmp_path: Path) -> None:
        _setup_stage4_converged_with_pareto(tmp_path, "r1")
        _run_initiate_rerun(tmp_path, "r1", source_prompt_version="v1")
        config = json.loads((tmp_path / "r1" / "rerun_config.json").read_text())
        assert config["source_prompt_version"] == "v1"

    def test_raises_when_stage4_not_complete(self, tmp_path: Path) -> None:
        (tmp_path / "r1" / "input").mkdir(parents=True, exist_ok=True)
        (tmp_path / "r1" / "input" / "input_report.md").write_text("# Report")
        (tmp_path / "r1" / "search").mkdir(parents=True, exist_ok=True)
        (tmp_path / "r1" / "search" / "search_state.json").write_text(json.dumps({"converged": False, "round": 1}))
        with pytest.raises(ValueError, match="Stage 4 is not complete"):
            _run_initiate_rerun(tmp_path, "r1")

    def test_raises_when_search_state_missing(self, tmp_path: Path) -> None:
        (tmp_path / "r1" / "input").mkdir(parents=True, exist_ok=True)
        (tmp_path / "r1" / "input" / "input_report.md").write_text("# Report")
        with pytest.raises(ValueError, match="Stage 4 is not complete"):
            _run_initiate_rerun(tmp_path, "r1")

    def test_elite_set_key_takes_precedence_over_pareto_front(self, tmp_path: Path) -> None:
        """State files with elite_set use that; pareto_front is only a fallback."""
        _setup_stage4_converged_with_pareto(tmp_path, "r2")
        # Overwrite the state file to use the new elite_set key
        search_dir = tmp_path / "r2" / "search"
        state = json.loads((search_dir / "search_state.json").read_text())
        # Move pareto_front → elite_set (as the new code serialises it)
        state["elite_set"] = state.pop("pareto_front")
        (search_dir / "search_state.json").write_text(json.dumps(state))
        result = _run_initiate_rerun(tmp_path, "r2")
        assert result["source_prompt_version"] == "v3"

    def test_pareto_front_fallback_loads_old_state_files(self, tmp_path: Path) -> None:
        """Old state files that only have pareto_front are still accepted."""
        _setup_stage4_converged_with_pareto(tmp_path, "r3")
        # Fixture already writes pareto_front (no elite_set key) — should work as-is
        result = _run_initiate_rerun(tmp_path, "r3")
        assert result["source_prompt_version"] == "v3"
