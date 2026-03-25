"""Smoke tests for Prompt Builder MCP tools."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from odysseus.mcp import (
    advance_round_tool,
    filter_holdout_dataset_tool,
    get_search_state_tool,
    init_search_state_tool,
    record_eval_result_tool,
    register_candidate_tool,
)


class TestSearchStateTools:
    async def test_init_returns_valid_json(self, tmp_path: Path) -> None:
        with patch("odysseus.agents.prompt_builder_search_ops._DEFAULT_OUTPUT_DIR", tmp_path):
            result = await init_search_state_tool(backend="test")
            data = json.loads(result)
            assert "search_state_id" in data
            assert data["backend"] == "test"

    async def test_init_sets_defaults(self, tmp_path: Path) -> None:
        with patch("odysseus.agents.prompt_builder_search_ops._DEFAULT_OUTPUT_DIR", tmp_path):
            result = await init_search_state_tool(backend="anthropic")
            data = json.loads(result)
            assert data["max_rounds"] == 50
            assert data["stagnation_limit"] == 3
            assert data["convergence_limit"] == 5
            assert data["round"] == 0
            assert data["converged"] is False

    async def test_full_round_lifecycle(self, tmp_path: Path) -> None:
        with patch("odysseus.agents.prompt_builder_search_ops._DEFAULT_OUTPUT_DIR", tmp_path):
            # Init → Register → Record → Advance → Get
            init_result = json.loads(await init_search_state_tool(backend="test"))
            sid = init_result["search_state_id"]

            await register_candidate_tool(sid, "v1")
            await record_eval_result_tool(sid, "v1", 0.85, 0.12)

            adv = json.loads(await advance_round_tool(sid))
            assert adv["round"] == 1
            assert adv["new_pareto_points"] == 1

            state = json.loads(await get_search_state_tool(sid))
            assert state["round"] == 1

    async def test_register_candidate_returns_confirmation(self, tmp_path: Path) -> None:
        with patch("odysseus.agents.prompt_builder_search_ops._DEFAULT_OUTPUT_DIR", tmp_path):
            init_result = json.loads(await init_search_state_tool(backend="test"))
            sid = init_result["search_state_id"]

            reg = json.loads(await register_candidate_tool(sid, "v1"))
            assert reg["registered"] == "v1"

    async def test_register_duplicate_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with patch("odysseus.agents.prompt_builder_search_ops._DEFAULT_OUTPUT_DIR", tmp_path):
            init_result = json.loads(await init_search_state_tool(backend="test"))
            sid = init_result["search_state_id"]

            await register_candidate_tool(sid, "v1")
            with pytest.raises(ToolError):
                await register_candidate_tool(sid, "v1")

    async def test_record_eval_result_returns_scores(self, tmp_path: Path) -> None:
        with patch("odysseus.agents.prompt_builder_search_ops._DEFAULT_OUTPUT_DIR", tmp_path):
            init_result = json.loads(await init_search_state_tool(backend="test"))
            sid = init_result["search_state_id"]

            await register_candidate_tool(sid, "v1")
            result = json.loads(await record_eval_result_tool(sid, "v1", 0.9, 0.05))
            assert result["prompt_version"] == "v1"
            assert result["quality_score"] == pytest.approx(0.9)
            assert result["cost"] == pytest.approx(0.05)

    async def test_record_eval_unknown_version_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with patch("odysseus.agents.prompt_builder_search_ops._DEFAULT_OUTPUT_DIR", tmp_path):
            init_result = json.loads(await init_search_state_tool(backend="test"))
            sid = init_result["search_state_id"]

            with pytest.raises(ToolError):
                await record_eval_result_tool(sid, "nonexistent", 0.5, 0.1)

    async def test_advance_round_no_pending_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with patch("odysseus.agents.prompt_builder_search_ops._DEFAULT_OUTPUT_DIR", tmp_path):
            init_result = json.loads(await init_search_state_tool(backend="test"))
            sid = init_result["search_state_id"]

            with pytest.raises(ToolError):
                await advance_round_tool(sid)

    async def test_get_search_state_unknown_id_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with patch("odysseus.agents.prompt_builder_search_ops._DEFAULT_OUTPUT_DIR", tmp_path), pytest.raises(ToolError):
            await get_search_state_tool("nonexistent-id")

    async def test_multiple_rounds_stagnation(self, tmp_path: Path) -> None:
        """Two rounds with same-quality candidates accumulates stagnation."""
        with patch("odysseus.agents.prompt_builder_search_ops._DEFAULT_OUTPUT_DIR", tmp_path):
            init_result = json.loads(await init_search_state_tool(backend="test", stagnation_limit=2))
            sid = init_result["search_state_id"]

            # Round 1: new candidate improves front
            await register_candidate_tool(sid, "v1")
            await record_eval_result_tool(sid, "v1", 0.8, 0.1)
            r1 = json.loads(await advance_round_tool(sid))
            assert r1["new_pareto_points"] == 1
            assert r1["stagnation_count"] == 0

            # Round 2: dominated candidate — no improvement
            await register_candidate_tool(sid, "v2")
            await record_eval_result_tool(sid, "v2", 0.5, 0.5)
            r2 = json.loads(await advance_round_tool(sid))
            assert r2["new_pareto_points"] == 0
            assert r2["stagnation_count"] == 1


class TestFilterHoldoutTool:
    async def test_filters_examples(self, tmp_path: Path) -> None:
        holdout = tmp_path / "holdout.jsonl"
        holdout.write_text(
            '{"id":"ex1","input":"q1","expected":{"route":"a","routes":{"a":{"cost":0.01,"quality_score":0.9}}},"split":"holdout"}\n'
            '{"id":"ex2","input":"q2","expected":{"route":"b","routes":{"b":{"cost":0.02,"quality_score":0.8}}},"split":"holdout"}\n'
        )
        result = json.loads(await filter_holdout_dataset_tool(str(holdout), ["ex1"]))
        assert "filtered_holdout_path" in result

        filtered = Path(result["filtered_holdout_path"])
        lines = filtered.read_text().strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["id"] == "ex2"

    async def test_missing_file_raises_tool_error(self) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with pytest.raises(ToolError):
            await filter_holdout_dataset_tool("/nonexistent.jsonl", [])

    async def test_empty_exclude_list_keeps_all_rows(self, tmp_path: Path) -> None:
        holdout = tmp_path / "holdout.jsonl"
        holdout.write_text(
            '{"id":"ex1","input":"q1","expected":{"route":"a","routes":{"a":{"cost":0.01,"quality_score":0.9}}},"split":"holdout"}\n'
            '{"id":"ex2","input":"q2","expected":{"route":"b","routes":{"b":{"cost":0.02,"quality_score":0.8}}},"split":"holdout"}\n'
        )
        result = json.loads(await filter_holdout_dataset_tool(str(holdout), []))
        filtered = Path(result["filtered_holdout_path"])
        lines = filtered.read_text().strip().splitlines()
        assert len(lines) == 2

    async def test_exclude_all_rows_produces_empty_file(self, tmp_path: Path) -> None:
        holdout = tmp_path / "holdout.jsonl"
        holdout.write_text(
            '{"id":"ex1","input":"q1","expected":{"route":"a","routes":{"a":{"cost":0.01,"quality_score":0.9}}},"split":"holdout"}\n'
        )
        result = json.loads(await filter_holdout_dataset_tool(str(holdout), ["ex1"]))
        filtered = Path(result["filtered_holdout_path"])
        content = filtered.read_text().strip()
        assert content == ""

    async def test_output_filename_has_filtered_suffix(self, tmp_path: Path) -> None:
        holdout = tmp_path / "holdout.jsonl"
        holdout.write_text(
            '{"id":"ex1","input":"q1","expected":{"route":"a","routes":{"a":{"cost":0.01,"quality_score":0.9}}},"split":"holdout"}\n'
        )
        result = json.loads(await filter_holdout_dataset_tool(str(holdout), []))
        assert "holdout_filtered" in result["filtered_holdout_path"]
