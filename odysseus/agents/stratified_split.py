"""Deterministic stratified split for annotated routing datasets (THP-110).

Spec: docs/superpowers/specs/2026-03-24-thp-110-stratified-split-methodology.md
"""

from __future__ import annotations

import random
from collections import defaultdict

from pydantic import BaseModel

from odysseus.agents.routing_rationale_models import RationaleCardSet
from odysseus.agents.routing_rationale_registry import compute_dataset_hash
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


def stratified_split(
    examples: list[Example],
    card_set: RationaleCardSet,
    dev_ratio: float = 0.8,
) -> tuple[list[Example], list[Example], SplitReport]:
    """Split annotated examples into dev and holdout sets.

    Uses hierarchical priority stratification on
    (assigned_route, intent_pattern, complexity_structure).

    Args:
        examples: Full dataset examples.
        card_set: Rationale cards matching examples by ID.
        dev_ratio: Proportion allocated to dev set. Default 0.8.

    Returns:
        (dev_examples, holdout_examples, report)

    Raises:
        SplitMismatchError: If examples and cards don't match by ID.
    """
    validate_split_inputs(examples, card_set)

    # Degenerate case
    if len(examples) < 2:
        return _build_result(examples, [], examples, card_set, dev_ratio)

    # Build strata
    strata: dict[tuple[str, str, str], list[Example]] = defaultdict(list)
    for ex in examples:
        card = card_set.cards[ex.id]
        key = (card.assigned_route, card.intent_pattern, card.complexity_structure)
        strata[key].append(ex)

    # Deterministic seed
    dataset_hash = compute_dataset_hash(examples)
    rng = random.Random(dataset_hash)

    dev: list[Example] = []
    holdout: list[Example] = []
    singleton_count = 0

    for _key, members in sorted(strata.items()):
        if len(members) < 2:
            dev.extend(members)
            singleton_count += 1
            continue

        # Sort by ID before shuffling for input-order independence
        shuffled = sorted(members, key=lambda ex: ex.id)
        rng.shuffle(shuffled)

        # holdout count = round(n * holdout_ratio), rest goes to dev
        holdout_count = round(len(shuffled) * (1.0 - dev_ratio))
        dev.extend(shuffled[holdout_count:])
        holdout.extend(shuffled[:holdout_count])

    return _build_result(dev, holdout, examples, card_set, dev_ratio, singleton_count)


def _build_result(
    dev: list[Example],
    holdout: list[Example],
    all_examples: list[Example],
    card_set: RationaleCardSet,
    dev_ratio: float,
    singleton_strata_count: int = 0,
) -> tuple[list[Example], list[Example], SplitReport]:
    """Construct the split result with report."""
    dataset_hash = compute_dataset_hash(all_examples)

    # Build strata report
    strata_counts: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {"total": 0, "dev": 0, "holdout": 0}
    )
    dev_ids = {ex.id for ex in dev}
    for ex in all_examples:
        card = card_set.cards[ex.id]
        key = (card.assigned_route, card.intent_pattern, card.complexity_structure)
        strata_counts[key]["total"] += 1
        if ex.id in dev_ids:
            strata_counts[key]["dev"] += 1
        else:
            strata_counts[key]["holdout"] += 1

    strata_report = [
        StratumReport(key=list(k), total=v["total"], dev=v["dev"], holdout=v["holdout"])
        for k, v in sorted(strata_counts.items())
    ]

    # Build distributions
    distributions = _compute_distributions(dev, holdout, card_set)

    report = SplitReport(
        dataset_hash=dataset_hash,
        split_ratio={"dev": dev_ratio, "holdout": round(1.0 - dev_ratio, 4)},
        total_examples=len(all_examples),
        dev_count=len(dev),
        holdout_count=len(holdout),
        singleton_strata_count=singleton_strata_count,
        strata=strata_report,
        distributions=distributions,
    )
    return dev, holdout, report


def _compute_distributions(
    dev: list[Example],
    holdout: list[Example],
    card_set: RationaleCardSet,
) -> dict[str, dict[str, dict[str, float | int]]]:
    """Compute per-dimension distributions for the split report."""
    result: dict[str, dict[str, dict[str, float | int]]] = {}

    # Normalized proportions for assigned_route, intent_pattern, complexity_structure
    for dim in ("assigned_route", "intent_pattern", "complexity_structure"):
        dev_counts: dict[str, int] = defaultdict(int)
        holdout_counts: dict[str, int] = defaultdict(int)
        for ex in dev:
            dev_counts[getattr(card_set.cards[ex.id], dim)] += 1
        for ex in holdout:
            holdout_counts[getattr(card_set.cards[ex.id], dim)] += 1

        dev_total = len(dev) or 1
        holdout_total = len(holdout) or 1
        result[dim] = {
            "dev": {k: round(v / dev_total, 4) for k, v in sorted(dev_counts.items())},
            "holdout": {k: round(v / holdout_total, 4) for k, v in sorted(holdout_counts.items())},
        }

    # Raw counts for ambiguity_tags (multi-label)
    dev_tags: dict[str, int] = defaultdict(int)
    holdout_tags: dict[str, int] = defaultdict(int)
    for ex in dev:
        for tag in card_set.cards[ex.id].ambiguity_tags:
            dev_tags[tag] += 1
    for ex in holdout:
        for tag in card_set.cards[ex.id].ambiguity_tags:
            holdout_tags[tag] += 1
    result["ambiguity_tags"] = {
        "dev": dict(sorted(dev_tags.items())),
        "holdout": dict(sorted(holdout_tags.items())),
    }

    return result
