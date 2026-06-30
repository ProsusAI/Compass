"""Tests for ScoreReport and ErrorBreakdown models."""

from datetime import UTC, datetime

from odysseus.eval.diff import MetricDiff, OverheadDiff
from odysseus.eval.models import (
    ErrorBreakdown,
    EvalResult,
    MetricConfig,
    RunConfig,
    RunDiff,
    RunReport,
    RunSummary,
    ScoreReport,
    TokenUsage,
)


class TestErrorBreakdown:
    def test_construction(self) -> None:
        eb = ErrorBreakdown(example_id="ex-1", error="timeout", retries=3)
        assert eb.example_id == "ex-1"
        assert eb.error == "timeout"
        assert eb.retries == 3

    def test_serialization_roundtrip(self) -> None:
        eb = ErrorBreakdown(example_id="ex-1", error="timeout", retries=2)
        data = eb.model_dump()
        assert data == {"example_id": "ex-1", "error": "timeout", "retries": 2}
        assert ErrorBreakdown(**data) == eb


class TestRunDiff:
    def test_construction_with_all_fields(self) -> None:
        rd = RunDiff(
            metric_diffs=[MetricDiff(key="accuracy", old=0.8, new=0.85, status="changed")],
            overhead_diff=OverheadDiff(old_cost=0.05, new_cost=0.04, old_duration=12.0, new_duration=10.0),
        )
        assert len(rd.metric_diffs) == 1
        assert rd.overhead_diff is not None

    def test_construction_no_overhead(self) -> None:
        rd = RunDiff(
            metric_diffs=[MetricDiff(key="accuracy", old=0.8, new=0.85, status="changed")],
            overhead_diff=None,
        )
        assert rd.overhead_diff is None

    def test_empty_diffs(self) -> None:
        rd = RunDiff(metric_diffs=[], overhead_diff=None)
        assert rd.metric_diffs == []


def _make_run_report(
    *,
    num_succeeded: int = 8,
    num_failed: int = 2,
    metrics: dict[str, float] | None = None,
) -> RunReport:
    """Helper to build a RunReport for testing."""
    results: list[EvalResult] = []
    for i in range(num_succeeded):
        results.append(
            EvalResult(
                example_id=f"ok-{i}",
                model="test-model",
                output={"route": "classA"},
                error=None,
                latency_ms=100.0,
                retries=0,
                token_usage=TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5),
                cost=0.001,
            )
        )
    for i in range(num_failed):
        results.append(
            EvalResult(
                example_id=f"fail-{i}",
                model="test-model",
                output=None,
                error="timeout" if i % 2 == 0 else "rate_limit",
                latency_ms=60000.0,
                retries=3,
                token_usage=None,
                cost=None,
            )
        )
    return RunReport(
        config=RunConfig(
            backend="test-backend",
            data_source="data/test.jsonl",
            metrics=[MetricConfig(name="accuracy")],
        ),
        metrics=metrics or {"accuracy": 0.85},
        results=results,
        summary=RunSummary(
            total=num_succeeded + num_failed,
            succeeded=num_succeeded,
            failed=num_failed,
            total_cost=0.008,
            start_time=datetime(2026, 3, 19, 10, 0, 0, tzinfo=UTC),
            end_time=datetime(2026, 3, 19, 10, 1, 0, tzinfo=UTC),
            duration_seconds=60.0,
        ),
    )


class TestScoreReport:
    def test_from_run_report_basic(self) -> None:
        report = _make_run_report()
        score = ScoreReport.from_run_report(
            report, report_path="outputs/report.json", results_path="outputs/results.jsonl"
        )

        assert score.metrics == {"accuracy": 0.85}
        assert score.summary.total == 10
        assert score.summary.succeeded == 8
        assert score.summary.failed == 2
        assert score.report_path == "outputs/report.json"
        assert score.diff is None

    def test_errors_extracted(self) -> None:
        report = _make_run_report(num_failed=3)
        score = ScoreReport.from_run_report(
            report, report_path="outputs/report.json", results_path="outputs/results.jsonl"
        )

        assert len(score.errors) == 3
        assert score.errors[0].example_id == "fail-0"
        assert score.errors[0].error == "timeout"
        assert score.errors[0].retries == 3
        assert score.errors[1].error == "rate_limit"

    def test_no_errors_when_all_succeed(self) -> None:
        report = _make_run_report(num_succeeded=5, num_failed=0)
        score = ScoreReport.from_run_report(
            report, report_path="outputs/report.json", results_path="outputs/results.jsonl"
        )
        assert score.errors == []

    def test_with_previous_report_generates_diff(self) -> None:
        current = _make_run_report(metrics={"accuracy": 0.85})
        previous = _make_run_report(metrics={"accuracy": 0.80})
        score = ScoreReport.from_run_report(
            current,
            report_path="outputs/report.json",
            results_path="outputs/results.jsonl",
            previous_report=previous,
        )

        assert score.diff is not None
        assert len(score.diff.metric_diffs) == 1
        assert score.diff.metric_diffs[0].key == "accuracy"
        assert score.diff.metric_diffs[0].old == 0.80
        assert score.diff.metric_diffs[0].new == 0.85

    def test_context_key(self) -> None:
        """The pipeline context key must be 'eval_score_report'."""
        assert ScoreReport.CONTEXT_KEY == "eval_score_report"

    def test_context_key_excluded_from_serialization(self) -> None:
        report = _make_run_report()
        score = ScoreReport.from_run_report(
            report, report_path="outputs/report.json", results_path="outputs/results.jsonl"
        )
        assert "CONTEXT_KEY" not in score.model_dump()

    def test_serialization_roundtrip(self) -> None:
        report = _make_run_report()
        score = ScoreReport.from_run_report(
            report, report_path="outputs/report.json", results_path="outputs/results.jsonl"
        )
        data = score.model_dump()
        restored = ScoreReport(**data)
        assert restored == score


class TestExports:
    def test_score_report_importable_from_eval(self) -> None:
        from odysseus.eval import ScoreReport as Exported

        assert Exported is ScoreReport

    def test_error_breakdown_importable_from_eval(self) -> None:
        from odysseus.eval import ErrorBreakdown as Exported

        assert Exported is ErrorBreakdown

    def test_run_diff_importable_from_eval(self) -> None:
        from odysseus.eval import RunDiff as Exported

        assert Exported is RunDiff
