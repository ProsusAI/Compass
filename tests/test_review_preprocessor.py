"""Tests for odysseus.agents.review_preprocessor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from odysseus.agents.prompt_builder.search import Candidate, SearchState
from odysseus.agents.review.preprocessor import (
    _delta,
    _extract_metric,
    build_candidate_comparisons,
    build_review_briefing,
    compute_diminishing_returns,
    compute_diversity_metrics,
    compute_near_misses,
    compute_oracle_metrics,
    compute_oracle_metrics_from_report,
    extract_per_class_recall,
    generate_executive_summary,
)


def _make_report_dict(**metric_overrides: float) -> dict[str, Any]:
    """Build a minimal ScoreReport-compatible dict for preprocessor tests.

    The preprocessor works with dicts internally (loaded from JSON on disk).
    ScoreReport.model_validate() is called at the CandidateAnalysis boundary.
    """
    now = datetime.now(tz=UTC).isoformat()
    return {
        "metrics": {"accuracy": 0.80, "cost": 1.0, **metric_overrides},
        "summary": {
            "total": 10,
            "succeeded": 10,
            "failed": 0,
            "total_cost": 1.0,
            "start_time": now,
            "end_time": now,
            "duration_seconds": 5.0,
        },
        "errors": [],
        "diff": None,
        "report_path": "report.json",
        "results_path": "results.jsonl",
    }


class TestBuildCandidateComparisons:
    def test_single_candidate_no_parent_no_front(self) -> None:
        """First round: one candidate, no parent, empty front."""
        score_reports = {
            "v1": _make_report_dict(accuracy=0.80, cost=1.50),
        }
        mutation_descriptions = {"v1": "Initial compilation"}
        parent_versions = {"v1": None}

        result = build_candidate_comparisons(
            score_reports=score_reports,
            mutation_descriptions=mutation_descriptions,
            parent_versions=parent_versions,
            primary_metric="accuracy",
        )

        assert len(result) == 1
        assert result[0].candidate_version == "v1"
        assert result[0].parent_version is None
        assert result[0].delta_vs_parent.quality_delta is None

    def test_candidate_with_parent(self) -> None:
        """Later round: candidate has parent."""
        score_reports = {
            "v3": _make_report_dict(accuracy=0.85, cost=1.20),
            "v2": _make_report_dict(accuracy=0.82, cost=1.30),  # parent
        }
        mutation_descriptions = {"v3": "Swapped Example 3"}
        parent_versions = {"v3": "v2"}

        result = build_candidate_comparisons(
            score_reports=score_reports,
            mutation_descriptions=mutation_descriptions,
            parent_versions=parent_versions,
            primary_metric="accuracy",
        )

        assert len(result) == 1
        ca = result[0]
        assert ca.candidate_version == "v3"
        assert ca.delta_vs_parent.quality_delta == pytest.approx(0.03)
        assert ca.delta_vs_parent.cost_delta == pytest.approx(-0.10)

    def test_multiple_candidates(self) -> None:
        """Multiple candidates in one round."""
        score_reports = {
            "v3": _make_report_dict(accuracy=0.85, cost=1.20),
            "v4": _make_report_dict(accuracy=0.83, cost=1.10),
            "v2": _make_report_dict(accuracy=0.82, cost=1.30),
        }
        mutation_descriptions = {
            "v3": "Swapped Example 3",
            "v4": "Pruned Rule 2",
        }
        parent_versions = {"v3": "v2", "v4": "v2"}

        result = build_candidate_comparisons(
            score_reports=score_reports,
            mutation_descriptions=mutation_descriptions,
            parent_versions=parent_versions,
            primary_metric="accuracy",
        )

        assert len(result) == 2
        versions = {ca.candidate_version for ca in result}
        assert versions == {"v3", "v4"}


class TestExtractPerClassRecall:
    def test_single_round_no_regression(self) -> None:
        current_reports = {
            "v1": {
                "metrics": {
                    "recall/model-a": 0.9,
                    "recall/model-b": 0.7,
                    "support/model-a": 15,
                    "support/model-b": 5,
                },
            },
        }
        historical: dict[int, dict[str, dict[str, Any]]] = {}

        result = extract_per_class_recall(
            current_reports=current_reports,
            historical_reports=historical,
            current_round=1,
        )

        assert "model-a" in result
        assert result["model-a"].recall == 0.9
        assert result["model-a"].support == 15
        assert result["model-a"].trend == [0.9]
        assert result["model-a"].regression_flag is False

    def test_multiple_rounds_with_regression(self) -> None:
        historical = {
            1: {"v1": {"metrics": {"recall/model-b": 0.8, "support/model-b": 5}}},
            2: {"v2": {"metrics": {"recall/model-b": 0.75, "support/model-b": 5}}},
        }
        current_reports = {
            "v3": {"metrics": {"recall/model-b": 0.6, "support/model-b": 5}},
        }

        result = extract_per_class_recall(
            current_reports=current_reports,
            historical_reports=historical,
            current_round=3,
        )

        assert result["model-b"].recall == 0.6
        assert result["model-b"].trend == [0.8, 0.75, 0.6]
        assert result["model-b"].regression_flag is True

    def test_best_candidate_used_per_round(self) -> None:
        """When multiple candidates exist in a round, use the best recall per class."""
        current_reports = {
            "v3": {"metrics": {"recall/model-a": 0.85, "support/model-a": 10}},
            "v4": {"metrics": {"recall/model-a": 0.90, "support/model-a": 10}},
        }

        result = extract_per_class_recall(
            current_reports=current_reports,
            historical_reports={},
            current_round=1,
        )

        assert result["model-a"].recall == 0.90


class TestComputeDiversityMetrics:
    def test_identical_prompts(self) -> None:
        prompt_texts = {
            "v1": "## Rules\n1. Route to A\n\n## Examples\n### Example 1\nfoo",
            "v2": "## Rules\n1. Route to A\n\n## Examples\n### Example 1\nfoo",
        }
        result = compute_diversity_metrics(
            prompt_texts=prompt_texts,
        )
        assert result.example_overlap_ratio == 1.0  # fully overlapping

    def test_completely_different_prompts(self) -> None:
        prompt_texts = {
            "v1": "## Rules\n1. Route to A\n\n## Examples\n### Example 1\nalpha",
            "v2": "## Rules\n1. Route to Z\n\n## Examples\n### Example 9\nomega",
        }
        result = compute_diversity_metrics(
            prompt_texts=prompt_texts,
        )
        assert result.example_overlap_ratio < 1.0

    def test_single_prompt_on_front(self) -> None:
        result = compute_diversity_metrics(
            prompt_texts={"v1": "## Rules\n1. Route to A"},
        )
        assert result.example_overlap_ratio == 1.0


class TestComputeDiminishingReturns:
    def test_improving_trajectory(self) -> None:
        result = compute_diminishing_returns(
            score_trajectory=[0.70, 0.75, 0.80, 0.85],
            stagnation_threshold=0.005,
        )
        assert result.improvement_trend > 0.01
        assert result.stagnation_flag is False

    def test_stagnating_trajectory(self) -> None:
        result = compute_diminishing_returns(
            score_trajectory=[0.85, 0.851, 0.852, 0.852],
            stagnation_threshold=0.005,
        )
        assert result.improvement_trend < 0.005
        assert result.stagnation_flag is True

    def test_single_point(self) -> None:
        result = compute_diminishing_returns(
            score_trajectory=[0.80],
            stagnation_threshold=0.005,
        )
        assert result.improvement_trend == 0.0
        assert result.stagnation_flag is False  # Can't determine stagnation from one point

    def test_empty_trajectory(self) -> None:
        result = compute_diminishing_returns(
            score_trajectory=[],
            stagnation_threshold=0.005,
        )
        assert result.improvement_trend == 0.0
        assert result.stagnation_flag is False

    def test_window_uses_last_7_values_of_8_round_trajectory(self) -> None:
        """8-element trajectory → window is last 7 → 6 deltas used for trend."""
        # Trajectory where only the last 7 values matter
        # First value ignored, rest are perfectly linear: +0.01 each step
        trajectory = [0.50, 0.70, 0.71, 0.72, 0.73, 0.74, 0.75, 0.76]
        result = compute_diminishing_returns(
            score_trajectory=trajectory,
            stagnation_threshold=0.005,
        )
        # Window: last 7 = [0.70, 0.71, 0.72, 0.73, 0.74, 0.75, 0.76]
        # 6 deltas each = 0.01 → trend = 0.01
        assert result.improvement_trend == pytest.approx(0.01)

    def test_improvement_stddev_computed_for_known_trajectory(self) -> None:
        """For a trajectory with known deltas, verify stddev is non-zero and correct."""
        import statistics

        # Deltas: [0.10, 0.20] → pstdev
        trajectory = [0.50, 0.60, 0.80]
        result = compute_diminishing_returns(
            score_trajectory=trajectory,
            stagnation_threshold=0.005,
        )
        expected_stddev = statistics.pstdev([0.10, 0.20])
        assert result.improvement_stddev == pytest.approx(expected_stddev)

    def test_effective_threshold_passed_through(self) -> None:
        """effective_threshold on the result matches the stagnation_threshold argument."""
        result = compute_diminishing_returns(
            score_trajectory=[0.80, 0.81],
            stagnation_threshold=0.012,
        )
        assert result.effective_threshold == pytest.approx(0.012)

    def test_relative_threshold_high_best_score(self) -> None:
        """best_score=0.95 → effective_threshold = max(0.005, 0.01 * 0.95) = 0.0095."""
        best_score = 0.95
        effective_threshold = max(0.005, 0.01 * best_score)
        assert effective_threshold == pytest.approx(0.0095)
        result = compute_diminishing_returns(
            score_trajectory=[0.94, 0.95],
            stagnation_threshold=effective_threshold,
        )
        assert result.effective_threshold == pytest.approx(0.0095)

    def test_relative_threshold_low_best_score_uses_floor(self) -> None:
        """best_score=0.40 → effective_threshold = max(0.005, 0.01 * 0.40) = 0.005 (floor)."""
        best_score = 0.40
        effective_threshold = max(0.005, 0.01 * best_score)
        assert effective_threshold == pytest.approx(0.005)
        result = compute_diminishing_returns(
            score_trajectory=[0.39, 0.40],
            stagnation_threshold=effective_threshold,
        )
        assert result.effective_threshold == pytest.approx(0.005)


# ---------------------------------------------------------------------------
# compute_near_misses
# ---------------------------------------------------------------------------


def _cand(
    version: str,
    quality_score: float,
    cost: float,
    round_introduced: int = 1,
) -> Candidate:
    return Candidate(
        prompt_version=version,
        parent_version=None,
        quality_score=quality_score,
        cost=cost,
        round_introduced=round_introduced,
    )


class TestComputeNearMisses:
    def test_empty_candidates_returns_empty(self) -> None:
        front = [_cand("f1", quality_score=0.9, cost=0.01)]
        result = compute_near_misses([], front)
        assert result == []

    def test_candidate_on_front_is_excluded(self) -> None:
        """A candidate whose version is in the front should not appear in near-misses."""
        f1 = _cand("f1", quality_score=0.9, cost=0.01)
        result = compute_near_misses([f1], [f1])
        assert result == []

    def test_dominated_candidate_included_with_gap(self) -> None:
        """A dominated candidate is a near-miss; gap values reflect domination distance."""
        f1 = _cand("f1", quality_score=0.9, cost=0.01)
        dominated = _cand("d1", quality_score=0.8, cost=0.05)
        result = compute_near_misses([dominated], [f1])
        assert len(result) == 1
        nm = result[0]
        assert nm.version == "d1"
        assert nm.domination_gap_quality == pytest.approx(0.9 - 0.8)
        assert nm.domination_gap_cost == pytest.approx(0.05 - 0.01)

    def test_incomparable_candidate_excluded(self) -> None:
        """Incomparable: higher quality but higher cost — not dominated, not on front."""
        f1 = _cand("f1", quality_score=0.8, cost=0.01)
        incomparable = _cand("ic1", quality_score=0.9, cost=0.05)
        result = compute_near_misses([incomparable], [f1])
        assert result == []

    def test_multiple_dominators_picks_smallest_combined_gap(self) -> None:
        """When multiple front members dominate, picks the one with smallest total gap."""
        # f1: quality=0.85, cost=0.02 → gaps: quality=0.05, cost=0.01, total=0.06
        # f2: quality=0.90, cost=0.05 → gaps: quality=0.10, cost=0.04, total=0.14
        f1 = _cand("f1", quality_score=0.85, cost=0.02)
        f2 = _cand("f2", quality_score=0.90, cost=0.05)
        dominated = _cand("d1", quality_score=0.80, cost=0.06)
        result = compute_near_misses([dominated], [f1, f2])
        assert len(result) == 1
        nm = result[0]
        # f1 has smaller combined gap
        assert nm.domination_gap_quality == pytest.approx(0.05)
        assert nm.domination_gap_cost == pytest.approx(0.04)


class TestComputeOracleMetrics:
    def test_normal_case(self) -> None:
        result = compute_oracle_metrics(
            oracle_cost_change=0.50,
            oracle_quality_change=0.10,
            candidate_cost_change=0.35,
            candidate_cost_change_with_overhead=0.30,
            candidate_quality_change=0.085,
        )
        assert result.oracle_cost_change == 0.50
        assert result.candidate_cost_captured == pytest.approx(0.70)
        assert result.candidate_cost_captured_with_overhead == pytest.approx(0.60)
        assert result.candidate_quality_captured == pytest.approx(0.85)

    def test_zero_oracle_returns_none(self) -> None:
        result = compute_oracle_metrics(
            oracle_cost_change=0.0,
            oracle_quality_change=0.0,
            candidate_cost_change=0.10,
            candidate_cost_change_with_overhead=0.08,
            candidate_quality_change=0.05,
        )
        assert result.candidate_cost_captured is None
        assert result.candidate_cost_captured_with_overhead is None
        assert result.candidate_quality_captured is None

    def test_partial_zero(self) -> None:
        result = compute_oracle_metrics(
            oracle_cost_change=0.50,
            oracle_quality_change=0.0,
            candidate_cost_change=0.25,
            candidate_cost_change_with_overhead=0.20,
            candidate_quality_change=0.0,
        )
        assert result.candidate_cost_captured == pytest.approx(0.50)
        assert result.candidate_cost_captured_with_overhead == pytest.approx(0.40)
        assert result.candidate_quality_captured is None

    def test_missing_metrics_returns_none(self) -> None:
        """compute_oracle_metrics_from_report returns None if keys are absent."""
        assert compute_oracle_metrics_from_report(metrics={}) is None


def _make_search_state(**overrides: Any) -> SearchState:
    """Helper to build a minimal SearchState for tests."""
    defaults: dict[str, Any] = dict(
        search_state_id="test-search",
        backend="anthropic",
        round=1,
        elite_set=[],
        round_history=[],
        stagnation_count=0,
        stagnation_limit=3,
        convergence_limit=5,
        max_rounds=50,
        mutation_mode="targeted",
        converged=False,
    )
    defaults.update(overrides)
    return SearchState(**defaults)


class TestBuildReviewBriefing:
    def test_builds_complete_briefing(self) -> None:
        """Integration test: all components assembled into a ReviewBriefing."""
        search_state = _make_search_state(
            round=2,
            elite_set=[
                Candidate(
                    prompt_version="v1",
                    parent_version=None,
                    quality_score=0.80,
                    cost=1.50,
                    round_introduced=1,
                ),
            ],
        )
        score_reports = {
            "v2": _make_report_dict(
                accuracy=0.85,
                cost=1.20,
                **{
                    "recall/model-a": 0.9,
                    "support/model-a": 10,
                    "oracle_cost_change": 0.50,
                    "oracle_quality_change": 0.10,
                    "cost_change": 0.35,
                    "cost_change_with_overhead": 0.30,
                    "quality_change": 0.085,
                },
            ),
            "v1": _make_report_dict(
                accuracy=0.80,
                cost=1.50,
                **{
                    "recall/model-a": 0.85,
                    "support/model-a": 10,
                    "oracle_cost_change": 0.50,
                    "oracle_quality_change": 0.10,
                    "cost_change": 0.20,
                    "cost_change_with_overhead": 0.15,
                    "quality_change": 0.05,
                },
            ),
        }
        historical_reports = {
            1: {
                "v1": score_reports["v1"],
            },
        }
        prompt_texts = {
            "v1": "## Rules\n1. Route to A\n\n## Examples\n### Example 1\nfoo",
            "v2": "## Rules\n1. Route to A\n2. Prefer B for complex\n\n## Examples\n### Example 1\nfoo",
        }

        briefing = build_review_briefing(
            search_state=search_state,
            score_reports=score_reports,
            historical_reports=historical_reports,
            prompt_texts=prompt_texts,
            directive_history=[],
            candidate_versions=["v2"],
            parent_versions={"v2": "v1"},
        )

        assert briefing.round == 2
        assert len(briefing.candidates) == 1
        assert briefing.candidates[0].candidate_version == "v2"
        assert briefing.oracle_metrics.oracle_cost_change == 0.50
        assert briefing.oracle_metrics.candidate_cost_captured is not None
        assert len(briefing.per_class_recall) > 0
        assert "model-a" in briefing.per_class_recall

        # New fields
        assert briefing.executive_summary != ""
        assert briefing.directive_history == []
        assert briefing.routing_context is None


def _make_empty_metrics_report() -> dict[str, Any]:
    """Build a ScoreReport-compatible dict with no metrics."""
    now = datetime.now(tz=UTC).isoformat()
    return {
        "metrics": {},
        "summary": {
            "total": 10,
            "succeeded": 0,
            "failed": 10,
            "total_cost": 0.0,
            "start_time": now,
            "end_time": now,
            "duration_seconds": 5.0,
        },
        "errors": [],
        "diff": None,
        "report_path": "report.json",
        "results_path": "results.jsonl",
    }


class TestExtractMetric:
    def test_missing_metric_returns_none(self) -> None:
        report: dict[str, Any] = {"metrics": {}}
        assert _extract_metric(report, "accuracy") is None

    def test_missing_metrics_key_returns_none(self) -> None:
        report: dict[str, Any] = {}
        assert _extract_metric(report, "accuracy") is None

    def test_zero_returns_zero(self) -> None:
        report: dict[str, Any] = {"metrics": {"accuracy": 0.0}}
        assert _extract_metric(report, "accuracy") == 0.0

    def test_present_metric_returns_value(self) -> None:
        report: dict[str, Any] = {"metrics": {"accuracy": 0.85}}
        assert _extract_metric(report, "accuracy") == 0.85


class TestDelta:
    def test_both_present(self) -> None:
        assert _delta(0.85, 0.80) == pytest.approx(0.05)

    def test_first_none(self) -> None:
        assert _delta(None, 0.80) is None

    def test_second_none(self) -> None:
        assert _delta(0.85, None) is None

    def test_both_none(self) -> None:
        assert _delta(None, None) is None


class TestMissingMetricBehavior:
    def test_candidate_comparison_missing_metric(self) -> None:
        """Candidate missing primary metric yields quality_delta=None."""
        score_reports = {
            "v2": _make_empty_metrics_report(),
            "v1": _make_report_dict(accuracy=0.80, cost=1.50),
        }
        result = build_candidate_comparisons(
            score_reports=score_reports,
            mutation_descriptions={"v2": "test mutation"},
            parent_versions={"v2": "v1"},
            primary_metric="accuracy",
        )
        assert len(result) == 1
        assert result[0].delta_vs_parent.quality_delta is None
        assert result[0].delta_vs_parent.cost_delta is None

    def test_recall_deltas_skips_absent_reference(self) -> None:
        """Reference lacks a recall key — that class should be skipped."""
        from odysseus.agents.review.preprocessor import _compute_recall_deltas

        candidate = {"metrics": {"recall/route-a": 0.9, "recall/route-b": 0.7}}
        reference = {"metrics": {"recall/route-a": 0.85}}  # no route-b

        deltas = _compute_recall_deltas(candidate, reference)
        assert "route-a" in deltas
        assert deltas["route-a"] == pytest.approx(0.05)
        assert "route-b" not in deltas  # skipped, not defaulted to 0.0

    def test_build_review_briefing_with_missing_metric(self) -> None:
        """End-to-end: briefing assembles without crashing when a candidate has no primary metric."""
        search_state = _make_search_state(
            round=2,
            elite_set=[
                Candidate(
                    prompt_version="v1",
                    parent_version=None,
                    quality_score=0.80,
                    cost=1.50,
                    round_introduced=1,
                ),
            ],
        )
        score_reports = {
            "v2": _make_empty_metrics_report(),
            "v1": _make_report_dict(accuracy=0.80, cost=1.50),
        }

        briefing = build_review_briefing(
            search_state=search_state,
            score_reports=score_reports,
            historical_reports={1: {"v1": score_reports["v1"]}},
            prompt_texts={"v1": "prompt v1", "v2": "prompt v2"},
            directive_history=[],
            candidate_versions=["v2"],
            parent_versions={"v2": "v1"},
        )

        assert briefing.round == 2
        assert len(briefing.candidates) == 1
        assert briefing.candidates[0].delta_vs_parent.quality_delta is None


class TestGenerateExecutiveSummary:
    def _make_briefing(self, **overrides: Any) -> Any:
        """Build a minimal ReviewBriefing for summary tests."""
        from odysseus.agents.review.models import (
            CandidateAnalysis,
            DiminishingReturns,
            DiversityMetrics,
            MetricDeltas,
            ReviewBriefing,
        )
        from odysseus.eval.models import ScoreReport

        default_score_report = ScoreReport.model_validate(_make_report_dict(accuracy=0.85, cost=1.20))

        defaults: dict[str, Any] = dict(
            round=3,
            candidates=[
                CandidateAnalysis(
                    candidate_version="v3",
                    parent_version="v2",
                    mutation_description="Swapped example 3",
                    score_report=default_score_report,
                    delta_vs_parent=MetricDeltas(
                        quality_delta=0.03,
                        cost_delta=-0.10,
                        per_class_recall_deltas={"model-a": 0.05},
                    ),
                ),
            ],
            elite_set=[],
            per_class_recall={},
            diversity_metrics=DiversityMetrics(
                example_overlap_ratio=0.3,
            ),
            diminishing_returns=DiminishingReturns(
                score_trajectory=[0.78, 0.82, 0.85],
                improvement_trend=0.035,
                stagnation_flag=False,
            ),
            oracle_metrics=None,
        )
        defaults.update(overrides)
        return ReviewBriefing(**defaults)

    def test_includes_round_info(self) -> None:
        briefing = self._make_briefing(round=5)
        summary = generate_executive_summary(briefing)
        assert "Round 5" in summary

    def test_includes_best_candidate(self) -> None:
        briefing = self._make_briefing()
        summary = generate_executive_summary(briefing)
        assert "v3" in summary
        assert "+0.030" in summary or "+0.03" in summary

    def test_flags_regressions(self) -> None:
        from odysseus.agents.review.models import ClassRecallEntry

        briefing = self._make_briefing(
            per_class_recall={
                "route-a": ClassRecallEntry(
                    recall=0.42,
                    support=8,
                    trend=[0.71, 0.42],
                    regression_flag=True,
                ),
            },
        )
        summary = generate_executive_summary(briefing)
        assert "REGRESSION" in summary
        assert "route-a" in summary
        assert "0.42" in summary

    def test_reports_oracle_gap(self) -> None:
        from odysseus.agents.review.models import OracleMetrics

        briefing = self._make_briefing(
            oracle_metrics=OracleMetrics(
                oracle_cost_change=0.50,
                oracle_quality_change=0.10,
                candidate_cost_captured=0.70,
                candidate_quality_captured=0.85,
            ),
        )
        summary = generate_executive_summary(briefing)
        assert "85%" in summary
        assert "70%" in summary

    def test_warns_stagnation(self) -> None:
        from odysseus.agents.review.models import DiminishingReturns

        briefing = self._make_briefing(
            diminishing_returns=DiminishingReturns(
                score_trajectory=[0.85, 0.851, 0.852],
                improvement_trend=0.001,
                stagnation_flag=True,
            ),
        )
        summary = generate_executive_summary(briefing)
        assert "Stagnation flag is set" in summary

    def test_no_crash_on_minimal_briefing(self) -> None:
        """Minimal briefing with no candidates produces a non-crashing summary."""
        briefing = self._make_briefing(candidates=[])
        summary = generate_executive_summary(briefing)
        assert "Round 3" in summary


class TestExampleSummaryInputText:
    def test_input_text_round_trips(self) -> None:
        from odysseus.agents.review.models import ExampleSummary

        es = ExampleSummary(example_id="h1", route="model-a", input_text="Hello world")
        data = es.model_dump()
        restored = ExampleSummary.model_validate(data)
        assert restored.input_text == "Hello world"

    def test_input_text_defaults_to_none(self) -> None:
        from odysseus.agents.review.models import ExampleSummary

        es = ExampleSummary(example_id="h1", route="model-a")
        assert es.input_text is None


# ---------------------------------------------------------------------------
# build_review_briefing — stagnation_signal and strategy-specific fields
# (Increment 4)
# ---------------------------------------------------------------------------


class TestBuildReviewBriefingStagnationSignal:
    """Tests that build_review_briefing populates stagnation_signal for hill-climb."""

    def _make_hillclimb_briefing(self, **state_overrides: Any) -> Any:
        base_state_kwargs: dict[str, Any] = dict(
            round=3,
            elite_set=[
                Candidate(
                    prompt_version="v1",
                    parent_version=None,
                    quality_score=0.80,
                    cost=1.50,
                    round_introduced=1,
                ),
            ],
            stagnation_count=2,
            stagnation_limit=3,
            mutation_mode="exploratory",
        )
        base_state_kwargs.update(state_overrides)
        search_state = _make_search_state(**base_state_kwargs)
        score_reports = {
            "v2": _make_report_dict(accuracy=0.82, cost=1.40),
            "v1": _make_report_dict(accuracy=0.80, cost=1.50),
        }
        return build_review_briefing(
            search_state=search_state,
            score_reports=score_reports,
            historical_reports={1: {"v1": score_reports["v1"]}},
            prompt_texts={"v1": "prompt v1", "v2": "prompt v2"},
            directive_history=[],
            candidate_versions=["v2"],
            parent_versions={"v2": "v1"},
        )

    def test_stagnation_signal_present(self) -> None:
        """build_review_briefing populates stagnation_signal for hill-climb."""
        briefing = self._make_hillclimb_briefing()
        assert briefing.stagnation_signal is not None

    def test_stagnation_signal_has_three_keys(self) -> None:
        """Hill-climb stagnation_signal has count, limit, and mutation_mode."""
        briefing = self._make_hillclimb_briefing()
        sig = briefing.stagnation_signal
        assert "count" in sig
        assert "limit" in sig
        assert "mutation_mode" in sig

    def test_stagnation_signal_values_match_state(self) -> None:
        """Stagnation signal values reflect SearchState fields."""
        briefing = self._make_hillclimb_briefing()
        sig = briefing.stagnation_signal
        assert sig["count"] == 2
        assert sig["limit"] == 3
        assert sig["mutation_mode"] == "exploratory"

    def test_stagnation_signal_targeted_mode(self) -> None:
        briefing = self._make_hillclimb_briefing(stagnation_count=0, mutation_mode="targeted")
        sig = briefing.stagnation_signal
        assert sig["count"] == 0
        assert sig["mutation_mode"] == "targeted"

    def test_strategy_specific_fields_are_none_for_hillclimb(self) -> None:
        """All strategy-specific optional fields should be None on hill-climb output."""
        briefing = self._make_hillclimb_briefing()
        assert briefing.parent_a_version is None
        assert briefing.parent_b_version is None
        assert briefing.beam_rank is None
        assert briefing.crowding_distance is None
        assert briefing.trajectory_id is None
        assert briefing.weight_vector is None
        assert briefing.binding_axis is None
        assert briefing.acceptance_history is None
        assert briefing.hypervolume is None
        assert briefing.reference_point is None
