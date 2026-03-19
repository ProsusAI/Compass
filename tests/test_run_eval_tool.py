"""Tests for the run_eval MCP tool."""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.eval.models import (
    EvalResult,
    MetricConfig,
    RunConfig,
    RunReport,
    RunSummary,
    TokenUsage,
)

# Import run_eval at module level — patches target odysseus.mcp.<dep>, not the function.
from odysseus.mcp import run_eval


def _stub_run_report() -> RunReport:
    """Create a minimal RunReport stub for mocking controller.run return values."""
    from datetime import datetime

    stub_config = RunConfig(
        backend="stub",
        data_source="stub.jsonl",
        data_split="dev",
        metrics=[MetricConfig(name="accuracy")],
    )
    return RunReport(
        config=stub_config,
        metrics={"accuracy": 0.85},
        results=[
            EvalResult(
                example_id="ex1",
                model="test-model",
                output={"content": "route-a"},
                error=None,
                latency_ms=100.0,
                retries=0,
                token_usage=TokenUsage(
                    input_tokens=10, cached_tokens=0, output_tokens=5
                ),
                cost=0.001,
            ),
        ],
        summary=RunSummary(
            total=1,
            succeeded=1,
            failed=0,
            total_cost=0.001,
            start_time=datetime(2026, 1, 1, tzinfo=UTC),
            end_time=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
            duration_seconds=60.0,
        ),
    )


def _write_config_yaml(path: Path) -> None:
    """Write a minimal run config YAML file."""
    config = {
        "metrics": [{"name": "accuracy"}],
        "concurrency": {"max_concurrent_requests": 5},
        "retry": {"max_attempts": 2, "backoff_factor": 2.0, "per_call_timeout_seconds": 30.0},
        "output": {
            "results_path": "outputs/results.jsonl",
            "report_path": "outputs/report.json",
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(config))


@pytest.fixture()
def config_dir(tmp_path: Path) -> Path:
    """Create a temp directory with a run config YAML."""
    config_path = tmp_path / "run_config.yaml"
    _write_config_yaml(config_path)
    return tmp_path


@pytest.fixture()
def mcp_mocks():
    """Patch all run_eval dependencies and yield mock handles."""
    with (
        patch("odysseus.mcp.BackendRegistry") as mock_registry_cls,
        patch("odysseus.mcp.FilePromptManager"),
        patch("odysseus.mcp.JsonlDatasetManager"),
        patch("odysseus.mcp.create_default_engine"),
        patch("odysseus.mcp.JsonResultsCollector"),
        patch("odysseus.mcp.controller") as mock_controller,
    ):
        mock_registry = MagicMock()
        mock_registry_cls.from_directory.return_value = mock_registry
        mock_profile = MagicMock()
        mock_profile.requests_per_minute = 100
        mock_profile.tokens_per_minute = 50000
        mock_registry.get_profile.return_value = mock_profile

        mock_controller.run = AsyncMock(return_value=_stub_run_report())

        yield SimpleNamespace(
            controller=mock_controller,
            registry=mock_registry,
            profile=mock_profile,
        )


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_eval_success(config_dir: Path, mcp_mocks: SimpleNamespace) -> None:
    """Successful run_eval returns report and results paths."""
    result = await run_eval(
        prompt_version="v1",
        data_source="data/test.jsonl",
        backend="test-backend",
        config_path=str(config_dir / "run_config.yaml"),
    )

    parsed = json.loads(result)
    assert parsed["report_path"] == "outputs/report.json"
    assert parsed["results_path"] == "outputs/results.jsonl"
    mcp_mocks.controller.run.assert_awaited_once()


# ---------------------------------------------------------------------------
# Config overlay and data_split hardcoding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_eval_hardcodes_dev_split(config_dir: Path, mcp_mocks: SimpleNamespace) -> None:
    """run_eval always passes data_split='dev' and forwards tool params."""
    await run_eval(
        prompt_version="v2",
        data_source="data/train.jsonl",
        backend="my-backend",
        config_path=str(config_dir / "run_config.yaml"),
    )

    run_config: RunConfig = mcp_mocks.controller.run.call_args.args[0]
    assert run_config.data_split == "dev"
    assert run_config.backend == "my-backend"
    assert run_config.prompt_version == "v2"
    assert run_config.data_source == "data/train.jsonl"


@pytest.mark.asyncio
async def test_run_eval_tool_params_override_yaml(
    tmp_path: Path, mcp_mocks: SimpleNamespace
) -> None:
    """Tool params override YAML values, and data_split is always 'dev'."""
    config_path = tmp_path / "run_config.yaml"
    config_path.write_text(yaml.dump({
        "backend": "yaml-backend",
        "prompt_version": "v0",
        "data_source": "data/old.jsonl",
        "data_split": "holdout",
        "metrics": [{"name": "accuracy"}],
        "concurrency": {"max_concurrent_requests": 5},
        "retry": {"max_attempts": 2, "backoff_factor": 2.0, "per_call_timeout_seconds": 30.0},
        "output": {
            "results_path": "outputs/results.jsonl",
            "report_path": "outputs/report.json",
        },
    }))

    await run_eval(
        prompt_version="v5",
        data_source="data/new.jsonl",
        backend="tool-backend",
        config_path=str(config_path),
    )

    run_config: RunConfig = mcp_mocks.controller.run.call_args.args[0]
    assert run_config.backend == "tool-backend"
    assert run_config.prompt_version == "v5"
    assert run_config.data_source == "data/new.jsonl"
    assert run_config.data_split == "dev"


# ---------------------------------------------------------------------------
# Recoverable error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_eval_missing_config_file(tmp_path: Path) -> None:
    """Nonexistent config path returns {'error': 'not_found'}."""
    result = await run_eval(
        prompt_version="v1",
        data_source="data/test.jsonl",
        backend="test-backend",
        config_path=str(tmp_path / "does_not_exist.yaml"),
    )

    parsed = json.loads(result)
    assert parsed["error"] == "not_found"


@pytest.mark.asyncio
async def test_run_eval_invalid_config_yaml(tmp_path: Path) -> None:
    """YAML with empty metrics list fails validation."""
    config_path = tmp_path / "run_config.yaml"
    config_path.write_text(yaml.dump({
        "metrics": [],
        "concurrency": {"max_concurrent_requests": 5},
        "retry": {"max_attempts": 2, "backoff_factor": 2.0, "per_call_timeout_seconds": 30.0},
        "output": {
            "results_path": "outputs/results.jsonl",
            "report_path": "outputs/report.json",
        },
    }))

    result = await run_eval(
        prompt_version="v1",
        data_source="data/test.jsonl",
        backend="test",
        config_path=str(config_path),
    )

    parsed = json.loads(result)
    assert parsed["error"] == "validation_error"


@pytest.mark.asyncio
async def test_run_eval_unknown_backend(
    config_dir: Path, mcp_mocks: SimpleNamespace
) -> None:
    """Unknown backend label returns {'error': 'not_found'}."""
    mcp_mocks.registry.get_profile.side_effect = KeyError("unknown-backend")

    result = await run_eval(
        prompt_version="v1",
        data_source="data/test.jsonl",
        backend="unknown-backend",
        config_path=str(config_dir / "run_config.yaml"),
    )

    parsed = json.loads(result)
    assert parsed["error"] == "not_found"


@pytest.mark.asyncio
async def test_run_eval_missing_prompt(
    config_dir: Path, mcp_mocks: SimpleNamespace
) -> None:
    """FileNotFoundError from controller.run returns {'error': 'not_found'}."""
    mcp_mocks.controller.run = AsyncMock(
        side_effect=FileNotFoundError("prompt v99 not found")
    )

    result = await run_eval(
        prompt_version="v99",
        data_source="data/test.jsonl",
        backend="test-backend",
        config_path=str(config_dir / "run_config.yaml"),
    )

    parsed = json.loads(result)
    assert parsed["error"] == "not_found"
    assert "v99" in parsed["detail"]


# ---------------------------------------------------------------------------
# Unexpected error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_eval_unexpected_error_raises_tool_error(
    config_dir: Path, mcp_mocks: SimpleNamespace
) -> None:
    """Unexpected RuntimeError is re-raised as ToolError."""
    mcp_mocks.controller.run = AsyncMock(
        side_effect=RuntimeError("connection reset")
    )

    with pytest.raises(ToolError, match="run_eval failed unexpectedly"):
        await run_eval(
            prompt_version="v1",
            data_source="data/test.jsonl",
            backend="test-backend",
            config_path=str(config_dir / "run_config.yaml"),
        )
