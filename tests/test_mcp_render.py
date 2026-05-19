"""Unit tests for pure MCP markdown renderers."""

from __future__ import annotations

from datetime import UTC, datetime

from odysseus.agents.final_report.models import BaselineComparison, BaselineResult
from odysseus.agents.prompt_builder.search import Candidate, RoundSummary, SearchState
from odysseus.agents.review.models import (
    CandidateAnalysis,
    ClassRecallEntry,
    DiminishingReturns,
    DiversityMetrics,
    MetricDeltas,
    ReviewBriefing,
)
from odysseus.agents.review.render import render_briefing_summary
from odysseus.agents.routing_context import RouteDefinition, RouteOrdering, RoutingContext, RoutingDimension
from odysseus.eval.models import (
    ConfidenceInterval,
    ErrorBreakdown,
    EvalResult,
    MetricConfig,
    OutputConfig,
    RunConfig,
    RunReport,
    RunSummary,
    ScoreReport,
)
from odysseus.mcp._render import (
    render_algorithm_state_md,
    render_baselines_md,
    render_review_briefing_md,
    render_routing_context_md,
    render_score_report_md,
    render_search_state_md,
)


def _make_summary() -> RunSummary:
    now = datetime.now(tz=UTC)
    return RunSummary(
        total=5,
        succeeded=4,
        failed=1,
        total_cost=0.125,
        start_time=now,
        end_time=now,
        duration_seconds=2.5,
    )


def _make_score_report(version: str = "v3") -> ScoreReport:
    return ScoreReport(
        metrics={"accuracy": 0.82, "quality_change": 0.02},
        summary=_make_summary(),
        errors=[ErrorBreakdown(example_id="ex-1", error="timeout", retries=2)],
        diff=None,
        report_path=f"outputs/run-1/eval/{version}/report.json",
        results_path=f"outputs/run-1/eval/{version}/results.jsonl",
    )


def _make_run_report(version: str = "v7") -> RunReport:
    return RunReport(
        config=RunConfig(
            backend="mock-echo",
            prompt_version=version,
            data_source="tests/fixtures/integration/dataset.jsonl",
            metrics=[MetricConfig(name="accuracy")],
            output=OutputConfig(),
        ),
        metrics={"accuracy": 0.91},
        results=[
            EvalResult(
                example_id="ex-ok",
                model="mock-echo",
                output={"route": "simple"},
                error=None,
                latency_ms=12.0,
                retries=0,
                token_usage=None,
                cost=0.01,
            ),
            EvalResult(
                example_id="ex-fail",
                model="mock-echo",
                output=None,
                error="timeout",
                latency_ms=30.0,
                retries=1,
                token_usage=None,
                cost=0.0,
            ),
        ],
        summary=_make_summary(),
        confidence_intervals={
            "accuracy": ConfidenceInterval(lower=0.85, upper=0.95, level=0.95),
        },
    )


def _make_routing_context() -> RoutingContext:
    return RoutingContext(
        domain="support triage",
        routes=[
            RouteDefinition(name="simple", description="Fast path"),
            RouteDefinition(name="complex", description="Escalation path"),
        ],
        routing_dimensions=[
            RoutingDimension(name="cost", direction="lower_is_better", description="Inference spend"),
            RoutingDimension(name="quality", direction="higher_is_better", description="Resolution quality"),
        ],
        route_ordering=RouteOrdering(dimension="cost", order=["simple", "complex"]),
    )


def _make_search_state() -> SearchState:
    elite = [
        Candidate(
            prompt_version="v5",
            parent_version="v3",
            quality_score=0.84,
            cost=0.42,
            round_introduced=4,
        )
    ]
    rounds = [
        RoundSummary(round=1, candidates_evaluated=["v1"], new_elite_entries=1, elite_size=1, target_improvement=0.10),
        RoundSummary(round=2, candidates_evaluated=["v2"], new_elite_entries=1, elite_size=2, target_improvement=0.08),
        RoundSummary(round=3, candidates_evaluated=["v3"], new_elite_entries=2, elite_size=3, target_improvement=0.04),
        RoundSummary(round=4, candidates_evaluated=["v4"], new_elite_entries=1, elite_size=3, target_improvement=0.02),
    ]
    return SearchState(
        search_state_id="run-1",
        backend="mock-echo",
        round=4,
        elite_set=elite,
        round_history=rounds,
        loop_phase="review",
        algorithm="beam",
        algorithm_state={
            "beam_width": 3,
            "hypervolume": 0.4,
            "reference_point": (0.0, 1.0),
        },
    )


def _make_briefing() -> ReviewBriefing:
    score_report = _make_score_report("v5")
    candidate = Candidate(
        prompt_version="v5",
        parent_version="v3",
        quality_score=0.84,
        cost=0.42,
        round_introduced=4,
    )
    return ReviewBriefing(
        round=4,
        routing_context=_make_routing_context(),
        candidates=[
            CandidateAnalysis(
                candidate_version="v5",
                parent_version="v3",
                mutation_description="tighten examples",
                score_report=score_report,
                delta_vs_parent=MetricDeltas(quality_delta=0.02, cost_delta=-0.01, per_class_recall_deltas={}),
            )
        ],
        elite_set=[candidate],
        per_class_recall={
            "simple": ClassRecallEntry(recall=0.8, support=10, trend=[0.7, 0.75, 0.8], regression_flag=False),
        },
        diversity_metrics=DiversityMetrics(example_overlap_ratio=0.25),
        diminishing_returns=DiminishingReturns(
            score_trajectory=[0.75, 0.80, 0.84],
            improvement_trend=0.03,
            stagnation_flag=False,
        ),
    )


class TestRenderRoutingContextMd:
    def test_renders_routes_dimensions_and_ordering(self) -> None:
        result = render_routing_context_md(_make_routing_context())
        assert "## Routing context" in result
        assert "support triage" in result
        assert "Fast path" in result
        assert "Inference spend" in result
        assert "ordering: dimension=cost" in result


class TestRenderAlgorithmStateMd:
    def test_empty_state_on_trunk_degrades_gracefully(self) -> None:
        assert render_algorithm_state_md({}, "__unset__") == ""

    def test_known_leaf_algorithm_renders_table(self) -> None:
        result = render_algorithm_state_md(
            {"beam_width": 3, "hypervolume": 0.4, "reference_point": (0.0, 1.0)},
            "beam",
        )
        assert "## Algorithm state (`beam`)" in result
        assert "| beam_width | 3 |" in result
        assert "hypervolume" in result
        assert "reference_point" in result

    def test_unknown_algorithm_uses_generic_fallback(self) -> None:
        result = render_algorithm_state_md({"mystery_knob": 7, "anneal": True}, "unknown_algo")
        assert "## Algorithm state (`unknown_algo`)" in result
        assert "mystery_knob" in result
        assert "anneal" in result


class TestRenderSearchStateMd:
    def test_default_round_history_limit_is_three(self) -> None:
        result = render_search_state_md(_make_search_state())
        assert "last 3 of 4" in result
        assert "| 2 | 1 | 1 | 2 | 0.080 | False |" in result
        assert "| 4 | 1 | 1 | 3 | 0.020 | False |" in result
        assert "| 1 | 1 | 1 | 1 | 0.100 | False |" not in result

    def test_none_round_history_limit_shows_full_history(self) -> None:
        result = render_search_state_md(_make_search_state(), round_history_limit=None)
        assert "last 3 of 4" not in result
        assert "| 1 | 1 | 1 | 1 | 0.100 | False |" in result


class TestRenderScoreReportMd:
    def test_score_report_renders_metrics_and_errors(self) -> None:
        result = render_score_report_md(_make_score_report())
        assert "## Score report — `v3`" in result
        assert "| accuracy | 0.8200 |" in result
        assert "### Errors (1)" in result
        assert "timeout" in result

    def test_run_report_normalizes_and_omits_confidence_intervals(self) -> None:
        result = render_score_report_md(_make_run_report())
        assert "## Score report — `v7`" in result
        assert "| accuracy | 0.9100 |" in result
        assert "confidence_intervals" not in result
        assert "0.95" not in result


class TestRenderBaselinesMd:
    def test_none_returns_empty_string(self) -> None:
        assert render_baselines_md(None) == ""

    def test_renders_baseline_table(self) -> None:
        baseline = BaselineComparison(
            baselines=[
                BaselineResult(strategy="always_cheapest", route="simple", quality_score=0.7, cost=0.01),
                BaselineResult(strategy="always_capable", route="complex", quality_score=0.9, cost=0.03),
            ],
            optimized=BaselineResult(strategy="optimized_prompt", route="mixed", quality_score=0.85, cost=0.02),
        )
        result = render_baselines_md(baseline)
        assert "## Baseline comparison" in result
        assert "always_cheapest" in result
        assert "optimized_prompt" in result


class TestRenderReviewBriefingMd:
    def test_wrapper_matches_direct_review_renderer(self) -> None:
        briefing = _make_briefing()
        assert render_review_briefing_md(briefing) == render_briefing_summary(briefing)
