"""Tests for odysseus.agents.review_preprocessor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from odysseus.agents.prompt_builder.search import Candidate, SearchState
from odysseus.agents.review.models import ExampleSummary, MutationRecord
from odysseus.agents.review.preprocessor import (
    build_candidate_comparisons,
    build_review_briefing,
    compute_diminishing_returns,
    compute_diversity_metrics,
    compute_oracle_metrics,
    compute_oracle_metrics_from_report,
    correlate_mutations,
    extract_per_class_recall,
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
        front_versions: list[str] = []

        result = build_candidate_comparisons(
            score_reports=score_reports,
            mutation_descriptions=mutation_descriptions,
            parent_versions=parent_versions,
            front_versions=front_versions,
            primary_metric="accuracy",
        )

        assert len(result) == 1
        assert result[0].candidate_version == "v1"
        assert result[0].parent_version is None
        assert result[0].delta_vs_parent.quality_delta == 0.0
        assert result[0].delta_vs_front == []

    def test_candidate_with_parent_and_front(self) -> None:
        """Later round: candidate has parent, front has members."""
        score_reports = {
            "v3": _make_report_dict(accuracy=0.85, cost=1.20),
            "v1": _make_report_dict(accuracy=0.80, cost=1.50),  # front member
            "v2": _make_report_dict(accuracy=0.82, cost=1.30),  # parent + front
        }
        mutation_descriptions = {"v3": "Swapped Example 3"}
        parent_versions = {"v3": "v2"}
        front_versions = ["v1", "v2"]

        result = build_candidate_comparisons(
            score_reports=score_reports,
            mutation_descriptions=mutation_descriptions,
            parent_versions=parent_versions,
            front_versions=front_versions,
            primary_metric="accuracy",
        )

        assert len(result) == 1
        ca = result[0]
        assert ca.candidate_version == "v3"
        assert ca.delta_vs_parent.quality_delta == pytest.approx(0.03)
        assert ca.delta_vs_parent.cost_delta == pytest.approx(-0.10)
        assert len(ca.delta_vs_front) == 2

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
        front_versions = ["v2"]

        result = build_candidate_comparisons(
            score_reports=score_reports,
            mutation_descriptions=mutation_descriptions,
            parent_versions=parent_versions,
            front_versions=front_versions,
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
            mutation_log=[],
        )
        assert result.prompt_similarity == 0.0  # identical = no diversity
        assert result.example_overlap_ratio == 1.0  # fully overlapping

    def test_completely_different_prompts(self) -> None:
        prompt_texts = {
            "v1": "## Rules\n1. Route to A\n\n## Examples\n### Example 1\nalpha",
            "v2": "## Rules\n1. Route to Z\n\n## Examples\n### Example 9\nomega",
        }
        result = compute_diversity_metrics(
            prompt_texts=prompt_texts,
            mutation_log=[],
        )
        assert result.prompt_similarity > 0.0

    def test_mutation_type_distribution(self) -> None:
        log = [
            MutationRecord(
                child_version="v2",
                parent_version="v1",
                mutation_type="example_swap",
                description="swap",
            ),
            MutationRecord(
                child_version="v3",
                parent_version="v2",
                mutation_type="example_swap",
                description="swap",
            ),
            MutationRecord(
                child_version="v4",
                parent_version="v2",
                mutation_type="rule_edit",
                description="edit",
            ),
        ]
        result = compute_diversity_metrics(
            prompt_texts={"v1": "a", "v2": "b"},
            mutation_log=log,
        )
        assert result.mutation_type_distribution == {"example_swap": 2, "rule_edit": 1}

    def test_single_prompt_on_front(self) -> None:
        result = compute_diversity_metrics(
            prompt_texts={"v1": "## Rules\n1. Route to A"},
            mutation_log=[],
        )
        assert result.prompt_similarity == 0.0
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


class TestCorrelateMutations:
    def test_classifies_effective_and_ineffective(self) -> None:
        log = [
            MutationRecord(
                child_version="v2",
                parent_version="v1",
                mutation_type="example_swap",
                description="swap ex 3",
            ),
            MutationRecord(
                child_version="v3",
                parent_version="v2",
                mutation_type="rule_edit",
                description="tighten rule 1",
            ),
        ]
        # v2 improved over v1, v3 did not improve over v2
        score_history = {
            "v1": 0.80,
            "v2": 0.85,
            "v3": 0.84,
        }

        result = correlate_mutations(
            mutation_log=log,
            score_history=score_history,
        )

        assert len(result.effective_mutations) == 1
        assert result.effective_mutations[0].child_version == "v2"
        assert len(result.ineffective_mutations) == 1
        assert result.ineffective_mutations[0].child_version == "v3"

    def test_identifies_untried_types(self) -> None:
        log = [
            MutationRecord(
                child_version="v2",
                parent_version="v1",
                mutation_type="example_swap",
                description="swap",
            ),
        ]
        all_mutation_types = [
            "example_swap",
            "rule_edit",
            "schema_change",
            "rule_add",
            "rule_remove",
            "assembly_policy",
        ]

        result = correlate_mutations(
            mutation_log=log,
            score_history={"v1": 0.8, "v2": 0.85},
            all_mutation_types=all_mutation_types,
        )

        assert "rule_edit" in result.untried_mutation_types
        assert "example_swap" not in result.untried_mutation_types

    def test_empty_log(self) -> None:
        result = correlate_mutations(mutation_log=[], score_history={})
        assert result.effective_mutations == []
        assert result.ineffective_mutations == []


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
        pareto_front=[],
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
            pareto_front=[
                Candidate(
                    prompt_version="v1",
                    parent_version=None,
                    quality_score=0.80,
                    cost=1.50,
                    round_introduced=1,
                    dominated=False,
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
        mutation_log = [
            MutationRecord(
                child_version="v2",
                parent_version="v1",
                mutation_type="rule_add",
                description="Added complexity routing rule",
            ),
        ]

        briefing = build_review_briefing(
            search_state=search_state,
            score_reports=score_reports,
            historical_reports=historical_reports,
            prompt_texts=prompt_texts,
            mutation_log=mutation_log,
            directive_history=[],
            holdout_examples=[
                ExampleSummary(example_id="h1", route="model-a", ambiguity_tags=[]),
            ],
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
