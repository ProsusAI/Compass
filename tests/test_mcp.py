"""Smoke tests for the MCP server."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from compass.agents.prompt_builder.search import Candidate, SearchState
from compass.eval.models import RunSummary, ScoreReport
from compass.mcp import _PROJECT_ROOT, _load_text, mcp, model_specific_conventions

RESOLVE_PROJECT_DIR = "compass.project_dir.resolve_project_dir"
FINAL_REPORT_RESOLVE_PROJECT_DIR = "compass.mcp.final_report_tools._project_dir_mod.resolve_project_dir"
FINAL_REPORT_GET_SEARCH_STATE = "compass.mcp.final_report_tools.get_search_state"
FINAL_REPORT_GET_CANDIDATE_EXAMPLE_IDS = "compass.mcp.final_report_tools.get_candidate_example_ids"
FINAL_REPORT_BUILD_PIPELINE_CONFIG = "compass.mcp.final_report_tools.build_pipeline_config"
FINAL_REPORT_RUN_EVAL = "compass.mcp.final_report_tools.run_eval"
FINAL_REPORT_BACKEND_REGISTRY = "compass.mcp.final_report_tools.BackendRegistry"


async def test_server_has_tools():
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "optimize_routing_prompt" in tool_names


async def test_run_holdout_eval_registered():
    """run_holdout_eval must be registered as an MCP tool."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "run_holdout_eval" in tool_names


async def test_run_batch_eval_tool_registered():
    """run_batch_eval must be registered as an MCP tool."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "run_batch_eval" in tool_names


async def test_run_holdout_eval_tool_registered():
    """run_holdout_eval must be registered as an MCP tool."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "run_holdout_eval" in tool_names


async def test_optimize_routing_prompt_has_no_user_params():
    """optimize_routing_prompt must expose no user-facing parameters."""
    tools = await mcp.list_tools()
    tool = next(t for t in tools if t.name == "optimize_routing_prompt")
    schema_properties = tool.inputSchema.get("properties", {})
    assert schema_properties == {}, f"optimize_routing_prompt must have no parameters, got: {list(schema_properties)}"


def _make_stub_score_report(
    *,
    report_path: str = "outputs/report.json",
    results_path: str = "outputs/results.jsonl",
) -> ScoreReport:
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
        report_path=report_path,
        results_path=results_path,
    )


def _setup_run_holdout_eval_guard(tmp_path: Path, run_id: str = "run-123") -> None:
    analysis = tmp_path / "outputs" / run_id / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    (analysis / "holdout.jsonl").write_text(
        json.dumps(
            {
                "id": "hold-1",
                "expected": {
                    "route": "haiku",
                    "routes": {
                        "haiku": {"cost": 0.1, "quality_score": 0.9},
                        "sonnet": {"cost": 0.4, "quality_score": 0.95},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    search_dir = tmp_path / "outputs" / run_id / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    (search_dir / "search_state.json").write_text("{}", encoding="utf-8")
    listed_path = tmp_path / "outputs" / run_id / "pareto_candidates_listed.json"
    listed_path.parent.mkdir(parents=True, exist_ok=True)
    listed_path.write_text(json.dumps({"candidates": ["v1"]}), encoding="utf-8")


def _search_state_for_holdout_eval(*, backend: str) -> SearchState:
    return SearchState(
        search_state_id="run-123",
        backend=backend,
        round=1,
        elite_set=[
            Candidate(
                prompt_version="v1",
                parent_version=None,
                quality_score=0.95,
                cost=0.1,
                round_introduced=1,
            )
        ],
        round_history=[],
    )


class TestRunHoldoutEval:
    async def test_backend_setup_preflight_is_unchanged(self, tmp_path: Path) -> None:
        _setup_run_holdout_eval_guard(tmp_path)
        mock_registry = SimpleNamespace(list_profiles=lambda: ["anthropic", "openai"])

        with (
            patch(FINAL_REPORT_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            patch(FINAL_REPORT_GET_SEARCH_STATE, return_value=_search_state_for_holdout_eval(backend="")),
            patch(FINAL_REPORT_BACKEND_REGISTRY) as mock_backend_registry,
        ):
            mock_backend_registry.from_directory.return_value = mock_registry

            from compass.mcp import run_holdout_eval

            result = await run_holdout_eval(ctx=None, run_id="run-123", prompt_versions=["v1"])

        parsed = json.loads(result)
        assert parsed == {
            "action_required": "backend_setup",
            "run_id": "run-123",
            "available_backends": ["anthropic", "openai"],
        }

    async def test_success_returns_artifact_manifest(self, tmp_path: Path) -> None:
        _setup_run_holdout_eval_guard(tmp_path)
        holdout_eval_dir = tmp_path / "outputs" / "run-123" / "holdout_eval" / "v1"
        holdout_eval_dir.mkdir(parents=True, exist_ok=True)
        report_path = holdout_eval_dir / "report.json"
        report_path.write_text(json.dumps({"metrics": {"accuracy": 0.95}}), encoding="utf-8")
        results_path = holdout_eval_dir / "results.jsonl"
        results_path.write_text(
            "\n".join(
                [
                    json.dumps({"__meta__": "run_fingerprint", "prompt_version": "v1"}),
                    json.dumps({"example_id": "hold-1", "output": {"route": "haiku"}, "error": None}),
                ]
            ),
            encoding="utf-8",
        )
        run_config = SimpleNamespace(
            backend="anthropic",
            output=SimpleNamespace(
                report_path=str(report_path),
                results_path=str(results_path),
            ),
        )
        score_report = _make_stub_score_report(
            report_path=str(report_path),
            results_path=str(results_path),
        )

        with (
            patch(FINAL_REPORT_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            patch(FINAL_REPORT_GET_SEARCH_STATE, return_value=_search_state_for_holdout_eval(backend="anthropic")),
            patch(FINAL_REPORT_GET_CANDIDATE_EXAMPLE_IDS, return_value=[]),
            patch(FINAL_REPORT_BUILD_PIPELINE_CONFIG, return_value=run_config),
            patch(FINAL_REPORT_RUN_EVAL, new_callable=AsyncMock, return_value={ScoreReport.CONTEXT_KEY: score_report}),
        ):
            from compass.mcp import run_holdout_eval

            result = await run_holdout_eval(ctx=None, run_id="run-123", prompt_versions=["v1"])

        parsed = json.loads(result)
        assert parsed["next_step"] == "build_final_report_briefing"
        assert len(parsed["evaluations"]) == 1

        evaluation = parsed["evaluations"][0]
        assert evaluation["prompt_version"] == "v1"
        assert evaluation["report_path"] == str(report_path)
        assert evaluation["results_path"] == str(results_path)
        assert evaluation["baseline_comparison_path"] == str(holdout_eval_dir / "baseline_comparison.json")
        assert Path(evaluation["baseline_comparison_path"]).is_file()

        assert "metrics" not in evaluation
        assert "summary" not in evaluation
        assert "confidence_intervals" not in evaluation
        assert "holdout_filtered" not in evaluation
        assert "excluded_example_ids" not in evaluation


class TestBuildFinalReportBriefingTool:
    async def test_requires_versioned_holdout_reports(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "outputs" / "run-123"
        run_dir.mkdir(parents=True, exist_ok=True)

        with patch(FINAL_REPORT_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            from compass.mcp import build_final_report_briefing

            with pytest.raises(ToolError, match="No versioned holdout reports found"):
                await build_final_report_briefing(ctx=None, run_id="run-123")


class TestStagPromptBodies:
    """Tests for _STAGE_PROMPT_BODIES pre-loaded stage prompt bodies."""

    def test_stage_1_body_loaded(self):
        """Stage 1 prompt body is pre-loaded and non-empty."""
        from compass.mcp.prompts import _STAGE_PROMPT_BODIES

        assert 1 in _STAGE_PROMPT_BODIES
        assert len(_STAGE_PROMPT_BODIES[1]) > 0

    def test_stage_1_body_matches_file(self):
        """Stage 1 body matches user_input_system.md content."""
        from compass.mcp.prompts import _STAGE_PROMPT_BODIES

        expected = _load_text("compass/agents/prompts/user_input_system.md")
        assert _STAGE_PROMPT_BODIES[1] == expected

    def test_all_stage_keys_present(self):
        """All expected stage keys are pre-loaded."""
        from compass.mcp.prompts import _STAGE_PROMPT_BODIES

        for key in [1, 2, 3, 5, "compass_prompt_builder", "compass_prompt_builder_rerun"]:
            assert key in _STAGE_PROMPT_BODIES, f"Missing key: {key}"
            assert len(_STAGE_PROMPT_BODIES[key]) > 0, f"Empty body for key: {key}"

    def test_routing_input_prompt_not_registered_as_mcp_prompt(self):
        """compass_routing_input is no longer registered as an MCP @mcp.prompt()."""
        prompt_names = [p.name for p in mcp._prompt_manager.list_prompts()]
        assert "compass_routing_input" not in prompt_names


class TestInputAgentResources:
    """Tests for the input agent MCP resources."""

    async def test_clarification_skill_registered(self):
        """Clarification skill resource is listed."""
        resources = await mcp.list_resources()
        uris = [str(r.uri) for r in resources]
        assert "compass://agents/input/clarification-skill" in uris

    async def test_defaults_registered(self):
        """Defaults resource is listed."""
        resources = await mcp.list_resources()
        uris = [str(r.uri) for r in resources]
        assert "compass://agents/input/defaults" in uris

    async def test_clarification_skill_returns_content(self):
        """Clarification skill resource returns non-empty content."""
        from compass.mcp import input_clarification_skill

        content = await input_clarification_skill()
        assert len(content) > 0
        assert "Clarification" in content

    async def test_defaults_returns_content(self):
        """Defaults resource returns non-empty content."""
        from compass.mcp import input_defaults

        content = await input_defaults()
        assert len(content) > 0
        assert "Default" in content

    async def test_final_report_template_registered(self):
        """Final report template resource is listed."""
        resources = await mcp.list_resources()
        uris = [str(r.uri) for r in resources]
        assert "compass://agents/final-report/template" in uris

    async def test_final_report_template_returns_content(self):
        """Final report template resource returns non-empty content."""
        from compass.mcp import final_report_template

        content = await final_report_template()
        assert len(content) > 0
        assert "Executive Summary" in content


class TestSubmitInputReport:
    """Tests for the submit_input_report stub tool."""

    async def test_tool_registered(self):
        """submit_input_report is listed as an MCP tool."""
        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]
        assert "submit_input_report" in tool_names

    async def test_stub_returns_confirmation(self, tmp_path: Path):
        """Returns JSON with run_id, report_path, and dataset_path."""
        from compass.mcp import submit_input_report

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
        from compass.mcp import submit_input_report

        with pytest.raises(ToolError, match="report is empty"):
            await submit_input_report(
                ctx=None,
                report="",
                dataset_path="/data/routing.jsonl",
                problem_description="Route queries.",
            )

    async def test_empty_dataset_path_raises_tool_error(self):
        """Empty dataset_path raises ToolError."""
        from compass.mcp import submit_input_report

        with pytest.raises(ToolError, match="dataset_path is empty"):
            await submit_input_report(
                ctx=None,
                report="# Report",
                dataset_path="",
                problem_description="Route queries.",
            )

    async def test_empty_problem_description_raises_tool_error(self):
        """Empty problem_description raises ToolError."""
        from compass.mcp import submit_input_report

        with pytest.raises(ToolError, match="problem_description is empty"):
            await submit_input_report(
                ctx=None,
                report="# Report",
                dataset_path="/data/routing.jsonl",
                problem_description="",
            )


def test_build_review_briefing_registered() -> None:
    """Verify build_review_briefing is a registered MCP tool."""
    from compass.mcp import mcp

    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    assert "build_review_briefing" in tool_names


def test_record_directive_outcomes_registered() -> None:
    """Verify record_directive_outcomes is a registered MCP tool."""
    from compass.mcp import mcp

    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    assert "record_directive_outcomes" in tool_names


def test_get_edit_directives_registered() -> None:
    """Verify get_edit_directives is a registered MCP tool."""
    from compass.mcp import mcp

    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    assert "get_edit_directives" in tool_names


def test_review_agent_iterative_prompt_registered() -> None:
    """Verify compass_review_agent_iterative is a registered MCP prompt."""
    from compass.mcp import mcp

    prompt_names = [p.name for p in mcp._prompt_manager.list_prompts()]
    assert "compass_review_agent_iterative" in prompt_names


def test_review_agent_cold_start_prompt_registered() -> None:
    """Verify compass_review_agent_cold_start is a registered MCP prompt."""
    from compass.mcp import mcp

    prompt_names = [p.name for p in mcp._prompt_manager.list_prompts()]
    assert "compass_review_agent_cold_start" in prompt_names


def test_review_agent_old_prompt_not_registered() -> None:
    """Verify the retired compass_review_agent prompt is no longer registered."""
    from compass.mcp import mcp

    prompt_names = [p.name for p in mcp._prompt_manager.list_prompts()]
    assert "compass_review_agent" not in prompt_names


class TestLoadText:
    """Tests for the _load_text file loader helper."""

    def test_loads_existing_file(self):
        """_load_text returns content of an existing file."""
        content = _load_text("compass/agents/prompts/user_input_system.md")
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
        with patch("compass.mcp.server._PROJECT_ROOT", tmp_path):
            agents_dir = tmp_path / "compass" / "agents"
            agents_dir.mkdir(parents=True)
            (agents_dir / "prompt_builder").mkdir()
            (agents_dir / "prompt_builder" / "conventions_openai_gpt-5-2.md").write_text(
                "# GPT-5.2 Addendum\nTest content."
            )
            result = await model_specific_conventions("openai", "gpt-5.2")
            assert "GPT-5.2 Addendum" in result

    async def test_returns_empty_string_when_file_missing(self, tmp_path: Path) -> None:
        """Missing model cookbook returns empty string, not an error."""
        agents_dir = tmp_path / "compass" / "agents"
        agents_dir.mkdir(parents=True)
        with patch("compass.mcp.server._PROJECT_ROOT", tmp_path):
            result = await model_specific_conventions("openai", "gpt-99")
            assert result == ""

    async def test_normalizes_dated_model_string(self, tmp_path: Path) -> None:
        """Date suffixes like -2025-03-11 are stripped before lookup."""
        agents_dir = tmp_path / "compass" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "prompt_builder").mkdir()
        (agents_dir / "prompt_builder" / "conventions_openai_gpt-5-2.md").write_text("content")
        with patch("compass.mcp.server._PROJECT_ROOT", tmp_path):
            result = await model_specific_conventions("openai", "gpt-5.2-2025-03-11")
            assert result == "content"

    async def test_normalizes_compact_dated_model_string(self, tmp_path: Path) -> None:
        """Compact date suffixes like -20250311 are stripped before lookup."""
        agents_dir = tmp_path / "compass" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "prompt_builder").mkdir()
        (agents_dir / "prompt_builder" / "conventions_openai_gpt-5-2.md").write_text("content")
        with patch("compass.mcp.server._PROJECT_ROOT", tmp_path):
            result = await model_specific_conventions("openai", "gpt-5.2-20250311")
            assert result == "content"

    async def test_dots_replaced_with_dashes_in_filename(self, tmp_path: Path) -> None:
        """Model string dots become dashes in filename lookup."""
        agents_dir = tmp_path / "compass" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "prompt_builder").mkdir()
        (agents_dir / "prompt_builder" / "conventions_claude_claude-sonnet-4-6.md").write_text("sonnet content")
        with patch("compass.mcp.server._PROJECT_ROOT", tmp_path):
            result = await model_specific_conventions("claude", "claude-sonnet-4.6")
            assert result == "sonnet content"

    async def test_passthrough_for_unrecognized_format(self, tmp_path: Path) -> None:
        """Unrecognized model strings pass through and miss gracefully."""
        agents_dir = tmp_path / "compass" / "agents"
        agents_dir.mkdir(parents=True)
        with patch("compass.mcp.server._PROJECT_ROOT", tmp_path):
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
        """get_pipeline_status returns a JSON checklist with subagent_instruction."""
        from compass.mcp import get_pipeline_status

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = await get_pipeline_status(ctx=None)
        data = json.loads(result)
        assert "current_stage" in data
        assert "subagent_instruction" in data
        assert "DISPATCH_REQUIRED" not in data

    async def test_returns_checklist_with_run_id(self, tmp_path: Path):
        """get_pipeline_status with a run_id returns its status."""
        from compass.mcp import get_pipeline_status

        # Create a run
        input_dir = tmp_path / "outputs" / "abc123" / "input"
        input_dir.mkdir(parents=True)
        (input_dir / "input_report.md").write_text("# Report")

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = await get_pipeline_status(ctx=None, run_id="abc123")
        data = json.loads(result)
        assert data["run_id"] == "abc123"
        assert data["current_stage"] >= 2

    async def test_get_pipeline_status_stage1_no_prompt_body_in_subagent_instruction(self, tmp_path: Path):
        """get_pipeline_status no longer embeds the stage system prompt in subagent_instruction.

        The dispatch checklist is returned but the prompt body (which was previously substituted
        into <stage_system_prompt></stage_system_prompt>) is now only available via start_stage's
        sub_agent_prompt field.
        """
        from compass.mcp import get_pipeline_status

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = await get_pipeline_status(ctx=None, run_id=None)
        data = json.loads(result)
        instr = data.get("subagent_instruction", "")
        # The dispatch checklist must still be present
        assert "<HARD_STOP>" in instr
        # The prompt body placeholder must NOT appear — it was removed from templates
        assert "<stage_system_prompt></stage_system_prompt>" not in instr
        # And the filled-in tags must not appear either — prompt body is not injected here
        assert "<stage_system_prompt>" not in instr

    async def test_get_pipeline_status_stage2_no_prompt_body_in_subagent_instruction(self, tmp_path: Path):
        """get_pipeline_status does not embed stage 2 system prompt in subagent_instruction."""
        from compass.mcp import get_pipeline_status

        # Create a stage-1-complete run (has input_report.md)
        input_dir = tmp_path / "outputs" / "stage2run" / "input"
        input_dir.mkdir(parents=True)
        (input_dir / "input_report.md").write_text("# Report")

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = await get_pipeline_status(ctx=None, run_id="stage2run")
        data = json.loads(result)
        assert data["current_stage"] == 2
        instr = data.get("subagent_instruction", "")
        assert "<HARD_STOP>" in instr
        assert "<stage_system_prompt></stage_system_prompt>" not in instr
        assert "<stage_system_prompt>" not in instr

    async def test_get_pipeline_status_unknown_stage_not_enriched(self, tmp_path: Path):
        """get_pipeline_status does not enrich subagent_instruction for unknown stages."""
        import compass.mcp.orchestrator_tools as orch_mod
        from compass.mcp import get_pipeline_status

        stage7_result = {
            "run_id": "test-run",
            "stages": [],
            "current_stage": 99,
            "current_stage_name": "Unknown",
            "next_action": "Pipeline complete.",
            "available_tools": [],
            "subagent_instruction": None,
        }
        with (
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            patch.object(orch_mod, "_get_pipeline_status", return_value=stage7_result),
        ):
            result = await get_pipeline_status(ctx=None, run_id=None)
        data = json.loads(result)
        assert data["subagent_instruction"] is None

    async def test_start_stage_review_missing_prompt_raises_tool_error(self, tmp_path: Path):
        """start_stage raises ToolError when the review agent prompt assembly fails (FileNotFoundError).

        Stage prompts for non-review stages are pre-loaded at import time; review prompts are
        assembled on demand via assemble_review_prompt and can still raise FileNotFoundError.
        """
        from unittest.mock import AsyncMock as _AsyncMock
        from unittest.mock import MagicMock

        import compass.mcp.orchestrator_tools as orch_mod
        from compass.mcp.orchestrator_tools import start_stage
        from compass.mcp.server import set_active_stage

        # Simulate a review stage being the next action
        review_status = {
            "run_id": "run1",
            "stages": [],
            "current_stage": 4,
            "current_stage_name": "Refinement Loop",
            "next_action": "review",
            "available_tools": [],
            "activate_prompt": "compass_review_agent_iterative",
            "algorithm": "hill_climb",
            "subagent_instruction": None,
        }

        mock_ctx = MagicMock()
        mock_ctx.session = MagicMock()
        mock_ctx.session.send_tool_list_changed = _AsyncMock()

        set_active_stage("orchestrator")
        with (
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            patch.object(orch_mod, "_get_pipeline_status", return_value=review_status),
            patch("compass.mcp.prompts.assemble_review_prompt", side_effect=FileNotFoundError("prompt not found")),
            pytest.raises(ToolError, match="installation may be broken"),
        ):
            await start_stage(ctx=mock_ctx, run_id="run1")


class TestOptimizeRoutingPrompt:
    """Tests for the optimize_routing_prompt MCP tool."""

    async def test_tool_registered(self):
        """optimize_routing_prompt is listed as an MCP tool."""
        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]
        assert "optimize_routing_prompt" in tool_names

    async def test_returns_activation_package(self, tmp_path: Path):
        """Returns a string with all three XML sections."""
        from compass.mcp import optimize_routing_prompt

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
        from compass.mcp import optimize_routing_prompt

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
        from compass.mcp import optimize_routing_prompt

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = await optimize_routing_prompt(ctx=None)

        start = result.index("<system_prompt>") + len("<system_prompt>")
        end = result.index("</system_prompt>")
        system_prompt = result[start:end].strip()
        assert "User Input agent" in system_prompt or "pipeline's entry gate" in system_prompt

    async def test_missing_system_prompt_raises_tool_error(self, tmp_path: Path):
        """FileNotFoundError from _load_text is surfaced as ToolError with installation message."""
        from compass.mcp import optimize_routing_prompt

        with (
            patch("compass.mcp.orchestrator_tools._load_text", side_effect=FileNotFoundError("no such file")),
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            pytest.raises(ToolError, match="installation may be broken"),
        ):
            await optimize_routing_prompt(ctx=None)

    async def test_pipeline_status_error_raises_tool_error(self, tmp_path: Path):
        """OSError from _get_pipeline_status is surfaced as ToolError with outputs_dir in message."""
        from compass.mcp import optimize_routing_prompt

        with (
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            patch(
                "compass.mcp.orchestrator_tools._get_pipeline_status",
                side_effect=OSError("disk read error"),
            ),
            pytest.raises(ToolError, match="outputs"),
        ):
            await optimize_routing_prompt(ctx=None)


class TestGuardRejection:
    """Tests that guards reject tools when prerequisites are missing."""

    async def test_validate_dataset_rejects_without_input_report(self, tmp_path: Path):
        from compass.mcp import validate_dataset

        with (
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            pytest.raises(ToolError, match="Pipeline precondition not met"),
        ):
            await validate_dataset(ctx=None, dataset_path="/some/path.jsonl", run_id="no_such_run")

    async def test_stratified_split_importable_from_data_validation_tools(self):
        """stratified_split must be importable from data_validation_tools."""
        from compass.mcp.data_validation_tools import stratified_split

        assert callable(stratified_split)


class TestSubmitInputReportPersistence:
    """Tests for run_id generation and artifact persistence."""

    async def test_returns_run_id(self, tmp_path: Path) -> None:
        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            from compass.mcp import submit_input_report

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
            from compass.mcp import submit_input_report

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
            from compass.mcp import submit_input_report

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
            from compass.mcp import submit_input_report

            result = await submit_input_report(
                ctx=None,
                report="# Report\n**Status:** proceed",
                dataset_path="/data/test.jsonl",
                problem_description="Route queries",
                bootstrap_from_run_id="no_such_run",
            )
        data = json.loads(result)
        assert "run_id" in data  # no error


class TestRoutingAnalysisRemoved:
    """Tests verifying routing analysis stage is removed from MCP registrations."""

    def test_routing_analysis_not_in_stage_registry(self):
        """STAGE_REGISTRY must not contain a 'routing_analysis' entry."""
        from compass.mcp import STAGE_REGISTRY

        assert "routing_analysis" not in STAGE_REGISTRY

    def test_stratified_split_in_data_validation_stage(self):
        """stratified_split must appear in the 'data_validation' stage."""
        from compass.mcp import STAGE_REGISTRY

        assert "stratified_split" in STAGE_REGISTRY["data_validation"]

    def test_compass_routing_analysis_prompt_not_registered(self):
        """compass_routing_analysis prompt must not be registered."""
        from compass.mcp import mcp

        prompt_names = [p.name for p in mcp._prompt_manager.list_prompts()]
        assert "compass_routing_analysis" not in prompt_names

    def test_routing_analysis_skill_resources_not_registered(self):
        """Routing analysis skill resources must not be registered."""
        from compass.mcp import mcp

        resource_uris = [str(r.uri) for r in mcp._resource_manager.list_resources()]
        assert "compass://agents/routing-analysis/classify-example-skill" not in resource_uris
        assert "compass://agents/routing-analysis/generate-rationale-skill" not in resource_uris
        assert "compass://agents/routing-analysis/check-overlap-skill" not in resource_uris
