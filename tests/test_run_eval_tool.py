"""Tests for the run_eval MCP tool."""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
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


def _make_run_report(config: RunConfig) -> RunReport:
    """Create a minimal RunReport for testing."""
    from datetime import datetime

    return RunReport(
        config=config,
        metrics={"accuracy": 0.85, "f1/macro": 0.80},
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


@pytest.mark.asyncio
async def test_run_eval_success(config_dir: Path) -> None:
    """Successful run_eval returns report and results paths."""
    from odysseus.mcp import run_eval

    config_path = str(config_dir / "run_config.yaml")

    expected_config = RunConfig(
        backend="test-backend",
        prompt_version="v1",
        data_source="data/test.jsonl",
        data_split="dev",
        metrics=[MetricConfig(name="accuracy")],
    )
    mock_report = _make_run_report(expected_config)

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

        mock_controller.run = AsyncMock(return_value=mock_report)

        result = await run_eval(
            prompt_version="v1",
            data_source="data/test.jsonl",
            backend="test-backend",
            config_path=config_path,
        )

    parsed = json.loads(result)
    assert parsed["report_path"] == "outputs/report.json"
    assert parsed["results_path"] == "outputs/results.jsonl"
    mock_controller.run.assert_awaited_once()


# ---------------------------------------------------------------------------
# Task 2: Config overlay and data_split hardcoding tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_eval_hardcodes_dev_split(config_dir: Path) -> None:
    """run_eval always passes data_split='dev' to the controller."""
    from odysseus.mcp import run_eval

    config_path = str(config_dir / "run_config.yaml")

    expected_config = RunConfig(
        backend="my-backend",
        prompt_version="v2",
        data_source="data/train.jsonl",
        data_split="dev",
        metrics=[MetricConfig(name="accuracy")],
    )
    mock_report = _make_run_report(expected_config)

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
        mock_profile.requests_per_minute = 60
        mock_profile.tokens_per_minute = 10000
        mock_registry.get_profile.return_value = mock_profile

        mock_controller.run = AsyncMock(return_value=mock_report)

        await run_eval(
            prompt_version="v2",
            data_source="data/train.jsonl",
            backend="my-backend",
            config_path=config_path,
        )

    # Verify controller.run received a RunConfig with data_split == "dev"
    mock_controller.run.assert_awaited_once()
    call_args = mock_controller.run.call_args
    run_config: RunConfig = call_args.args[0]
    assert run_config.data_split == "dev"
    assert run_config.backend == "my-backend"
    assert run_config.prompt_version == "v2"
    assert run_config.data_source == "data/train.jsonl"


@pytest.mark.asyncio
async def test_run_eval_tool_params_override_yaml(tmp_path: Path) -> None:
    """Tool params override YAML values, and data_split is always 'dev'."""
    from odysseus.mcp import run_eval

    # Write YAML with values that should be overridden
    config_path = tmp_path / "run_config.yaml"
    yaml_config = {
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
    }
    config_path.write_text(yaml.dump(yaml_config))

    expected_config = RunConfig(
        backend="tool-backend",
        prompt_version="v5",
        data_source="data/new.jsonl",
        data_split="dev",
        metrics=[MetricConfig(name="accuracy")],
    )
    mock_report = _make_run_report(expected_config)

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

        mock_controller.run = AsyncMock(return_value=mock_report)

        await run_eval(
            prompt_version="v5",
            data_source="data/new.jsonl",
            backend="tool-backend",
            config_path=str(config_path),
        )

    mock_controller.run.assert_awaited_once()
    call_args = mock_controller.run.call_args
    run_config: RunConfig = call_args.args[0]
    # Tool params must override YAML
    assert run_config.backend == "tool-backend"
    assert run_config.prompt_version == "v5"
    assert run_config.data_source == "data/new.jsonl"
    # data_split is always hardcoded to "dev" regardless of YAML
    assert run_config.data_split == "dev"
