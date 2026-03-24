"""Tests for stratified_split card set partitioning."""

from __future__ import annotations

from datetime import datetime

from odysseus.agents.routing_rationale_models import (
    RationaleCard,
    RationaleCardSet,
    RouteExclusion,
    VocabularyEntry,
    VocabularyRegistry,
)
from odysseus.agents.stratified_split import stratified_split
from odysseus.eval.models import Example, Expected, ModelCostQuality


def _make_example(id_: str, input_: str, route: str) -> Example:
    """Create a minimal Example for testing."""
    return Example(
        id=id_,
        input=input_,
        expected=Expected(
            route=route,
            routes={route: ModelCostQuality(cost=0.01, quality_score=0.9)},
        ),
        split="dev",
    )


def _make_card(example_id: str, route: str, intent: str, complexity: str):
    return RationaleCard(
        example_id=example_id,
        assigned_route=route,
        intent_pattern=intent,
        complexity_structure=complexity,
        route_exclusions=[
            RouteExclusion(route="other", reason="not relevant"),
        ],
        ambiguity_tags=[],
    )


def _make_registry():
    return VocabularyRegistry(
        intent_pattern=[
            VocabularyEntry(
                name="direct-question",
                definition="A straightforward question",
                example_ids=["ex1", "ex2", "ex3", "ex4"],
            ),
        ],
        complexity_structure=[
            VocabularyEntry(
                name="single-step",
                definition="One-step reasoning",
                example_ids=["ex1", "ex2", "ex3", "ex4"],
            ),
        ],
        ambiguity_tags=[],
    )


def _make_card_set(examples, cards, registry):
    return RationaleCardSet(
        cards=cards,
        dataset_hash="abc123",
        registry=registry,
        created_at=datetime(2026, 1, 1),
    )


def test_split_returns_five_elements():
    """stratified_split returns (dev, holdout, dev_cards, holdout_cards, report)."""
    examples = [
        _make_example(f"ex{i}", f"query {i}", "route-a")
        for i in range(1, 5)
    ]
    cards = {
        ex.id: _make_card(ex.id, "route-a", "direct-question", "single-step")
        for ex in examples
    }
    registry = _make_registry()
    card_set = _make_card_set(examples, cards, registry)

    result = stratified_split(examples, card_set)
    assert len(result) == 5, f"Expected 5-tuple, got {len(result)}-tuple"

    dev_ex, holdout_ex, dev_cards, holdout_cards, report = result
    assert isinstance(dev_cards, RationaleCardSet)
    assert isinstance(holdout_cards, RationaleCardSet)


def test_split_card_sets_match_examples():
    """Dev/holdout card sets contain exactly the cards for their examples."""
    examples = [
        _make_example(f"ex{i}", f"query {i}", "route-a")
        for i in range(1, 11)
    ]
    cards = {
        ex.id: _make_card(ex.id, "route-a", "direct-question", "single-step")
        for ex in examples
    }
    registry = _make_registry()
    card_set = _make_card_set(examples, cards, registry)

    dev_ex, holdout_ex, dev_cards, holdout_cards, report = stratified_split(
        examples, card_set
    )

    dev_ids = {ex.id for ex in dev_ex}
    holdout_ids = {ex.id for ex in holdout_ex}

    assert set(dev_cards.cards.keys()) == dev_ids
    assert set(holdout_cards.cards.keys()) == holdout_ids


def test_split_card_sets_share_registry():
    """Both dev and holdout card sets have the same registry."""
    examples = [
        _make_example(f"ex{i}", f"query {i}", "route-a")
        for i in range(1, 5)
    ]
    cards = {
        ex.id: _make_card(ex.id, "route-a", "direct-question", "single-step")
        for ex in examples
    }
    registry = _make_registry()
    card_set = _make_card_set(examples, cards, registry)

    _, _, dev_cards, holdout_cards, _ = stratified_split(examples, card_set)

    assert dev_cards.registry == holdout_cards.registry
    assert dev_cards.dataset_hash == holdout_cards.dataset_hash


def test_degenerate_single_example_all_to_dev():
    """Single example: all goes to dev, holdout card set is empty."""
    examples = [_make_example("ex1", "query 1", "route-a")]
    cards = {"ex1": _make_card("ex1", "route-a", "direct-question", "single-step")}
    registry = _make_registry()
    card_set = _make_card_set(examples, cards, registry)

    dev_ex, holdout_ex, dev_cards, holdout_cards, _ = stratified_split(
        examples, card_set
    )

    assert len(dev_ex) == 1
    assert len(holdout_ex) == 0
    assert set(dev_cards.cards.keys()) == {"ex1"}
    assert len(holdout_cards.cards) == 0
