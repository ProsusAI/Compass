# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Compass agents — domain logic for each pipeline stage.

Subdirectories:
  pipeline/          — status detection and artifact guards
  user_input/        — input report constants and status handling
  data_validation/   — format detection, field mapping, quality checks, stratified split
  prompt_builder/    — search state, candidate management, holdout filtering
  review/            — briefing models, directive persistence, preprocessing

Root-level modules:
  eval_runner.py     — run_eval() (cross-cutting eval orchestration)
  routing_context.py — domain-agnostic routing context models
"""

from __future__ import annotations

# --- Data Validation ---
from compass.agents.data_validation import (
    DataQualityReport,
    DetectionResult,
    LabelDistribution,
    QueryLengthDistribution,
    SchemaFinding,
    SplitReport,
    TierDistribution,
    TierVolume,
    TransformResult,
    VolumeAssessment,
    check_label_distribution,
    check_query_length_distribution,
    check_schema_conformance,
    check_volume_adequacy,
    compute_dataset_hash,
    detect_and_parse,
    run_all_checks,
    stratified_split,
    transform_dataset,
)

# --- Root-level modules ---
from compass.agents.eval_runner import run_eval

# --- Prompt Builder ---
from compass.agents.prompt_builder import (
    Candidate,
    RoundSummary,
    SearchState,
    dominates,
    update_pareto_front,
)

# --- Review ---
from compass.agents.review import (
    BatchOutcome,
    CandidateAnalysis,
    ChildVariant,
    ClassRecallEntry,
    DirectiveOutcome,
    DiversityMetrics,
    EditDirective,
    ExampleContent,
    ExampleSummary,
    LoopSignal,
    MetricDeltas,
    NearMissCandidate,
    OracleMetrics,
    PromotionDecision,
    RankedCandidate,
    RegressionFlag,
    ReviewBriefing,
    ReviewResult,
    UserTarget,
    UserTargetProgress,
)

# --- Routing Context ---
from compass.agents.routing_context import (
    RouteDefinition,
    RouteOrdering,
    RoutingContext,
    RoutingDimension,
)
from compass.agents.user_input.report import (
    CONTEXT_KEY as USER_INPUT_REPORT_CONTEXT_KEY,
)
from compass.agents.user_input.report import (
    STATUS_PROCEED,
    STATUS_PROCEED_WITH_DEFAULTS,
)
from compass.agents.user_input.report import (
    read_status as read_user_input_report_status,
)

__all__ = [
    # Root
    "run_eval",
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
    "SplitReport",
    "TierDistribution",
    "TierVolume",
    "TransformResult",
    "VolumeAssessment",
    "check_label_distribution",
    "check_query_length_distribution",
    "check_schema_conformance",
    "check_volume_adequacy",
    "compute_dataset_hash",
    "detect_and_parse",
    "run_all_checks",
    "stratified_split",
    "transform_dataset",
    # Routing Context
    "RouteDefinition",
    "RouteOrdering",
    "RoutingContext",
    "RoutingDimension",
    # Prompt Builder
    "Candidate",
    "RoundSummary",
    "SearchState",
    "dominates",
    "update_pareto_front",
    # Review
    "BatchOutcome",
    "CandidateAnalysis",
    "ChildVariant",
    "ClassRecallEntry",
    "DirectiveOutcome",
    "DiversityMetrics",
    "EditDirective",
    "ExampleContent",
    "ExampleSummary",
    "LoopSignal",
    "MetricDeltas",
    "NearMissCandidate",
    "OracleMetrics",
    "PromotionDecision",
    "RankedCandidate",
    "RegressionFlag",
    "ReviewBriefing",
    "ReviewResult",
    "UserTarget",
    "UserTargetProgress",
]
