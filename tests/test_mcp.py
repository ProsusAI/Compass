"""Smoke tests for the MCP server."""

from odysseus.mcp import mcp


async def test_server_has_tools():
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "optimize_routing_prompt" in tool_names


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
