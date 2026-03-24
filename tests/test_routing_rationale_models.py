"""Tests for routing rationale schema models (THP-82)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from odysseus.agents.routing_rationale_models import (
    KEBAB_CASE_RE,
    SCREAMING_SNAKE_RE,
    RationaleCard,
    RationaleCardSet,
    TierDisqualifier,
    VocabularyEntry,
    VocabularyRegistry,
)


# ---------------------------------------------------------------------------
# Regex constants
# ---------------------------------------------------------------------------


def test_kebab_case_re_matches_valid():
    valid = ["data-analysis", "simple", "multi-step-reasoning", "abc123", "a1-b2"]
    for s in valid:
        assert KEBAB_CASE_RE.match(s), f"Expected {s!r} to match KEBAB_CASE_RE"


def test_kebab_case_re_rejects_invalid():
    invalid = [
        "DataAnalysis",   # uppercase
        "data_analysis",  # underscore
        "-leading-dash",  # leading dash
        "trailing-",      # trailing dash
        "",               # empty
        "SCREAMING",      # uppercase
    ]
    for s in invalid:
        assert not KEBAB_CASE_RE.fullmatch(s), f"Expected {s!r} to NOT match KEBAB_CASE_RE"


def test_screaming_snake_re_matches_valid():
    valid = ["MULTI_HOP", "SIMPLE", "A1_B2", "AMBIGUOUS_SCOPE"]
    for s in valid:
        assert SCREAMING_SNAKE_RE.match(s), f"Expected {s!r} to match SCREAMING_SNAKE_RE"


def test_screaming_snake_re_rejects_invalid():
    invalid = [
        "lower_case",
        "Mixed_Case",
        "_LEADING",
        "TRAILING_",
        "",
        "kebab-case",
    ]
    for s in invalid:
        assert not SCREAMING_SNAKE_RE.fullmatch(s), f"Expected {s!r} to NOT match SCREAMING_SNAKE_RE"


# ---------------------------------------------------------------------------
# TierDisqualifier
# ---------------------------------------------------------------------------


def test_tier_disqualifier_valid():
    td = TierDisqualifier(route="claude-haiku", reason="Too simple for haiku tier")
    assert td.route == "claude-haiku"
    assert td.reason == "Too simple for haiku tier"


def test_tier_disqualifier_empty_route_rejected():
    with pytest.raises(ValidationError, match="route must be non-empty"):
        TierDisqualifier(route="", reason="some reason")


def test_tier_disqualifier_whitespace_route_rejected():
    with pytest.raises(ValidationError, match="route must be non-empty"):
        TierDisqualifier(route="   ", reason="some reason")


def test_tier_disqualifier_empty_reason_rejected():
    with pytest.raises(ValidationError, match="reason must be non-empty"):
        TierDisqualifier(route="claude-haiku", reason="")


def test_tier_disqualifier_whitespace_reason_rejected():
    with pytest.raises(ValidationError, match="reason must be non-empty"):
        TierDisqualifier(route="claude-haiku", reason="   ")


def test_tier_disqualifier_round_trip():
    td = TierDisqualifier(route="claude-haiku", reason="Not capable enough")
    data = td.model_dump()
    td2 = TierDisqualifier(**data)
    assert td2 == td


# ---------------------------------------------------------------------------
# RationaleCard
# ---------------------------------------------------------------------------


def _make_rationale_card(**overrides) -> RationaleCard:
    defaults = dict(
        example_id="ex-001",
        assigned_route="claude-sonnet",
        intent_pattern="data-analysis",
        complexity_structure="multi-step-reasoning",
        tier_disqualifiers=[
            TierDisqualifier(route="claude-haiku", reason="Requires nuanced reasoning")
        ],
        ambiguity_tags=["AMBIGUOUS_SCOPE"],
    )
    defaults.update(overrides)
    return RationaleCard(**defaults)


def test_rationale_card_valid():
    card = _make_rationale_card()
    assert card.example_id == "ex-001"
    assert card.assigned_route == "claude-sonnet"
    assert card.intent_pattern == "data-analysis"
    assert card.complexity_structure == "multi-step-reasoning"
    assert len(card.tier_disqualifiers) == 1
    assert card.ambiguity_tags == ["AMBIGUOUS_SCOPE"]


def test_rationale_card_empty_example_id_rejected():
    with pytest.raises(ValidationError, match="example_id must be non-empty"):
        _make_rationale_card(example_id="")


def test_rationale_card_empty_assigned_route_rejected():
    with pytest.raises(ValidationError, match="assigned_route must be non-empty"):
        _make_rationale_card(assigned_route="")


def test_rationale_card_intent_pattern_invalid_kebab():
    with pytest.raises(ValidationError, match="intent_pattern must be kebab-case"):
        _make_rationale_card(intent_pattern="DataAnalysis")


def test_rationale_card_intent_pattern_with_underscore_rejected():
    with pytest.raises(ValidationError, match="intent_pattern must be kebab-case"):
        _make_rationale_card(intent_pattern="data_analysis")


def test_rationale_card_complexity_structure_invalid():
    with pytest.raises(ValidationError, match="complexity_structure must be kebab-case"):
        _make_rationale_card(complexity_structure="MultiStep")


def test_rationale_card_ambiguity_tag_invalid_screaming_snake():
    with pytest.raises(ValidationError, match="ambiguity_tags entries must be SCREAMING_SNAKE_CASE"):
        _make_rationale_card(ambiguity_tags=["ambiguous-scope"])


def test_rationale_card_ambiguity_tag_mixed_case_rejected():
    with pytest.raises(ValidationError, match="ambiguity_tags entries must be SCREAMING_SNAKE_CASE"):
        _make_rationale_card(ambiguity_tags=["Ambiguous_Scope"])


def test_rationale_card_empty_ambiguity_tags_allowed():
    card = _make_rationale_card(ambiguity_tags=[])
    assert card.ambiguity_tags == []


def test_rationale_card_empty_tier_disqualifiers_allowed():
    card = _make_rationale_card(tier_disqualifiers=[])
    assert card.tier_disqualifiers == []


def test_rationale_card_round_trip():
    card = _make_rationale_card()
    data = card.model_dump()
    card2 = RationaleCard(**data)
    assert card2 == card


def test_rationale_card_single_segment_intent_pattern():
    card = _make_rationale_card(intent_pattern="summarization")
    assert card.intent_pattern == "summarization"


# ---------------------------------------------------------------------------
# VocabularyEntry
# ---------------------------------------------------------------------------


def test_vocabulary_entry_valid():
    entry = VocabularyEntry(
        name="data-analysis",
        definition="Tasks involving structured data querying or transformation.",
        example_ids=["ex-001", "ex-002"],
    )
    assert entry.name == "data-analysis"
    assert entry.justification is None


def test_vocabulary_entry_with_justification():
    entry = VocabularyEntry(
        name="data-analysis",
        definition="Tasks involving data.",
        example_ids=[],
        justification="Added in run 3 to capture SQL-heavy examples.",
    )
    assert entry.justification == "Added in run 3 to capture SQL-heavy examples."


def test_vocabulary_entry_empty_name_rejected():
    with pytest.raises(ValidationError, match="name must be non-empty"):
        VocabularyEntry(name="", definition="some def", example_ids=[])


def test_vocabulary_entry_empty_definition_rejected():
    with pytest.raises(ValidationError, match="definition must be non-empty"):
        VocabularyEntry(name="data-analysis", definition="", example_ids=[])


def test_vocabulary_entry_round_trip():
    entry = VocabularyEntry(
        name="multi-hop",
        definition="Reasoning requiring multiple inference steps.",
        example_ids=["ex-003"],
        justification="Captured from run 2.",
    )
    data = entry.model_dump()
    entry2 = VocabularyEntry(**data)
    assert entry2 == entry


# ---------------------------------------------------------------------------
# VocabularyRegistry
# ---------------------------------------------------------------------------


def _make_registry(**overrides) -> VocabularyRegistry:
    defaults = dict(
        intent_pattern=[
            VocabularyEntry(name="data-analysis", definition="Data tasks.", example_ids=["ex-001"]),
        ],
        complexity_structure=[
            VocabularyEntry(name="multi-step-reasoning", definition="Complex reasoning.", example_ids=["ex-001"]),
        ],
        ambiguity_tags=[
            VocabularyEntry(name="AMBIGUOUS_SCOPE", definition="Scope is unclear.", example_ids=["ex-001"]),
        ],
    )
    defaults.update(overrides)
    return VocabularyRegistry(**defaults)


def test_vocabulary_registry_valid():
    reg = _make_registry()
    assert len(reg.intent_pattern) == 1
    assert len(reg.complexity_structure) == 1
    assert len(reg.ambiguity_tags) == 1


def test_vocabulary_registry_empty_lists_allowed():
    reg = VocabularyRegistry(intent_pattern=[], complexity_structure=[], ambiguity_tags=[])
    assert reg.intent_pattern == []


def test_vocabulary_registry_intent_pattern_non_kebab_rejected():
    with pytest.raises(ValidationError, match="intent_pattern entries must have kebab-case names"):
        _make_registry(
            intent_pattern=[
                VocabularyEntry(name="DataAnalysis", definition="Data tasks.", example_ids=[]),
            ]
        )


def test_vocabulary_registry_complexity_structure_non_kebab_rejected():
    with pytest.raises(ValidationError, match="complexity_structure entries must have kebab-case names"):
        _make_registry(
            complexity_structure=[
                VocabularyEntry(name="MultiStep", definition="Complex reasoning.", example_ids=[]),
            ]
        )


def test_vocabulary_registry_ambiguity_tags_non_screaming_snake_rejected():
    with pytest.raises(ValidationError, match="ambiguity_tags entries must have SCREAMING_SNAKE_CASE names"):
        _make_registry(
            ambiguity_tags=[
                VocabularyEntry(name="ambiguous-scope", definition="Scope unclear.", example_ids=[]),
            ]
        )


def test_vocabulary_registry_round_trip():
    reg = _make_registry()
    data = reg.model_dump()
    reg2 = VocabularyRegistry(**data)
    assert reg2 == reg


# ---------------------------------------------------------------------------
# RationaleCardSet
# ---------------------------------------------------------------------------


def _make_card_set(**overrides) -> RationaleCardSet:
    card = _make_rationale_card()
    registry = _make_registry()
    defaults = dict(
        cards={"ex-001": card},
        dataset_hash="abc123def456",
        registry=registry,
        created_at=datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return RationaleCardSet(**defaults)


def test_rationale_card_set_valid():
    card_set = _make_card_set()
    assert "ex-001" in card_set.cards
    assert card_set.dataset_hash == "abc123def456"
    assert card_set.inherited_from is None


def test_rationale_card_set_with_inherited_from():
    card_set = _make_card_set(inherited_from="sha256:oldhashabc")
    assert card_set.inherited_from == "sha256:oldhashabc"


def test_rationale_card_set_empty_dataset_hash_rejected():
    with pytest.raises(ValidationError, match="dataset_hash must be non-empty"):
        _make_card_set(dataset_hash="")


def test_rationale_card_set_whitespace_dataset_hash_rejected():
    with pytest.raises(ValidationError, match="dataset_hash must be non-empty"):
        _make_card_set(dataset_hash="   ")


def test_rationale_card_set_empty_cards_allowed():
    card_set = _make_card_set(cards={})
    assert card_set.cards == {}


def test_rationale_card_set_round_trip():
    card_set = _make_card_set()
    data = card_set.model_dump()
    card_set2 = RationaleCardSet(**data)
    assert card_set2 == card_set


def test_rationale_card_set_json_serialization():
    card_set = _make_card_set()
    json_str = card_set.model_dump_json()
    card_set2 = RationaleCardSet.model_validate_json(json_str)
    assert card_set2.dataset_hash == card_set.dataset_hash
    assert card_set2.created_at == card_set.created_at
