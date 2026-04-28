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
# CandidateAnalysis
# ---------------------------------------------------------------------------


class TestCandidateAnalysis:
    def test_with_parent(self) -> None:
        from odysseus.agents.review.models import CandidateAnalysis, MetricDeltas

        ca = CandidateAnalysis(
            candidate_version="v2",
            parent_version="v1",
            mutation_description="added an example",
            score_report=_make_score_report(),
            delta_vs_parent=MetricDeltas(quality_delta=0.01, cost_delta=0.0, per_class_recall_deltas={}),
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
        )
        assert dm.example_overlap_ratio == 0.3

    def test_full_overlap(self) -> None:
        from odysseus.agents.review.models import DiversityMetrics

        dm = DiversityMetrics(example_overlap_ratio=1.0)
        assert dm.example_overlap_ratio == 1.0

    def test_zero_overlap(self) -> None:
        from odysseus.agents.review.models import DiversityMetrics

        dm = DiversityMetrics(example_overlap_ratio=0.0)
        assert dm.example_overlap_ratio == 0.0


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
# UserTarget
# ---------------------------------------------------------------------------


class TestUserTarget:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import UserTarget

        t = UserTarget(metric="accuracy", operator=">=", threshold=0.90)
        assert t.metric == "accuracy"
        assert t.operator == ">="
        assert t.threshold == 0.90

    def test_all_operators_valid(self) -> None:
        from odysseus.agents.review.models import UserTarget

        for op in ("<=", ">=", "<", ">", "=="):
            t = UserTarget(metric="cost", operator=op, threshold=1.0)  # type: ignore[arg-type]
            assert t.operator == op

    def test_invalid_operator_raises(self) -> None:
        from odysseus.agents.review.models import UserTarget

        with pytest.raises(ValidationError):
            UserTarget(metric="accuracy", operator="!=", threshold=0.5)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# UserTargetProgress
# ---------------------------------------------------------------------------


class TestUserTargetProgress:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import UserTarget, UserTargetProgress

        target = UserTarget(metric="accuracy", operator=">=", threshold=0.90)
        utp = UserTargetProgress(
            target=target,
            current_value=0.85,
            met=False,
            progress_ratio=0.94,
            oracle_ceiling=0.95,
            target_above_oracle=False,
        )
        assert utp.met is False
        assert utp.current_value == 0.85
        assert utp.progress_ratio == pytest.approx(0.94)

    def test_met_target(self) -> None:
        from odysseus.agents.review.models import UserTarget, UserTargetProgress

        target = UserTarget(metric="accuracy", operator=">=", threshold=0.80)
        utp = UserTargetProgress(
            target=target,
            current_value=0.92,
            met=True,
            progress_ratio=1.0,
            oracle_ceiling=None,
            target_above_oracle=False,
        )
        assert utp.met is True

    def test_surplus_fields_optional(self) -> None:
        from odysseus.agents.review.models import UserTarget, UserTargetProgress

        target = UserTarget(metric="cost", operator="<=", threshold=1.0)
        utp = UserTargetProgress(
            target=target,
            current_value=0.8,
            met=True,
            progress_ratio=1.0,
            oracle_ceiling=None,
            target_above_oracle=False,
            surplus=0.2,
            regression_budget=0.2,
            priority_weight=0.0,
        )
        assert utp.surplus == pytest.approx(0.2)
        assert utp.regression_budget == pytest.approx(0.2)
        assert utp.priority_weight == 0.0


# ---------------------------------------------------------------------------
# ChildVariant
# ---------------------------------------------------------------------------


class TestChildVariant:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import ChildVariant, EditDirective

        ed = EditDirective(
            directive_id="d1",
            target_version="v1",
            block_type="rule",
            block_identifier="Rule 1",
            granularity="micro",
            directive="Tighten wording",
            priority="medium",
        )
        cv = ChildVariant(
            variant_id="cv-0-0",
            hypothesis="Test hypothesis",
            directives=[ed],
        )
        assert cv.variant_id == "cv-0-0"
        assert len(cv.directives) == 1

    def test_variant_id_defaults_to_none(self) -> None:
        from odysseus.agents.review.models import ChildVariant

        cv = ChildVariant(hypothesis="hypothesis", directives=[])
        assert cv.variant_id is None

    def test_parent_preference_fields(self) -> None:
        from odysseus.agents.review.models import ChildVariant

        cv = ChildVariant(
            variant_id="cv-1-0",
            hypothesis="target weak class",
            directives=[],
            parent_preference="weakest_on_class",
            parent_preference_class="route_a",
        )
        assert cv.parent_preference == "weakest_on_class"
        assert cv.parent_preference_class == "route_a"


# ---------------------------------------------------------------------------
# BatchOutcome
# ---------------------------------------------------------------------------


class TestBatchOutcome:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import BatchOutcome

        bo = BatchOutcome(
            variant_id="cv-0-0",
            parent_version="v1",
            mutation_strategy="targeted",
            directive_ids=["d1", "d2"],
            candidate_version="v2",
            eval_status="scored",
            quality_delta_vs_parent=0.03,
            is_new_best=True,
        )
        assert bo.variant_id == "cv-0-0"
        assert bo.eval_status == "scored"
        assert bo.quality_delta_vs_parent == pytest.approx(0.03)
        assert bo.is_new_best is True

    def test_failed_eval(self) -> None:
        from odysseus.agents.review.models import BatchOutcome

        bo = BatchOutcome(
            variant_id="cv-0-1",
            parent_version="v1",
            mutation_strategy="exploratory",
            candidate_version=None,
            eval_status="failed",
            quality_delta_vs_parent=None,
            is_new_best=False,
        )
        assert bo.eval_status == "failed"
        assert bo.candidate_version is None
        assert bo.quality_delta_vs_parent is None

    def test_invalid_mutation_strategy_raises(self) -> None:
        from odysseus.agents.review.models import BatchOutcome

        with pytest.raises(ValidationError):
            BatchOutcome(
                variant_id="cv-0-2",
                parent_version="v1",
                mutation_strategy="random",  # type: ignore[arg-type]
                candidate_version=None,
                eval_status=None,
                quality_delta_vs_parent=None,
                is_new_best=False,
            )


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
            oracle_cost_change=0.15,
            oracle_quality_change=0.05,
        )
        assert om.oracle_cost_change == 0.15
        assert om.candidate_cost_captured is None
        assert om.candidate_quality_captured is None

    def test_all_fields(self) -> None:
        from odysseus.agents.review.models import OracleMetrics

        om = OracleMetrics(
            oracle_cost_change=0.15,
            oracle_quality_change=0.05,
            candidate_cost_captured=0.10,
            candidate_quality_captured=0.03,
        )
        assert om.candidate_cost_captured == 0.10
        assert om.candidate_quality_captured == 0.03


# ---------------------------------------------------------------------------
# ReviewBriefing
# ---------------------------------------------------------------------------


def _make_minimal_briefing_kwargs() -> dict:
    from odysseus.agents.prompt_builder.search import Candidate
    from odysseus.agents.review.models import (
        CandidateAnalysis,
        ClassRecallEntry,
        DiminishingReturns,
        DiversityMetrics,
        MetricDeltas,
        OracleMetrics,
    )

    candidate = CandidateAnalysis(
        candidate_version="v2",
        parent_version="v1",
        mutation_description="swap",
        score_report=_make_score_report(),
        delta_vs_parent=MetricDeltas(quality_delta=0.01, cost_delta=0.0, per_class_recall_deltas={}),
    )
    front_member = Candidate(
        prompt_version="v1",
        parent_version=None,
        quality_score=0.80,
        cost=1.0,
        round_introduced=1,
    )
    return dict(
        round=2,
        candidates=[candidate],
        elite_set=[front_member],
        per_class_recall={
            "route_a": ClassRecallEntry(recall=0.85, support=50, trend=[0.80, 0.85], regression_flag=False)
        },
        diversity_metrics=DiversityMetrics(example_overlap_ratio=0.2),
        diminishing_returns=DiminishingReturns(
            score_trajectory=[0.78, 0.80],
            improvement_trend=0.02,
            stagnation_flag=False,
        ),
        oracle_metrics=OracleMetrics(oracle_cost_change=0.10, oracle_quality_change=0.02),
    )


class TestReviewBriefing:
    def test_basic_construction(self) -> None:
        from odysseus.agents.review.models import ReviewBriefing

        briefing = ReviewBriefing(**_make_minimal_briefing_kwargs())
        assert briefing.round == 2
        assert len(briefing.candidates) == 1
        assert len(briefing.elite_set) == 1
        assert "route_a" in briefing.per_class_recall

    def test_empty_collections(self) -> None:
        from odysseus.agents.review.models import (
            DiminishingReturns,
            DiversityMetrics,
            OracleMetrics,
            ReviewBriefing,
        )

        briefing = ReviewBriefing(
            round=1,
            candidates=[],
            elite_set=[],
            per_class_recall={},
            diversity_metrics=DiversityMetrics(example_overlap_ratio=0.0),
            diminishing_returns=DiminishingReturns(
                score_trajectory=[],
                improvement_trend=0.0,
                stagnation_flag=False,
            ),
            oracle_metrics=OracleMetrics(oracle_cost_change=0.0, oracle_quality_change=0.0),
        )
        assert briefing.candidates == []
        assert briefing.batch_outcomes == []
        assert briefing.child_variants == []
        assert briefing.target_progress == []

    def test_new_fields_default(self) -> None:
        """New fields default to empty/False."""
        from odysseus.agents.review.models import ReviewBriefing

        briefing = ReviewBriefing(**_make_minimal_briefing_kwargs())
        assert briefing.batch_outcomes == []
        assert briefing.child_variants == []
        assert briefing.target_progress == []
        assert briefing.backtracking is False
        assert briefing.beam_width == 2

    def test_old_json_without_new_fields_still_loads(self) -> None:
        """A ReviewBriefing serialised before new fields loads without error (extra=ignore)."""
        from odysseus.agents.review.models import ReviewBriefing

        briefing = ReviewBriefing(**_make_minimal_briefing_kwargs())
        data = briefing.model_dump()
        # Simulate old serialised briefing by removing new fields
        for field in ("batch_outcomes", "child_variants", "target_progress", "backtracking"):
            data.pop(field, None)
        restored = ReviewBriefing.model_validate(data)
        assert restored.round == 2

    def test_unknown_future_field_is_ignored(self) -> None:
        """extra='ignore' ensures unknown fields do not raise."""
        from odysseus.agents.review.models import ReviewBriefing

        briefing = ReviewBriefing(**_make_minimal_briefing_kwargs())
        data = briefing.model_dump()
        data["some_future_strategy_field"] = "this should be silently ignored"
        restored = ReviewBriefing.model_validate(data)
        assert restored.round == 2


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

        for bt in ("rule", "example", "output_schema", "vocabulary"):
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
            ChildVariant,
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
            child_variants=[
                ChildVariant(
                    variant_id="cv-0-0",
                    hypothesis="Fix recall on route_a",
                    directives=[
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
        assert len(result.child_variants) == 1
        assert result.child_variants[0].variant_id == "cv-0-0"
        assert len(result.promotion_decisions) == 1
        assert len(result.regression_guards) == 1
        assert len(result.directive_history_update) == 1

    def test_empty_lists(self) -> None:
        from odysseus.agents.review.models import LoopSignal, ReviewResult

        result = ReviewResult(
            candidate_ranking=[],
            child_variants=[],
            promotion_decisions=[],
            loop_signal=LoopSignal(action="refine", reason="still iterating"),
            regression_guards=[],
            directive_history_update=[],
        )
        assert result.candidate_ranking == []
        assert result.child_variants == []


# ---------------------------------------------------------------------------
# ExampleContent
# ---------------------------------------------------------------------------


def test_example_content_model():
    from odysseus.agents.review.models import ExampleContent

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


# ---------------------------------------------------------------------------
# ExampleContent
# ---------------------------------------------------------------------------


class TestExampleContent:
    def test_with_example_id(self) -> None:
        from odysseus.agents.review.models import ExampleContent
        content = ExampleContent(
            example_id="ex-042",
            input="Build a multi-step data pipeline",
            route="complex",
            reasoning="Requires chained operations",
            exclusions=[],
        )
        assert content.example_id == "ex-042"

    def test_example_id_defaults_to_none(self) -> None:
        from odysseus.agents.review.models import ExampleContent
        content = ExampleContent(
            input="Hello",
            route="simple",
            reasoning="Trivial greeting",
            exclusions=[],
        )
        assert content.example_id is None


# ---------------------------------------------------------------------------
# ReviewBriefing — strategy-specific optional fields (Increment 4)
# ---------------------------------------------------------------------------


class TestReviewBriefingStrategyFields:
    """Round-trip and backward-compat tests for the new optional fields."""

    def test_strategy_fields_round_trip(self) -> None:
        """All strategy-specific optional fields survive a model_dump / model_validate round-trip."""
        from odysseus.agents.review.models import ReviewBriefing

        briefing = ReviewBriefing(
            **_make_minimal_briefing_kwargs(),
            stagnation_signal={"count": 2, "limit": 3, "mutation_mode": "targeted"},
            parent_a_version="v1",
            parent_b_version="v2",
            beam_rank={"v1": 0, "v2": 1},
            crowding_distance={"v1": 0.5, "v2": 1.2},
            trajectory_id=3,
            weight_vector=(0.7, 0.3),
            binding_axis="quality",
            acceptance_history=[True, False, True],
            hypervolume=0.42,
            reference_point=(0.0, 2.0),
        )

        data = briefing.model_dump()
        restored = ReviewBriefing.model_validate(data)

        assert restored.stagnation_signal == {"count": 2, "limit": 3, "mutation_mode": "targeted"}
        assert restored.parent_a_version == "v1"
        assert restored.parent_b_version == "v2"
        assert restored.beam_rank == {"v1": 0, "v2": 1}
        assert restored.crowding_distance == {"v1": 0.5, "v2": 1.2}
        assert restored.trajectory_id == 3
        assert restored.weight_vector == (0.7, 0.3)
        assert restored.binding_axis == "quality"
        assert restored.acceptance_history == [True, False, True]
        assert restored.hypervolume == pytest.approx(0.42)
        assert restored.reference_point == (0.0, 2.0)

    def test_new_fields_default_to_none(self) -> None:
        """When none of the optional fields are set, they all default to None."""
        from odysseus.agents.review.models import ReviewBriefing

        briefing = ReviewBriefing(**_make_minimal_briefing_kwargs())

        assert briefing.stagnation_signal is None
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
