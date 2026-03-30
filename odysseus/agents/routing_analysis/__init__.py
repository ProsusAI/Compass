"""Routing analysis — rationale models, vocabulary registry, validation, stratified split."""

from __future__ import annotations

from odysseus.agents.routing_analysis.checks import (
    RationaleCheckResult,
    check_ambiguity_tag_membership,
    check_card_completeness,
    check_cluster_thresholds,
    check_exclusion_coverage,
    check_exclusion_format,
    check_pruning_cleanup,
    check_registry_consistency,
    check_required_fields,
    check_vocabulary_membership,
    find_orphaned_examples,
    validate_rationale_card_set,
)
from odysseus.agents.routing_analysis.checks_deterministic import (
    validate_deterministic,
)
from odysseus.agents.routing_analysis.models import (
    RationaleCard,
    RationaleCardSet,
    RouteDefinition,
    RouteExclusion,
    RouteOrdering,
    RoutingContext,
    RoutingDimension,
    SeedVocabulary,
    VocabularyEntry,
    VocabularyRegistry,
)
from odysseus.agents.routing_analysis.registry import (
    RegistryMergeError,
    compute_dataset_hash,
    create_seed_registry,
    load_registry,
    merge_registry,
    prune_registry,
    resolve_registry,
    save_registry,
)
from odysseus.agents.routing_analysis.split import (
    SplitMismatchError,
    SplitReport,
    stratified_split,
)

__all__ = [
    "RationaleCard",
    "RationaleCardSet",
    "RationaleCheckResult",
    "RegistryMergeError",
    "RouteDefinition",
    "RouteExclusion",
    "RouteOrdering",
    "RoutingContext",
    "RoutingDimension",
    "SeedVocabulary",
    "SplitMismatchError",
    "SplitReport",
    "VocabularyEntry",
    "VocabularyRegistry",
    "check_ambiguity_tag_membership",
    "check_card_completeness",
    "check_cluster_thresholds",
    "check_exclusion_coverage",
    "check_exclusion_format",
    "check_pruning_cleanup",
    "check_registry_consistency",
    "check_required_fields",
    "check_vocabulary_membership",
    "compute_dataset_hash",
    "create_seed_registry",
    "find_orphaned_examples",
    "load_registry",
    "merge_registry",
    "prune_registry",
    "resolve_registry",
    "save_registry",
    "stratified_split",
    "validate_deterministic",
    "validate_rationale_card_set",
]
