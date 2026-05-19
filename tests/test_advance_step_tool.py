"""Tests for advance_step MCP tool on the beam leaf branch."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.agents.prompt_builder.search_ops import (
    _BRANCH_ALGORITHM,
    init_search_state,
    record_eval_result,
    register_candidate,
)


@pytest.mark.skipif(
    _BRANCH_ALGORITHM == "__unset__",
    reason="leaf-branch advance_step behavior is not available on pipeline",
)
async def test_advance_step_returns_round_summary_for_beam(tmp_path) -> None:
    """advance_step returns a JSON RoundSummary dict after processing beam candidates."""
    from odysseus.mcp.prompt_building_tools import advance_step

    run_id = "beam_advance_test"
    outputs_dir = tmp_path / "outputs"

    # Patch get_project_dir at every import site so all default-dir calls
    # (search_ops, paths, dispatch) resolve to the same tmp tree.
    with (
        patch("odysseus.agents.prompt_builder.search_ops.get_project_dir", return_value=tmp_path),
        patch("odysseus.agents.pipeline.paths.get_project_dir", return_value=tmp_path),
        patch("odysseus.agents.pipeline.dispatch.get_project_dir", return_value=tmp_path),
    ):
        init_search_state(backend="anthropic", run_id=run_id, output_dir=outputs_dir)

        register_candidate(run_id, "v1", parent_version=None, output_dir=outputs_dir)
        record_eval_result(run_id, "v1", quality_score=0.9, cost=0.1, output_dir=outputs_dir)

        register_candidate(run_id, "v2", parent_version=None, output_dir=outputs_dir)
        record_eval_result(run_id, "v2", quality_score=0.75, cost=0.25, output_dir=outputs_dir)

        register_candidate(run_id, "v3", parent_version=None, output_dir=outputs_dir)
        record_eval_result(run_id, "v3", quality_score=0.6, cost=0.4, output_dir=outputs_dir)

        result = await advance_step(run_id=run_id)

    data = json.loads(result)
    assert isinstance(data, dict), "advance_step must return a JSON object"
    assert "round" in data, f"RoundSummary must include 'round'; got keys: {list(data)}"
    assert data["round"] >= 1


async def test_advance_step_raises_tool_error_for_missing_run(tmp_path) -> None:
    """advance_step raises ToolError when the run_id has no initialised state."""
    from odysseus.mcp.prompt_building_tools import advance_step

    with (
        patch("odysseus.project_dir.get_project_dir", return_value=tmp_path),
        pytest.raises(ToolError),
    ):
        await advance_step(run_id="nonexistent-run")
