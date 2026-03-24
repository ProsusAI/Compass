"""Smoke tests for the MCP server."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.eval.models import RunSummary, ScoreReport
from odysseus.mcp import _PROJECT_ROOT, _load_text, mcp

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


class TestOdysseusRoutingInputPrompt:
    """Tests for the odysseus_routing_input MCP prompt."""

    async def test_prompt_registered(self):
        """odysseus_routing_input is listed as an MCP prompt."""
        prompts = await mcp.list_prompts()
        prompt_names = [p.name for p in prompts]
        assert "odysseus_routing_input" in prompt_names

    async def test_prompt_returns_messages(self):
        """Prompt returns a non-empty list of messages."""
        from odysseus.mcp import odysseus_routing_input

        messages = await odysseus_routing_input()
        assert len(messages) >= 1

    async def test_prompt_content_matches_system_prompt(self):
        """Prompt content matches the user_input_system.md file."""
        from odysseus.mcp import odysseus_routing_input

        messages = await odysseus_routing_input()
        expected = _load_text("odysseus/agents/prompts/user_input_system.md")
        assert messages[0].content.text == expected


class TestInputAgentResources:
    """Tests for the input agent MCP resources."""

    async def test_clarification_skill_registered(self):
        """Clarification skill resource is listed."""
        resources = await mcp.list_resources()
        uris = [str(r.uri) for r in resources]
        assert "odysseus://agents/input/clarification-skill" in uris

    async def test_defaults_registered(self):
        """Defaults resource is listed."""
        resources = await mcp.list_resources()
        uris = [str(r.uri) for r in resources]
        assert "odysseus://agents/input/defaults" in uris

    async def test_clarification_skill_returns_content(self):
        """Clarification skill resource returns non-empty content."""
        from odysseus.mcp import input_clarification_skill

        content = await input_clarification_skill()
        assert len(content) > 0
        assert "Clarification" in content

    async def test_defaults_returns_content(self):
        """Defaults resource returns non-empty content."""
        from odysseus.mcp import input_defaults

        content = await input_defaults()
        assert len(content) > 0
        assert "Default" in content


class TestSubmitInputReport:
    """Tests for the submit_input_report stub tool."""

    async def test_tool_registered(self):
        """submit_input_report is listed as an MCP tool."""
        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]
        assert "submit_input_report" in tool_names

    async def test_stub_returns_confirmation(self):
        """Stub returns a confirmation message."""
        from odysseus.mcp import submit_input_report

        result = await submit_input_report(
            report="# Validated Input Report\n**Status:** proceed",
            dataset_path="/data/routing.jsonl",
            problem_description="Route support queries to tiers.",
        )
        assert "received" in result.lower()

    async def test_empty_report_raises_tool_error(self):
        """Empty report raises ToolError."""
        from odysseus.mcp import submit_input_report

        with pytest.raises(ToolError, match="report is empty"):
            await submit_input_report(
                report="",
                dataset_path="/data/routing.jsonl",
                problem_description="Route queries.",
            )

    async def test_empty_dataset_path_raises_tool_error(self):
        """Empty dataset_path raises ToolError."""
        from odysseus.mcp import submit_input_report

        with pytest.raises(ToolError, match="dataset_path is empty"):
            await submit_input_report(
                report="# Report",
                dataset_path="",
                problem_description="Route queries.",
            )

    async def test_empty_problem_description_raises_tool_error(self):
        """Empty problem_description raises ToolError."""
        from odysseus.mcp import submit_input_report

        with pytest.raises(ToolError, match="problem_description is empty"):
            await submit_input_report(
                report="# Report",
                dataset_path="/data/routing.jsonl",
                problem_description="",
            )


class TestLoadText:
    """Tests for the _load_text file loader helper."""

    def test_loads_existing_file(self):
        """_load_text returns content of an existing file."""
        content = _load_text("odysseus/agents/prompts/user_input_system.md")
        assert len(content) > 0
        assert "User Input" in content

    def test_missing_file_raises_file_not_found(self):
        """_load_text raises FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError, match="not found"):
            _load_text("nonexistent/file.md")

    def test_project_root_points_to_repo(self):
        """_PROJECT_ROOT resolves to the directory containing pyproject.toml."""
        assert (_PROJECT_ROOT / "pyproject.toml").is_file()
