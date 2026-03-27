"""Smoke tests for the MCP server."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.eval.models import RunSummary, ScoreReport
from odysseus.mcp import _PROJECT_ROOT, _load_text, mcp, model_specific_conventions

AGENT_RUN = "odysseus.agents.eval_runner.EvalRunnerAgent.run"
RESOLVE_PROJECT_DIR = "odysseus.mcp.resolve_project_dir"


async def test_server_has_tools():
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "optimize_routing_prompt" in tool_names


async def test_run_holdout_eval_is_stub(tmp_path: Path):
    """run_holdout_eval is still a stub (out of THP-129 scope)."""
    from odysseus.mcp import run_holdout_eval

    # Set up guard artifact
    search_dir = tmp_path / "outputs" / "test_run" / "search"
    search_dir.mkdir(parents=True)
    (search_dir / "search_state.json").write_text("{}")

    with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
        result = await run_holdout_eval(ctx=None, prompt_version="v1", data_source="data/test.jsonl", run_id="test_run")
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


async def test_optimize_routing_prompt_has_no_user_params():
    """optimize_routing_prompt must expose no user-facing parameters."""
    tools = await mcp.list_tools()
    tool = next(t for t in tools if t.name == "optimize_routing_prompt")
    schema_properties = tool.inputSchema.get("properties", {})
    assert schema_properties == {}, (
        f"optimize_routing_prompt must have no parameters, got: {list(schema_properties)}"
    )


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
        """Successful run returns JSON with report_path, results_path, metrics, and summary."""
        score_report = _make_stub_score_report()

        with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run, patch(
            RESOLVE_PROJECT_DIR, new_callable=AsyncMock
        ):
            mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

            from odysseus.mcp import run_eval

            result = await run_eval(
                ctx=None,
                prompt_version="v1",
                data_source="data/test.jsonl",
                backend="test-backend",
            )

        parsed = json.loads(result)
        assert parsed["report_path"] == "outputs/report.json"
        assert parsed["results_path"] == "outputs/results.jsonl"
        assert parsed["metrics"] == {"accuracy": 0.95}
        assert parsed["summary"]["total_cost"] == 0.01

    async def test_agent_receives_correct_context(self):
        """MCP tool passes all parameters to agent context."""
        score_report = _make_stub_score_report()

        with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run, patch(
            RESOLVE_PROJECT_DIR, new_callable=AsyncMock
        ):
            mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

            from odysseus.mcp import run_eval

            await run_eval(
                ctx=None,
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
        with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run, patch(
            RESOLVE_PROJECT_DIR, new_callable=AsyncMock
        ):
            mock_run.return_value = {"error": {"category": "not_found", "detail": "config missing"}}

            from odysseus.mcp import run_eval

            with pytest.raises(ToolError, match="not_found"):
                await run_eval(
                    ctx=None,
                    prompt_version="v1",
                    data_source="data/test.jsonl",
                    backend="test-backend",
                )

    async def test_validation_error_raises_tool_error(self):
        """Agent validation error is translated to ToolError."""
        with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run, patch(
            RESOLVE_PROJECT_DIR, new_callable=AsyncMock
        ):
            mock_run.return_value = {"error": {"category": "validation_error", "detail": "bad config"}}

            from odysseus.mcp import run_eval

            with pytest.raises(ToolError, match="validation_error"):
                await run_eval(
                    ctx=None,
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

    async def test_stub_returns_confirmation(self, tmp_path: Path):
        """Returns JSON with run_id, report_path, and dataset_path."""
        from odysseus.mcp import submit_input_report

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = await submit_input_report(
                ctx=None,
                report="# Validated Input Report\n**Status:** proceed",
                dataset_path="/data/routing.jsonl",
                problem_description="Route support queries to tiers.",
            )
        data = json.loads(result)
        assert "run_id" in data
        assert "report_path" in data
        assert data["dataset_path"] == "/data/routing.jsonl"

    async def test_empty_report_raises_tool_error(self):
        """Empty report raises ToolError."""
        from odysseus.mcp import submit_input_report

        with pytest.raises(ToolError, match="report is empty"):
            await submit_input_report(
                ctx=None,
                report="",
                dataset_path="/data/routing.jsonl",
                problem_description="Route queries.",
            )

    async def test_empty_dataset_path_raises_tool_error(self):
        """Empty dataset_path raises ToolError."""
        from odysseus.mcp import submit_input_report

        with pytest.raises(ToolError, match="dataset_path is empty"):
            await submit_input_report(
                ctx=None,
                report="# Report",
                dataset_path="",
                problem_description="Route queries.",
            )

    async def test_empty_problem_description_raises_tool_error(self):
        """Empty problem_description raises ToolError."""
        from odysseus.mcp import submit_input_report

        with pytest.raises(ToolError, match="problem_description is empty"):
            await submit_input_report(
                ctx=None,
                report="# Report",
                dataset_path="/data/routing.jsonl",
                problem_description="",
            )


def test_build_review_briefing_tool_registered() -> None:
    """Verify build_review_briefing_tool is a registered MCP tool."""
    from odysseus.mcp import mcp

    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    assert "build_review_briefing_tool" in tool_names


def test_record_directive_outcomes_tool_registered() -> None:
    """Verify record_directive_outcomes_tool is a registered MCP tool."""
    from odysseus.mcp import mcp

    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    assert "record_directive_outcomes_tool" in tool_names


def test_review_agent_prompt_registered() -> None:
    """Verify odysseus_review_agent is a registered MCP prompt."""
    from odysseus.mcp import mcp

    prompt_names = [p.name for p in mcp._prompt_manager.list_prompts()]
    assert "odysseus_review_agent" in prompt_names


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


class TestModelSpecificConventions:
    async def test_returns_content_when_file_exists(self, tmp_path: Path) -> None:
        """Model-specific cookbook is returned when the file exists."""
        with patch("odysseus.mcp._PROJECT_ROOT", tmp_path):
            agents_dir = tmp_path / "odysseus" / "agents"
            agents_dir.mkdir(parents=True)
            (agents_dir / "prompt_builder_conventions_openai_gpt-5-2.md").write_text(
                "# GPT-5.2 Addendum\nTest content."
            )
            result = await model_specific_conventions("openai", "gpt-5.2")
            assert "GPT-5.2 Addendum" in result

    async def test_returns_empty_string_when_file_missing(self, tmp_path: Path) -> None:
        """Missing model cookbook returns empty string, not an error."""
        agents_dir = tmp_path / "odysseus" / "agents"
        agents_dir.mkdir(parents=True)
        with patch("odysseus.mcp._PROJECT_ROOT", tmp_path):
            result = await model_specific_conventions("openai", "gpt-99")
            assert result == ""

    async def test_normalizes_dated_model_string(self, tmp_path: Path) -> None:
        """Date suffixes like -2025-03-11 are stripped before lookup."""
        agents_dir = tmp_path / "odysseus" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "prompt_builder_conventions_openai_gpt-5-2.md").write_text("content")
        with patch("odysseus.mcp._PROJECT_ROOT", tmp_path):
            result = await model_specific_conventions("openai", "gpt-5.2-2025-03-11")
            assert result == "content"

    async def test_normalizes_compact_dated_model_string(self, tmp_path: Path) -> None:
        """Compact date suffixes like -20250311 are stripped before lookup."""
        agents_dir = tmp_path / "odysseus" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "prompt_builder_conventions_openai_gpt-5-2.md").write_text("content")
        with patch("odysseus.mcp._PROJECT_ROOT", tmp_path):
            result = await model_specific_conventions("openai", "gpt-5.2-20250311")
            assert result == "content"

    async def test_dots_replaced_with_dashes_in_filename(self, tmp_path: Path) -> None:
        """Model string dots become dashes in filename lookup."""
        agents_dir = tmp_path / "odysseus" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "prompt_builder_conventions_claude_claude-sonnet-4-6.md").write_text("sonnet content")
        with patch("odysseus.mcp._PROJECT_ROOT", tmp_path):
            result = await model_specific_conventions("claude", "claude-sonnet-4.6")
            assert result == "sonnet content"

    async def test_passthrough_for_unrecognized_format(self, tmp_path: Path) -> None:
        """Unrecognized model strings pass through and miss gracefully."""
        agents_dir = tmp_path / "odysseus" / "agents"
        agents_dir.mkdir(parents=True)
        with patch("odysseus.mcp._PROJECT_ROOT", tmp_path):
            result = await model_specific_conventions("openai", "gpt-5.2-turbo-preview")
            assert result == ""


class TestGetPipelineStatus:
    """Tests for the get_pipeline_status MCP tool."""

    async def test_tool_registered(self):
        """get_pipeline_status is listed as an MCP tool."""
        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]
        assert "get_pipeline_status" in tool_names

    async def test_returns_checklist(self, tmp_path: Path):
        """get_pipeline_status returns a JSON checklist."""
        from odysseus.mcp import get_pipeline_status

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = await get_pipeline_status(ctx=None)
        data = json.loads(result)
        assert "current_stage" in data
        assert "next_action" in data

    async def test_returns_checklist_with_run_id(self, tmp_path: Path):
        """get_pipeline_status with a run_id returns its status."""
        from odysseus.mcp import get_pipeline_status

        # Create a run
        input_dir = tmp_path / "outputs" / "abc123" / "input"
        input_dir.mkdir(parents=True)
        (input_dir / "input_report.md").write_text("# Report")

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = await get_pipeline_status(ctx=None, run_id="abc123")
        data = json.loads(result)
        assert data["run_id"] == "abc123"
        assert data["current_stage"] >= 2


class TestOptimizeRoutingPrompt:
    """Tests for the optimize_routing_prompt MCP tool."""

    async def test_tool_registered(self):
        """optimize_routing_prompt is listed as an MCP tool."""
        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]
        assert "optimize_routing_prompt" in tool_names

    async def test_returns_activation_package(self, tmp_path: Path):
        """Returns a string with all three XML sections."""
        from odysseus.mcp import optimize_routing_prompt

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = await optimize_routing_prompt(ctx=None)

        assert "<pipeline_status>" in result
        assert "</pipeline_status>" in result
        assert "<instructions>" in result
        assert "</instructions>" in result
        assert "<system_prompt>" in result
        assert "</system_prompt>" in result

    async def test_pipeline_status_is_valid_json(self, tmp_path: Path):
        """The content inside <pipeline_status> is valid JSON."""
        from odysseus.mcp import optimize_routing_prompt

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = await optimize_routing_prompt(ctx=None)

        start = result.index("<pipeline_status>") + len("<pipeline_status>")
        end = result.index("</pipeline_status>")
        status_json = result[start:end].strip()
        data = json.loads(status_json)
        assert "current_stage" in data
        assert "next_action" in data

    async def test_system_prompt_contains_agent_content(self, tmp_path: Path):
        """The <system_prompt> section contains the User Input Agent content."""
        from odysseus.mcp import optimize_routing_prompt

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = await optimize_routing_prompt(ctx=None)

        start = result.index("<system_prompt>") + len("<system_prompt>")
        end = result.index("</system_prompt>")
        system_prompt = result[start:end].strip()
        assert "User Input agent" in system_prompt or "pipeline's entry gate" in system_prompt

    async def test_missing_system_prompt_raises_tool_error(self, tmp_path: Path):
        """FileNotFoundError from _load_text is surfaced as ToolError with installation message."""
        from odysseus.mcp import optimize_routing_prompt

        with (
            patch("odysseus.mcp._load_text", side_effect=FileNotFoundError("no such file")),
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            pytest.raises(ToolError, match="installation may be broken"),
        ):
            await optimize_routing_prompt(ctx=None)

    async def test_pipeline_status_error_raises_tool_error(self, tmp_path: Path):
        """OSError from _get_pipeline_status is surfaced as ToolError with outputs_dir in message."""
        from odysseus.mcp import optimize_routing_prompt

        with (
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            patch(
                "odysseus.mcp._get_pipeline_status",
                side_effect=OSError("disk read error"),
            ),
            pytest.raises(ToolError, match="outputs"),
        ):
            await optimize_routing_prompt(ctx=None)


class TestGuardRejection:
    """Tests that guards reject tools when prerequisites are missing."""

    async def test_validate_dataset_rejects_without_input_report(self, tmp_path: Path):
        from odysseus.mcp import validate_dataset

        with (
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            pytest.raises(ToolError, match="Pipeline precondition not met"),
        ):
            await validate_dataset(ctx=None, dataset_path="/some/path.jsonl", run_id="no_such_run")

    async def test_create_seed_registry_rejects_without_validation(self, tmp_path: Path):
        from odysseus.mcp import create_seed_registry_tool

        # Create input report but no validation artifacts
        input_dir = tmp_path / "outputs" / "test_run" / "input"
        input_dir.mkdir(parents=True)
        (input_dir / "input_report.md").write_text("# Report")

        with (
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            pytest.raises(ToolError, match="Pipeline precondition not met"),
        ):
            await create_seed_registry_tool(ctx=None, run_id="test_run")


class TestSubmitInputReportPersistence:
    """Tests for run_id generation and artifact persistence."""

    async def test_returns_run_id(self, tmp_path: Path) -> None:
        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            from odysseus.mcp import submit_input_report

            result = await submit_input_report(
                ctx=None,
                report="# Validated Input Report\n**Status:** proceed",
                dataset_path="/data/test.jsonl",
                problem_description="Route queries to models",
            )
        data = json.loads(result)
        assert "run_id" in data
        assert len(data["run_id"]) == 8

    async def test_persists_report_to_disk(self, tmp_path: Path) -> None:
        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            from odysseus.mcp import submit_input_report

            result = await submit_input_report(
                ctx=None,
                report="# Validated Input Report\n**Status:** proceed",
                dataset_path="/data/test.jsonl",
                problem_description="Route queries to models",
            )
        data = json.loads(result)
        report_path = tmp_path / "outputs" / data["run_id"] / "input" / "input_report.md"
        assert report_path.is_file()
        assert "Validated Input Report" in report_path.read_text()

    async def test_bootstrap_copies_latest_prompt(self, tmp_path: Path) -> None:
        old_prompts = tmp_path / "outputs" / "old_run" / "prompts"
        old_prompts.mkdir(parents=True)
        (old_prompts / "v1.txt").write_text("prompt v1")
        (old_prompts / "v2.txt").write_text("prompt v2")
        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            from odysseus.mcp import submit_input_report

            result = await submit_input_report(
                ctx=None,
                report="# Report\n**Status:** proceed",
                dataset_path="/data/test.jsonl",
                problem_description="Route queries",
                bootstrap_from_run_id="old_run",
            )
        data = json.loads(result)
        bootstrap = tmp_path / "outputs" / data["run_id"] / "prompts" / "bootstrap.txt"
        assert bootstrap.is_file()
        assert bootstrap.read_text() == "prompt v2"

    async def test_bootstrap_nonexistent_run_is_noop(self, tmp_path: Path) -> None:
        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            from odysseus.mcp import submit_input_report

            result = await submit_input_report(
                ctx=None,
                report="# Report\n**Status:** proceed",
                dataset_path="/data/test.jsonl",
                problem_description="Route queries",
                bootstrap_from_run_id="no_such_run",
            )
        data = json.loads(result)
        assert "run_id" in data  # no error
