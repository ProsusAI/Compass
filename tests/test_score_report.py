"""Tests for ScoreReport and ErrorBreakdown models."""

from odysseus.eval.models import ErrorBreakdown


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


from odysseus.eval.diff import MetricDiff, OverheadDiff
from odysseus.eval.models import RunDiff


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
