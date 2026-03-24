"""Tests for stratified split (THP-110)."""

from __future__ import annotations

from datetime import datetime

import pytest

from odysseus.agents.routing_rationale_models import (
    RationaleCard,
    RationaleCardSet,
    RouteExclusion,
    VocabularyEntry,
    VocabularyRegistry,
)
from odysseus.agents.stratified_split import SplitMismatchError, SplitReport, validate_split_inputs
from odysseus.eval.models import Example, Expected, ModelCostQuality


def make_example(id: str, input: str, route: str) -> Example:
    return Example(
        id=id,
        input=input,
        expected=Expected(
            route=route,
            routes={route: ModelCostQuality(cost=0.01, quality_score=0.9)},
        ),
        split="dev",
    )


def make_card(example_id: str, route: str, intent: str, complexity: str) -> RationaleCard:
    return RationaleCard(
        example_id=example_id,
        assigned_route=route,
        intent_pattern=intent,
        complexity_structure=complexity,
        route_exclusions=[
            RouteExclusion(route="other", reason="Not applicable"),
        ],
        ambiguity_tags=[],
    )


def make_card_set(cards: list[RationaleCard]) -> RationaleCardSet:
    return RationaleCardSet(
        cards={c.example_id: c for c in cards},
        dataset_hash="abc123",
        registry=VocabularyRegistry(
            intent_pattern=[
                VocabularyEntry(name="data-analysis", definition="Analysis tasks", example_ids=[]),
            ],
            complexity_structure=[
                VocabularyEntry(name="single-step", definition="Simple tasks", example_ids=[]),
            ],
            ambiguity_tags=[],
        ),
        created_at=datetime(2026, 1, 1),
    )


def test_split_report_round_trip():
    """SplitReport can be constructed and serialized."""
    report = SplitReport(
        dataset_hash="abc123",
        split_ratio={"dev": 0.8, "holdout": 0.2},
        total_examples=10,
        dev_count=8,
        holdout_count=2,
        singleton_strata_count=0,
        strata=[],
        distributions={
            "assigned_route": {"dev": {}, "holdout": {}},
            "intent_pattern": {"dev": {}, "holdout": {}},
            "complexity_structure": {"dev": {}, "holdout": {}},
            "ambiguity_tags": {"dev": {}, "holdout": {}},
        },
    )
    data = report.model_dump()
    assert data["dataset_hash"] == "abc123"
    assert data["total_examples"] == 10


def test_split_mismatch_error_is_exception():
    """SplitMismatchError can be raised and caught."""
    with pytest.raises(SplitMismatchError, match="missing"):
        raise SplitMismatchError("missing cards for examples: ex-1")


def test_validate_split_inputs_matching():
    """No error when examples and cards match."""
    examples = [make_example("ex-1", "query", "route-a")]
    cards = [make_card("ex-1", "route-a", "data-analysis", "single-step")]
    card_set = make_card_set(cards)
    validate_split_inputs(examples, card_set)


def test_validate_split_inputs_missing_card():
    """Raise SplitMismatchError when an example has no card."""
    examples = [
        make_example("ex-1", "query", "route-a"),
        make_example("ex-2", "query2", "route-b"),
    ]
    cards = [make_card("ex-1", "route-a", "data-analysis", "single-step")]
    card_set = make_card_set(cards)
    with pytest.raises(SplitMismatchError, match="ex-2"):
        validate_split_inputs(examples, card_set)


def test_validate_split_inputs_extra_card():
    """Raise SplitMismatchError when a card has no example."""
    examples = [make_example("ex-1", "query", "route-a")]
    cards = [
        make_card("ex-1", "route-a", "data-analysis", "single-step"),
        make_card("ex-2", "route-a", "data-analysis", "single-step"),
    ]
    card_set = make_card_set(cards)
    with pytest.raises(SplitMismatchError, match="ex-2"):
        validate_split_inputs(examples, card_set)
