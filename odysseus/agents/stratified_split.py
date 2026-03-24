"""Deterministic stratified split for annotated routing datasets (THP-110).

Spec: docs/superpowers/specs/2026-03-24-thp-110-stratified-split-methodology.md
"""

from __future__ import annotations

from pydantic import BaseModel

from odysseus.agents.routing_rationale_models import RationaleCardSet
from odysseus.eval.models import Example


class SplitMismatchError(Exception):
    """Raised when examples and rationale cards don't match by example_id."""


class StratumReport(BaseModel):
    """Distribution report for a single stratum."""

    key: list[str]
    total: int
    dev: int
    holdout: int


class SplitReport(BaseModel):
    """Report produced alongside the dev/holdout split."""

    dataset_hash: str
    split_ratio: dict[str, float]
    total_examples: int
    dev_count: int
    holdout_count: int
    singleton_strata_count: int
    strata: list[StratumReport]
    distributions: dict[str, dict[str, dict[str, float | int]]]


def validate_split_inputs(
    examples: list[Example],
    card_set: RationaleCardSet,
) -> None:
    """Validate that examples and rationale cards match by ID.

    Raises SplitMismatchError if any example lacks a card or vice versa.
    """
    example_ids = {ex.id for ex in examples}
    card_ids = set(card_set.cards.keys())

    missing_cards = example_ids - card_ids
    extra_cards = card_ids - example_ids

    messages: list[str] = []
    if missing_cards:
        messages.append(f"examples missing cards: {sorted(missing_cards)}")
    if extra_cards:
        messages.append(f"cards missing examples: {sorted(extra_cards)}")

    if messages:
        raise SplitMismatchError("; ".join(messages))
