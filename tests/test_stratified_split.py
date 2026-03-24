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
from odysseus.agents.stratified_split import (
    SplitMismatchError,
    SplitReport,
    stratified_split,
    validate_split_inputs,
)
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


def test_stratified_split_basic_80_20():
    """10 examples in one stratum: 8 dev, 2 holdout."""
    examples = [make_example(f"ex-{i}", f"query-{i}", "route-a") for i in range(10)]
    cards = [make_card(f"ex-{i}", "route-a", "data-analysis", "single-step") for i in range(10)]
    card_set = make_card_set(cards)

    dev, holdout, report = stratified_split(examples, card_set, dev_ratio=0.8)

    assert len(dev) == 8
    assert len(holdout) == 2
    assert report.dev_count == 8
    assert report.holdout_count == 2
    assert report.total_examples == 10


def test_stratified_split_singleton_goes_to_dev():
    """A stratum with 1 member goes to dev; larger strata still split."""
    examples = [
        *[make_example(f"ex-{i}", f"query-{i}", "route-a") for i in range(10)],
        make_example("ex-solo", "query-solo", "route-b"),
    ]
    cards = [
        *[make_card(f"ex-{i}", "route-a", "data-analysis", "single-step") for i in range(10)],
        make_card("ex-solo", "route-b", "code-generation", "multi-step"),
    ]
    card_set = make_card_set(cards)

    dev, holdout, report = stratified_split(examples, card_set, dev_ratio=0.8)

    dev_ids = {ex.id for ex in dev}
    assert "ex-solo" in dev_ids
    assert report.singleton_strata_count == 1
    assert len(holdout) > 0
    holdout_ids = {ex.id for ex in holdout}
    assert "ex-solo" not in holdout_ids


def test_stratified_split_deterministic():
    """Same inputs in different order produce same split."""
    examples = [make_example(f"ex-{i}", f"query-{i}", "route-a") for i in range(20)]
    cards = [make_card(f"ex-{i}", "route-a", "data-analysis", "single-step") for i in range(20)]
    card_set = make_card_set(cards)

    dev1, holdout1, _ = stratified_split(examples, card_set)
    dev2, holdout2, _ = stratified_split(list(reversed(examples)), card_set)

    assert sorted(e.id for e in dev1) == sorted(e.id for e in dev2)
    assert sorted(e.id for e in holdout1) == sorted(e.id for e in holdout2)


def test_stratified_split_rounding_favors_dev():
    """When stratum size doesn't divide cleanly, dev gets the extra."""
    examples = [make_example(f"ex-{i}", f"query-{i}", "route-a") for i in range(7)]
    cards = [make_card(f"ex-{i}", "route-a", "data-analysis", "single-step") for i in range(7)]
    card_set = make_card_set(cards)

    dev, holdout, report = stratified_split(examples, card_set, dev_ratio=0.8)

    assert len(dev) >= len(holdout)
    assert len(dev) + len(holdout) == 7
    assert report.dev_count == 6
    assert report.holdout_count == 1


def test_stratified_split_degenerate_single_example():
    """Dataset with 1 example: all to dev, empty holdout."""
    examples = [make_example("ex-0", "query-0", "route-a")]
    cards = [make_card("ex-0", "route-a", "data-analysis", "single-step")]
    card_set = make_card_set(cards)

    dev, holdout, report = stratified_split(examples, card_set)

    assert len(dev) == 1
    assert len(holdout) == 0


def test_stratified_split_preserves_route_balance():
    """Both dev and holdout have examples from each route."""
    examples = [make_example(f"a-{i}", f"query-a-{i}", "route-a") for i in range(10)] + [
        make_example(f"b-{i}", f"query-b-{i}", "route-b") for i in range(10)
    ]
    cards = [make_card(f"a-{i}", "route-a", "data-analysis", "single-step") for i in range(10)] + [
        make_card(f"b-{i}", "route-b", "code-generation", "multi-step") for i in range(10)
    ]
    card_set = make_card_set(cards)

    dev, holdout, report = stratified_split(examples, card_set)

    dev_routes = {ex.expected.route for ex in dev}
    holdout_routes = {ex.expected.route for ex in holdout}
    assert "route-a" in dev_routes
    assert "route-b" in dev_routes
    assert "route-a" in holdout_routes
    assert "route-b" in holdout_routes


def test_split_report_ambiguity_tag_distribution():
    """Report includes raw counts for ambiguity tags across dev/holdout."""
    examples = [make_example(f"ex-{i}", f"query-{i}", "route-a") for i in range(10)]
    cards = []
    for i in range(10):
        card = make_card(f"ex-{i}", "route-a", "data-analysis", "single-step")
        if i < 3:
            card = card.model_copy(update={"ambiguity_tags": ["BOUNDARY_CASE"]})
        cards.append(card)
    card_set = make_card_set(cards)

    _, _, report = stratified_split(examples, card_set)

    tags = report.distributions["ambiguity_tags"]
    total_boundary = tags["dev"].get("BOUNDARY_CASE", 0) + tags["holdout"].get("BOUNDARY_CASE", 0)
    assert total_boundary == 3


def test_public_api_exports():
    """Key names are importable from odysseus.agents."""
    from odysseus.agents import (
        SplitMismatchError,  # noqa: F811
        SplitReport,  # noqa: F811
        stratified_split,  # noqa: F811
    )

    assert SplitMismatchError is not None
    assert SplitReport is not None
    assert stratified_split is not None


def test_stratified_split_empty_dataset():
    """Empty dataset: both outputs empty."""
    card_set = make_card_set([])

    dev, holdout, report = stratified_split([], card_set)

    assert len(dev) == 0
    assert len(holdout) == 0
    assert report.total_examples == 0


def test_stratified_split_all_singletons_empty_holdout():
    """When every stratum is a singleton, holdout is empty."""
    examples = [
        make_example("ex-0", "q0", "route-a"),
        make_example("ex-1", "q1", "route-b"),
        make_example("ex-2", "q2", "route-c"),
    ]
    cards = [
        make_card("ex-0", "route-a", "data-analysis", "single-step"),
        make_card("ex-1", "route-b", "code-generation", "multi-step"),
        make_card("ex-2", "route-c", "summarization", "sequential-dependency"),
    ]
    card_set = make_card_set(cards)

    dev, holdout, report = stratified_split(examples, card_set)

    assert len(dev) == 3
    assert len(holdout) == 0
    assert report.singleton_strata_count == 3


def test_stratified_split_custom_ratio():
    """Custom split ratio is respected."""
    examples = [make_example(f"ex-{i}", f"q-{i}", "route-a") for i in range(10)]
    cards = [make_card(f"ex-{i}", "route-a", "data-analysis", "single-step") for i in range(10)]
    card_set = make_card_set(cards)

    dev, holdout, report = stratified_split(examples, card_set, dev_ratio=0.5)

    assert len(dev) == 5
    assert len(holdout) == 5
    assert report.split_ratio == {"dev": 0.5, "holdout": 0.5}
