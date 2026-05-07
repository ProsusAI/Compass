"""Smoke tests for odysseus.agents.review.render."""

from __future__ import annotations

import pytest

from odysseus.agents.review.models import (
    BatchOutcome,
    CandidateAnalysis,
    ChildVariant,
    ClassRecallEntry,
    ConfusionImpact,
    DiminishingReturns,
    DirectiveOutcome,
    DiversityMetrics,
    EditDirective,
    MetricDeltas,
    OracleMetrics,
    ReviewBriefing,
    UserTarget,
    UserTargetProgress,
)
from odysseus.agents.review.render import render_briefing_summary
from odysseus.agents.prompt_builder.search import Candidate
from odysseus.agents.routing_context import RouteDefinition, RouteOrdering, RoutingContext, RoutingDimension
from odysseus.eval.models import ErrorBreakdown, RunSummary, ScoreReport


def _make_score_report(version: str) -> ScoreReport:
    from datetime import UTC, datetime

    now = datetime.now(tz=UTC)
    return ScoreReport(
        metrics={"accuracy": 0.82, "quality_change": 0.02},
        summary=RunSummary(
            total=100,
            succeeded=98,
            failed=2,
            total_cost=0.05,
            start_time=now,
            end_time=now,
            duration_seconds=10.0,
        ),
        errors=[ErrorBreakdown(example_id="e1", error="timeout", retries=2)],
        diff=None,
        report_path=f"outputs/run1/eval/{version}/report.json",
        results_path=f"outputs/run1/eval/{version}/results.jsonl",
    )


def _make_minimal_briefing() -> ReviewBriefing:
    candidate = Candidate(
        prompt_version="v1",
        parent_version=None,
        quality_score=0.82,
        cost=0.05,
        round_introduced=1,
    )
    candidate_analysis = CandidateAnalysis(
        candidate_version="v1",
        parent_version=None,
        mutation_description="seed",
        score_report=_make_score_report("v1"),
        delta_vs_parent=MetricDeltas(quality_delta=0.02, cost_delta=-0.01, per_class_recall_deltas={}),
    )
    return ReviewBriefing(
        round=2,
        candidates=[candidate_analysis],
        elite_set=[candidate],
        per_class_recall={
            "route_a": ClassRecallEntry(recall=0.80, support=50, trend=[0.75, 0.78, 0.80], regression_flag=False),
            "route_b": ClassRecallEntry(recall=0.60, support=20, trend=[0.70, 0.65, 0.60], regression_flag=True),
        },
        diversity_metrics=DiversityMetrics(example_overlap_ratio=0.3),
        diminishing_returns=DiminishingReturns(
            score_trajectory=[0.75, 0.78, 0.80],
            improvement_trend=0.025,
            stagnation_flag=False,
        ),
        oracle_metrics=OracleMetrics(
            oracle_cost_change=-0.10,
            oracle_quality_change=0.15,
            candidate_quality_captured=0.67,
        ),
        target_progress=[
            UserTargetProgress(
                target=UserTarget(metric="accuracy", operator=">=", threshold=0.85),
                current_value=0.82,
                met=False,
                progress_ratio=0.965,
                oracle_ceiling=0.90,
                target_above_oracle=False,
            )
        ],
        confusion_analysis=[
            ConfusionImpact(
                true_route="route_a",
                predicted_route="route_b",
                count=10,
                support=50,
                misroute_rate=0.20,
                cost_impact=0.05,
                quality_impact=0.08,
                avg_cost_impact=0.005,
                avg_quality_impact=0.008,
                persistence_rate=0.6,
                persistent_count=6,
                volatile_count=4,
                effective_impact=0.08,
            )
        ],
        directive_history=[
            DirectiveOutcome(prior_directive_id="d-1-1", was_attempted=True, outcome="improved")
        ],
        batch_outcomes=[
            BatchOutcome(
                variant_id="cv1",
                parent_version="v0",
                mutation_strategy="targeted",
                directive_ids=["d-1-1"],
                candidate_version="v1",
                eval_status="scored",
                quality_delta_vs_parent=0.02,
                is_new_best=True,
            )
        ],
        child_variants=[
            ChildVariant(
                variant_id="cv2",
                hypothesis="Fix recall on route_a by adding contrast pair",
                directives=[
                    EditDirective(
                        directive_id="d-2-1",
                        target_version="v1",
                        block_type="contrast_pair",
                        block_identifier="contrast-1",
                        granularity="macro",
                        directive="Add a contrast pair for route_a vs route_b",
                        priority="high",
                    )
                ],
            )
        ],
        single_candidate_meets_all=False,
        backtracking=False,
        executive_summary="Round 2 summary: moderate improvement on quality.",
    )


class TestRenderBriefingSummary:
    def test_returns_non_empty_string(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_length_under_12000_chars(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert len(result) < 12_000, f"render output too long: {len(result)} chars"

    def test_contains_round_header(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert "## Round 2" in result

    def test_contains_per_class_recall_header(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert "## Per-class recall" in result

    def test_contains_confusion_analysis_header(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert "## Confusion analysis" in result

    def test_contains_diversity_header(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert "## Diversity" in result

    def test_contains_target_progress_header(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert "## Target progress" in result

    def test_contains_candidates_header(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert "## Candidates this round" in result

    def test_contains_elite_set_header(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert "## Elite set" in result

    def test_contains_executive_summary(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert "# Executive summary" in result
        assert "Round 2 summary" in result

    def test_version_ids_backticked(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert "`v1`" in result

    def test_confusion_routes_backticked(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert "`route_a`" in result
        assert "`route_b`" in result

    def test_no_executive_summary_when_empty(self) -> None:
        briefing = _make_minimal_briefing()
        briefing = briefing.model_copy(update={"executive_summary": ""})
        result = render_briefing_summary(briefing)
        assert "# Executive summary" not in result

    def test_no_routing_context_section_when_none(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert "## Routing context" not in result

    def test_no_beam_section_when_no_beam_width(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert "## Beam state" not in result

    def test_beam_section_present_when_beam_width_set(self) -> None:
        briefing = _make_minimal_briefing()
        briefing = briefing.model_copy(
            update={"beam_width": 4, "hypervolume": 0.75, "reference_point": (0.0, 1.0)}
        )
        result = render_briefing_summary(briefing)
        assert "## Beam state" in result
        assert "beam_width: 4" in result

    def test_last_round_directives_present_for_round_2(self) -> None:
        briefing = _make_minimal_briefing()
        result = render_briefing_summary(briefing)
        assert "## Last round directives" in result
        assert "`d-1-1`" in result


def _make_routing_context() -> RoutingContext:
    return RoutingContext(
        domain="test-domain",
        routes=[
            RouteDefinition(name="simple", description="Handles simple factual queries"),
            RouteDefinition(name="complex", description="Handles multi-step reasoning tasks"),
        ],
        routing_dimensions=[
            RoutingDimension(name="cost", direction="lower_is_better", description="Inference cost per query"),
            RoutingDimension(name="quality", direction="higher_is_better", description="Output accuracy score"),
        ],
        route_ordering=RouteOrdering(dimension="cost", order=["simple", "complex"]),
    )


class TestRoutingContextRendering:
    def test_routing_context_section_present(self) -> None:
        briefing = _make_minimal_briefing()
        briefing = briefing.model_copy(update={"routing_context": _make_routing_context()})
        result = render_briefing_summary(briefing)
        assert "## Routing context" in result

    def test_route_descriptions_rendered(self) -> None:
        briefing = _make_minimal_briefing()
        briefing = briefing.model_copy(update={"routing_context": _make_routing_context()})
        result = render_briefing_summary(briefing)
        assert "Handles simple factual queries" in result
        assert "Handles multi-step reasoning tasks" in result

    def test_routing_dimensions_table(self) -> None:
        briefing = _make_minimal_briefing()
        briefing = briefing.model_copy(update={"routing_context": _make_routing_context()})
        result = render_briefing_summary(briefing)
        assert "cost" in result
        assert "lower_is_better" in result
        assert "higher_is_better" in result
        assert "Inference cost per query" in result

    def test_route_ordering_line(self) -> None:
        briefing = _make_minimal_briefing()
        briefing = briefing.model_copy(update={"routing_context": _make_routing_context()})
        result = render_briefing_summary(briefing)
        assert "ordering: dimension=cost" in result
        assert "simple" in result
        assert "complex" in result


class TestPerClassRecallHiddenFooter:
    def test_hidden_footer_when_low_support_routes_filtered(self) -> None:
        """When low-support routes are filtered, footer shows how many were hidden."""
        briefing = _make_minimal_briefing()
        # route_b has support=20 (below median of ~35), no regression — should be hidden
        # route_a has support=50, no regression — above median — shown
        # route_c has support=5, regression=False — below median — hidden
        pcr = {
            "route_a": ClassRecallEntry(recall=0.90, support=50, trend=[0.85, 0.88, 0.90], regression_flag=False),
            "route_b": ClassRecallEntry(recall=0.70, support=20, trend=[0.72, 0.71, 0.70], regression_flag=False),
            "route_c": ClassRecallEntry(recall=0.50, support=5, trend=[0.55, 0.52, 0.50], regression_flag=False),
        }
        briefing = briefing.model_copy(update={"per_class_recall": pcr})
        result = render_briefing_summary(briefing)
        assert "hidden" in result
        assert "get_per_class_recall_tool" in result

    def test_no_hidden_footer_when_all_routes_shown(self) -> None:
        """When all routes pass the filter, no hidden footer is appended."""
        briefing = _make_minimal_briefing()
        # Both routes have regression=True so both are shown
        pcr = {
            "route_a": ClassRecallEntry(recall=0.80, support=50, trend=[0.85, 0.82, 0.80], regression_flag=True),
            "route_b": ClassRecallEntry(recall=0.60, support=20, trend=[0.70, 0.65, 0.60], regression_flag=True),
        }
        briefing = briefing.model_copy(update={"per_class_recall": pcr})
        result = render_briefing_summary(briefing)
        # No routes were filtered
        assert "hidden" not in result or "get_per_class_recall_tool" not in result


class TestConfusionAnalysisExampleIds:
    def test_sample_example_ids_rendered(self) -> None:
        """When sample_example_ids is populated, example ids appear under the cell row."""
        briefing = _make_minimal_briefing()
        confusion = [
            ConfusionImpact(
                true_route="route_a",
                predicted_route="route_b",
                count=10,
                support=50,
                misroute_rate=0.20,
                cost_impact=0.05,
                quality_impact=0.08,
                avg_cost_impact=0.005,
                avg_quality_impact=0.008,
                persistence_rate=0.6,
                persistent_count=6,
                volatile_count=4,
                effective_impact=0.13,
                sample_example_ids=["ex-001", "ex-002", "ex-003"],
            )
        ]
        briefing = briefing.model_copy(update={"confusion_analysis": confusion})
        result = render_briefing_summary(briefing)
        assert "ex-001" in result
        assert "ex-002" in result
        assert "ex-003" in result

    def test_no_sample_ids_when_empty(self) -> None:
        """When sample_example_ids is empty, no sample line is appended."""
        briefing = _make_minimal_briefing()
        # The minimal briefing has sample_example_ids=[] by default
        result = render_briefing_summary(briefing)
        assert "sample examples:" not in result

    def test_at_most_3_example_ids_rendered(self) -> None:
        """Only up to 3 sample_example_ids are rendered per cell."""
        briefing = _make_minimal_briefing()
        confusion = [
            ConfusionImpact(
                true_route="route_a",
                predicted_route="route_b",
                count=10,
                support=50,
                misroute_rate=0.20,
                cost_impact=0.05,
                quality_impact=0.08,
                avg_cost_impact=0.005,
                avg_quality_impact=0.008,
                persistence_rate=0.6,
                persistent_count=6,
                volatile_count=4,
                effective_impact=0.13,
                # Preprocessor caps at 3, but renderer also enforces [:3]
                sample_example_ids=["ex-001", "ex-002", "ex-003"],
            )
        ]
        briefing = briefing.model_copy(update={"confusion_analysis": confusion})
        result = render_briefing_summary(briefing)
        # ex-004 should NOT appear
        assert "ex-004" not in result
