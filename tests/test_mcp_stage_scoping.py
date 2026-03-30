"""Tests for MCP session-scoped tool filtering."""

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.mcp.server import STAGE_REGISTRY, mcp, set_active_stage

# ---------------------------------------------------------------------------
# Stage registry structure tests
# ---------------------------------------------------------------------------


def test_stage_registry_has_all_stages():
    """All 8 stages are defined."""
    expected = {
        "orchestrator",
        "input_report",
        "data_validation",
        "routing_analysis",
        "backend_setup",
        "prompt_building",
        "review",
        "holdout",
    }
    assert set(STAGE_REGISTRY) == expected


def test_every_stage_includes_get_pipeline_status():
    """Every stage includes get_pipeline_status."""
    for stage, tools in STAGE_REGISTRY.items():
        assert "get_pipeline_status" in tools, f"Stage '{stage}' missing get_pipeline_status"


def test_orchestrator_stage_has_only_4_tools():
    """Orchestrator stage has exactly: optimize_routing_prompt, get_pipeline_status, start_stage, complete_stage."""
    expected = {
        "optimize_routing_prompt",
        "get_pipeline_status",
        "start_stage",
        "complete_stage",
    }
    assert set(STAGE_REGISTRY["orchestrator"]) == expected


def test_no_stage_specific_tools_in_orchestrator():
    """Stage-specific tools like submit_input_report, run_eval etc. are NOT in orchestrator."""
    orchestrator_tools = set(STAGE_REGISTRY["orchestrator"])
    stage_only_tools = {
        "submit_input_report",
        "run_eval",
        "detect_and_parse_dataset",
        "create_seed_registry_tool",
        "get_default_pricing",
        "init_search_state_tool",
        "build_review_briefing_tool",
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
    assert not missing, f"Tools not in any stage: {missing}"


# ---------------------------------------------------------------------------
# Tool filtering tests
# ---------------------------------------------------------------------------


async def test_filtering_returns_only_stage_tools():
    """When a stage is active, list_tools returns only that stage's tools."""
    set_active_stage("input_report")
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert tool_names == {"submit_input_report", "get_pipeline_status"}


async def test_filtering_disabled_returns_all_tools():
    """When active stage is None, all tools are returned."""
    set_active_stage(None)
    all_tools = await mcp.list_tools()

    set_active_stage("orchestrator")
    filtered = await mcp.list_tools()

    assert len(all_tools) > len(filtered)


async def test_orchestrator_stage_filtering():
    """Orchestrator stage returns exactly its 4 tools."""
    set_active_stage("orchestrator")
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert tool_names == {
        "optimize_routing_prompt",
        "get_pipeline_status",
        "start_stage",
        "complete_stage",
    }


async def test_prompt_building_stage_filtering():
    """Prompt building stage returns all its tools."""
    set_active_stage("prompt_building")
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    expected = set(STAGE_REGISTRY["prompt_building"])
    assert tool_names == expected


# ---------------------------------------------------------------------------
# start_stage / complete_stage tool tests
# ---------------------------------------------------------------------------


async def test_start_stage_sets_active_stage():
    """start_stage activates the given stage."""
    from odysseus.mcp.server import get_active_stage

    set_active_stage("orchestrator")
    from odysseus.mcp.orchestrator_tools import start_stage

    result = await start_stage(run_id="test-run", stage="data_validation")
    assert get_active_stage() == "data_validation"
    assert "data_validation" in result
    assert "detect_and_parse_dataset" in result


async def test_start_stage_rejects_unknown_stage():
    """start_stage raises ToolError for an unknown stage name."""
    from odysseus.mcp.orchestrator_tools import start_stage

    with pytest.raises(ToolError, match="Unknown stage"):
        await start_stage(run_id="test-run", stage="nonexistent")


async def test_complete_stage_resets_to_orchestrator():
    """complete_stage returns to orchestrator scope."""
    from odysseus.mcp.orchestrator_tools import complete_stage, start_stage
    from odysseus.mcp.server import get_active_stage

    await start_stage(run_id="test-run", stage="review")
    assert get_active_stage() == "review"

    result = await complete_stage(run_id="test-run")
    assert get_active_stage() == "orchestrator"
    assert "review" in result
    assert "orchestrator" in result
