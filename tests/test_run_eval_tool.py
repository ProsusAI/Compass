"""Tests for the run_eval MCP tool (thin adapter over EvalRunnerAgent).

These tests verify that the MCP layer correctly:
- Passes tool parameters to the agent as a context dict
- Translates agent success (ScoreReport) into JSON with paths
- Translates agent errors into ToolError
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.agents.prompt_builder_search import SearchState
from odysseus.eval.models import RunSummary, ScoreReport
from odysseus.mcp import run_eval

AGENT_RUN = "odysseus.agents.eval_runner.EvalRunnerAgent.run"


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
    """Successful run_eval returns report and results paths."""
    score_report = _stub_score_report()

    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

        result = await run_eval(
            prompt_version="v1",
            data_source="data/test.jsonl",
            backend="test-backend",
        )

    parsed = json.loads(result)
    assert parsed["report_path"] == "outputs/report.json"
    assert parsed["results_path"] == "outputs/results.jsonl"


# ---------------------------------------------------------------------------
# Context forwarding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_eval_forwards_all_params() -> None:
    """run_eval passes all tool parameters to the agent context."""
    score_report = _stub_score_report()

    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

        await run_eval(
            prompt_version="v5",
            data_source="data/new.jsonl",
            backend="tool-backend",
            config_path="custom/config.yaml",
        )

    context = mock_run.call_args.args[0]
    assert context["prompt_version"] == "v5"
    assert context["data_source"] == "data/new.jsonl"
    assert context["backend"] == "tool-backend"
    assert context["config_path"] == "custom/config.yaml"


@pytest.mark.asyncio
async def test_run_eval_default_config_path() -> None:
    """run_eval uses default config_path when not specified."""
    score_report = _stub_score_report()

    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

        await run_eval(
            prompt_version="v1",
            data_source="data/test.jsonl",
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
    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"error": {"category": "not_found", "detail": "config missing"}}

        with pytest.raises(ToolError, match="not_found"):
            await run_eval(
                prompt_version="v1",
                data_source="data/test.jsonl",
                backend="test-backend",
            )


@pytest.mark.asyncio
async def test_run_eval_validation_error_raises_tool_error() -> None:
    """Agent validation_error is translated to ToolError."""
    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"error": {"category": "validation_error", "detail": "bad config"}}

        with pytest.raises(ToolError, match="validation_error"):
            await run_eval(
                prompt_version="v1",
                data_source="data/test.jsonl",
                backend="test-backend",
            )


@pytest.mark.asyncio
async def test_run_eval_run_error_raises_tool_error() -> None:
    """Agent run_error is translated to ToolError."""
    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"error": {"category": "run_error", "detail": "connection reset"}}

        with pytest.raises(ToolError, match="run_error"):
            await run_eval(
                prompt_version="v1",
                data_source="data/test.jsonl",
                backend="test-backend",
            )


@pytest.mark.asyncio
async def test_run_eval_permission_error_raises_tool_error() -> None:
    """Agent permission_denied error is translated to ToolError."""
    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"error": {"category": "permission_denied", "detail": "read-only"}}

        with pytest.raises(ToolError, match="permission_denied"):
            await run_eval(
                prompt_version="v1",
                data_source="data/test.jsonl",
                backend="test-backend",
            )


# ---------------------------------------------------------------------------
# Pre-flight check
# ---------------------------------------------------------------------------

GET_SEARCH_STATE = "odysseus.mcp.get_search_state"
BACKEND_REGISTRY = "odysseus.mcp.BackendRegistry"


def _setup_run_eval_guard(tmp_path: Path, run_id: str = "test-123") -> None:
    """Create guard artifacts for run_eval (needs dev.jsonl + backend)."""
    analysis = tmp_path / "outputs" / run_id / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    (analysis / "dev.jsonl").write_text("")
    backends = tmp_path / "backends"
    backends.mkdir(parents=True, exist_ok=True)
    (backends / "anthropic.yaml").write_text("provider: anthropic")


@pytest.mark.asyncio
async def test_run_eval_preflight_triggers_on_round_zero(tmp_path: Path) -> None:
    """First run in loop (round 0, no history) returns action_required."""
    _setup_run_eval_guard(tmp_path)
    state = SearchState(
        search_state_id="test-123",
        backend="anthropic",
        round=0,
        round_history=[],
    )
    mock_registry = MagicMock()
    mock_registry.list_profiles.return_value = ["anthropic", "openai"]

    with (
        patch(GET_SEARCH_STATE, return_value=state),
        patch(BACKEND_REGISTRY) as MockRegistry,  # noqa: N806
        patch("odysseus.mcp.get_project_dir", return_value=tmp_path),
    ):
        MockRegistry.from_directory.return_value = mock_registry

        result = await run_eval(
            prompt_version="v1",
            data_source="data/test.jsonl",
            backend="anthropic",
            run_id="test-123",
        )

    parsed = json.loads(result)
    assert parsed["action_required"] == "backend_setup"
    assert parsed["run_id"] == "test-123"
    assert "anthropic" in parsed["available_backends"]


@pytest.mark.asyncio
async def test_run_eval_preflight_skipped_after_round_zero(tmp_path: Path) -> None:
    """After first round, run_eval proceeds normally (no action_required)."""
    _setup_run_eval_guard(tmp_path)
    state = SearchState(
        search_state_id="test-123",
        backend="anthropic",
        round=1,
        round_history=[],
    )
    score_report = _stub_score_report()

    with (
        patch(GET_SEARCH_STATE, return_value=state),
        patch(AGENT_RUN, new_callable=AsyncMock) as mock_run,
        patch("odysseus.mcp.get_project_dir", return_value=tmp_path),
    ):
        mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

        result = await run_eval(
            prompt_version="v1",
            data_source="data/test.jsonl",
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

    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

        result = await run_eval(
            prompt_version="v1",
            data_source="data/test.jsonl",
            backend="anthropic",
        )

    parsed = json.loads(result)
    assert "action_required" not in parsed
    assert "report_path" in parsed
