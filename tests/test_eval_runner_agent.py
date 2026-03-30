"""Tests for EvalRunnerAgent (THP-131)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import yaml

from odysseus.agents.eval_runner import EvalRunnerAgent
from odysseus.eval.models import (
    EvalResult,
    MetricConfig,
    OutputConfig,
    RunConfig,
    RunReport,
    RunSummary,
    ScoreReport,
    TokenUsage,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _stub_run_report(
    *,
    accuracy: float = 0.85,
    total: int = 1,
    succeeded: int = 1,
    failed: int = 0,
    results: list[EvalResult] | None = None,
) -> RunReport:
    """A minimal RunReport for building ScoreReports in tests."""
    if results is None:
        results = [
            EvalResult(
                example_id="ex1",
                model="test-model",
                output={"content": "route-a"},
                error=None,
                latency_ms=100.0,
                retries=0,
                token_usage=TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5),
                cost=0.001,
            ),
        ]
    return RunReport(
        config=RunConfig(
            backend="stub",
            data_source="data/test.jsonl",
            metrics=[MetricConfig(name="accuracy")],
        ),
        metrics={"accuracy": accuracy},
        results=results,
        summary=RunSummary(
            total=total,
            succeeded=succeeded,
            failed=failed,
            total_cost=0.001,
            start_time=datetime(2026, 1, 1, tzinfo=UTC),
            end_time=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
            duration_seconds=60.0,
        ),
    )


def _stub_all_errors_report() -> RunReport:
    """RunReport where all examples errored."""
    error_results = [
        EvalResult(
            example_id=f"ex{i}",
            model="test-model",
            output=None,
            error=f"Error on example {i}",
            latency_ms=50.0,
            retries=2,
            token_usage=None,
            cost=None,
        )
        for i in range(1, 4)
    ]
    return _stub_run_report(
        accuracy=0.0,
        total=3,
        succeeded=0,
        failed=3,
        results=error_results,
    )


def _default_context() -> dict[str, Any]:
    """Standard pipeline context for tests."""
    return {
        "prompt_version": "v1",
        "data_source": "data/test.jsonl",
        "backend": "test-backend",
        "config_path": "",  # Will be overridden per-test
    }


def _write_run_config(tmp_path: Path) -> Path:
    """Write a minimal YAML run config with tmp_path-rooted output paths."""
    output_dir = tmp_path / "outputs"
    config = {
        "metrics": [{"name": "accuracy"}],
        "concurrency": {"max_concurrent_requests": 5},
        "retry": {"max_attempts": 2, "backoff_factor": 2.0, "per_call_timeout_seconds": 30.0},
        "output": {
            "results_path": str(output_dir / "results.jsonl"),
            "report_path": str(output_dir / "report.json"),
        },
    }
    config_path = tmp_path / "run_config.yaml"
    config_path.write_text(yaml.dump(config))
    return config_path


# ---------------------------------------------------------------------------
# THP-131 Case 1: Successful run
# ---------------------------------------------------------------------------


class TestEvalRunnerAgentSuccess:
    """Happy-path tests."""

    async def test_successful_run_returns_score_report(self, tmp_path: Path) -> None:
        """Agent calls controller, builds ScoreReport, returns it in context."""
        config_path = _write_run_config(tmp_path)
        report = _stub_run_report()

        agent = EvalRunnerAgent()

        context = {
            **_default_context(),
            "config_path": str(config_path),
        }

        with patch("odysseus.agents.eval_runner.controller") as mock_ctrl:
            mock_ctrl.run = AsyncMock(return_value=report)
            with patch("odysseus.agents.eval_runner.EvalRunnerAgent._wire_dependencies"):
                result = await agent.run(context)

        assert ScoreReport.CONTEXT_KEY in result
        score_report = result[ScoreReport.CONTEXT_KEY]
        assert isinstance(score_report, ScoreReport)
        assert score_report.metrics == {"accuracy": 0.85}
        assert score_report.summary.total == 1
        assert score_report.summary.succeeded == 1
        assert score_report.summary.failed == 0

    async def test_name_property(self) -> None:
        """Agent name is 'eval_runner'."""
        agent = EvalRunnerAgent()
        assert agent.name == "eval_runner"


# ---------------------------------------------------------------------------
# THP-131 Case 3: All-errored run
# ---------------------------------------------------------------------------


class TestEvalRunnerAgentAllErrors:
    """Tests for runs where all examples fail."""

    async def test_all_errored_run_returns_graceful_report(self, tmp_path: Path) -> None:
        """All examples fail — agent returns ScoreReport with correct counts, no crash."""
        config_path = _write_run_config(tmp_path)
        report = _stub_all_errors_report()

        agent = EvalRunnerAgent()
        context = {
            **_default_context(),
            "config_path": str(config_path),
        }

        with patch("odysseus.agents.eval_runner.controller") as mock_ctrl:
            mock_ctrl.run = AsyncMock(return_value=report)
            with patch("odysseus.agents.eval_runner.EvalRunnerAgent._wire_dependencies"):
                result = await agent.run(context)

        assert ScoreReport.CONTEXT_KEY in result
        score_report = result[ScoreReport.CONTEXT_KEY]
        assert isinstance(score_report, ScoreReport)
        assert score_report.metrics == {"accuracy": 0.0}
        assert score_report.summary.total == 3
        assert score_report.summary.succeeded == 0
        assert score_report.summary.failed == 3
        assert len(score_report.errors) == 3


# ---------------------------------------------------------------------------
# THP-131 Case 4: Previous run diff
# ---------------------------------------------------------------------------


class TestEvalRunnerAgentDiff:
    """Tests for previous-run diffing."""

    async def test_previous_run_diff_included_in_score_report(self, tmp_path: Path) -> None:
        """When a previous report exists on disk, ScoreReport includes a diff."""
        config_path = _write_run_config(tmp_path)
        current_report = _stub_run_report(accuracy=0.90)

        # Write a previous report to the config's output path before the run.
        # _write_run_config uses tmp_path-rooted paths, so this aligns.
        report_output_path = tmp_path / "outputs" / "report.json"
        report_output_path.parent.mkdir(parents=True, exist_ok=True)
        previous_report = _stub_run_report(accuracy=0.80)
        report_output_path.write_text(previous_report.model_dump_json(indent=2))

        agent = EvalRunnerAgent()
        context = {
            **_default_context(),
            "config_path": str(config_path),
        }

        with patch("odysseus.agents.eval_runner.controller") as mock_ctrl:
            mock_ctrl.run = AsyncMock(return_value=current_report)
            with patch("odysseus.agents.eval_runner.EvalRunnerAgent._wire_dependencies"):
                result = await agent.run(context)

        assert ScoreReport.CONTEXT_KEY in result
        score_report = result[ScoreReport.CONTEXT_KEY]
        assert score_report.diff is not None
        assert len(score_report.diff.metric_diffs) > 0
        accuracy_diff = next(d for d in score_report.diff.metric_diffs if d.key == "accuracy")
        assert accuracy_diff.old == 0.80
        assert accuracy_diff.new == 0.90


# ---------------------------------------------------------------------------
# THP-131 Case 5: Tool call / controller failures
# ---------------------------------------------------------------------------


class TestEvalRunnerAgentErrors:
    """Error handling tests."""

    async def test_controller_raises_returns_structured_error(self, tmp_path: Path) -> None:
        """When controller.run raises, agent returns structured error in context."""
        config_path = _write_run_config(tmp_path)

        agent = EvalRunnerAgent()
        context = {
            **_default_context(),
            "config_path": str(config_path),
        }

        with patch("odysseus.agents.eval_runner.controller") as mock_ctrl:
            mock_ctrl.run = AsyncMock(side_effect=RuntimeError("connection reset"))
            with patch("odysseus.agents.eval_runner.EvalRunnerAgent._wire_dependencies"):
                result = await agent.run(context)

        assert "error" in result
        assert result["error"]["category"] == "run_error"
        assert "connection reset" in result["error"]["detail"]

    async def test_missing_config_returns_structured_error(self, tmp_path: Path) -> None:
        """Nonexistent config_path returns not_found error."""
        agent = EvalRunnerAgent()
        context = {
            **_default_context(),
            "config_path": str(tmp_path / "does_not_exist.yaml"),
        }

        result = await agent.run(context)

        assert "error" in result
        assert result["error"]["category"] == "not_found"

    async def test_invalid_config_returns_validation_error(self, tmp_path: Path) -> None:
        """YAML with invalid content returns validation_error."""
        config_path = tmp_path / "run_config.yaml"
        config_path.write_text(yaml.dump({"metrics": []}))  # Empty metrics list

        agent = EvalRunnerAgent()
        context = {
            **_default_context(),
            "config_path": str(config_path),
        }

        result = await agent.run(context)

        assert "error" in result
        assert result["error"]["category"] == "validation_error"

    async def test_missing_prompt_returns_not_found_error(self, tmp_path: Path) -> None:
        """FileNotFoundError from controller surfaces as not_found."""
        config_path = _write_run_config(tmp_path)

        agent = EvalRunnerAgent()
        context = {
            **_default_context(),
            "config_path": str(config_path),
        }

        with patch("odysseus.agents.eval_runner.controller") as mock_ctrl:
            mock_ctrl.run = AsyncMock(side_effect=FileNotFoundError("prompt v99 not found"))
            with patch("odysseus.agents.eval_runner.EvalRunnerAgent._wire_dependencies"):
                result = await agent.run(context)

        assert "error" in result
        assert result["error"]["category"] == "not_found"
        assert "v99" in result["error"]["detail"]

    async def test_unknown_backend_returns_not_found_error(self, tmp_path: Path) -> None:
        """KeyError from backend registry surfaces as not_found."""
        config_path = _write_run_config(tmp_path)

        agent = EvalRunnerAgent()
        context = {
            **_default_context(),
            "config_path": str(config_path),
            "backend": "unknown-backend",
        }

        with patch("odysseus.agents.eval_runner.EvalRunnerAgent._wire_dependencies") as mock_wire:
            mock_wire.side_effect = KeyError("unknown-backend")
            result = await agent.run(context)

        assert "error" in result
        assert result["error"]["category"] == "not_found"


# ---------------------------------------------------------------------------
# Pipeline config (direct RunConfig) path
# ---------------------------------------------------------------------------


class TestEvalRunnerAgentPipelineConfig:
    """Tests for direct RunConfig (pipeline) path."""

    async def test_uses_prebuilt_run_config(self, tmp_path: Path) -> None:
        """When context has 'run_config', agent uses it directly — no YAML."""
        report = _stub_run_report()
        eval_dir = tmp_path / "outputs" / "test-run" / "eval"
        run_config = RunConfig(
            backend="anthropic",
            prompt_version="v1",
            data_source="data/dev.jsonl",
            metrics=[MetricConfig(name="accuracy")],
            output=OutputConfig(
                results_path=str(eval_dir / "results.jsonl"),
                report_path=str(eval_dir / "report.json"),
            ),
        )

        agent = EvalRunnerAgent()
        context = {
            "prompt_version": "v1",
            "data_source": "data/dev.jsonl",
            "backend": "anthropic",
            "run_id": "test-run",
            "run_config": run_config,
        }

        with patch("odysseus.agents.eval_runner.controller") as mock_ctrl:
            mock_ctrl.run = AsyncMock(return_value=report)
            with patch("odysseus.agents.eval_runner.EvalRunnerAgent._wire_dependencies"):
                result = await agent.run(context)

        assert ScoreReport.CONTEXT_KEY in result
        called_config = mock_ctrl.run.call_args.args[0]
        assert called_config.backend == "anthropic"
        assert called_config.output.results_path == str(eval_dir / "results.jsonl")

    async def test_prebuilt_config_skips_yaml_loading(self, tmp_path: Path) -> None:
        """When run_config is in context, _load_config is never called."""
        report = _stub_run_report()
        run_config = RunConfig(
            backend="anthropic",
            prompt_version="v1",
            data_source="data/dev.jsonl",
            metrics=[MetricConfig(name="accuracy")],
        )

        agent = EvalRunnerAgent()
        context = {
            "prompt_version": "v1",
            "data_source": "data/dev.jsonl",
            "backend": "anthropic",
            "run_config": run_config,
        }

        with patch("odysseus.agents.eval_runner.controller") as mock_ctrl:
            mock_ctrl.run = AsyncMock(return_value=report)
            with patch("odysseus.agents.eval_runner.EvalRunnerAgent._wire_dependencies"):
                with patch.object(agent, "_load_config") as mock_load:
                    result = await agent.run(context)
                    mock_load.assert_not_called()

        assert ScoreReport.CONTEXT_KEY in result
