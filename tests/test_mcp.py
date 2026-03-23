"""Smoke tests for the MCP server."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.eval.models import RunSummary, ScoreReport
from odysseus.mcp import mcp

AGENT_RUN = "odysseus.agents.eval_runner.EvalRunnerAgent.run"


async def test_server_has_tools():
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "optimize_routing_prompt" in tool_names


async def test_run_holdout_eval_is_stub():
    """run_holdout_eval is still a stub (out of THP-129 scope)."""
    from odysseus.mcp import run_holdout_eval

    result = await run_holdout_eval(prompt_version="v1", data_source="data/test.jsonl")
    assert "stub" in result


async def test_run_eval_tool_registered():
    """run_eval must be registered as an MCP tool."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "run_eval" in tool_names


async def test_run_holdout_eval_tool_registered():
    """run_holdout_eval must be registered as an MCP tool."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "run_holdout_eval" in tool_names


async def test_run_eval_does_not_expose_data_split():
    """run_eval must not expose data_split as a parameter."""
    tools = await mcp.list_tools()
    run_eval_tool = next(t for t in tools if t.name == "run_eval")
    schema_properties = run_eval_tool.inputSchema.get("properties", {})
    assert "data_split" not in schema_properties, "data_split must not be exposed as a tool parameter"


async def test_run_holdout_eval_does_not_expose_data_split():
    """run_holdout_eval must not expose data_split as a parameter."""
    tools = await mcp.list_tools()
    holdout_tool = next(t for t in tools if t.name == "run_holdout_eval")
    schema_properties = holdout_tool.inputSchema.get("properties", {})
    assert "data_split" not in schema_properties, "data_split must not be exposed as a tool parameter"


def _make_stub_score_report() -> ScoreReport:
    """Create a minimal ScoreReport for testing."""
    return ScoreReport(
        metrics={"accuracy": 0.95},
        summary=RunSummary(
            total=10,
            succeeded=10,
            failed=0,
            total_cost=0.01,
            start_time=datetime(2026, 1, 1, tzinfo=UTC),
            end_time=datetime(2026, 1, 1, tzinfo=UTC),
            duration_seconds=5.0,
        ),
        errors=[],
        diff=None,
        report_path="outputs/report.json",
        results_path="outputs/results.jsonl",
    )


class TestRunEval:
    """Integration tests for the run_eval MCP tool."""

    async def test_success_returns_paths(self):
        """Successful run returns JSON with report_path and results_path."""
        score_report = _make_stub_score_report()

        with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

            from odysseus.mcp import run_eval

            result = await run_eval(
                prompt_version="v1",
                data_source="data/test.jsonl",
                backend="test-backend",
            )

        parsed = json.loads(result)
        assert parsed["report_path"] == "outputs/report.json"
        assert parsed["results_path"] == "outputs/results.jsonl"

    async def test_agent_receives_correct_context(self):
        """MCP tool passes all parameters to agent context."""
        score_report = _make_stub_score_report()

        with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

            from odysseus.mcp import run_eval

            await run_eval(
                prompt_version="v3",
                data_source="data/routing.jsonl",
                backend="openai",
                config_path="custom/config.yaml",
            )

        context = mock_run.call_args.args[0]
        assert context["prompt_version"] == "v3"
        assert context["data_source"] == "data/routing.jsonl"
        assert context["backend"] == "openai"
        assert context["config_path"] == "custom/config.yaml"

    async def test_agent_error_raises_tool_error(self):
        """Agent error dict is translated to ToolError."""
        with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {"error": {"category": "not_found", "detail": "config missing"}}

            from odysseus.mcp import run_eval

            with pytest.raises(ToolError, match="not_found"):
                await run_eval(
                    prompt_version="v1",
                    data_source="data/test.jsonl",
                    backend="test-backend",
                )

    async def test_validation_error_raises_tool_error(self):
        """Agent validation error is translated to ToolError."""
        with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {"error": {"category": "validation_error", "detail": "bad config"}}

            from odysseus.mcp import run_eval

            with pytest.raises(ToolError, match="validation_error"):
                await run_eval(
                    prompt_version="v1",
                    data_source="data/test.jsonl",
                    backend="test-backend",
                )
