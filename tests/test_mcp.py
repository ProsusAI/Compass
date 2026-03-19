"""Smoke tests for the MCP server."""

from unittest.mock import patch

from odysseus.mcp import _build_run_config, mcp


async def test_server_has_tools():
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "optimize_routing_prompt" in tool_names


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


def test_run_eval_does_not_construct_holdout_config():
    """run_eval's hardcoded split must be 'dev', never 'holdout'.

    This is the spec's 'internal misuse' guard (Section 2): verify that
    only run_holdout_eval constructs a holdout RunConfig.
    """
    import ast
    import inspect

    from odysseus.mcp import run_eval

    source = inspect.getsource(run_eval)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "data_split":
            assert isinstance(node.value, ast.Constant)
            assert node.value.value == "dev", "run_eval must hardcode data_split='dev'"


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
