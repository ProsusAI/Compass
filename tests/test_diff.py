"""Tests for odysseus.eval.diff — shared diff computation."""

from odysseus.eval.diff import MetricDiff, OverheadDiff, compute_metric_diffs, compute_overhead_diff


class TestComputeMetricDiffs:
    def test_changed_metric(self) -> None:
        old = {"accuracy": 0.82}
        new = {"accuracy": 0.85}
        result = compute_metric_diffs(old, new)
        assert result == [MetricDiff(key="accuracy", old=0.82, new=0.85, status="changed")]

    def test_added_metric(self) -> None:
        old: dict[str, float] = {}
        new = {"accuracy": 0.85}
        result = compute_metric_diffs(old, new)
        assert result == [MetricDiff(key="accuracy", old=None, new=0.85, status="added")]

    def test_removed_metric(self) -> None:
        old = {"accuracy": 0.82}
        new: dict[str, float] = {}
        result = compute_metric_diffs(old, new)
        assert result == [MetricDiff(key="accuracy", old=0.82, new=None, status="removed")]

    def test_unchanged_metric_excluded(self) -> None:
        old = {"accuracy": 0.85}
        new = {"accuracy": 0.85}
        result = compute_metric_diffs(old, new)
        assert result == []

    def test_multiple_metrics_sorted_by_key(self) -> None:
        old = {"f1/macro": 0.7, "accuracy": 0.8}
        new = {"f1/macro": 0.75, "accuracy": 0.85}
        result = compute_metric_diffs(old, new)
        assert result[0].key == "accuracy"
        assert result[1].key == "f1/macro"

    def test_both_empty(self) -> None:
        assert compute_metric_diffs({}, {}) == []


class TestComputeOverheadDiff:
    def test_cost_and_duration_changed(self) -> None:
        result = compute_overhead_diff(
            old_cost=0.05, old_duration=12.0,
            new_cost=0.04, new_duration=10.0,
        )
        assert result == OverheadDiff(
            old_cost=0.05, new_cost=0.04,
            old_duration=12.0, new_duration=10.0,
        )

    def test_no_change_returns_none(self) -> None:
        result = compute_overhead_diff(
            old_cost=0.05, old_duration=12.0,
            new_cost=0.05, new_duration=12.0,
        )
        assert result is None

    def test_only_cost_changed(self) -> None:
        result = compute_overhead_diff(
            old_cost=0.05, old_duration=12.0,
            new_cost=0.04, new_duration=12.0,
        )
        assert result is not None
        assert result.old_cost == 0.05
        assert result.new_cost == 0.04
