"""Smoke tests for the MCP server."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from odysseus.eval.models import MetricConfig, RunConfig, RunReport, RunSummary
from odysseus.mcp import _load_config, mcp

FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadConfig:
    """Unit tests for _load_config overlay mechanism."""

    def test_loads_yaml_and_overlays_tool_params(self):
        config = _load_config(
            prompt_version="v3",
            data_source="data/test.jsonl",
            backend="claude-sonnet",
            data_split="dev",
            config_path=str(FIXTURES / "minimal_config.yaml"),
        )
        assert config.backend == "claude-sonnet"
        assert config.prompt_version == "v3"
        assert config.data_source == "data/test.jsonl"
        assert config.data_split == "dev"
        assert len(config.metrics) == 2
        assert config.metrics[0].name == "accuracy"
        assert config.metrics[1].name == "f1"

    def test_tool_params_override_yaml_keys(self):
        """Tool params win over YAML values for overlapping keys."""
        config = _load_config(
            prompt_version="v5",
            data_source="data/override.jsonl",
            backend="gpt-4o",
            data_split="holdout",
            config_path=str(FIXTURES / "minimal_config.yaml"),
        )
        assert config.backend == "gpt-4o"
        assert config.data_split == "holdout"

    def test_missing_optional_sections_use_defaults(self):
        """concurrency, retry, output fall back to RunConfig defaults."""
        config = _load_config(
            prompt_version="v1",
            data_source="data/test.jsonl",
            backend="default",
            data_split="dev",
            config_path=str(FIXTURES / "minimal_config.yaml"),
        )
        assert config.concurrency.max_concurrent_requests == 20
        assert config.retry.max_attempts == 3
        assert config.output.results_path == "outputs/results.jsonl"
        assert config.output.report_path == "outputs/report.json"

    def test_missing_metrics_uses_default_metrics(self, tmp_path):
        """When YAML omits metrics, all 4 built-in defaults are used."""
        empty_yaml = tmp_path / "empty.yaml"
        empty_yaml.write_text("{}")

        config = _load_config(
            prompt_version="v1",
            data_source="data/test.jsonl",
            backend="default",
            data_split="dev",
            config_path=str(empty_yaml),
        )
        assert len(config.metrics) == 4
        names = [m.name for m in config.metrics]
        assert names == ["accuracy", "confusion", "f1", "cost_quality_reduction"]

    def test_missing_config_file_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            _load_config(
                prompt_version="v1",
                data_source="data/test.jsonl",
                backend="default",
                data_split="dev",
                config_path="nonexistent/path.yaml",
            )

    def test_invalid_yaml_values_raise_validation_error(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("concurrency:\n  max_concurrent_requests: -5\nmetrics:\n  - name: accuracy")

        with pytest.raises(ValidationError):
            _load_config(
                prompt_version="v1",
                data_source="data/test.jsonl",
                backend="default",
                data_split="dev",
                config_path=str(bad_yaml),
            )


async def test_server_has_tools():
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "optimize_routing_prompt" in tool_names


async def test_run_eval_hardcodes_dev_split(tmp_path):
    """run_eval must always call _load_config with data_split='dev'."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("metrics:\n  - name: accuracy")

    # Wraps the real _load_config so we can inspect the call args.
    # run_eval will proceed past _load_config but fail at BackendRegistry;
    # the error is caught and returned as JSON, so the test completes.
    with patch("odysseus.mcp._load_config", wraps=_load_config) as mock_load:
        from odysseus.mcp import run_eval

        await run_eval(
            prompt_version="v1",
            data_source="data/test.jsonl",
            backend="test",
            config_path=str(config_file),
        )
        mock_load.assert_called_once_with(
            prompt_version="v1",
            data_source="data/test.jsonl",
            backend="test",
            data_split="dev",
            config_path=str(config_file),
        )


async def test_run_holdout_eval_is_stub():
    """run_holdout_eval is still a stub (out of THP-129 scope)."""
    from odysseus.mcp import run_holdout_eval

    result = await run_holdout_eval(prompt_version="v1", data_source="data/test.jsonl")
    assert "stub" in result


def test_run_eval_does_not_construct_holdout_config():
    """run_eval's hardcoded split must be 'dev', never 'holdout'.

    This is the spec's 'internal misuse' guard (Section 2): verify that
    only run_holdout_eval constructs a holdout RunConfig.
    """
    import ast
    import inspect

    from odysseus.mcp import run_eval

    source = inspect.getsource(run_eval)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "data_split":
            assert isinstance(node.value, ast.Constant)
            assert node.value.value == "dev", "run_eval must hardcode data_split='dev'"


async def test_run_eval_tool_registered():
    """run_eval must be registered as an MCP tool."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "run_eval" in tool_names


async def test_run_holdout_eval_tool_registered():
    """run_holdout_eval must be registered as an MCP tool."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "run_holdout_eval" in tool_names


async def test_run_eval_does_not_expose_data_split():
    """run_eval must not expose data_split as a parameter."""
    tools = await mcp.list_tools()
    run_eval_tool = next(t for t in tools if t.name == "run_eval")
    schema_properties = run_eval_tool.inputSchema.get("properties", {})
    assert "data_split" not in schema_properties, "data_split must not be exposed as a tool parameter"


async def test_run_holdout_eval_does_not_expose_data_split():
    """run_holdout_eval must not expose data_split as a parameter."""
    tools = await mcp.list_tools()
    holdout_tool = next(t for t in tools if t.name == "run_holdout_eval")
    schema_properties = holdout_tool.inputSchema.get("properties", {})
    assert "data_split" not in schema_properties, "data_split must not be exposed as a tool parameter"


def _make_stub_report() -> RunReport:
    """Create a minimal RunReport for testing."""
    return RunReport(
        config=RunConfig(
            backend="test",
            data_source="data/test.jsonl",
            data_split="dev",
            metrics=[MetricConfig(name="accuracy")],
        ),
        metrics={"accuracy": 0.95},
        results=[],
        summary=RunSummary(
            total=10,
            succeeded=10,
            failed=0,
            total_cost=0.01,
            start_time=datetime(2026, 1, 1),
            end_time=datetime(2026, 1, 1),
            duration_seconds=5.0,
        ),
    )


class TestRunEval:
    """Integration tests for the run_eval MCP tool."""

    async def test_success_returns_paths(self, tmp_path):
        """Successful run returns JSON with report_path and results_path."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("metrics:\n  - name: accuracy")

        mock_report = _make_stub_report()
        mock_profile = MagicMock()
        mock_profile.requests_per_minute = 100
        mock_profile.tokens_per_minute = 100000
        mock_registry = MagicMock()
        mock_registry.create_backend.return_value = MagicMock()
        mock_registry.get_profile.return_value = mock_profile

        with (
            patch("odysseus.mcp.controller.run", new_callable=AsyncMock, return_value=mock_report),
            patch("odysseus.mcp.BackendRegistry.from_directory", return_value=mock_registry),
            patch("odysseus.mcp.FilePromptManager"),
            patch("odysseus.mcp.JsonlDatasetManager"),
            patch("odysseus.mcp.create_default_engine"),
            patch("odysseus.mcp.JsonResultsCollector"),
        ):
            from odysseus.mcp import run_eval

            result = await run_eval(
                prompt_version="v1",
                data_source="data/test.jsonl",
                backend="test-backend",
                config_path=str(config_file),
            )

        parsed = json.loads(result)
        assert parsed["report_path"] == "outputs/report.json"
        assert parsed["results_path"] == "outputs/results.jsonl"

    async def test_missing_config_returns_not_found(self):
        """Missing config file returns structured not_found error."""
        from odysseus.mcp import run_eval

        result = await run_eval(
            prompt_version="v1",
            data_source="data/test.jsonl",
            backend="test-backend",
            config_path="nonexistent/config.yaml",
        )
        parsed = json.loads(result)
        assert parsed["error"] == "not_found"

    async def test_missing_backend_profile_returns_not_found(self, tmp_path):
        """Missing backend profile (KeyError) returns structured not_found error."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("metrics:\n  - name: accuracy")

        mock_registry = MagicMock()
        mock_registry.create_backend.side_effect = KeyError("no-such-backend")

        with patch("odysseus.mcp.BackendRegistry.from_directory", return_value=mock_registry):
            from odysseus.mcp import run_eval

            result = await run_eval(
                prompt_version="v1",
                data_source="data/test.jsonl",
                backend="no-such-backend",
                config_path=str(config_file),
            )

        parsed = json.loads(result)
        assert parsed["error"] == "not_found"

    async def test_validation_error_returns_validation_error(self, tmp_path):
        """Invalid config returns structured validation_error."""
        bad_config = tmp_path / "bad.yaml"
        bad_config.write_text("concurrency:\n  max_concurrent_requests: -1\nmetrics:\n  - name: accuracy")

        from odysseus.mcp import run_eval

        result = await run_eval(
            prompt_version="v1",
            data_source="data/test.jsonl",
            backend="test-backend",
            config_path=str(bad_config),
        )
        parsed = json.loads(result)
        assert parsed["error"] == "validation_error"

    async def test_unexpected_error_propagates(self, tmp_path):
        """Unexpected exceptions propagate to FastMCP's ToolError wrapping."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("metrics:\n  - name: accuracy")

        mock_profile = MagicMock()
        mock_profile.requests_per_minute = 100
        mock_profile.tokens_per_minute = 100000
        mock_registry = MagicMock()
        mock_registry.create_backend.return_value = MagicMock()
        mock_registry.get_profile.return_value = mock_profile

        with (
            patch("odysseus.mcp.controller.run", new_callable=AsyncMock, side_effect=RuntimeError("boom")),
            patch("odysseus.mcp.BackendRegistry.from_directory", return_value=mock_registry),
            patch("odysseus.mcp.FilePromptManager"),
            patch("odysseus.mcp.JsonlDatasetManager"),
            patch("odysseus.mcp.create_default_engine"),
            patch("odysseus.mcp.JsonResultsCollector"),
        ):
            from odysseus.mcp import run_eval

            with pytest.raises(RuntimeError, match="boom"):
                await run_eval(
                    prompt_version="v1",
                    data_source="data/test.jsonl",
                    backend="test-backend",
                    config_path=str(config_file),
                )
