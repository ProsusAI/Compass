"""Tests for deterministic validation runner (no LLM judge)."""

from __future__ import annotations

from datetime import datetime

from odysseus.agents.routing_rationale_checks_deterministic import (
    validate_deterministic,
)
from odysseus.agents.routing_rationale_models import (
    RationaleCard,
    RationaleCardSet,
    RouteDefinition,
    RouteExclusion,
    RoutingContext,
    RoutingDimension,
    VocabularyEntry,
    VocabularyRegistry,
)


def _make_routing_context():
    return RoutingContext(
        domain="test",
        routes=[
            RouteDefinition(name="route-a", description="Route A"),
            RouteDefinition(name="route-b", description="Route B"),
        ],
        routing_dimensions=[
            RoutingDimension(
                name="complexity",
                direction="lower_is_better",
                description="test",
            ),
        ],
    )


def _make_valid_card_set():
    registry = VocabularyRegistry(
        intent_pattern=[
            VocabularyEntry(
                name="direct-question",
                definition="A straightforward question",
                example_ids=["ex1", "ex2", "ex3"],
            ),
        ],
        complexity_structure=[
            VocabularyEntry(
                name="single-step",
                definition="One-step reasoning",
                example_ids=["ex1", "ex2", "ex3"],
            ),
        ],
        ambiguity_tags=[],
    )
    cards = {
        f"ex{i}": RationaleCard(
            example_id=f"ex{i}",
            assigned_route="route-a",
            intent_pattern="direct-question",
            complexity_structure="single-step",
            route_exclusions=[
                RouteExclusion(route="route-b", reason="not relevant"),
            ],
            ambiguity_tags=[],
        )
        for i in range(1, 4)
    }
    return RationaleCardSet(
        cards=cards,
        dataset_hash="abc",
        registry=registry,
        created_at=datetime(2026, 1, 1),
    )


def test_valid_card_set_all_pass():
    """Valid card set passes all deterministic checks."""
    ctx = _make_routing_context()
    card_set = _make_valid_card_set()
    results = validate_deterministic(card_set, ctx, dataset_size=3)
    failures = [r for r in results if not r.passed]
    assert failures == [], f"Unexpected failures: {failures}"


def test_does_not_include_registry_consistency():
    """Deterministic runner excludes check_registry_consistency."""
    ctx = _make_routing_context()
    card_set = _make_valid_card_set()
    results = validate_deterministic(card_set, ctx, dataset_size=3)
    check_names = {r.check_name for r in results}
    assert "check_registry_consistency" not in check_names


def test_missing_exclusion_detected():
    """Missing route exclusion is caught."""
    ctx = _make_routing_context()
    card_set = _make_valid_card_set()
    # Remove the exclusion for route-b
    card_set.cards["ex1"].route_exclusions = []
    results = validate_deterministic(card_set, ctx, dataset_size=3)
    coverage_results = [r for r in results if r.check_name == "check_exclusion_coverage"]
    failed = [r for r in coverage_results if not r.passed]
    assert len(failed) == 1
    assert "ex1" in failed[0].affected_ids


def test_incomplete_card_set_detected():
    """Fewer cards than dataset_size triggers check_card_completeness failure."""
    ctx = _make_routing_context()
    card_set = _make_valid_card_set()  # 3 cards
    results = validate_deterministic(card_set, ctx, dataset_size=10)
    completeness = [r for r in results if r.check_name == "check_card_completeness"]
    assert len(completeness) == 1
    assert completeness[0].passed is False


def test_card_completeness_runs_first():
    """check_card_completeness is the first dataset-level check."""
    ctx = _make_routing_context()
    card_set = _make_valid_card_set()
    results = validate_deterministic(card_set, ctx, dataset_size=3)
    assert results[0].check_name == "check_card_completeness"
