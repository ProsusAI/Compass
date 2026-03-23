"""Integration tests for the data validation MCP tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.mcp import validate_dataset


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
        dataset = tmp_path / "data.jsonl"
        _write_jsonl([_valid_row("ex-1"), _valid_row("ex-2")], dataset)

        result = await validate_dataset(str(dataset))
        report = json.loads(result)

        assert "schema_findings" in report
        assert "label_distribution" in report
        assert "volume_assessment" in report
        assert "query_length" in report
        assert report["query_length"]["count"] == 2

    @pytest.mark.asyncio
    async def test_nonexistent_file_raises_tool_error(self) -> None:
        with pytest.raises(ToolError, match="Dataset file not found"):
            await validate_dataset("/nonexistent/path/data.jsonl")

    @pytest.mark.asyncio
    async def test_malformed_jsonl_raises_tool_error(self, tmp_path: Path) -> None:
        dataset = tmp_path / "bad.jsonl"
        dataset.write_text("not valid json\n", encoding="utf-8")

        with pytest.raises(ToolError, match="Malformed JSONL"):
            await validate_dataset(str(dataset))

    @pytest.mark.asyncio
    async def test_empty_file_returns_empty_report(self, tmp_path: Path) -> None:
        dataset = tmp_path / "empty.jsonl"
        dataset.write_text("", encoding="utf-8")

        result = await validate_dataset(str(dataset))
        report = json.loads(result)

        assert report["label_distribution"]["total_records"] == 0
        assert report["query_length"]["count"] == 0

    @pytest.mark.asyncio
    async def test_blank_lines_tolerated(self, tmp_path: Path) -> None:
        dataset = tmp_path / "data.jsonl"
        row_json = json.dumps(_valid_row("ex-1"))
        dataset.write_text(f"\n{row_json}\n\n", encoding="utf-8")

        result = await validate_dataset(str(dataset))
        report = json.loads(result)

        assert report["query_length"]["count"] == 1
