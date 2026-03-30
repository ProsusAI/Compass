"""Odysseus agents — domain logic for each pipeline stage.

Subdirectories:
  pipeline/          — status detection and artifact guards
  user_input/        — input report constants and status handling
  data_validation/   — format detection, field mapping, quality checks
  routing_analysis/  — rationale models, vocabulary registry, validation, split
  prompt_builder/    — search state, candidate management, holdout filtering
  review/            — briefing models, directive persistence, preprocessing

Root-level modules:
  base.py            — BaseAgent abstract interface
  eval_runner.py     — EvalRunnerAgent (cross-cutting)
"""

from __future__ import annotations

# --- Data Validation ---
from odysseus.agents.data_validation import (
    DataQualityReport,
    DetectionResult,
    LabelDistribution,
    QueryLengthDistribution,
    SchemaFinding,
    TierDistribution,
    TierVolume,
    TransformResult,
    VolumeAssessment,
    check_label_distribution,
    check_query_length_distribution,
    check_schema_conformance,
    check_volume_adequacy,
    detect_and_parse,
    run_all_checks,
    transform_dataset,
)

# --- Root-level modules ---
from odysseus.agents.eval_runner import EvalRunnerAgent

# --- Prompt Builder ---
from odysseus.agents.prompt_builder import (
    Candidate,
    RoundSummary,
    SearchState,
    dominates,
    select_best,
    update_pareto_front,
)

# --- Review ---
from odysseus.agents.review import (
    CandidateAnalysis,
    ClassRecallEntry,
    DirectiveOutcome,
    DiversityMetrics,
    EditDirective,
    ExampleSummary,
    LoopSignal,
    MetricDeltas,
    MutationHistory,
    MutationRecord,
    OracleMetrics,
    PromotionDecision,
    RankedCandidate,
    RegressionFlag,
    ReviewBriefing,
    ReviewResult,
)

# --- Routing Analysis ---
from odysseus.agents.routing_analysis import (
    RationaleCard,
    RationaleCardSet,
    RationaleCheckResult,
    RegistryMergeError,
    RouteDefinition,
    RouteExclusion,
    RouteOrdering,
    RoutingContext,
    RoutingDimension,
    SeedVocabulary,
    SplitMismatchError,
    SplitReport,
    VocabularyEntry,
    VocabularyRegistry,
    check_ambiguity_tag_membership,
    check_cluster_thresholds,
    check_exclusion_coverage,
    check_exclusion_format,
    check_pruning_cleanup,
    check_registry_consistency,
    check_required_fields,
    check_vocabulary_membership,
    compute_dataset_hash,
    create_seed_registry,
    find_orphaned_examples,
    load_registry,
    merge_registry,
    prune_registry,
    resolve_registry,
    save_registry,
    stratified_split,
    validate_deterministic,
    validate_rationale_card_set,
)
from odysseus.agents.user_input.report import (
    CONTEXT_KEY as USER_INPUT_REPORT_CONTEXT_KEY,
)
from odysseus.agents.user_input.report import (
    STATUS_PROCEED,
    STATUS_PROCEED_WITH_DEFAULTS,
)
from odysseus.agents.user_input.report import (
    read_status as read_user_input_report_status,
)

__all__ = [
    # Root
    "EvalRunnerAgent",
    "STATUS_PROCEED",
    "STATUS_PROCEED_WITH_DEFAULTS",
    "USER_INPUT_REPORT_CONTEXT_KEY",
    "read_user_input_report_status",
    # Data Validation
    "DataQualityReport",
    "DetectionResult",
    "LabelDistribution",
    "QueryLengthDistribution",
    "SchemaFinding",
    "TierDistribution",
    "TierVolume",
    "TransformResult",
    "VolumeAssessment",
    "check_label_distribution",
    "check_query_length_distribution",
    "check_schema_conformance",
    "check_volume_adequacy",
    "detect_and_parse",
    "run_all_checks",
    "transform_dataset",
    # Routing Analysis
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
    "run_all_checks",
    "save_registry",
    "stratified_split",
    "validate_deterministic",
    "validate_rationale_card_set",
    # Prompt Builder
    "Candidate",
    "RoundSummary",
    "SearchState",
    "dominates",
    "select_best",
    "update_pareto_front",
    # Review
    "CandidateAnalysis",
    "ClassRecallEntry",
    "DirectiveOutcome",
    "DiversityMetrics",
    "EditDirective",
    "ExampleSummary",
    "LoopSignal",
    "MetricDeltas",
    "MutationHistory",
    "MutationRecord",
    "OracleMetrics",
    "PromotionDecision",
    "RankedCandidate",
    "RegressionFlag",
    "ReviewBriefing",
    "ReviewResult",
]
