"""Smoke tests for the MCP server."""

from odysseus.mcp import mcp


async def test_server_has_tools():
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "optimize_routing_prompt" in tool_names


from odysseus.mcp import _build_run_config


def test_build_run_config_dev_split():
    """_build_run_config with split='dev' sets data_split='dev'."""
    config = _build_run_config(
        prompt_version="v1",
        data_source="data/test.jsonl",
        data_split="dev",
    )
    assert config.data_split == "dev"
    assert config.prompt_version == "v1"
    assert config.data_source == "data/test.jsonl"


def test_build_run_config_holdout_split():
    """_build_run_config with split='holdout' sets data_split='holdout'."""
    config = _build_run_config(
        prompt_version="v1",
        data_source="data/test.jsonl",
        data_split="holdout",
    )
    assert config.data_split == "holdout"
