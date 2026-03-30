"""Tests for Review Agent data models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from odysseus.eval.models import RunSummary, ScoreReport


def _make_score_report(**metric_overrides: float) -> ScoreReport:
    return ScoreReport(
        metrics={"accuracy": 0.80, "cost": 1.0, **metric_overrides},
        summary=RunSummary(
            total=10,
            succeeded=10,
            failed=0,
            total_cost=1.0,
            start_time=datetime.now(tz=UTC),
            end_time=datetime.now(tz=UTC),
            duration_seconds=5.0,
        ),
        errors=[],
        diff=None,
        report_path="report.json",
        results_path="results.jsonl",
    )


# ---------------------------------------------------------------------------
# MetricDeltas
# ---------------------------------------------------------------------------


class TestMetricDeltas:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import MetricDeltas

        delta = MetricDeltas(
            quality_delta=0.05,
            cost_delta=-0.10,
            per_class_recall_deltas={"route_a": 0.03, "route_b": -0.01},
        )
        assert delta.quality_delta == 0.05
        assert delta.cost_delta == -0.10
        assert delta.per_class_recall_deltas["route_a"] == 0.03

    def test_empty_per_class_recalls(self) -> None:
        from odysseus.agents.review.models import MetricDeltas

        delta = MetricDeltas(quality_delta=0.0, cost_delta=0.0, per_class_recall_deltas={})
        assert delta.per_class_recall_deltas == {}


# ---------------------------------------------------------------------------
# FrontComparison
# ---------------------------------------------------------------------------


class TestFrontComparison:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import FrontComparison

        fc = FrontComparison(
            front_candidate_version="v1",
            quality_delta=0.02,
            cost_delta=-0.05,
        )
        assert fc.front_candidate_version == "v1"
        assert fc.quality_delta == 0.02
        assert fc.cost_delta == -0.05


# ---------------------------------------------------------------------------
# CandidateAnalysis
# ---------------------------------------------------------------------------


class TestCandidateAnalysis:
    def test_with_parent(self) -> None:
        from odysseus.agents.review.models import CandidateAnalysis, FrontComparison, MetricDeltas

        ca = CandidateAnalysis(
            candidate_version="v2",
            parent_version="v1",
            mutation_description="added an example",
            score_report=_make_score_report(),
            delta_vs_parent=MetricDeltas(quality_delta=0.01, cost_delta=0.0, per_class_recall_deltas={}),
            delta_vs_front=[FrontComparison(front_candidate_version="v1", quality_delta=0.01, cost_delta=0.0)],
        )
        assert ca.candidate_version == "v2"
        assert ca.parent_version == "v1"

    def test_no_parent(self) -> None:
        from odysseus.agents.review.models import CandidateAnalysis, MetricDeltas

        ca = CandidateAnalysis(
            candidate_version="v1",
            parent_version=None,
            mutation_description="seed candidate",
            score_report=_make_score_report(),
            delta_vs_parent=MetricDeltas(quality_delta=0.0, cost_delta=0.0, per_class_recall_deltas={}),
            delta_vs_front=[],
        )
        assert ca.parent_version is None


# ---------------------------------------------------------------------------
# ClassRecallEntry
# ---------------------------------------------------------------------------


class TestClassRecallEntry:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import ClassRecallEntry

        entry = ClassRecallEntry(
            recall=0.85,
            support=100,
            trend=[0.80, 0.82, 0.85],
            regression_flag=False,
        )
        assert entry.recall == 0.85
        assert entry.support == 100
        assert entry.regression_flag is False

    def test_regression_flag_set(self) -> None:
        from odysseus.agents.review.models import ClassRecallEntry

        entry = ClassRecallEntry(recall=0.60, support=50, trend=[0.80, 0.70, 0.60], regression_flag=True)
        assert entry.regression_flag is True


# ---------------------------------------------------------------------------
# DiversityMetrics
# ---------------------------------------------------------------------------


class TestDiversityMetrics:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import DiversityMetrics

        dm = DiversityMetrics(
            example_overlap_ratio=0.3,
            prompt_similarity=0.7,
            mutation_type_distribution={"example_swap": 2, "rule_edit": 1},
        )
        assert dm.example_overlap_ratio == 0.3
        assert dm.mutation_type_distribution["example_swap"] == 2


# ---------------------------------------------------------------------------
# DiminishingReturns
# ---------------------------------------------------------------------------


class TestDiminishingReturns:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import DiminishingReturns

        dr = DiminishingReturns(
            score_trajectory=[0.70, 0.72, 0.73, 0.73],
            improvement_trend=0.01,
            stagnation_flag=True,
        )
        assert dr.stagnation_flag is True
        assert dr.improvement_trend == 0.01


# ---------------------------------------------------------------------------
# MutationRecord
# ---------------------------------------------------------------------------


class TestMutationRecord:
    def test_with_directive_ids(self) -> None:
        from odysseus.agents.review.models import MutationRecord

        mr = MutationRecord(
            child_version="v3",
            parent_version="v2",
            mutation_type="example_swap",
            description="swapped two examples",
            directive_ids=["d1", "d2"],
        )
        assert mr.mutation_type == "example_swap"
        assert mr.directive_ids == ["d1", "d2"]

    def test_directive_ids_optional_none(self) -> None:
        from odysseus.agents.review.models import MutationRecord

        mr = MutationRecord(
            child_version="v3",
            parent_version="v2",
            mutation_type="rule_edit",
            description="edited a rule",
        )
        assert mr.directive_ids is None

    def test_invalid_mutation_type(self) -> None:
        from odysseus.agents.review.models import MutationRecord

        with pytest.raises(ValidationError):
            MutationRecord(
                child_version="v3",
                parent_version="v2",
                mutation_type="invalid_type",  # type: ignore[arg-type]
                description="bad",
            )

    def test_all_mutation_types_valid(self) -> None:
        from odysseus.agents.review.models import MutationRecord, MutationType

        valid_types: list[MutationType] = [
            "example_swap",
            "rule_edit",
            "schema_change",
            "rule_add",
            "rule_remove",
            "assembly_policy",
        ]
        for mt in valid_types:
            mr = MutationRecord(
                child_version="v2",
                parent_version="v1",
                mutation_type=mt,
                description="test",
            )
            assert mr.mutation_type == mt


# ---------------------------------------------------------------------------
# MutationHistory
# ---------------------------------------------------------------------------


class TestMutationHistory:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import MutationHistory, MutationRecord

        record = MutationRecord(
            child_version="v2",
            parent_version="v1",
            mutation_type="rule_add",
            description="added a rule",
        )
        mh = MutationHistory(
            effective_mutations=[record],
            ineffective_mutations=[],
            untried_mutation_types=["schema_change", "assembly_policy"],
        )
        assert len(mh.effective_mutations) == 1
        assert mh.untried_mutation_types == ["schema_change", "assembly_policy"]


# ---------------------------------------------------------------------------
# ExampleSummary
# ---------------------------------------------------------------------------


class TestExampleSummary:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import ExampleSummary

        es = ExampleSummary(
            example_id="ex-001",
            route="route_a",
            ambiguity_tags=["low_confidence", "multi_route"],
        )
        assert es.example_id == "ex-001"
        assert "low_confidence" in es.ambiguity_tags

    def test_empty_ambiguity_tags(self) -> None:
        from odysseus.agents.review.models import ExampleSummary

        es = ExampleSummary(example_id="ex-002", route="route_b", ambiguity_tags=[])
        assert es.ambiguity_tags == []


# ---------------------------------------------------------------------------
# OracleMetrics
# ---------------------------------------------------------------------------


class TestOracleMetrics:
    def test_required_fields_only(self) -> None:
        from odysseus.agents.review.models import OracleMetrics

        om = OracleMetrics(
            oracle_cost_reduction=0.15,
            oracle_quality_reduction=0.05,
        )
        assert om.oracle_cost_reduction == 0.15
        assert om.candidate_cost_captured is None
        assert om.candidate_quality_captured is None

    def test_all_fields(self) -> None:
        from odysseus.agents.review.models import OracleMetrics

        om = OracleMetrics(
            oracle_cost_reduction=0.15,
            oracle_quality_reduction=0.05,
            candidate_cost_captured=0.10,
            candidate_quality_captured=0.03,
        )
        assert om.candidate_cost_captured == 0.10
        assert om.candidate_quality_captured == 0.03


# ---------------------------------------------------------------------------
# ReviewBriefing
# ---------------------------------------------------------------------------


class TestReviewBriefing:
    def _make_briefing(self) -> ReviewBriefing:  # noqa: F821
        from odysseus.agents.prompt_builder.search import Candidate
        from odysseus.agents.review.models import (
            CandidateAnalysis,
            ClassRecallEntry,
            DiminishingReturns,
            DiversityMetrics,
            ExampleSummary,
            MetricDeltas,
            MutationHistory,
            OracleMetrics,
            ReviewBriefing,
        )

        candidate = CandidateAnalysis(
            candidate_version="v2",
            parent_version="v1",
            mutation_description="swap",
            score_report=_make_score_report(),
            delta_vs_parent=MetricDeltas(quality_delta=0.01, cost_delta=0.0, per_class_recall_deltas={}),
            delta_vs_front=[],
        )
        front_member = Candidate(
            prompt_version="v1",
            parent_version=None,
            quality_score=0.80,
            cost=1.0,
            round_introduced=1,
        )
        return ReviewBriefing(
            round=2,
            candidates=[candidate],
            pareto_front=[front_member],
            per_class_recall={
                "route_a": ClassRecallEntry(recall=0.85, support=50, trend=[0.80, 0.85], regression_flag=False)
            },
            diversity_metrics=DiversityMetrics(
                example_overlap_ratio=0.2,
                prompt_similarity=0.5,
                mutation_type_distribution={"example_swap": 1},
            ),
            diminishing_returns=DiminishingReturns(
                score_trajectory=[0.78, 0.80],
                improvement_trend=0.02,
                stagnation_flag=False,
            ),
            mutation_history=MutationHistory(
                effective_mutations=[],
                ineffective_mutations=[],
                untried_mutation_types=["schema_change"],
            ),
            oracle_metrics=OracleMetrics(oracle_cost_reduction=0.10, oracle_quality_reduction=0.02),
            prompt_versions={"v1": "prompt text v1", "v2": "prompt text v2"},
            holdout_examples=[ExampleSummary(example_id="ex-1", route="route_a", ambiguity_tags=[])],
        )

    def test_basic_construction(self) -> None:
        briefing = self._make_briefing()
        assert briefing.round == 2
        assert len(briefing.candidates) == 1
        assert len(briefing.pareto_front) == 1
        assert "route_a" in briefing.per_class_recall

    def test_empty_collections(self) -> None:
        from odysseus.agents.review.models import (
            DiminishingReturns,
            DiversityMetrics,
            MutationHistory,
            OracleMetrics,
            ReviewBriefing,
        )

        briefing = ReviewBriefing(
            round=1,
            candidates=[],
            pareto_front=[],
            per_class_recall={},
            diversity_metrics=DiversityMetrics(
                example_overlap_ratio=0.0,
                prompt_similarity=0.0,
                mutation_type_distribution={},
            ),
            diminishing_returns=DiminishingReturns(
                score_trajectory=[],
                improvement_trend=0.0,
                stagnation_flag=False,
            ),
            mutation_history=MutationHistory(
                effective_mutations=[],
                ineffective_mutations=[],
                untried_mutation_types=[],
            ),
            oracle_metrics=OracleMetrics(oracle_cost_reduction=0.0, oracle_quality_reduction=0.0),
            prompt_versions={},
            holdout_examples=[],
        )
        assert briefing.candidates == []
        assert briefing.holdout_examples == []


# ---------------------------------------------------------------------------
# RankedCandidate
# ---------------------------------------------------------------------------


class TestRankedCandidate:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import RankedCandidate

        rc = RankedCandidate(version="v2", rank=1, rationale="best accuracy")
        assert rc.version == "v2"
        assert rc.rank == 1


# ---------------------------------------------------------------------------
# EditDirective
# ---------------------------------------------------------------------------


class TestEditDirective:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import EditDirective

        ed = EditDirective(
            directive_id="d1",
            target_version="v2",
            block_type="rule",
            block_identifier="rule_001",
            granularity="micro",
            directive="Rephrase the condition to be more specific.",
            priority="high",
        )
        assert ed.directive_id == "d1"
        assert ed.block_type == "rule"
        assert ed.granularity == "micro"
        assert ed.priority == "high"

    def test_invalid_block_type(self) -> None:
        from odysseus.agents.review.models import EditDirective

        with pytest.raises(ValidationError):
            EditDirective(
                directive_id="d2",
                target_version="v2",
                block_type="invalid",  # type: ignore[arg-type]
                block_identifier="b1",
                granularity="macro",
                directive="do something",
                priority="low",
            )

    def test_all_block_types_valid(self) -> None:
        from odysseus.agents.review.models import EditDirective

        for bt in ("rule", "example", "output_schema", "assembly_policy"):
            ed = EditDirective(
                directive_id="d",
                target_version="v1",
                block_type=bt,  # type: ignore[arg-type]
                block_identifier="b",
                granularity="macro",
                directive="directive",
                priority="medium",
            )
            assert ed.block_type == bt


# ---------------------------------------------------------------------------
# PromotionDecision
# ---------------------------------------------------------------------------


class TestPromotionDecision:
    def test_promote(self) -> None:
        from odysseus.agents.review.models import PromotionDecision

        pd = PromotionDecision(version="v2", decision="promote", reason="best candidate")
        assert pd.decision == "promote"

    def test_prune(self) -> None:
        from odysseus.agents.review.models import PromotionDecision

        pd = PromotionDecision(version="v3", decision="prune", reason="dominated")
        assert pd.decision == "prune"

    def test_refine(self) -> None:
        from odysseus.agents.review.models import PromotionDecision

        pd = PromotionDecision(version="v4", decision="refine", reason="promising but needs work")
        assert pd.decision == "refine"

    def test_invalid_decision(self) -> None:
        from odysseus.agents.review.models import PromotionDecision

        with pytest.raises(ValidationError):
            PromotionDecision(version="v5", decision="reject", reason="bad")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# LoopSignal
# ---------------------------------------------------------------------------


class TestLoopSignal:
    def test_refine_with_budget(self) -> None:
        from odysseus.agents.review.models import LoopSignal

        ls = LoopSignal(
            action="refine",
            reason="not converged",
            suggested_budget=5,
            suggested_mutation_mode="targeted",
        )
        assert ls.action == "refine"
        assert ls.suggested_budget == 5
        assert ls.suggested_mutation_mode == "targeted"

    def test_exit_no_optional_fields(self) -> None:
        from odysseus.agents.review.models import LoopSignal

        ls = LoopSignal(action="exit", reason="converged")
        assert ls.action == "exit"
        assert ls.suggested_budget is None
        assert ls.suggested_mutation_mode is None

    def test_invalid_action(self) -> None:
        from odysseus.agents.review.models import LoopSignal

        with pytest.raises(ValidationError):
            LoopSignal(action="continue", reason="test")  # type: ignore[arg-type]

    def test_invalid_mutation_mode(self) -> None:
        from odysseus.agents.review.models import LoopSignal

        with pytest.raises(ValidationError):
            LoopSignal(
                action="refine",
                reason="test",
                suggested_mutation_mode="random",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# RegressionFlag
# ---------------------------------------------------------------------------


class TestRegressionFlag:
    def test_warning(self) -> None:
        from odysseus.agents.review.models import RegressionFlag

        rf = RegressionFlag(
            version="v2",
            metric="accuracy",
            previous_value=0.85,
            current_value=0.82,
            severity="warning",
        )
        assert rf.severity == "warning"
        assert rf.previous_value == 0.85

    def test_block(self) -> None:
        from odysseus.agents.review.models import RegressionFlag

        rf = RegressionFlag(
            version="v2",
            metric="f1_score",
            previous_value=0.90,
            current_value=0.70,
            severity="block",
        )
        assert rf.severity == "block"

    def test_invalid_severity(self) -> None:
        from odysseus.agents.review.models import RegressionFlag

        with pytest.raises(ValidationError):
            RegressionFlag(
                version="v2",
                metric="accuracy",
                previous_value=0.85,
                current_value=0.80,
                severity="critical",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# DirectiveOutcome
# ---------------------------------------------------------------------------


class TestDirectiveOutcome:
    def test_improved(self) -> None:
        from odysseus.agents.review.models import DirectiveOutcome

        do = DirectiveOutcome(
            prior_directive_id="d1",
            was_attempted=True,
            outcome="improved",
        )
        assert do.outcome == "improved"
        assert do.was_attempted is True

    def test_not_attempted(self) -> None:
        from odysseus.agents.review.models import DirectiveOutcome

        do = DirectiveOutcome(
            prior_directive_id="d2",
            was_attempted=False,
            outcome="no_effect",
        )
        assert do.was_attempted is False

    def test_invalid_outcome(self) -> None:
        from odysseus.agents.review.models import DirectiveOutcome

        with pytest.raises(ValidationError):
            DirectiveOutcome(
                prior_directive_id="d3",
                was_attempted=True,
                outcome="unknown",  # type: ignore[arg-type]
            )

    def test_all_outcomes_valid(self) -> None:
        from odysseus.agents.review.models import DirectiveOutcome

        for outcome in ("improved", "no_effect", "regressed"):
            do = DirectiveOutcome(prior_directive_id="d", was_attempted=True, outcome=outcome)  # type: ignore[arg-type]
            assert do.outcome == outcome


# ---------------------------------------------------------------------------
# ReviewResult
# ---------------------------------------------------------------------------


class TestReviewResult:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import (
            DirectiveOutcome,
            EditDirective,
            LoopSignal,
            PromotionDecision,
            RankedCandidate,
            RegressionFlag,
            ReviewResult,
        )

        result = ReviewResult(
            candidate_ranking=[RankedCandidate(version="v2", rank=1, rationale="best")],
            edit_directives=[
                EditDirective(
                    directive_id="d1",
                    target_version="v2",
                    block_type="example",
                    block_identifier="ex_001",
                    granularity="macro",
                    directive="Replace with a clearer example.",
                    priority="medium",
                )
            ],
            promotion_decisions=[PromotionDecision(version="v2", decision="promote", reason="top rank")],
            loop_signal=LoopSignal(action="exit", reason="converged"),
            regression_guards=[
                RegressionFlag(
                    version="v2",
                    metric="recall",
                    previous_value=0.80,
                    current_value=0.78,
                    severity="warning",
                )
            ],
            directive_history_update=[
                DirectiveOutcome(prior_directive_id="d0", was_attempted=True, outcome="improved")
            ],
        )
        assert result.loop_signal.action == "exit"
        assert len(result.candidate_ranking) == 1
        assert len(result.edit_directives) == 1
        assert len(result.promotion_decisions) == 1
        assert len(result.regression_guards) == 1
        assert len(result.directive_history_update) == 1

    def test_empty_lists(self) -> None:
        from odysseus.agents.review.models import LoopSignal, ReviewResult

        result = ReviewResult(
            candidate_ranking=[],
            edit_directives=[],
            promotion_decisions=[],
            loop_signal=LoopSignal(action="refine", reason="still iterating"),
            regression_guards=[],
            directive_history_update=[],
        )
        assert result.candidate_ranking == []
        assert result.edit_directives == []


# ---------------------------------------------------------------------------
# ExampleContent
# ---------------------------------------------------------------------------


from odysseus.agents.review.models import ExampleContent


def test_example_content_model():
    content = ExampleContent(
        input="Build a multi-step data pipeline",
        route="complex",
        reasoning="Requires chained operations with control flow",
        exclusions=[
            {"route": "simple", "reason": "Single-step tasks only"},
            {"route": "moderate", "reason": "No error handling at this tier"},
        ],
    )
    assert content.route == "complex"
    assert len(content.exclusions) == 2


def test_edit_directive_with_example_content():
    from odysseus.agents.review.models import EditDirective, ExampleContent
    directive = EditDirective(
        directive_id="d1",
        target_version="v2",
        block_type="example",
        block_identifier="example_0",
        granularity="macro",
        directive="Replace with boundary case example",
        priority="high",
        example_content=ExampleContent(
            input="Translate this document",
            route="moderate",
            reasoning="Requires language understanding but no multi-step logic",
            exclusions=[{"route": "simple", "reason": "Needs domain knowledge"}],
        ),
    )
    assert directive.example_content is not None
    assert directive.example_content.route == "moderate"


def test_edit_directive_without_example_content():
    from odysseus.agents.review.models import EditDirective
    directive = EditDirective(
        directive_id="d2",
        target_version="v2",
        block_type="rule",
        block_identifier="rule_1",
        granularity="micro",
        directive="Paraphrase for clarity",
        priority="medium",
    )
    assert directive.example_content is None
