"""Integration tests for the data validation MCP tool."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from compass.mcp import get_routing_context, save_routing_context, stratified_split, validate_dataset

RUN_ID = "test_run"
RESOLVE_PROJECT_DIR = "compass.project_dir.resolve_project_dir"


def _setup_guard(tmp_path: Path) -> None:
    """Create guard artifacts so validate_dataset passes preconditions."""
    d = tmp_path / "outputs" / RUN_ID / "input"
    d.mkdir(parents=True, exist_ok=True)
    (d / "input_report.md").write_text("# Report")


def _write_jsonl(rows: list[dict], path: Path) -> None:
    """Write rows as JSONL to a file."""
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _valid_row(id: str = "ex-1") -> dict:
    return {
        "id": id,
        "input": "What is quantum entanglement?",
        "expected": {
            "route": "opus",
            "routes": {
                "opus": {"cost": 0.05, "quality_score": 0.98},
                "haiku": {"cost": 0.002, "quality_score": 0.72},
            },
        },
    }


class TestValidateDataset:
    @pytest.mark.asyncio
    async def test_valid_dataset_returns_report(self, tmp_path: Path) -> None:
        _setup_guard(tmp_path)
        dataset = tmp_path / "data.jsonl"
        _write_jsonl([_valid_row("ex-1"), _valid_row("ex-2")], dataset)

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = await validate_dataset(ctx=None, dataset_path=str(dataset), run_id=RUN_ID)
        report = json.loads(result)

        assert "schema_findings" in report
        assert "label_distribution" in report
        assert "volume_assessment" in report
        assert "query_length" in report
        assert report["query_length"]["count"] == 2

    @pytest.mark.asyncio
    async def test_nonexistent_file_raises_tool_error(self, tmp_path: Path) -> None:
        _setup_guard(tmp_path)
        with (
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            pytest.raises(ToolError, match="Dataset file not found"),
        ):
            await validate_dataset(ctx=None, dataset_path="/nonexistent/path/data.jsonl", run_id=RUN_ID)

    @pytest.mark.asyncio
    async def test_malformed_jsonl_raises_tool_error(self, tmp_path: Path) -> None:
        _setup_guard(tmp_path)
        dataset = tmp_path / "bad.jsonl"
        dataset.write_text("not valid json\n", encoding="utf-8")

        with (
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            pytest.raises(ToolError, match="Malformed JSONL"),
        ):
            await validate_dataset(ctx=None, dataset_path=str(dataset), run_id=RUN_ID)

    @pytest.mark.asyncio
    async def test_empty_file_returns_empty_report(self, tmp_path: Path) -> None:
        _setup_guard(tmp_path)
        dataset = tmp_path / "empty.jsonl"
        dataset.write_text("", encoding="utf-8")

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = await validate_dataset(ctx=None, dataset_path=str(dataset), run_id=RUN_ID)
        report = json.loads(result)

        assert report["label_distribution"]["total_records"] == 0
        assert report["query_length"]["count"] == 0

    @pytest.mark.asyncio
    async def test_blank_lines_tolerated(self, tmp_path: Path) -> None:
        _setup_guard(tmp_path)
        dataset = tmp_path / "data.jsonl"
        row_json = json.dumps(_valid_row("ex-1"))
        dataset.write_text(f"\n{row_json}\n\n", encoding="utf-8")

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = await validate_dataset(ctx=None, dataset_path=str(dataset), run_id=RUN_ID)
        report = json.loads(result)

        assert report["query_length"]["count"] == 1


def _routing_context_json(route_names: list[str]) -> str:
    return json.dumps(
        {
            "domain": "test domain",
            "routes": [{"name": n, "description": f"desc {n}"} for n in route_names],
            "routing_dimensions": [
                {"name": "cost", "direction": "lower_is_better", "description": "cost"},
            ],
        }
    )


def _write_transformed_dataset(tmp_path: Path, route_keys: list[str]) -> Path:
    validation_dir = tmp_path / "outputs" / RUN_ID / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    transformed = validation_dir / "transformed.jsonl"
    rows = [
        {
            "id": "ex-1",
            "input": "q",
            "expected": {
                "route": route_keys[0],
                "routes": {k: {"cost": 0.01, "quality_score": 0.5} for k in route_keys},
            },
        }
    ]
    _write_jsonl(rows, transformed)
    return transformed


class TestSaveRoutingContext:
    @pytest.mark.asyncio
    async def test_matching_route_names_persists(self, tmp_path: Path) -> None:
        _write_transformed_dataset(tmp_path, ["0_simple", "1_complex"])
        rc_json = _routing_context_json(["0_simple", "1_complex"])

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            msg = await save_routing_context(ctx=None, run_id=RUN_ID, routing_context_json=rc_json)

        out = tmp_path / "outputs" / RUN_ID / "validation" / "routing_context.json"
        assert out.is_file()
        assert "Routing context saved" in msg

    @pytest.mark.asyncio
    async def test_mismatched_route_names_raises(self, tmp_path: Path) -> None:
        _write_transformed_dataset(tmp_path, ["0_simple", "1_complex"])
        rc_json = _routing_context_json(["simple", "complex"])

        with (
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            pytest.raises(ToolError, match="do not match the canonical"),
        ):
            await save_routing_context(ctx=None, run_id=RUN_ID, routing_context_json=rc_json)

        out = tmp_path / "outputs" / RUN_ID / "validation" / "routing_context.json"
        assert not out.exists()

    @pytest.mark.asyncio
    async def test_missing_transformed_dataset_raises(self, tmp_path: Path) -> None:
        (tmp_path / "outputs" / RUN_ID / "validation").mkdir(parents=True, exist_ok=True)
        rc_json = _routing_context_json(["a", "b"])

        with (
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            pytest.raises(ToolError, match="Transformed dataset not found"),
        ):
            await save_routing_context(ctx=None, run_id=RUN_ID, routing_context_json=rc_json)


class TestGetRoutingContextTool:
    @pytest.mark.asyncio
    async def test_round_trip_save_then_get(self, tmp_path: Path) -> None:
        """save_routing_context then get_routing_context returns the markdown summary."""
        _write_transformed_dataset(tmp_path, ["0_simple", "1_complex"])
        rc_json = _routing_context_json(["0_simple", "1_complex"])

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            await save_routing_context(ctx=None, run_id=RUN_ID, routing_context_json=rc_json)
            result = await get_routing_context(ctx=None, run_id=RUN_ID)

        from compass.agents.routing_context import RoutingContext

        saved = RoutingContext.model_validate_json(rc_json)
        assert "## Routing context" in result
        assert "### Routes" in result
        assert saved.domain in result
        for route in saved.routes:
            assert route.name in result

    @pytest.mark.asyncio
    async def test_missing_file_raises_tool_error(self, tmp_path: Path) -> None:
        """get_routing_context raises ToolError with a helpful message when file is absent."""
        (tmp_path / "outputs" / RUN_ID / "validation").mkdir(parents=True, exist_ok=True)
        expected_path = tmp_path / "outputs" / RUN_ID / "validation" / "routing_context.json"

        with (
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            pytest.raises(ToolError) as exc_info,
        ):
            await get_routing_context(ctx=None, run_id=RUN_ID)

        msg = str(exc_info.value)
        assert "Complete data validation" in msg
        assert str(expected_path) in msg


def _make_quality_report(tmp_path: Path) -> None:
    """Write a passing data_quality_report so the split tool guard passes."""
    validation_dir = tmp_path / "outputs" / RUN_ID / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    (validation_dir / "data_quality_report.json").write_text("{}", encoding="utf-8")


class TestStratifiedSplitToolRouteInRoutes:
    @pytest.mark.asyncio
    async def test_misaligned_route_raises(self, tmp_path: Path) -> None:
        _make_quality_report(tmp_path)
        dataset = tmp_path / "data.jsonl"
        rows = [
            {
                "id": f"ex-{i}",
                "input": f"q{i}",
                "expected": {
                    "route": "simple",
                    "routes": {
                        "0_simple": {"cost": 0.01, "quality_score": 0.5},
                        "1_complex": {"cost": 0.1, "quality_score": 0.9},
                    },
                },
            }
            for i in range(10)
        ]
        _write_jsonl(rows, dataset)

        with (
            patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            pytest.raises(ToolError, match="expected.route is not a key of"),
        ):
            await stratified_split(ctx=None, run_id=RUN_ID, dataset_path=str(dataset))

        analysis_dir = tmp_path / "outputs" / RUN_ID / "analysis"
        assert not (analysis_dir / "dev.jsonl").exists()
        assert not (analysis_dir / "holdout.jsonl").exists()


class TestStratifiedSplitDebugArtifacts:
    @pytest.mark.asyncio
    async def test_split_report_not_written_by_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("COMPASS_DEBUG", raising=False)
        _make_quality_report(tmp_path)
        dataset = tmp_path / "data.jsonl"
        _write_jsonl([_valid_row(f"ex-{i}") for i in range(10)], dataset)

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = json.loads(await stratified_split(ctx=None, run_id=RUN_ID, dataset_path=str(dataset)))

        analysis_dir = tmp_path / "outputs" / RUN_ID / "analysis"
        assert (analysis_dir / "dev.jsonl").exists()
        assert (analysis_dir / "holdout.jsonl").exists()
        assert not (analysis_dir / "split_report.json").exists()
        assert result["split_report_path"] is None

    @pytest.mark.asyncio
    async def test_split_report_written_when_debug_enabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COMPASS_DEBUG", "1")
        _make_quality_report(tmp_path)
        dataset = tmp_path / "data.jsonl"
        _write_jsonl([_valid_row(f"ex-{i}") for i in range(10)], dataset)

        with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
            result = json.loads(await stratified_split(ctx=None, run_id=RUN_ID, dataset_path=str(dataset)))

        analysis_dir = tmp_path / "outputs" / RUN_ID / "analysis"
        split_report_path = analysis_dir / "split_report.json"
        assert (analysis_dir / "dev.jsonl").exists()
        assert (analysis_dir / "holdout.jsonl").exists()
        assert split_report_path.exists()
        assert result["split_report_path"] == str(split_report_path)
