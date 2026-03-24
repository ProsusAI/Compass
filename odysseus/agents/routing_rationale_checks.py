"""Validation checks for routing rationale card sets (THP-82).

Provides per-card and dataset-level validation functions that operate on
RationaleCard / RationaleCardSet models and return typed RationaleCheckResult
instances. Used by the routing rationale agent pipeline.

See: docs/superpowers/specs/2026-03-23-thp-82-routing-rationale-schema.md
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from itertools import combinations
from typing import Literal

from pydantic import BaseModel

from odysseus.agents.routing_rationale_models import (
    RationaleCard,
    RationaleCardSet,
    VocabularyRegistry,
)

# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class RationaleCheckResult(BaseModel):
    """Result of a single routing rationale validation check."""

    passed: bool
    check_name: str
    severity: Literal["critical", "warning", "info"]
    details: str
    affected_ids: list[str]


# ---------------------------------------------------------------------------
# Per-card checks
# ---------------------------------------------------------------------------


def check_required_fields(
    card: RationaleCard,
    registry: VocabularyRegistry,  # noqa: ARG001 — reserved for future use
) -> RationaleCheckResult:
    """Check that all 4 required card fields are present and non-empty.

    ambiguity_tags is allowed to be an empty list — it is not a missing field.
    """
    missing: list[str] = []

    if not card.assigned_route or not card.assigned_route.strip():
        missing.append("assigned_route")
    if not card.intent_pattern or not card.intent_pattern.strip():
        missing.append("intent_pattern")
    if not card.complexity_structure or not card.complexity_structure.strip():
        missing.append("complexity_structure")
    # route_exclusions and ambiguity_tags may be [] — that is not a failure

    passed = len(missing) == 0
    return RationaleCheckResult(
        passed=passed,
        check_name="check_required_fields",
        severity="critical",
        details=(
            "All required fields present and non-empty." if passed else f"Missing or empty fields: {', '.join(missing)}"
        ),
        affected_ids=[] if passed else [card.example_id],
    )


def check_vocabulary_membership(
    card: RationaleCard,
    registry: VocabularyRegistry,
) -> RationaleCheckResult:
    """Check that intent_pattern and complexity_structure exist in the registry."""
    intent_names = {e.name for e in registry.intent_pattern}
    complexity_names = {e.name for e in registry.complexity_structure}

    issues: list[str] = []
    if card.intent_pattern not in intent_names:
        issues.append(f"intent_pattern {card.intent_pattern!r} not in registry")
    if card.complexity_structure not in complexity_names:
        issues.append(f"complexity_structure {card.complexity_structure!r} not in registry")

    passed = len(issues) == 0
    return RationaleCheckResult(
        passed=passed,
        check_name="check_vocabulary_membership",
        severity="critical",
        details=(
            "intent_pattern and complexity_structure are registered vocabulary terms." if passed else "; ".join(issues)
        ),
        affected_ids=[] if passed else [card.example_id],
    )


def check_exclusion_coverage(
    card: RationaleCard,
    available_routes: set[str],
) -> RationaleCheckResult:
    """Check that every route other than assigned_route has a route exclusion."""
    routes_needing_exclusion = available_routes - {card.assigned_route}
    covered_routes = {d.route for d in card.route_exclusions}
    missing_routes = routes_needing_exclusion - covered_routes

    passed = len(missing_routes) == 0
    return RationaleCheckResult(
        passed=passed,
        check_name="check_exclusion_coverage",
        severity="critical",
        details=(
            "All non-assigned routes have a route exclusion."
            if passed
            else f"Routes missing exclusion: {', '.join(sorted(missing_routes))}"
        ),
        affected_ids=[] if passed else [card.example_id],
    )


def check_exclusion_format(card: RationaleCard) -> RationaleCheckResult:
    """Check that each route exclusion has a non-empty route and reason."""
    bad_indices: list[int] = []
    for i, d in enumerate(card.route_exclusions):
        if not d.route or not d.route.strip() or not d.reason or not d.reason.strip():
            bad_indices.append(i)

    passed = len(bad_indices) == 0
    return RationaleCheckResult(
        passed=passed,
        check_name="check_exclusion_format",
        severity="critical",
        details=(
            "All route exclusions have non-empty route and reason."
            if passed
            else f"Malformed exclusions at indices: {bad_indices}"
        ),
        affected_ids=[] if passed else [card.example_id],
    )


def check_ambiguity_tag_membership(
    card: RationaleCard,
    registry: VocabularyRegistry,
) -> RationaleCheckResult:
    """Check that all ambiguity tags on the card exist in the registry."""
    known_tags = {e.name for e in registry.ambiguity_tags}
    unknown = [t for t in card.ambiguity_tags if t not in known_tags]

    passed = len(unknown) == 0
    return RationaleCheckResult(
        passed=passed,
        check_name="check_ambiguity_tag_membership",
        severity="warning",
        details=(
            "All ambiguity tags are registered vocabulary terms."
            if passed
            else f"Unknown ambiguity tags: {', '.join(unknown)}"
        ),
        affected_ids=[] if passed else [card.example_id],
    )


# ---------------------------------------------------------------------------
# Dataset-level checks
# ---------------------------------------------------------------------------


def check_cluster_thresholds(
    registry: VocabularyRegistry,
    dataset_size: int,
) -> RationaleCheckResult:
    """Check that every registry entry meets the minimum example_ids threshold.

    Threshold: max(3, ceil(0.05 * dataset_size))
    """
    threshold = max(3, math.ceil(0.05 * dataset_size))
    below: list[str] = []

    all_entries = list(registry.intent_pattern) + list(registry.complexity_structure) + list(registry.ambiguity_tags)

    for entry in all_entries:
        if len(entry.example_ids) < threshold:
            below.append(entry.name)

    passed = len(below) == 0
    return RationaleCheckResult(
        passed=passed,
        check_name="check_cluster_thresholds",
        severity="warning",
        details=(
            f"All entries meet the cluster threshold of {threshold}."
            if passed
            else (f"Entries below threshold ({threshold}): {', '.join(below)}")
        ),
        affected_ids=below,
    )


def check_pruning_cleanup(card_set: RationaleCardSet) -> RationaleCheckResult:
    """Check that no card references vocabulary entries absent from the registry."""
    registry = card_set.registry
    intent_names = {e.name for e in registry.intent_pattern}
    complexity_names = {e.name for e in registry.complexity_structure}
    tag_names = {e.name for e in registry.ambiguity_tags}

    stale_ids: list[str] = []

    for example_id, card in card_set.cards.items():
        is_stale = False
        if card.intent_pattern not in intent_names or card.complexity_structure not in complexity_names:
            is_stale = True
        else:
            for tag in card.ambiguity_tags:
                if tag not in tag_names:
                    is_stale = True
                    break
        if is_stale:
            stale_ids.append(example_id)

    passed = len(stale_ids) == 0
    return RationaleCheckResult(
        passed=passed,
        check_name="check_pruning_cleanup",
        severity="critical",
        details=(
            "No cards reference vocabulary entries absent from the registry."
            if passed
            else f"Cards with stale vocabulary references: {', '.join(sorted(stale_ids))}"
        ),
        affected_ids=sorted(stale_ids),
    )


def find_orphaned_examples(card_set: RationaleCardSet) -> RationaleCheckResult:
    """Return IDs of examples whose example_id is not listed in any registry entry."""
    registry = card_set.registry
    all_referenced: set[str] = set()
    for entry in list(registry.intent_pattern) + list(registry.complexity_structure) + list(registry.ambiguity_tags):
        all_referenced.update(entry.example_ids)

    orphaned = [example_id for example_id in card_set.cards if example_id not in all_referenced]

    passed = len(orphaned) == 0
    return RationaleCheckResult(
        passed=passed,
        check_name="find_orphaned_examples",
        severity="warning",
        details=(
            "No orphaned examples found."
            if passed
            else f"Orphaned examples (not referenced by any registry entry): {', '.join(sorted(orphaned))}"
        ),
        affected_ids=sorted(orphaned),
    )


async def check_registry_consistency(
    registry: VocabularyRegistry,
    judge_fn: Callable[[str, str], Awaitable[bool]],
) -> RationaleCheckResult:
    """Async LLM-judged semantic overlap check across all vocabulary pairs.

    Compares all pairs within each vocabulary dimension (intent_pattern,
    complexity_structure, ambiguity_tags). Calls judge_fn(def_a, def_b)
    for each pair; if overlap is detected the pair is flagged.

    judge_fn: receives two definition strings, returns True if semantic
    overlap is detected.
    """
    overlapping: list[str] = []

    all_vocabs = [
        registry.intent_pattern,
        registry.complexity_structure,
        registry.ambiguity_tags,
    ]

    for vocab in all_vocabs:
        for entry_a, entry_b in combinations(vocab, 2):
            overlap = await judge_fn(entry_a.definition, entry_b.definition)
            if overlap:
                # Record the names of both overlapping entries
                for name in (entry_a.name, entry_b.name):
                    if name not in overlapping:
                        overlapping.append(name)

    passed = len(overlapping) == 0
    return RationaleCheckResult(
        passed=passed,
        check_name="check_registry_consistency",
        severity="warning",
        details=(
            "No semantic overlap detected between registry entries."
            if passed
            else f"Entries with potential semantic overlap: {', '.join(overlapping)}"
        ),
        affected_ids=overlapping,
    )


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------


async def validate_rationale_card_set(
    card_set: RationaleCardSet,
    available_routes: set[str],
    dataset_size: int,
    judge_fn: Callable[[str, str], Awaitable[bool]],
) -> list[RationaleCheckResult]:
    """Run all validation checks on a RationaleCardSet.

    Dataset-level checks run FIRST, then per-card checks. This ordering
    ensures ambiguity tag membership validates against the post-pruning
    registry.

    Returns a flat list of RationaleCheckResult in the order:
    1. check_cluster_thresholds
    2. check_pruning_cleanup
    3. find_orphaned_examples
    4. check_registry_consistency
    5. Per-card: check_required_fields, check_vocabulary_membership,
       check_exclusion_coverage, check_exclusion_format,
       check_ambiguity_tag_membership (one result per card per check)
    """
    results: list[RationaleCheckResult] = []

    # --- Dataset-level checks ---
    results.append(check_cluster_thresholds(card_set.registry, dataset_size))
    results.append(check_pruning_cleanup(card_set))
    results.append(find_orphaned_examples(card_set))
    results.append(await check_registry_consistency(card_set.registry, judge_fn))

    # --- Per-card checks ---
    for card in card_set.cards.values():
        results.append(check_required_fields(card, card_set.registry))
        results.append(check_vocabulary_membership(card, card_set.registry))
        results.append(check_exclusion_coverage(card, available_routes))
        results.append(check_exclusion_format(card))
        results.append(check_ambiguity_tag_membership(card, card_set.registry))

    return results
