"""Tests for the run_eval MCP tool (thin adapter over EvalRunnerAgent).

These tests verify that the MCP layer correctly:
- Passes tool parameters to the agent as a context dict
- Translates agent success (ScoreReport) into JSON with paths and metrics
- Translates agent errors into ToolError
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.agents.prompt_builder.search import RoundSummary, SearchState
from odysseus.eval.models import RunSummary, ScoreReport
from odysseus.mcp import run_eval
from odysseus.mcp.prompt_building_tools import build_pipeline_config

AGENT_RUN = "odysseus.agents.eval_runner.EvalRunnerAgent.run"
RESOLVE_PROJECT_DIR = "odysseus.project_dir.resolve_project_dir"


def _stub_score_report(
    *,
    report_path: str = "outputs/report.json",
    results_path: str = "outputs/results.jsonl",
    accuracy: float = 0.85,
) -> ScoreReport:
    """Create a minimal ScoreReport for testing."""
    return ScoreReport(
        metrics={"accuracy": accuracy},
        summary=RunSummary(
            total=1,
            succeeded=1,
            failed=0,
            total_cost=0.001,
            start_time=datetime(2026, 1, 1, tzinfo=UTC),
            end_time=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
            duration_seconds=60.0,
        ),
        errors=[],
        diff=None,
        report_path=report_path,
        results_path=results_path,
    )


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_eval_success() -> None:
    """Successful run_eval returns report path, results path, metrics, and summary."""
    score_report = _stub_score_report()

    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run, patch(
        RESOLVE_PROJECT_DIR, new_callable=AsyncMock
    ):
        mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

        result = await run_eval(
            ctx=None,
            prompt_version="v1",
            backend="test-backend",
        )

    parsed = json.loads(result)
    assert parsed["report_path"] == "outputs/report.json"
    assert parsed["results_path"] == "outputs/results.jsonl"
    assert parsed["metrics"] == {"accuracy": 0.85}
    assert parsed["summary"]["total_cost"] == 0.001


# ---------------------------------------------------------------------------
# Context forwarding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_eval_forwards_all_params() -> None:
    """run_eval passes all tool parameters to the agent context."""
    score_report = _stub_score_report()

    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run, patch(
        RESOLVE_PROJECT_DIR, new_callable=AsyncMock
    ):
        mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

        await run_eval(
            ctx=None,
            prompt_version="v5",
            backend="tool-backend",
            config_path="custom/config.yaml",
        )

    context = mock_run.call_args.args[0]
    assert context["prompt_version"] == "v5"
    assert context["backend"] == "tool-backend"
    assert context["config_path"] == "custom/config.yaml"
    assert "data_source" not in context


@pytest.mark.asyncio
async def test_run_eval_default_config_path() -> None:
    """run_eval uses default config_path when not specified."""
    score_report = _stub_score_report()

    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run, patch(
        RESOLVE_PROJECT_DIR, new_callable=AsyncMock
    ):
        mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

        await run_eval(
            ctx=None,
            prompt_version="v1",
            backend="test-backend",
        )

    context = mock_run.call_args.args[0]
    assert context["config_path"] == "outputs/run_config.yaml"


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_eval_not_found_raises_tool_error() -> None:
    """Agent not_found error is translated to ToolError."""
    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run, patch(
        RESOLVE_PROJECT_DIR, new_callable=AsyncMock
    ):
        mock_run.return_value = {"error": {"category": "not_found", "detail": "config missing"}}

        with pytest.raises(ToolError, match="not_found"):
            await run_eval(
                ctx=None,
                prompt_version="v1",
                backend="test-backend",
            )


@pytest.mark.asyncio
async def test_run_eval_validation_error_raises_tool_error() -> None:
    """Agent validation_error is translated to ToolError."""
    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run, patch(
        RESOLVE_PROJECT_DIR, new_callable=AsyncMock
    ):
        mock_run.return_value = {"error": {"category": "validation_error", "detail": "bad config"}}

        with pytest.raises(ToolError, match="validation_error"):
            await run_eval(
                ctx=None,
                prompt_version="v1",
                backend="test-backend",
            )


@pytest.mark.asyncio
async def test_run_eval_run_error_raises_tool_error() -> None:
    """Agent run_error is translated to ToolError."""
    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run, patch(
        RESOLVE_PROJECT_DIR, new_callable=AsyncMock
    ):
        mock_run.return_value = {"error": {"category": "run_error", "detail": "connection reset"}}

        with pytest.raises(ToolError, match="run_error"):
            await run_eval(
                ctx=None,
                prompt_version="v1",
                backend="test-backend",
            )


@pytest.mark.asyncio
async def test_run_eval_permission_error_raises_tool_error() -> None:
    """Agent permission_denied error is translated to ToolError."""
    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run, patch(
        RESOLVE_PROJECT_DIR, new_callable=AsyncMock
    ):
        mock_run.return_value = {"error": {"category": "permission_denied", "detail": "read-only"}}

        with pytest.raises(ToolError, match="permission_denied"):
            await run_eval(
                ctx=None,
                prompt_version="v1",
                backend="test-backend",
            )


# ---------------------------------------------------------------------------
# Pre-flight check
# ---------------------------------------------------------------------------

GET_SEARCH_STATE = "odysseus.mcp.prompt_building_tools.get_search_state"
BACKEND_REGISTRY = "odysseus.mcp.prompt_building_tools.BackendRegistry"


def _setup_run_eval_guard(tmp_path: Path, run_id: str = "test-123") -> None:
    """Create guard artifacts for run_eval (needs dev.jsonl + backend)."""
    analysis = tmp_path / "outputs" / run_id / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    (analysis / "dev.jsonl").write_text("")
    backends = tmp_path / "backends"
    backends.mkdir(parents=True, exist_ok=True)
    (backends / "anthropic.yaml").write_text("provider: anthropic")


@pytest.mark.asyncio
async def test_run_eval_preflight_triggers_when_backend_missing(tmp_path: Path) -> None:
    """Missing backend on search state returns action_required."""
    _setup_run_eval_guard(tmp_path)
    state = SearchState(
        search_state_id="test-123",
        backend="",
        round=0,
        round_history=[],
    )
    mock_registry = MagicMock()
    mock_registry.list_profiles.return_value = ["anthropic", "openai"]

    with (
        patch(GET_SEARCH_STATE, return_value=state),
        patch(BACKEND_REGISTRY) as MockRegistry,  # noqa: N806
        patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
    ):
        MockRegistry.from_directory.return_value = mock_registry

        result = await run_eval(
            ctx=None,
            prompt_version="v1",
            run_id="test-123",
        )

    parsed = json.loads(result)
    assert parsed["action_required"] == "backend_setup"
    assert parsed["run_id"] == "test-123"
    assert "anthropic" in parsed["available_backends"]


@pytest.mark.asyncio
async def test_run_eval_preflight_skipped_when_backend_set(tmp_path: Path) -> None:
    """When backend is set on search state, run_eval proceeds normally."""
    _setup_run_eval_guard(tmp_path)
    state = SearchState(
        search_state_id="test-123",
        backend="anthropic",
        round=0,
        round_history=[],
    )
    score_report = _stub_score_report()

    with (
        patch(GET_SEARCH_STATE, return_value=state),
        patch(AGENT_RUN, new_callable=AsyncMock) as mock_run,
        patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
    ):
        mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

        result = await run_eval(
            ctx=None,
            prompt_version="v1",
            backend="anthropic",
            run_id="test-123",
        )

    parsed = json.loads(result)
    assert "action_required" not in parsed
    assert "report_path" in parsed


@pytest.mark.asyncio
async def test_run_eval_no_search_state_id_skips_preflight() -> None:
    """Without search_state_id, run_eval behaves as before."""
    score_report = _stub_score_report()

    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run, patch(
        RESOLVE_PROJECT_DIR, new_callable=AsyncMock
    ):
        mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

        result = await run_eval(
            ctx=None,
            prompt_version="v1",
            backend="anthropic",
        )

    parsed = json.loads(result)
    assert "action_required" not in parsed
    assert "report_path" in parsed


# ---------------------------------------------------------------------------
# Pipeline config building
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_eval_pipeline_builds_config_from_state(tmp_path: Path) -> None:
    """Pipeline run (run_id set) builds RunConfig from search state, no YAML needed."""
    run_id = "test-cfg"
    _setup_run_eval_guard(tmp_path, run_id=run_id)

    state = SearchState(
        search_state_id=run_id,
        backend="anthropic",
        primary_metric_name="f1/macro",
        round=1,
        round_history=[
            RoundSummary(
                round=1, candidates_evaluated=["v1"], new_elite_entries=1,
                elite_size=1, mutation_mode="targeted", stagnation_count=0, converged=False,
            ),
        ],
    )
    score_report = _stub_score_report(
        report_path=str(tmp_path / "outputs" / run_id / "eval" / "report.json"),
        results_path=str(tmp_path / "outputs" / run_id / "eval" / "results.jsonl"),
    )

    with (
        patch(GET_SEARCH_STATE, return_value=state),
        patch(AGENT_RUN, new_callable=AsyncMock) as mock_run,
        patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
    ):
        mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

        result = await run_eval(
            ctx=None,
            prompt_version="v1",
            run_id=run_id,
        )

    parsed = json.loads(result)
    assert "report_path" in parsed

    context = mock_run.call_args.args[0]
    assert "run_config" in context
    assert context["run_config"].backend == "anthropic"
    assert any(m.name == "f1" for m in context["run_config"].metrics)
    assert run_id in context["run_config"].output.results_path


@pytest.mark.asyncio
async def test_run_eval_backend_optional_for_pipeline() -> None:
    """run_eval can be called without backend when run_id is provided."""
    import inspect
    sig = inspect.signature(run_eval)
    param = sig.parameters["backend"]
    assert param.default is not inspect.Parameter.empty, "backend should have a default"


# ---------------------------------------------------------------------------
# Standalone run_eval context forwarding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_eval_standalone_forwards_backend_and_config() -> None:
    """Standalone run_eval (no run_id) passes backend and config_path to agent."""
    score_report = _stub_score_report()

    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run, patch(
        RESOLVE_PROJECT_DIR, new_callable=AsyncMock
    ):
        mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

        await run_eval(
            ctx=None,
            prompt_version="v5",
            backend="tool-backend",
            config_path="custom/config.yaml",
        )

    context = mock_run.call_args.args[0]
    assert context["backend"] == "tool-backend"
    assert context["config_path"] == "custom/config.yaml"
    assert "run_config" not in context
    assert "data_source" not in context


# ---------------------------------------------------------------------------
# build_pipeline_config helper
# ---------------------------------------------------------------------------


class TestBuildPipelineConfig:
    """Tests for build_pipeline_config helper."""

    def test_default_metric_when_no_primary(self, tmp_path: Path) -> None:
        """No primary_metric_name → accuracy + confusion + f1 + cost_quality_change."""
        state = SearchState(
            search_state_id="r1", backend="anthropic", primary_metric_name=None
        )
        config = build_pipeline_config(
            state=state, prompt_version="v1", data_source="d.jsonl",
            run_id="r1", project_dir=tmp_path,
        )
        names = [m.name for m in config.metrics]
        assert names == ["accuracy", "confusion", "f1", "cost_quality_change"]

    def test_primary_metric_with_slash(self, tmp_path: Path) -> None:
        """primary_metric_name='f1/macro' → default metrics; f1 already included with default params."""
        state = SearchState(
            search_state_id="r1", backend="anthropic", primary_metric_name="f1/macro"
        )
        config = build_pipeline_config(
            state=state, prompt_version="v1", data_source="d.jsonl",
            run_id="r1", project_dir=tmp_path,
        )
        assert len(config.metrics) == 4
        names = [m.name for m in config.metrics]
        assert "accuracy" in names
        assert "confusion" in names
        assert "f1" in names
        assert "cost_quality_change" in names

    def test_primary_metric_accuracy_no_duplicate(self, tmp_path: Path) -> None:
        """primary_metric_name='accuracy' → defaults only (no duplicate accuracy)."""
        state = SearchState(
            search_state_id="r1", backend="anthropic", primary_metric_name="accuracy"
        )
        config = build_pipeline_config(
            state=state, prompt_version="v1", data_source="d.jsonl",
            run_id="r1", project_dir=tmp_path,
        )
        names = [m.name for m in config.metrics]
        assert names == ["accuracy", "confusion", "f1", "cost_quality_change"]

    def test_output_paths_scoped_to_run(self, tmp_path: Path) -> None:
        """Output paths are under outputs/<run_id>/eval/."""
        state = SearchState(
            search_state_id="r1", backend="anthropic"
        )
        config = build_pipeline_config(
            state=state, prompt_version="v1", data_source="d.jsonl",
            run_id="r1", project_dir=tmp_path,
        )
        assert "r1/eval/v1/results.jsonl" in config.output.results_path
        assert "r1/eval/v1/report.json" in config.output.report_path

    def test_backend_from_state(self, tmp_path: Path) -> None:
        """Backend comes from search state."""
        state = SearchState(
            search_state_id="r1", backend="openai"
        )
        config = build_pipeline_config(
            state=state, prompt_version="v1", data_source="d.jsonl",
            run_id="r1", project_dir=tmp_path,
        )
        assert config.backend == "openai"
