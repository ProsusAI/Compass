"""Integration tests for the data validation MCP tool."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.mcp import validate_dataset

RUN_ID = "test_run"
RESOLVE_PROJECT_DIR = "odysseus.mcp.resolve_project_dir"


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
