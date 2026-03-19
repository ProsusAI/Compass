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


from unittest.mock import patch


async def test_run_eval_hardcodes_dev_split():
    """run_eval must always construct RunConfig with data_split='dev'."""
    with patch("odysseus.mcp._build_run_config") as mock_build:
        mock_build.return_value = _build_run_config("v1", "data/test.jsonl", "dev")
        # Import the tool function and call it directly
        from odysseus.mcp import run_eval

        await run_eval(prompt_version="v1", data_source="data/test.jsonl")
        mock_build.assert_called_once_with(
            prompt_version="v1",
            data_source="data/test.jsonl",
            data_split="dev",
        )


async def test_run_holdout_eval_hardcodes_holdout_split():
    """run_holdout_eval must always construct RunConfig with data_split='holdout'."""
    with patch("odysseus.mcp._build_run_config") as mock_build:
        mock_build.return_value = _build_run_config("v1", "data/test.jsonl", "holdout")
        from odysseus.mcp import run_holdout_eval

        await run_holdout_eval(prompt_version="v1", data_source="data/test.jsonl")
        mock_build.assert_called_once_with(
            prompt_version="v1",
            data_source="data/test.jsonl",
            data_split="holdout",
        )
