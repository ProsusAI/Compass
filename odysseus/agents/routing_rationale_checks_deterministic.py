"""Deterministic validation checks for routing rationale card sets.

Wraps the individual check functions from routing_rationale_checks,
excluding the async LLM-judged check_registry_consistency. This module
is used by the MCP tool — semantic overlap is handled by the
check-semantic-overlap skill instead.
"""

from __future__ import annotations

from odysseus.agents.routing_rationale_checks import (
    RationaleCheckResult,
    check_ambiguity_tag_membership,
    check_cluster_thresholds,
    check_exclusion_coverage,
    check_exclusion_format,
    check_pruning_cleanup,
    check_required_fields,
    check_vocabulary_membership,
    find_orphaned_examples,
)
from odysseus.agents.routing_rationale_models import (
    RationaleCardSet,
    RoutingContext,
)


def validate_deterministic(
    card_set: RationaleCardSet,
    routing_context: RoutingContext,
    dataset_size: int,
) -> list[RationaleCheckResult]:
    """Run all deterministic validation checks on a RationaleCardSet.

    Same ordering as validate_rationale_card_set but without
    check_registry_consistency (the async LLM-judged check).

    Returns a flat list of RationaleCheckResult in the order:
    1. check_cluster_thresholds
    2. check_pruning_cleanup
    3. find_orphaned_examples
    4. Per-card: check_required_fields, check_vocabulary_membership,
       check_exclusion_coverage, check_exclusion_format,
       check_ambiguity_tag_membership
    """
    results: list[RationaleCheckResult] = []

    # --- Dataset-level checks ---
    results.append(check_cluster_thresholds(card_set.registry, dataset_size))
    results.append(check_pruning_cleanup(card_set))
    results.append(find_orphaned_examples(card_set))

    # --- Per-card checks ---
    available_routes = {r.name for r in routing_context.routes}
    for card in card_set.cards.values():
        results.append(check_required_fields(card, card_set.registry))
        results.append(check_vocabulary_membership(card, card_set.registry))
        results.append(check_exclusion_coverage(card, available_routes))
        results.append(check_exclusion_format(card))
        results.append(check_ambiguity_tag_membership(card, card_set.registry))

    return results
