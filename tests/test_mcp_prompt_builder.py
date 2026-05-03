"""Smoke tests for Prompt Builder MCP tools."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from odysseus.mcp import (
    filter_holdout_dataset_tool,
    get_child_variants_tool,
    get_edit_directives_tool,
    get_search_state_tool,
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
    async def test_get_search_state_unknown_id_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with _patch_project_dir(tmp_path), pytest.raises(ToolError):
            await get_search_state_tool("nonexistent-id")


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


class TestEditDirectivesPersistence:
    @pytest.mark.asyncio
    async def test_get_edit_directives_tool(self, tmp_path: Path) -> None:
        from odysseus.agents.review.models import ChildVariant, EditDirective
        from odysseus.agents.review.ops import save_child_variants

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            variant = ChildVariant(
                hypothesis="Test hypothesis",
                directives=[
                    EditDirective(
                        directive_id="d1",
                        target_version="v1",
                        block_type="rule",
                        block_identifier="Rule 1",
                        granularity="micro",
                        directive="Tighten wording",
                        priority="medium",
                    ),
                ],
            )
            save_child_variants(_RUN_ID, [variant], output_dir=tmp_path / "outputs")

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

    @pytest.mark.asyncio
    async def test_get_edit_directives_tool_flattens_multiple_variants(self, tmp_path: Path) -> None:
        """get_edit_directives_tool must flatten directives across all child variants in file order."""
        from odysseus.agents.review.models import ChildVariant, EditDirective
        from odysseus.agents.review.ops import save_child_variants

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            variant_a = ChildVariant(
                hypothesis="First variant",
                directives=[
                    EditDirective(
                        directive_id="d1",
                        target_version="v1",
                        block_type="rule",
                        block_identifier="Rule 1",
                        granularity="micro",
                        directive="Edit A",
                        priority="high",
                    ),
                ],
            )
            variant_b = ChildVariant(
                hypothesis="Second variant",
                directives=[
                    EditDirective(
                        directive_id="d2",
                        target_version="v1",
                        block_type="example",
                        block_identifier="Example 1",
                        granularity="macro",
                        directive="Edit B",
                        priority="medium",
                    ),
                    EditDirective(
                        directive_id="d3",
                        target_version="v1",
                        block_type="rule",
                        block_identifier="Rule 2",
                        granularity="micro",
                        directive="Edit C",
                        priority="low",
                    ),
                ],
            )
            save_child_variants(_RUN_ID, [variant_a, variant_b], output_dir=tmp_path / "outputs")

            result = await get_edit_directives_tool(
                ctx=None,
                run_id=_RUN_ID,
                output_dir=str(tmp_path / "outputs"),
            )
            data = json.loads(result)
            assert len(data) == 3
            assert [d["directive_id"] for d in data] == ["d1", "d2", "d3"]

    @pytest.mark.asyncio
    async def test_get_child_variants_tool(self, tmp_path: Path) -> None:
        from odysseus.agents.review.models import ChildVariant, EditDirective
        from odysseus.agents.review.ops import save_child_variants

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            variant = ChildVariant(
                hypothesis="Add a clearer boundary example",
                directives=[
                    EditDirective(
                        directive_id="d1",
                        target_version="v1",
                        block_type="example",
                        block_identifier="Example 1",
                        granularity="macro",
                        directive="Add example",
                        priority="high",
                    ),
                ],
            )
            save_child_variants(_RUN_ID, [variant], output_dir=tmp_path / "outputs")

            result = await get_child_variants_tool(
                ctx=None,
                run_id=_RUN_ID,
                output_dir=str(tmp_path / "outputs"),
            )
            data = json.loads(result)
            assert len(data) == 1
            assert data[0]["hypothesis"] == "Add a clearer boundary example"
            assert len(data[0]["directives"]) == 1
            assert data[0]["directives"][0]["directive_id"] == "d1"


class TestTrajectoryChildVariantsFallback:
    """Tests for child variant source-resolution (trajectory-based on leaf branches)."""

    @pytest.mark.asyncio
    async def test_get_child_variants_falls_back_to_single_slot(self, tmp_path: Path) -> None:
        """When no per-trajectory files exist, get_child_variants_tool returns single-slot variants."""
        from odysseus.agents.review.models import ChildVariant, EditDirective
        from odysseus.agents.review.ops import save_child_variants

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            variant = ChildVariant(
                hypothesis="Single-slot variant",
                directives=[
                    EditDirective(
                        directive_id="single_d1",
                        target_version="v1",
                        block_type="example",
                        block_identifier="Example 1",
                        granularity="macro",
                        directive="Edit",
                        priority="medium",
                    ),
                ],
            )
            save_child_variants(_RUN_ID, [variant], output_dir=tmp_path / "outputs")

            result = await get_child_variants_tool(
                ctx=None,
                run_id=_RUN_ID,
                output_dir=str(tmp_path / "outputs"),
            )
            data = json.loads(result)
            assert len(data) == 1
            assert data[0]["hypothesis"] == "Single-slot variant"
            assert data[0]["directives"][0]["directive_id"] == "single_d1"
