"""Smoke tests for Prompt Builder MCP tools."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from odysseus.mcp import (
    advance_step_tool,
    filter_holdout_dataset_tool,
    get_edit_directives_tool,
    get_search_state_tool,
    init_search_state_tool,
    record_eval_result_tool,
    register_candidate_tool,
)

_RUN_ID = "test_run"

RESOLVE_PROJECT_DIR = "odysseus.project_dir.resolve_project_dir"
_SEARCH_OPS_PATCH = "odysseus.agents.prompt_builder.search_ops.get_project_dir"


@contextmanager
def _patch_project_dir(tmp_path: Path):
    """Patch project dir resolution in all relevant modules."""
    with (
        patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
        patch(_SEARCH_OPS_PATCH, return_value=tmp_path),
    ):
        yield


def _setup_guard_artifacts(tmp_path: Path, run_id: str = _RUN_ID, stage: str = "analysis") -> None:
    """Create prerequisite artifacts so pipeline guards pass."""
    # Stage 1 prerequisite
    input_dir = tmp_path / "outputs" / run_id / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "input_report.md").write_text("# Report")

    # Stage 2 prerequisites
    val_dir = tmp_path / "outputs" / run_id / "validation"
    val_dir.mkdir(parents=True, exist_ok=True)
    (val_dir / "data_quality_report.json").write_text("{}")
    (val_dir / "routing_context.json").write_text("{}")
    (val_dir / "transformed.jsonl").write_text("")

    if stage in ("analysis", "search"):
        # Stage 3 prerequisites
        analysis_dir = tmp_path / "outputs" / run_id / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "validation_report.json").write_text("{}")
        (analysis_dir / "dev.jsonl").write_text("")
        (analysis_dir / "holdout.jsonl").write_text("")


class TestSearchStateTools:
    async def test_init_returns_valid_json(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            result = await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test")
            data = json.loads(result)
            assert "search_state_id" in data
            assert data["backend"] == "test"

    async def test_init_sets_defaults(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            result = await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="anthropic")
            data = json.loads(result)
            assert data["max_rounds"] == 50
            assert data["stagnation_limit"] == 3
            assert data["convergence_limit"] == 5
            assert data["round"] == 0
            assert data["converged"] is False

    async def test_full_round_lifecycle(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            # Init -> Register -> Record -> Advance -> Get
            init_result = json.loads(await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test"))
            assert "search_state_id" in init_result

            await register_candidate_tool(_RUN_ID, "v1")
            await record_eval_result_tool(_RUN_ID, "v1", 0.85, 0.12)

            adv = json.loads(await advance_step_tool(_RUN_ID))
            assert adv["round"] == 1
            assert adv["new_elite_entries"] == 1

            state = json.loads(await get_search_state_tool(_RUN_ID))
            assert state["round"] == 1

    async def test_register_candidate_returns_confirmation(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test")

            reg = json.loads(await register_candidate_tool(_RUN_ID, "v1"))
            assert reg["registered"] == "v1"

    async def test_register_duplicate_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test")

            await register_candidate_tool(_RUN_ID, "v1")
            with pytest.raises(ToolError):
                await register_candidate_tool(_RUN_ID, "v1")

    async def test_record_eval_result_returns_scores(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test")

            await register_candidate_tool(_RUN_ID, "v1")
            result = json.loads(await record_eval_result_tool(_RUN_ID, "v1", 0.9, 0.05))
            assert result["prompt_version"] == "v1"
            assert result["quality_score"] == pytest.approx(0.9)
            assert result["cost"] == pytest.approx(0.05)

    async def test_record_eval_unknown_version_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test")

            with pytest.raises(ToolError):
                await record_eval_result_tool(_RUN_ID, "nonexistent", 0.5, 0.1)

    async def test_advance_round_no_pending_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test")

            with pytest.raises(ToolError):
                await advance_step_tool(_RUN_ID)

    async def test_get_search_state_unknown_id_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with _patch_project_dir(tmp_path), pytest.raises(ToolError):
            await get_search_state_tool("nonexistent-id")

    async def test_multiple_rounds_stagnation(self, tmp_path: Path) -> None:
        """Two rounds with same-quality candidates accumulates stagnation."""
        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test", stagnation_limit=2)

            # Round 1: new candidate improves front
            await register_candidate_tool(_RUN_ID, "v1")
            await record_eval_result_tool(_RUN_ID, "v1", 0.8, 0.1)
            r1 = json.loads(await advance_step_tool(_RUN_ID))
            assert r1["new_elite_entries"] == 1
            assert r1["stagnation_count"] == 0

            # Round 2: dominated candidate - no improvement
            await register_candidate_tool(_RUN_ID, "v2")
            await record_eval_result_tool(_RUN_ID, "v2", 0.5, 0.5)
            r2 = json.loads(await advance_step_tool(_RUN_ID))
            assert r2["new_elite_entries"] == 0
            assert r2["stagnation_count"] == 1


class TestFilterHoldoutTool:
    async def test_filters_examples(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        holdout = tmp_path / "holdout.jsonl"
        holdout.write_text(
            '{"id":"ex1","input":"q1","expected":{"route":"a","routes":{"a":{"cost":0.01,"quality_score":0.9}}}}\n'
            '{"id":"ex2","input":"q2","expected":{"route":"b","routes":{"b":{"cost":0.02,"quality_score":0.8}}}}\n'
        )
        with _patch_project_dir(tmp_path):
            result = json.loads(
                await filter_holdout_dataset_tool(
                    ctx=None, holdout_jsonl_path=str(holdout), exclude_ids=["ex1"], run_id=_RUN_ID
                )
            )
        assert "filtered_holdout_path" in result

        filtered = Path(result["filtered_holdout_path"])
        lines = filtered.read_text().strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["id"] == "ex2"

    async def test_missing_file_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path), pytest.raises(ToolError):
            await filter_holdout_dataset_tool(
                ctx=None, holdout_jsonl_path="/nonexistent.jsonl", exclude_ids=[], run_id=_RUN_ID
            )

    async def test_empty_exclude_list_keeps_all_rows(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        holdout = tmp_path / "holdout.jsonl"
        holdout.write_text(
            '{"id":"ex1","input":"q1","expected":{"route":"a","routes":{"a":{"cost":0.01,"quality_score":0.9}}}}\n'
            '{"id":"ex2","input":"q2","expected":{"route":"b","routes":{"b":{"cost":0.02,"quality_score":0.8}}}}\n'
        )
        with _patch_project_dir(tmp_path):
            result = json.loads(
                await filter_holdout_dataset_tool(
                    ctx=None, holdout_jsonl_path=str(holdout), exclude_ids=[], run_id=_RUN_ID
                )
            )
        filtered = Path(result["filtered_holdout_path"])
        lines = filtered.read_text().strip().splitlines()
        assert len(lines) == 2

    async def test_exclude_all_rows_produces_empty_file(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        holdout = tmp_path / "holdout.jsonl"
        holdout.write_text(
            '{"id":"ex1","input":"q1","expected":{"route":"a","routes":{"a":{"cost":0.01,"quality_score":0.9}}}}\n'
        )
        with _patch_project_dir(tmp_path):
            result = json.loads(
                await filter_holdout_dataset_tool(
                    ctx=None, holdout_jsonl_path=str(holdout), exclude_ids=["ex1"], run_id=_RUN_ID
                )
            )
        filtered = Path(result["filtered_holdout_path"])
        content = filtered.read_text().strip()
        assert content == ""

    async def test_output_filename_has_filtered_suffix(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        holdout = tmp_path / "holdout.jsonl"
        holdout.write_text(
            '{"id":"ex1","input":"q1","expected":{"route":"a","routes":{"a":{"cost":0.01,"quality_score":0.9}}}}\n'
        )
        with _patch_project_dir(tmp_path):
            result = json.loads(
                await filter_holdout_dataset_tool(
                    ctx=None, holdout_jsonl_path=str(holdout), exclude_ids=[], run_id=_RUN_ID
                )
            )
        assert "holdout_filtered" in result["filtered_holdout_path"]


class TestRecordDirectiveOutcomesToolLoopPhase:
    @pytest.mark.asyncio
    async def test_transitions_loop_phase_to_build(self, tmp_path: Path) -> None:
        from odysseus.agents.prompt_builder.search_ops import get_search_state, init_search_state, set_loop_phase
        from odysseus.mcp import record_directive_outcomes_tool

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            # Init search state in review phase
            init_search_state(
                "anthropic",
                run_id=_RUN_ID,
                output_dir=tmp_path / "outputs",
            )
            set_loop_phase(_RUN_ID, "review", output_dir=tmp_path / "outputs")

            await record_directive_outcomes_tool(
                ctx=None,
                run_id=_RUN_ID,
                outcomes=[],
                output_dir=str(tmp_path / "outputs"),
            )

            state = get_search_state(run_id=_RUN_ID, output_dir=tmp_path / "outputs")
            assert state.loop_phase == "build"


class TestEditDirectivesPersistence:
    @pytest.mark.asyncio
    async def test_record_persists_edit_directives(self, tmp_path: Path) -> None:
        from odysseus.agents.prompt_builder.search_ops import init_search_state, set_loop_phase
        from odysseus.agents.review.ops import load_edit_directives
        from odysseus.mcp import record_directive_outcomes_tool

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            init_search_state("anthropic", run_id=_RUN_ID, output_dir=tmp_path / "outputs")
            set_loop_phase(_RUN_ID, "review", output_dir=tmp_path / "outputs")

            result = await record_directive_outcomes_tool(
                ctx=None,
                run_id=_RUN_ID,
                outcomes=[],
                edit_directives=[{
                    "directive_id": "d1",
                    "target_version": "v1",
                    "block_type": "example",
                    "block_identifier": "Example 1",
                    "granularity": "macro",
                    "directive": "Add example",
                    "priority": "high",
                }],
                output_dir=str(tmp_path / "outputs"),
            )

            data = json.loads(result)
            assert data["edit_directives_saved"] == 1

            loaded = load_edit_directives(_RUN_ID, output_dir=tmp_path / "outputs")
            assert len(loaded) == 1
            assert loaded[0].directive_id == "d1"

    @pytest.mark.asyncio
    async def test_get_edit_directives_tool(self, tmp_path: Path) -> None:
        from odysseus.agents.review.models import EditDirective
        from odysseus.agents.review.ops import save_edit_directives

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            directives = [
                EditDirective(
                    directive_id="d1",
                    target_version="v1",
                    block_type="rule",
                    block_identifier="Rule 1",
                    granularity="micro",
                    directive="Tighten wording",
                    priority="medium",
                ),
            ]
            save_edit_directives(_RUN_ID, directives, output_dir=tmp_path / "outputs")

            result = await get_edit_directives_tool(
                ctx=None,
                run_id=_RUN_ID,
                output_dir=str(tmp_path / "outputs"),
            )
            data = json.loads(result)
            assert len(data) == 1
            assert data[0]["directive_id"] == "d1"

    @pytest.mark.asyncio
    async def test_get_edit_directives_tool_empty(self, tmp_path: Path) -> None:
        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            result = await get_edit_directives_tool(
                ctx=None,
                run_id=_RUN_ID,
                output_dir=str(tmp_path / "outputs"),
            )
            data = json.loads(result)
            assert data == []
