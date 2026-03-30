"""Tests for save_prompt_tool."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError


@pytest.fixture()
def mock_ctx(tmp_path):
    """Create a mock Context that resolves to a temp project dir."""
    ctx = MagicMock(spec=Context)
    ctx.session = MagicMock()
    ctx.session.send_tool_list_changed = AsyncMock()
    return ctx


@pytest.fixture()
def project_dir(tmp_path):
    """Create a temp project directory."""
    return tmp_path


async def test_save_prompt_writes_file(mock_ctx, project_dir):
    """save_prompt_tool writes prompt content to the correct path."""
    from odysseus.mcp.prompt_building_tools import save_prompt_tool

    run_id = "test-run"
    content = "# Routing Objective\nRoute customer queries.\n\n<example>\nInput: hello\nRoute: greeting\n</example>"

    with patch("odysseus.mcp.prompt_building_tools._project_dir_mod.resolve_project_dir", return_value=project_dir):
        result = await save_prompt_tool(ctx=mock_ctx, run_id=run_id, prompt_version="v1", content=content)

    result_data = json.loads(result)
    prompt_path = project_dir / "outputs" / run_id / "prompts" / "v1.txt"
    assert prompt_path.exists()
    assert prompt_path.read_text(encoding="utf-8") == content
    assert result_data["prompt_path"] == str(prompt_path)


async def test_save_prompt_preserves_xml_tags(mock_ctx, project_dir):
    """XML-like tags in prompt content are preserved exactly."""
    from odysseus.mcp.prompt_building_tools import save_prompt_tool

    content = (
        "<important>\nNever route ambiguous queries to billing.\n</important>\n"
        "<example>\n<input>refund</input>\n<route>billing</route>\n</example>"
    )

    with patch("odysseus.mcp.prompt_building_tools._project_dir_mod.resolve_project_dir", return_value=project_dir):
        await save_prompt_tool(ctx=mock_ctx, run_id="test-run", prompt_version="v2", content=content)

    written = (project_dir / "outputs" / "test-run" / "prompts" / "v2.txt").read_text(encoding="utf-8")
    assert written == content


async def test_save_prompt_rejects_empty_content(mock_ctx, project_dir):
    """save_prompt_tool raises ToolError for empty content."""
    from odysseus.mcp.prompt_building_tools import save_prompt_tool

    with (
        patch("odysseus.mcp.prompt_building_tools._project_dir_mod.resolve_project_dir", return_value=project_dir),
        pytest.raises(ToolError, match="content must not be empty"),
    ):
        await save_prompt_tool(ctx=mock_ctx, run_id="test-run", prompt_version="v1", content="")


async def test_save_prompt_creates_directories(mock_ctx, project_dir):
    """save_prompt_tool creates the prompts directory if it doesn't exist."""
    from odysseus.mcp.prompt_building_tools import save_prompt_tool

    with patch("odysseus.mcp.prompt_building_tools._project_dir_mod.resolve_project_dir", return_value=project_dir):
        await save_prompt_tool(ctx=mock_ctx, run_id="new-run", prompt_version="v1", content="test prompt")

    assert (project_dir / "outputs" / "new-run" / "prompts" / "v1.txt").exists()
