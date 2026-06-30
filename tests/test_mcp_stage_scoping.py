# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Tests for MCP session-scoped tool filtering."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

from compass.mcp.server import STAGE_REGISTRY, mcp, set_active_stage

_RESOLVE_PROJECT_DIR = "compass.project_dir.resolve_project_dir"
_DEPRECATED_REVIEW_TOOLS = {"get_directive_history", "get_batch_outcomes"}


@pytest.fixture()
def mock_ctx() -> Context:
    """Create a mock Context with a session that accepts send_tool_list_changed."""
    ctx = MagicMock(spec=Context)
    ctx.session = MagicMock()
    ctx.session.send_tool_list_changed = AsyncMock()
    return ctx


# ---------------------------------------------------------------------------
# Stage registry structure tests
# ---------------------------------------------------------------------------


def test_stage_registry_has_all_stages():
    """All stage scopes are defined."""
    expected = {
        "orchestrator",
        "input_report",
        "data_validation",
        "backend_setup",
        "prompt_building",
        "review_cold",
        "review",
        "calibration",
        "final_report",
    }
    assert set(STAGE_REGISTRY) == expected


def test_calibration_excludes_prompt_and_dataset_row_tools():
    """calibration toolbelt must not include prompt text or dataset row query tools."""
    calibration_tools = set(STAGE_REGISTRY["calibration"])
    assert "get_prompt_text" not in calibration_tools
    assert "query_dev_examples" not in calibration_tools
    assert "query_holdout_examples" not in calibration_tools


def test_calibration_includes_builder_tools():
    """calibration toolbelt must include prompt-building tools for K-seed scoring."""
    calibration_tools = set(STAGE_REGISTRY["calibration"])
    expected_builder_tools = {
        "init_search_state",
        "register_candidate",
        "run_batch_eval",
        "record_eval_result",
        "advance_step",
        "save_prompt",
        "get_edit_directives",
        "signal_eval_complete",
    }
    assert expected_builder_tools.issubset(calibration_tools), (
        f"calibration stage missing builder tools: {expected_builder_tools - calibration_tools}"
    )


async def test_calibration_stage_filtering():
    """set_active_stage('calibration') excludes prompt text and dataset row query tools."""
    set_active_stage("calibration")
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "get_prompt_text" not in tool_names
    assert "query_dev_examples" not in tool_names
    assert "query_holdout_examples" not in tool_names
    # Builder tools must be included
    assert "run_batch_eval" in tool_names
    assert "advance_step" in tool_names


def test_review_cold_includes_dev_queries_but_excludes_prompt_and_holdout_tools():
    """review_cold can query dev rows, but still cannot inspect prompts or holdout rows."""
    cold_tools = set(STAGE_REGISTRY["review_cold"])
    assert "query_dev_examples" in cold_tools
    assert "query_eval_results" in cold_tools
    assert "get_prompt_text" not in cold_tools
    assert "query_holdout_examples" not in cold_tools
    assert _DEPRECATED_REVIEW_TOOLS.isdisjoint(cold_tools)


def test_review_steady_includes_prompt_and_dataset_row_tools():
    """Steady review toolbelt must include prompt text plus both dataset row query tools."""
    review_tools = set(STAGE_REGISTRY["review"])
    assert "get_prompt_text" in review_tools
    assert "query_dev_examples" in review_tools
    assert "query_holdout_examples" in review_tools
    assert "query_eval_results" in review_tools
    assert _DEPRECATED_REVIEW_TOOLS.isdisjoint(review_tools)


def test_every_stage_includes_get_pipeline_status():
    """Every stage includes get_pipeline_status."""
    for stage, tools in STAGE_REGISTRY.items():
        assert "get_pipeline_status" in tools, f"Stage '{stage}' missing get_pipeline_status"


def test_orchestrator_stage_has_only_expected_tools():
    """Orchestrator stage has exactly the expected lifecycle and rerun tools."""
    expected = {
        "optimize_routing_prompt",
        "get_pipeline_status",
        "start_stage",
        "complete_stage",
        "initiate_rerun",
    }
    assert set(STAGE_REGISTRY["orchestrator"]) == expected


def test_no_stage_specific_tools_in_orchestrator():
    """Stage-specific tools like submit_input_report and run_batch_eval are NOT in orchestrator."""
    orchestrator_tools = set(STAGE_REGISTRY["orchestrator"])
    stage_only_tools = {
        "submit_input_report",
        "run_batch_eval",
        "detect_and_parse_dataset",
        "get_default_pricing",
        "init_search_state",
        "build_review_briefing",
        "run_holdout_eval",
    }
    assert orchestrator_tools.isdisjoint(stage_only_tools)


async def test_all_registered_tools_appear_in_at_least_one_stage():
    """Every tool registered with the MCP server appears in at least one stage."""
    # Disable filtering to get all tools
    set_active_stage(None)
    all_tools = await mcp.list_tools()
    all_tool_names = {t.name for t in all_tools}

    all_stage_tools: set[str] = set()
    for tools in STAGE_REGISTRY.values():
        all_stage_tools.update(tools)

    missing = all_tool_names - all_stage_tools
    assert missing == _DEPRECATED_REVIEW_TOOLS, f"Unexpected tools not in any stage: {missing}"


# ---------------------------------------------------------------------------
# Tool filtering tests
# ---------------------------------------------------------------------------


async def test_filtering_returns_stage_tools_plus_lifecycle():
    """When a stage is active, list_tools returns stage tools plus lifecycle tools."""
    set_active_stage("input_report")
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert tool_names == {"submit_input_report", "get_pipeline_status", "start_stage", "complete_stage"}


async def test_filtering_disabled_returns_all_tools():
    """When active stage is None, all tools are returned."""
    set_active_stage(None)
    all_tools = await mcp.list_tools()

    set_active_stage("orchestrator")
    filtered = await mcp.list_tools()

    assert len(all_tools) > len(filtered)


async def test_orchestrator_stage_filtering():
    """Orchestrator stage returns exactly its expected tools."""
    set_active_stage("orchestrator")
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert tool_names == {
        "optimize_routing_prompt",
        "get_pipeline_status",
        "start_stage",
        "complete_stage",
        "initiate_rerun",
    }


async def test_prompt_building_stage_filtering():
    """Prompt building stage returns its tools plus lifecycle tools."""
    set_active_stage("prompt_building")
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    expected = set(STAGE_REGISTRY["prompt_building"]) | {"start_stage", "complete_stage"}
    assert tool_names == expected


# ---------------------------------------------------------------------------
# start_stage / complete_stage tool tests
# ---------------------------------------------------------------------------


async def test_start_stage_sets_active_stage(mock_ctx, tmp_path: Path):
    """start_stage infers the next stage from artifacts and returns JSON with scope and tools."""
    import json

    from compass.mcp.server import get_active_stage

    # Set up stage 1 complete so the server infers stage 2 (data_validation).
    input_dir = tmp_path / "outputs" / "test-run" / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "input_report.md").write_text("# Report")

    set_active_stage("orchestrator")
    from compass.mcp.orchestrator_tools import start_stage

    with patch(_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
        result = await start_stage(ctx=mock_ctx, run_id="test-run")
    assert get_active_stage() == "data_validation"
    data = json.loads(result)
    assert data["scope"] == "data_validation"
    assert "detect_and_parse_dataset" in data["tools"]
    assert "sub_agent_prompt" in data
    assert data["run_id"] == "test-run"


async def test_start_stage_sends_tool_list_changed(mock_ctx, tmp_path: Path):
    """start_stage sends a tool list changed notification."""
    from compass.mcp.orchestrator_tools import start_stage

    # Set up stage 1 complete so the server infers stage 2 (data_validation).
    input_dir = tmp_path / "outputs" / "test-run" / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "input_report.md").write_text("# Report")

    set_active_stage("orchestrator")
    with patch(_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
        await start_stage(ctx=mock_ctx, run_id="test-run")
    mock_ctx.session.send_tool_list_changed.assert_awaited_once()


async def test_start_stage_rejects_from_non_orchestrator_scope(mock_ctx, tmp_path: Path):
    """start_stage raises ToolError when called from a stage scope."""
    from compass.mcp.orchestrator_tools import start_stage

    set_active_stage("input_report")
    with (
        patch(_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
        pytest.raises(ToolError, match="only be called from orchestrator scope"),
    ):
        await start_stage(ctx=mock_ctx, run_id="test-run")


async def test_start_stage_allows_entry_without_run_id(mock_ctx, tmp_path: Path):
    """start_stage dispatches to input_report when called without a run_id (no existing runs)."""
    import json

    from compass.mcp.orchestrator_tools import start_stage
    from compass.mcp.server import get_active_stage

    # Empty outputs dir — no runs yet, should land on stage 1.
    (tmp_path / "outputs").mkdir(parents=True)

    set_active_stage("orchestrator")
    with patch(_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
        result = await start_stage(ctx=mock_ctx)
    assert get_active_stage() == "input_report"
    data = json.loads(result)
    assert data["scope"] == "input_report"
    assert "submit_input_report" in data["tools"]
    assert data["run_id"] is None


async def test_start_stage_requires_run_id_when_pipeline_past_stage1(mock_ctx, tmp_path: Path):
    """start_stage raises ToolError when run_id is missing but pipeline is past stage 1."""
    from compass.mcp.orchestrator_tools import start_stage

    # Set up a run at stage 2 (stage 1 complete).
    input_dir = tmp_path / "outputs" / "some-run" / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "input_report.md").write_text("# Report")

    set_active_stage("orchestrator")
    # Passing run_id=None while a run exists that is at stage 2 — server picks up
    # the most recent run (some-run) which is at stage 2, so it should raise.
    with (
        patch(_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
        pytest.raises(ToolError, match="run_id is required"),
    ):
        await start_stage(ctx=mock_ctx)


async def test_complete_stage_rejects_from_orchestrator_scope(mock_ctx):
    """complete_stage raises ToolError when already in orchestrator scope."""
    from compass.mcp.orchestrator_tools import complete_stage

    set_active_stage("orchestrator")
    with pytest.raises(ToolError, match="only be called from within a stage scope"):
        await complete_stage(ctx=mock_ctx, run_id="test-run")


async def test_complete_stage_resets_to_orchestrator(mock_ctx, tmp_path):
    """complete_stage returns to orchestrator scope.

    The review fanout guard requires child_variants.json to exist.  We create
    it in a temp dir and patch the dispatch module so the guard passes.
    """
    from compass.mcp.orchestrator_tools import complete_stage
    from compass.mcp.server import get_active_stage

    search_dir = tmp_path / "outputs" / "test-run" / "search"
    search_dir.mkdir(parents=True)
    (search_dir / "child_variants.json").write_text("[]")

    # Directly activate review scope — we're testing complete_stage, not start_stage.
    set_active_stage("review")
    assert get_active_stage() == "review"

    with patch("compass.agents.pipeline.paths.get_project_dir", return_value=tmp_path):
        result = await complete_stage(ctx=mock_ctx, run_id="test-run")
    assert get_active_stage() == "orchestrator"
    assert "review" in result
    assert "orchestrator" in result


async def test_complete_stage_sends_tool_list_changed(mock_ctx, tmp_path):
    """complete_stage sends a tool list changed notification.

    The review fanout guard requires child_variants.json.  We satisfy it via
    a temp dir and a patch on the dispatch module.
    """
    from compass.mcp.orchestrator_tools import complete_stage

    search_dir = tmp_path / "outputs" / "test-run" / "search"
    search_dir.mkdir(parents=True)
    (search_dir / "child_variants.json").write_text("[]")

    # Directly activate review scope — we're testing complete_stage, not start_stage.
    set_active_stage("review")
    with patch("compass.agents.pipeline.paths.get_project_dir", return_value=tmp_path):
        await complete_stage(ctx=mock_ctx, run_id="test-run")
    mock_ctx.session.send_tool_list_changed.assert_awaited_once()


# ---------------------------------------------------------------------------
# Regression: stage system prompt split between get_pipeline_status / start_stage
# ---------------------------------------------------------------------------


async def test_get_pipeline_status_subagent_instruction_has_no_stage_prompt_body(tmp_path: Path):
    """Regression: get_pipeline_status must not embed stage system prompt in subagent_instruction.

    The prompt body was previously substituted into a <stage_system_prompt></stage_system_prompt>
    placeholder. After the fix the placeholder is gone from templates and the prompt body is
    only returned by start_stage's sub_agent_prompt field.
    """
    import json

    from compass.mcp import get_pipeline_status

    # Stage 2: has input_report.md so current_stage == 2
    input_dir = tmp_path / "outputs" / "r1" / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "input_report.md").write_text("# Report")

    # First heading of the data_validation_system.md — invariant substring
    dv_prompt_sentinel = "You are the Data Validation agent"

    with patch(_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
        result = await get_pipeline_status(ctx=None, run_id="r1")
    data = json.loads(result)
    instr = data.get("subagent_instruction", "")
    # The data_validation system prompt should NOT appear verbatim in subagent_instruction
    assert dv_prompt_sentinel not in instr, (
        "Stage system prompt body must not be embedded in subagent_instruction; "
        "it should only be in start_stage's sub_agent_prompt field."
    )


async def test_start_stage_sub_agent_prompt_contains_data_validation_prompt(mock_ctx, tmp_path: Path):
    """start_stage(run_id=...) infers data_validation and returns sub_agent_prompt from the prompt file.

    The sub_agent_prompt field must contain the stage system prompt body so the orchestrator
    can forward it verbatim to the sub-agent.
    """
    import json

    from compass.mcp.orchestrator_tools import start_stage

    # Set up a run at stage 2 (stage 1 complete)
    input_dir = tmp_path / "outputs" / "r1" / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "input_report.md").write_text("# Report")

    set_active_stage("orchestrator")
    with patch(_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
        result = await start_stage(ctx=mock_ctx, run_id="r1")

    data = json.loads(result)
    assert "sub_agent_prompt" in data
    sub_prompt = data["sub_agent_prompt"]
    assert sub_prompt is not None
    # The data_validation system prompt starts with "You are the Data Validation agent"
    assert "You are the Data Validation agent" in sub_prompt, (
        "start_stage sub_agent_prompt must contain the data_validation system prompt body"
    )
