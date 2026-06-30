# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Tests for compass.agents.review_preprocessor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from compass.agents.prompt_builder.search import Candidate, SearchState
from compass.agents.review.preprocessor import (
    _delta,
    _extract_metric,
    _synthesize_directive_outcomes,
    build_candidate_comparisons,
    build_confusion_analysis,
    build_review_briefing,
    compute_diminishing_returns,
    compute_diversity_metrics,
    compute_near_misses,
    compute_oracle_metrics,
    compute_oracle_metrics_from_report,
    extract_per_class_recall,
    generate_executive_summary,
    parse_evaluation_budget,
    parse_user_targets,
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
        parent_versions: dict[str, str | None] = {"v1": None}

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
        parent_versions: dict[str, str | None] = {"v3": "v2"}

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
        parent_versions: dict[str, str | None] = {"v3": "v2", "v4": "v2"}

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
        # candidate quality_change=0.085, oracle=0.10 → ratio = (1 + 0.085)/(1 + 0.10) = 1.085/1.10
        assert result.candidate_quality_captured == pytest.approx(1.085 / 1.10)

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
            candidate_versions=["v2"],
            parent_versions={"v2": "v1"},
        )

        assert briefing.round == 2
        assert len(briefing.candidates) == 1
        assert briefing.candidates[0].candidate_version == "v2"
        assert briefing.oracle_metrics is not None
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
        from compass.agents.review.preprocessor import _compute_recall_deltas

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
            candidate_versions=["v2"],
            parent_versions={"v2": "v1"},
        )

        assert briefing.round == 2
        assert len(briefing.candidates) == 1
        assert briefing.candidates[0].delta_vs_parent.quality_delta is None

    def test_confusion_analysis_populated_when_results_provided(self) -> None:
        from compass.eval.models import EvalResult, Example, Expected, ModelCostQuality

        search_state = _make_search_state(
            round=2,
            elite_set=[
                Candidate(prompt_version="v1", parent_version=None, quality_score=0.80, cost=1.50, round_introduced=1),
            ],
        )
        score_reports = {
            "v2": _make_report_dict(accuracy=0.85, cost=1.20),
            "v1": _make_report_dict(accuracy=0.80, cost=1.50),
        }
        routes = {
            "simple": ModelCostQuality(cost=0.01, quality_score=0.80),
            "complex": ModelCostQuality(cost=0.10, quality_score=0.95),
        }
        examples = [
            Example(id="e1", input="a", expected=Expected(route="simple", routes=routes)),
            Example(id="e2", input="b", expected=Expected(route="simple", routes=routes)),
        ]
        eval_results = [
            EvalResult(
                example_id="e1",
                model="test",
                output={"route": "complex"},
                error=None,
                latency_ms=100,
                retries=0,
                token_usage=None,
                cost=0.01,
            ),
            EvalResult(
                example_id="e2",
                model="test",
                output={"route": "simple"},
                error=None,
                latency_ms=100,
                retries=0,
                token_usage=None,
                cost=0.01,
            ),
        ]
        briefing = build_review_briefing(
            search_state=search_state,
            score_reports=score_reports,
            historical_reports={1: {"v1": score_reports["v1"]}},
            prompt_texts={"v1": "p1", "v2": "p2"},
            candidate_versions=["v2"],
            parent_versions={"v2": "v1"},
            eval_results=eval_results,
            examples=examples,
        )
        assert len(briefing.confusion_analysis) == 1
        assert briefing.confusion_analysis[0].true_route == "simple"
        assert briefing.confusion_analysis[0].predicted_route == "complex"

    def test_confusion_analysis_empty_when_no_results(self) -> None:
        search_state = _make_search_state(
            round=2,
            elite_set=[
                Candidate(prompt_version="v1", parent_version=None, quality_score=0.80, cost=1.50, round_introduced=1),
            ],
        )
        score_reports = {
            "v2": _make_report_dict(accuracy=0.85),
            "v1": _make_report_dict(accuracy=0.80),
        }
        briefing = build_review_briefing(
            search_state=search_state,
            score_reports=score_reports,
            historical_reports={1: {"v1": score_reports["v1"]}},
            prompt_texts={"v1": "p1", "v2": "p2"},
            candidate_versions=["v2"],
            parent_versions={"v2": "v1"},
        )
        assert briefing.confusion_analysis == []


class TestGenerateExecutiveSummary:
    def _make_briefing(self, **overrides: Any) -> Any:
        """Build a minimal ReviewBriefing for summary tests."""
        from compass.agents.review.models import (
            CandidateAnalysis,
            DiminishingReturns,
            DiversityMetrics,
            MetricDeltas,
            ReviewBriefing,
        )
        from compass.eval.models import ScoreReport

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
        from compass.agents.review.models import ClassRecallEntry

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
        from compass.agents.review.models import OracleMetrics

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
        from compass.agents.review.models import DiminishingReturns

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

    def test_includes_confusion_analysis(self) -> None:
        from compass.agents.review.models import ConfusionImpact

        briefing = self._make_briefing()
        ci = ConfusionImpact(
            true_route="simple",
            predicted_route="complex",
            count=10,
            support=40,
            misroute_rate=0.25,
            cost_impact=0.50,
            quality_impact=-0.10,
            avg_cost_impact=0.05,
            avg_quality_impact=-0.01,
            persistence_rate=0.85,
            persistent_count=8,
            volatile_count=2,
        )
        briefing = briefing.model_copy(update={"confusion_analysis": [ci]})
        summary = generate_executive_summary(briefing)
        assert "CONFUSION: simple->complex" in summary
        assert "structural" in summary


class TestExampleSummaryInputText:
    def test_input_text_round_trips(self) -> None:
        from compass.agents.review.models import ExampleSummary

        es = ExampleSummary(example_id="h1", route="model-a", input_text="Hello world")
        data = es.model_dump()
        restored = ExampleSummary.model_validate(data)
        assert restored.input_text == "Hello world"

    def test_input_text_defaults_to_none(self) -> None:
        from compass.agents.review.models import ExampleSummary

        es = ExampleSummary(example_id="h1", route="model-a")
        assert es.input_text is None


# ---------------------------------------------------------------------------
# build_review_briefing — stagnation_signal and strategy-specific fields
# (Increment 4)
# ---------------------------------------------------------------------------


class TestBuildReviewBriefingStagnationSignal:
    """Tests that build_review_briefing populates stagnation_signal for beam."""

    def _make_beam_briefing(self, **state_overrides: Any) -> Any:
        algorithm_state: dict[str, Any] = {
            "beam_width": 3,
            "hypervolume": 0.5,
            "prev_hypervolume": 0.4,
            "backtrack_threshold": 2,
            "reference_point": [0.6, 2.0],
        }
        base_state_kwargs: dict[str, Any] = dict(
            round=3,
            algorithm="beam",
            algorithm_state=algorithm_state,
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
            candidate_versions=["v2"],
            parent_versions={"v2": "v1"},
        )

    def test_stagnation_signal_present(self) -> None:
        """build_review_briefing populates stagnation_signal for beam."""
        briefing = self._make_beam_briefing()
        assert briefing.stagnation_signal is not None

    def test_stagnation_signal_has_three_keys(self) -> None:
        """Beam stagnation_signal has hypervolume_delta and backtrack_threshold."""
        briefing = self._make_beam_briefing()
        sig = briefing.stagnation_signal
        assert "hypervolume_delta" in sig
        assert "backtrack_threshold" in sig

    def test_stagnation_signal_values_match_state(self) -> None:
        """Beam stagnation signal values reflect algorithm_state pocket."""
        briefing = self._make_beam_briefing()
        sig = briefing.stagnation_signal
        # hypervolume - prev_hypervolume = 0.5 - 0.4 = 0.1
        assert abs(sig["hypervolume_delta"] - 0.1) < 1e-9
        assert sig["backtrack_threshold"] == 2

    def test_stagnation_signal_targeted_mode(self) -> None:
        """Beam stagnation signal is unaffected by mutation_mode (beam-specific)."""
        briefing = self._make_beam_briefing(stagnation_count=0, mutation_mode="targeted")
        sig = briefing.stagnation_signal
        assert "hypervolume_delta" in sig

    def test_strategy_specific_fields_are_none_for_no_parent_versions(self) -> None:
        """Strategy-specific optional fields are absent / None when not set."""
        briefing = self._make_beam_briefing()
        assert briefing.parent_a_version is None


class TestBuildConfusionAnalysis:
    def _make_example(self, eid: str, route: str, routes: dict[str, tuple[float, float]]) -> Any:
        """Helper: routes dict is {route_name: (cost, quality_score)}."""
        from compass.eval.models import Example, Expected, ModelCostQuality

        return Example(
            id=eid,
            input=f"input for {eid}",
            expected=Expected(
                route=route,
                routes={name: ModelCostQuality(cost=c, quality_score=q) for name, (c, q) in routes.items()},
            ),
        )

    def _make_result(self, eid: str, route: str) -> Any:
        from compass.eval.models import EvalResult

        return EvalResult(
            example_id=eid,
            model="test",
            output={"route": route},
            error=None,
            latency_ms=100.0,
            retries=0,
            token_usage=None,
            cost=0.01,
        )

    @staticmethod
    def _write_results(run_dir: Any, version: str, results: list[Any]) -> None:
        """Write results.jsonl for a version to disk."""
        import json

        eval_dir = run_dir / "eval" / version
        eval_dir.mkdir(parents=True, exist_ok=True)
        with open(eval_dir / "results.jsonl", "w") as f:
            f.write(
                json.dumps(
                    {
                        "__meta__": "run_fingerprint",
                        "prompt_version": version,
                        "backend": "test",
                        "data_source": "test",
                    }
                )
                + "\n"
            )
            for r in results:
                f.write(r.model_dump_json() + "\n")

    def test_basic_impact_computation(self) -> None:
        """3 examples (2 simple, 1 complex), 1 misrouted (simple->complex)."""
        examples = [
            self._make_example("e1", "simple", {"simple": (0.01, 0.80), "complex": (0.10, 0.95)}),
            self._make_example("e2", "simple", {"simple": (0.01, 0.80), "complex": (0.10, 0.95)}),
            self._make_example("e3", "complex", {"simple": (0.01, 0.80), "complex": (0.10, 0.95)}),
        ]
        results = [
            self._make_result("e1", "complex"),  # misrouted
            self._make_result("e2", "simple"),  # correct
            self._make_result("e3", "complex"),  # correct
        ]
        cells = build_confusion_analysis(
            eval_results=results,
            examples=examples,
            elite_versions=[],
            parent_versions=[],
            run_dir=None,
        )
        assert len(cells) == 1
        cell = cells[0]
        assert cell.true_route == "simple"
        assert cell.predicted_route == "complex"
        assert cell.count == 1
        assert cell.support == 2  # 2 examples with true_route=simple
        assert cell.cost_impact == pytest.approx(0.09)  # 0.10 - 0.01
        assert cell.quality_impact == pytest.approx(0.15)  # 0.95 - 0.80

    def test_empty_results(self) -> None:
        """Empty inputs -> empty list."""
        cells = build_confusion_analysis(
            eval_results=[],
            examples=[],
            elite_versions=[],
            parent_versions=[],
            run_dir=None,
        )
        assert cells == []

    def test_no_misclassifications(self) -> None:
        """All correct -> empty list."""
        examples = [
            self._make_example("e1", "simple", {"simple": (0.01, 0.80), "complex": (0.10, 0.95)}),
            self._make_example("e2", "complex", {"simple": (0.01, 0.80), "complex": (0.10, 0.95)}),
        ]
        results = [
            self._make_result("e1", "simple"),
            self._make_result("e2", "complex"),
        ]
        cells = build_confusion_analysis(
            eval_results=results,
            examples=examples,
            elite_versions=[],
            parent_versions=[],
            run_dir=None,
        )
        assert cells == []

    def test_hallucinated_route_excluded(self) -> None:
        """Predicted route not in example's routes dict -> excluded."""
        examples = [
            self._make_example("e1", "simple", {"simple": (0.01, 0.80), "complex": (0.10, 0.95)}),
        ]
        results = [
            self._make_result("e1", "unknown_route"),  # not in routes dict
        ]
        cells = build_confusion_analysis(
            eval_results=results,
            examples=examples,
            elite_versions=[],
            parent_versions=[],
            run_dir=None,
        )
        assert cells == []

    def test_missing_cost_data(self) -> None:
        """Routes with cost=None and quality_score=None -> cost_impact=0.0, quality_impact=0.0."""
        from compass.eval.models import Example, Expected, ModelCostQuality

        examples = [
            Example(
                id="e1",
                input="input",
                expected=Expected(
                    route="simple",
                    routes={
                        "simple": ModelCostQuality(cost=None, quality_score=None),
                        "complex": ModelCostQuality(cost=None, quality_score=None),
                    },
                ),
            )
        ]
        results = [self._make_result("e1", "complex")]
        cells = build_confusion_analysis(
            eval_results=results,
            examples=examples,
            elite_versions=[],
            parent_versions=[],
            run_dir=None,
        )
        assert len(cells) == 1
        assert cells[0].cost_impact == pytest.approx(0.0)
        assert cells[0].quality_impact == pytest.approx(0.0)

    def test_sorted_by_impact_and_capped(self) -> None:
        """Create 25+ distinct cells, verify len <= 20 and sorted descending by impact."""
        from compass.eval.models import EvalResult, Example, Expected, ModelCostQuality

        examples = []
        results = []
        # Create 25 distinct (true, predicted) pairs each with one example
        for i in range(25):
            true_route = f"route_true_{i}"
            pred_route = f"route_pred_{i}"
            cost_diff = (i + 1) * 0.01
            examples.append(
                Example(
                    id=f"e{i}",
                    input=f"input {i}",
                    expected=Expected(
                        route=true_route,
                        routes={
                            true_route: ModelCostQuality(cost=0.01, quality_score=0.5),
                            pred_route: ModelCostQuality(cost=0.01 + cost_diff, quality_score=0.5),
                        },
                    ),
                )
            )
            results.append(
                EvalResult(
                    example_id=f"e{i}",
                    model="test",
                    output={"route": pred_route},
                    error=None,
                    latency_ms=100.0,
                    retries=0,
                    token_usage=None,
                    cost=0.01,
                )
            )

        cells = build_confusion_analysis(
            eval_results=results,
            examples=examples,
            elite_versions=[],
            parent_versions=[],
            run_dir=None,
        )
        assert len(cells) <= 20
        # Verify sorted descending by abs(cost_impact) + abs(quality_impact)
        impacts = [abs(c.cost_impact) + abs(c.quality_impact) for c in cells]
        assert impacts == sorted(impacts, reverse=True)

    # --- Task 4: Persistence tests ---

    def test_persistence_across_versions(self, tmp_path: Any) -> None:
        """Both simple misrouted in best candidate. v1: e1 wrong, e2 correct. v2: both wrong.
        e1 persistent (wrong in all: v1+v2), e2 volatile (correct in v1)."""
        examples = [
            self._make_example("e1", "simple", {"simple": (0.01, 0.80), "complex": (0.10, 0.95)}),
            self._make_example("e2", "simple", {"simple": (0.01, 0.80), "complex": (0.10, 0.95)}),
        ]
        best_results = [
            self._make_result("e1", "complex"),
            self._make_result("e2", "complex"),
        ]
        # v1: e1 wrong, e2 correct
        v1_results = [
            self._make_result("e1", "complex"),
            self._make_result("e2", "simple"),
        ]
        # v2: both wrong
        v2_results = [
            self._make_result("e1", "complex"),
            self._make_result("e2", "complex"),
        ]
        self._write_results(tmp_path, "v1", v1_results)
        self._write_results(tmp_path, "v2", v2_results)

        cells = build_confusion_analysis(
            eval_results=best_results,
            examples=examples,
            elite_versions=["v1"],
            parent_versions=["v2"],
            run_dir=tmp_path,
        )
        assert len(cells) == 1
        cell = cells[0]
        assert cell.count == 2
        assert cell.persistent_count == 1  # e1 persistent, e2 volatile
        assert cell.volatile_count == 1
        assert cell.persistence_rate == pytest.approx(0.5)

    def test_persistence_missing_results_file(self, tmp_path: Any) -> None:
        """Elite version points to nonexistent file -> skipped, persistence_rate=0.0."""
        examples = [
            self._make_example("e1", "simple", {"simple": (0.01, 0.80), "complex": (0.10, 0.95)}),
        ]
        best_results = [self._make_result("e1", "complex")]

        cells = build_confusion_analysis(
            eval_results=best_results,
            examples=examples,
            elite_versions=["v_nonexistent"],
            parent_versions=[],
            run_dir=tmp_path,
        )
        assert len(cells) == 1
        assert cells[0].persistence_rate == pytest.approx(0.0)

    def test_persistence_single_version_fallback(self, tmp_path: Any) -> None:
        """No elite/parent versions, run_dir=None -> persistence_rate=0.0."""
        examples = [
            self._make_example("e1", "simple", {"simple": (0.01, 0.80), "complex": (0.10, 0.95)}),
        ]
        best_results = [self._make_result("e1", "complex")]

        cells = build_confusion_analysis(
            eval_results=best_results,
            examples=examples,
            elite_versions=[],
            parent_versions=[],
            run_dir=None,
        )
        assert len(cells) == 1
        assert cells[0].persistence_rate == pytest.approx(0.0)

    def test_dedupes_overlapping_misroutes(self) -> None:
        """Three EvalResults with same example_id and same wrong route.

        Dedup ensures count == 1 (not 3), and cost/quality impacts reflect
        a single-example contribution.
        """
        example = self._make_example("e1", "simple", {"simple": (0.01, 0.80), "complex": (0.10, 0.95)})
        examples = [example]
        # Three results from three "candidates" — same example_id, same wrong route
        results = [
            self._make_result("e1", "complex"),
            self._make_result("e1", "complex"),
            self._make_result("e1", "complex"),
        ]
        cells = build_confusion_analysis(
            eval_results=results,
            examples=examples,
            elite_versions=[],
            parent_versions=[],
            run_dir=None,
        )
        assert len(cells) == 1
        cell = cells[0]
        support = 1  # only one example with true_route=simple
        assert cell.count == 1  # dedup: not 3
        assert cell.misroute_rate == pytest.approx(1 / support)
        # Single-example cost and quality deltas
        assert cell.cost_impact == pytest.approx(0.10 - 0.01)  # 0.09
        assert cell.quality_impact == pytest.approx(0.95 - 0.80)  # 0.15


class TestSignalToNoiseFilters:
    def test_filter_metric_deltas_basic(self) -> None:
        from compass.agents.review.preprocessor import _filter_metric_deltas

        deltas = {
            "accuracy": 0.05,
            "cost_change": -0.02,
            "recall/route_a": 0.001,  # below threshold
            "confusion/a/b": 3.0,  # confusion key
            "f1/macro": 0.015,
            "recall/route_b": 0.0,  # zero delta
        }
        filtered = _filter_metric_deltas(deltas)
        assert "accuracy" in filtered
        assert "cost_change" in filtered
        assert "f1/macro" in filtered
        assert "recall/route_a" not in filtered
        assert "confusion/a/b" not in filtered
        assert "recall/route_b" not in filtered

    def test_target_metrics_always_kept(self) -> None:
        from compass.agents.review.preprocessor import _filter_metric_deltas

        deltas = {"recall/route_a": 0.005}
        filtered = _filter_metric_deltas(deltas, target_metrics={"recall/route_a"})
        assert "recall/route_a" in filtered

    def test_primary_metrics_kept_even_at_zero(self) -> None:
        from compass.agents.review.preprocessor import _filter_metric_deltas

        deltas = {"accuracy": 0.0}
        filtered = _filter_metric_deltas(deltas)
        assert "accuracy" in filtered

    def test_per_class_recall_trend_truncated(self) -> None:
        """Trend should be limited to last 5 rounds."""
        historical = {}
        for i in range(1, 12):
            historical[i] = {
                "v1": _make_report_dict(
                    **{
                        "recall/route_a": 0.50 + i * 0.02,
                        "support/route_a": 10,
                    }
                )
            }
        current = {
            "v1": _make_report_dict(
                **{
                    "recall/route_a": 0.75,
                    "support/route_a": 10,
                }
            )
        }
        result = extract_per_class_recall(
            current_reports=current,
            historical_reports=historical,
            current_round=12,
        )
        assert len(result["route_a"].trend) <= 5

    def test_diminishing_returns_trajectory_truncated(self) -> None:
        trajectory = [0.5 + i * 0.01 for i in range(15)]
        result = compute_diminishing_returns(score_trajectory=trajectory)
        assert len(result.score_trajectory) <= 8


# ---------------------------------------------------------------------------
# Holistic version selection and single_candidate_meets_all
# ---------------------------------------------------------------------------


class TestHolisticVersionSelection:
    """Tests for the holistic tuple scoring and single_candidate_meets_all flag."""

    def _make_state(self, elite_versions: list[str]) -> Any:
        """Build a minimal SearchState with the given elite set."""
        from compass.agents.prompt_builder.search import Candidate

        return _make_search_state(
            round=2,
            elite_set=[
                Candidate(
                    prompt_version=v,
                    parent_version=None,
                    quality_score=0.80,
                    cost=1.0,
                    round_introduced=1,
                )
                for v in elite_versions
            ],
        )

    def test_holistic_tuple_beats_primary_metric_tie(self) -> None:
        """Candidate B meets more targets than A, so B wins even if A scores higher on primary."""
        from compass.agents.review.models import UserTarget
        from compass.agents.review.preprocessor import build_review_briefing

        user_targets = [
            UserTarget(metric="quality_change", operator=">=", threshold=0.03),
            UserTarget(metric="cost_change_with_overhead", operator="<=", threshold=-0.30),
        ]
        # v_a: high primary (quality) but only meets quality target
        # v_b: lower quality but meets both targets
        score_reports = {
            "v_a": _make_report_dict(
                **{
                    "quality_change": 0.040,  # meets quality target
                    "cost_change_with_overhead": -0.20,  # misses cost target
                    "cost_change": -0.10,
                    "oracle_cost_change": 0.5,
                    "oracle_quality_change": 0.1,
                }
            ),
            "v_b": _make_report_dict(
                **{
                    "quality_change": 0.035,  # meets quality target
                    "cost_change_with_overhead": -0.35,  # meets cost target
                    "cost_change": -0.25,
                    "oracle_cost_change": 0.5,
                    "oracle_quality_change": 0.1,
                }
            ),
        }
        state = self._make_state(["v_a", "v_b"])
        briefing = build_review_briefing(
            search_state=state,
            score_reports=score_reports,
            historical_reports={1: {"v_a": score_reports["v_a"]}},
            prompt_texts={"v_a": "## Rules\n1. foo", "v_b": "## Rules\n1. bar"},
            candidate_versions=["v_a", "v_b"],
            parent_versions={"v_a": None, "v_b": None},
            user_targets=user_targets,
        )
        # v_b meets both targets; v_a meets only one — holistic tuple selects v_b
        sources = {tp.source_version for tp in briefing.target_progress}
        assert sources == {"v_b"}
        assert briefing.single_candidate_meets_all is True

    def test_single_candidate_meets_all_true(self) -> None:
        """Flag is True when the single candidate satisfies every target."""
        from compass.agents.review.models import UserTarget
        from compass.agents.review.preprocessor import build_review_briefing

        user_targets = [
            UserTarget(metric="quality_change", operator=">=", threshold=0.03),
        ]
        score_reports = {
            "v1": _make_report_dict(
                **{
                    "quality_change": 0.05,  # meets target
                    "cost_change": -0.10,
                    "oracle_cost_change": 0.5,
                    "oracle_quality_change": 0.1,
                }
            ),
        }
        state = self._make_state(["v1"])
        briefing = build_review_briefing(
            search_state=state,
            score_reports=score_reports,
            historical_reports={1: {"v1": score_reports["v1"]}},
            prompt_texts={"v1": "## Rules\n1. foo"},
            candidate_versions=["v1"],
            parent_versions={"v1": None},
            user_targets=user_targets,
        )
        assert briefing.single_candidate_meets_all is True

    def test_single_candidate_meets_all_false(self) -> None:
        """Flag is False when at least one target is not met."""
        from compass.agents.review.models import UserTarget
        from compass.agents.review.preprocessor import build_review_briefing

        user_targets = [
            UserTarget(metric="quality_change", operator=">=", threshold=0.10),  # high bar
        ]
        score_reports = {
            "v1": _make_report_dict(
                **{
                    "quality_change": 0.02,  # misses target
                    "cost_change": -0.10,
                    "oracle_cost_change": 0.5,
                    "oracle_quality_change": 0.1,
                }
            ),
        }
        state = self._make_state(["v1"])
        briefing = build_review_briefing(
            search_state=state,
            score_reports=score_reports,
            historical_reports={1: {"v1": score_reports["v1"]}},
            prompt_texts={"v1": "## Rules\n1. foo"},
            candidate_versions=["v1"],
            parent_versions={"v1": None},
            user_targets=user_targets,
        )
        assert briefing.single_candidate_meets_all is False

    def test_source_version_matches_best_version(self) -> None:
        """Every target_progress entry's source_version equals the chosen best version."""
        from compass.agents.review.models import UserTarget
        from compass.agents.review.preprocessor import build_review_briefing

        user_targets = [
            UserTarget(metric="quality_change", operator=">=", threshold=0.03),
            UserTarget(metric="cost_change_with_overhead", operator="<=", threshold=-0.20),
        ]
        score_reports = {
            "v1": _make_report_dict(
                **{
                    "quality_change": 0.04,
                    "cost_change_with_overhead": -0.25,
                    "cost_change": -0.15,
                    "oracle_cost_change": 0.5,
                    "oracle_quality_change": 0.1,
                }
            ),
            "v2": _make_report_dict(
                **{
                    "quality_change": 0.02,
                    "cost_change_with_overhead": -0.10,
                    "cost_change": -0.05,
                    "oracle_cost_change": 0.5,
                    "oracle_quality_change": 0.1,
                }
            ),
        }
        state = self._make_state(["v1", "v2"])
        briefing = build_review_briefing(
            search_state=state,
            score_reports=score_reports,
            historical_reports={1: {"v1": score_reports["v1"]}},
            prompt_texts={"v1": "## Rules\n1. foo", "v2": "## Rules\n1. bar"},
            candidate_versions=["v1", "v2"],
            parent_versions={"v1": None, "v2": None},
            user_targets=user_targets,
        )
        assert len(briefing.target_progress) == 2
        # All entries must share the same source_version (no cross-version composite)
        source_versions = {tp.source_version for tp in briefing.target_progress}
        assert len(source_versions) == 1
        assert source_versions.pop() is not None


class TestSynthesizeDirectiveOutcomes:
    """Unit tests for _synthesize_directive_outcomes."""

    def _make_batch_outcome(
        self,
        directive_ids: list[str],
        quality_delta: float | None,
        eval_status: str | None = "scored",
    ):
        from compass.agents.review.models import BatchOutcome

        return BatchOutcome(
            variant_id="cv-1-0",
            parent_version="v1",
            mutation_strategy="targeted",
            directive_ids=directive_ids,
            candidate_version="v2",
            eval_status=eval_status,  # type: ignore[arg-type]
            quality_delta_vs_parent=quality_delta,
            is_new_best=False,
        )

    def test_improved_directive(self) -> None:
        bo = self._make_batch_outcome(["d-1-0"], quality_delta=0.05)
        results = _synthesize_directive_outcomes([bo])
        assert len(results) == 1
        assert results[0].prior_directive_id == "d-1-0"
        assert results[0].was_attempted is True
        assert results[0].outcome == "improved"

    def test_regressed_directive(self) -> None:
        bo = self._make_batch_outcome(["d-1-1"], quality_delta=-0.03)
        results = _synthesize_directive_outcomes([bo])
        assert len(results) == 1
        assert results[0].outcome == "regressed"

    def test_no_effect_when_delta_zero(self) -> None:
        bo = self._make_batch_outcome(["d-1-2"], quality_delta=0.0)
        results = _synthesize_directive_outcomes([bo])
        assert results[0].outcome == "no_effect"

    def test_no_effect_when_delta_none(self) -> None:
        bo = self._make_batch_outcome(["d-1-3"], quality_delta=None)
        results = _synthesize_directive_outcomes([bo])
        assert results[0].outcome == "no_effect"

    def test_failed_eval_sets_not_attempted(self) -> None:
        bo = self._make_batch_outcome(["d-1-4"], quality_delta=None, eval_status="failed")
        results = _synthesize_directive_outcomes([bo])
        assert results[0].was_attempted is False

    def test_multiple_directives_in_one_variant(self) -> None:
        bo = self._make_batch_outcome(["d-1-0", "d-1-1"], quality_delta=0.05)
        results = _synthesize_directive_outcomes([bo])
        assert len(results) == 2
        assert {r.prior_directive_id for r in results} == {"d-1-0", "d-1-1"}
        assert all(r.outcome == "improved" for r in results)

    def test_empty_batch_outcomes_returns_empty(self) -> None:
        results = _synthesize_directive_outcomes([])
        assert results == []

    def test_synthesized_outcomes_appear_in_briefing_directive_history(self) -> None:
        """Round-2 build_review_briefing surfaces synthesized outcomes in directive_history."""
        from compass.agents.review.models import BatchOutcome

        bo = BatchOutcome(
            variant_id="cv-1-t0-0",
            parent_version="v1",
            mutation_strategy="targeted",
            directive_ids=["d-1-0"],
            candidate_version="v2",
            eval_status="scored",
            quality_delta_vs_parent=0.05,
            is_new_best=False,
        )
        search_state = _make_search_state(round=2)
        briefing = build_review_briefing(
            search_state=search_state,
            score_reports={},
            historical_reports={},
            prompt_texts={},
            candidate_versions=[],
            parent_versions={},
        )
        assert briefing.directive_history == []

        results = _synthesize_directive_outcomes([bo])
        assert len(results) == 1
        assert results[0].prior_directive_id == "d-1-0"
        assert results[0].outcome == "improved"


class TestParseUserTargets:
    def test_h3_heading_with_canonical_bullets(self) -> None:
        from compass.agents.review.models import UserTarget

        report = (
            "## Metrics and Baseline\n"
            "\n"
            "### Target Metrics\n"
            "- cost_change_with_overhead <= -0.45\n"
            "- quality_change >= -0.03\n"
            "\n"
            "## Optimization Approach\n"
        )
        targets = parse_user_targets(report)
        assert UserTarget(metric="cost_change_with_overhead", operator="<=", threshold=-0.45) in targets
        assert UserTarget(metric="quality_change", operator=">=", threshold=-0.03) in targets
        assert len(targets) == 2

    def test_bold_heading_with_numbered_labeled_bullets(self) -> None:
        from compass.agents.review.models import UserTarget

        report = (
            "## Metrics and Baseline\n"
            "\n"
            "**Target Metrics:**\n"
            "1. **Cost Change:** <= -0.45 (45% reduction with overhead)\n"
            "2. **Quality Change:** >= -0.03 (acceptable 3% quality reduction)\n"
            "\n"
            "## Optimization Approach\n"
        )
        targets = parse_user_targets(report)
        # Label "Cost Change" maps to canonical cost_change_with_overhead.
        assert UserTarget(metric="cost_change_with_overhead", operator="<=", threshold=-0.45) in targets
        assert UserTarget(metric="quality_change", operator=">=", threshold=-0.03) in targets
        assert len(targets) == 2

    def test_inline_success_metric_fallback(self) -> None:
        from compass.agents.review.models import UserTarget

        report = (
            "## Problem Statement\n"
            "- **Success Metric:** Achieve cost_change_with_overhead <= -0.45 "
            "while maintaining quality_change >= -0.03\n"
        )
        targets = parse_user_targets(report)
        assert UserTarget(metric="cost_change_with_overhead", operator="<=", threshold=-0.45) in targets
        assert UserTarget(metric="quality_change", operator=">=", threshold=-0.03) in targets
        assert len(targets) == 2

    def test_no_targets_returns_empty(self) -> None:
        report = "## Problem Statement\n\nNo numeric thresholds anywhere.\n"
        assert parse_user_targets(report) == []

    def test_unknown_bold_label_is_skipped(self) -> None:
        report = "**Target Metrics:**\n1. **Unknown Metric:** <= 0.5\n"
        # No canonical mapping and no fallback hit → empty.
        assert parse_user_targets(report) == []


# ---------------------------------------------------------------------------
# parse_evaluation_budget
# ---------------------------------------------------------------------------


class TestParseEvaluationBudget:
    def test_h3_plain_integer(self) -> None:
        report = "### Evaluation Budget\n9\n"
        assert parse_evaluation_budget(report) == 9

    def test_h3_integer_with_description(self) -> None:
        report = "### Evaluation Budget\n9 (cap on optimization evaluations / generations)\n"
        assert parse_evaluation_budget(report) == 9

    def test_bold_paragraph_form(self) -> None:
        report = "**Evaluation Budget:** 12\n"
        assert parse_evaluation_budget(report) == 12

    def test_no_section_returns_none(self) -> None:
        report = "## Problem Statement\n\nNo budget here.\n"
        assert parse_evaluation_budget(report) is None

    def test_empty_section_returns_none(self) -> None:
        report = "### Evaluation Budget\n\n### Next Section\n"
        assert parse_evaluation_budget(report) is None
