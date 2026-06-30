# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Data models for the Review Agent.

See docs/superpowers/specs/2026-03-25-review-agent-design.md for the full spec.
"""

from __future__ import annotations

from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from compass.agents.prompt_builder.search import Candidate
from compass.agents.routing_context import RoutingContext
from compass.eval.models import ScoreReport

INITIAL_PARENT_VERSION: Final[str] = "base"
"""Canonical parent_version for cold-start seed ChildVariants and round-1 candidates."""

# ---------------------------------------------------------------------------
# ReviewBriefing components
# ---------------------------------------------------------------------------


class MetricDeltas(BaseModel):
    """Metric differences between two candidates or a candidate and a reference."""

    model_config = ConfigDict(extra="forbid")

    quality_delta: float | None
    cost_delta: float | None
    per_class_recall_deltas: dict[str, float]


class UserTarget(BaseModel):
    """A user-specified target metric with threshold."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    operator: Literal["<=", ">=", "<", ">", "=="]
    threshold: float


class UserTargetProgress(BaseModel):
    """Progress toward a single user target."""

    model_config = ConfigDict(extra="forbid")

    target: UserTarget
    current_value: float | None
    met: bool
    progress_ratio: float | None
    oracle_ceiling: float | None
    full_dataset_oracle_ceiling: float | None = None
    target_above_oracle: bool
    translated_threshold: float | None = None
    capture_ratio: float | None = None
    # Merged from TargetSlack — slack/budget relative to target threshold
    surplus: float | None = None
    regression_budget: float | None = None
    priority_weight: float | None = None
    source_version: str | None = None


class CandidateAnalysis(BaseModel):
    """Pre-processed analysis of a single candidate in the current round."""

    model_config = ConfigDict(extra="forbid")

    candidate_version: str
    parent_version: str | None
    mutation_description: str
    score_report: ScoreReport
    delta_vs_parent: MetricDeltas


class ClassRecallEntry(BaseModel):
    """Per-route recall with historical trend and regression detection."""

    model_config = ConfigDict(extra="forbid")

    recall: float = Field(ge=0.0, le=1.0)
    support: int
    trend: list[float]
    regression_flag: bool


class DiversityMetrics(BaseModel):
    """Measures of search diversity across the elite set."""

    model_config = ConfigDict(extra="forbid")

    example_overlap_ratio: float = Field(ge=0.0, le=1.0)


class DiminishingReturns(BaseModel):
    """Score trajectory analysis for detecting stagnation."""

    model_config = ConfigDict(extra="forbid")

    score_trajectory: list[float]
    improvement_trend: float
    stagnation_flag: bool
    improvement_stddev: float = 0.0
    effective_threshold: float = 0.005


class ExampleContent(BaseModel):
    """Concrete content for a few-shot example."""

    model_config = ConfigDict(extra="forbid")

    example_id: str | None = Field(
        default=None,
        description="Holdout dataset row ID for tracking — never included in prompt text",
    )
    input: str = Field(description="The example input/query text")
    route: str = Field(description="The assigned route for this example")
    reasoning: str = Field(
        description=(
            "Concrete explanation of why this route is the correct classification"
            " for this specific input, including what distinguishing signals are"
            " present and why the most plausible alternative routes do not apply"
        ),
    )
    exclusions: list[dict[str, str]] = Field(description="List of {route, reason} for excluded routes")


class ContrastPairContent(BaseModel):
    """Two similar inputs that route differently, teaching boundary discrimination."""

    model_config = ConfigDict(extra="forbid")

    example_a: ExampleContent
    example_b: ExampleContent
    distinguishing_signal: str
    contrast_reasoning: str
    target_true_route: str
    target_predicted_route: str

    @model_validator(mode="after")
    def validate_contrast_pair(self) -> ContrastPairContent:
        if self.example_a.route == self.example_b.route:
            raise ValueError("Contrast pair examples must have different routes")
        pair_routes = {self.example_a.route, self.example_b.route}
        target_routes = {self.target_true_route, self.target_predicted_route}
        if pair_routes != target_routes:
            raise ValueError(f"Example routes {pair_routes} must match target routes {target_routes}")
        return self


class ExampleSummary(BaseModel):
    """Lightweight reference to a holdout example for the exemplar bank."""

    model_config = ConfigDict(extra="forbid")

    example_id: str
    route: str
    ambiguity_tags: list[str] = Field(default_factory=list)
    input_text: str | None = None


class OracleMetrics(BaseModel):
    """How much of the theoretical routing improvement has been captured."""

    model_config = ConfigDict(extra="forbid")

    oracle_cost_change: float
    oracle_quality_change: float
    candidate_cost_captured: float | None = None
    candidate_cost_captured_with_overhead: float | None = None
    candidate_quality_captured: float | None = None


class ConfusionImpact(BaseModel):
    """Impact-weighted confusion matrix cell with persistence analysis."""

    model_config = ConfigDict(extra="forbid")

    true_route: str
    predicted_route: str
    count: int
    support: int
    misroute_rate: float
    cost_impact: float
    quality_impact: float
    avg_cost_impact: float
    avg_quality_impact: float
    persistence_rate: float
    persistent_count: int
    volatile_count: int
    attempt_count: int = 0
    failed_attempt_count: int = 0
    last_attempted_round: int | None = None
    best_outcome: Literal["improved", "no_effect", "regressed"] | None = None
    effective_impact: float = 0.0
    sample_example_ids: list[str] = Field(default_factory=list)


class NearMissCandidate(BaseModel):
    """A dominated candidate that was close to the Pareto front."""

    model_config = ConfigDict(extra="forbid")

    version: str
    domination_gap_quality: float
    domination_gap_cost: float


class ReviewBriefing(BaseModel):
    """Complete pre-processed input for the Review Agent LLM.

    ``extra="ignore"`` allows older serialised briefings that predate the
    cross-branch generalisation (or future fields added on strategy branches)
    to load without raising a validation error.

    Fields are ordered stable-first, varying-last for cache-prefix stability.
    """

    model_config = ConfigDict(extra="ignore")

    # --- stable round-to-round ---
    round: int
    routing_context: RoutingContext | None = None
    # Canonical parent_version for cold-start / warm-up seeds. Read this instead of hard-coding "base".
    initial_parent_version: str = INITIAL_PARENT_VERSION
    oracle_metrics: OracleMetrics | None = None
    diversity_metrics: DiversityMetrics
    diminishing_returns: DiminishingReturns
    per_class_recall: dict[str, ClassRecallEntry]
    target_progress: list[UserTargetProgress] = Field(default_factory=list)
    single_candidate_meets_all: bool = False
    backtracking: bool = False
    # Beam stagnation signal: {"hypervolume_delta": float, "backtrack_threshold": int}
    stagnation_signal: dict[str, Any] | None = None
    # --- varying per round ---
    elite_set: list[Candidate]
    confusion_analysis: list[ConfusionImpact] = Field(default_factory=list)
    candidates: list[CandidateAnalysis]
    near_miss_candidates: list[NearMissCandidate] = []
    directive_history: list[DirectiveOutcome] = Field(default_factory=list)
    batch_outcomes: list[BatchOutcome] = Field(default_factory=list)
    child_variants: list[ChildVariant] = Field(default_factory=list)
    parent_a_version: str | None = None
    parent_b_version: str | None = None
    executive_summary: str = ""
    # --- Beam trailer (populated by _populate_beam_review_fields) ---
    beam_width: int | None = None
    beam_rank: dict[str, int] | None = None  # prompt_version -> rank within elite_set
    crowding_distance: dict[str, float] | None = None  # prompt_version -> crowding distance
    hypervolume: float | None = None
    reference_point: tuple[float, float] | None = None


# ---------------------------------------------------------------------------
# ReviewResult components (LLM output)
# ---------------------------------------------------------------------------


class RankedCandidate(BaseModel):
    """A candidate with its rank and ranking rationale."""

    model_config = ConfigDict(extra="forbid")

    version: str
    rank: int
    rationale: str


class EditDirective(BaseModel):
    """A localized, block-level edit instruction for the Prompt Builder."""

    model_config = ConfigDict(extra="forbid")

    directive_id: str
    target_version: str
    block_type: Literal["rule", "example", "output_schema", "vocabulary", "contrast_pair"]
    block_identifier: str
    granularity: Literal["macro", "micro"]
    directive: str
    priority: Literal["high", "medium", "low"]
    example_content: ExampleContent | None = None
    contrast_pair_content: ContrastPairContent | None = None


class ChildVariant(BaseModel):
    """A group of directives that should be applied together as one child prompt."""

    model_config = ConfigDict(extra="forbid")

    variant_id: str | None = None  # assigned by algorithm; maps to Candidate.source_directive_batch_id
    parent_preference: (
        Literal[
            "best_quality",
            "best_cost",
            "weakest_on_class",
            "nearest_target",
        ]
        | None
    ) = None
    parent_preference_class: str | None = None
    parent_preference_metric: str | None = None
    # resolved parent — cold-start: ReviewBriefing.initial_parent_version ("base"); iterative: per overlay
    parent_version: str | None = None
    secondary_parent_preference: (
        Literal[
            "best_quality",
            "best_cost",
            "weakest_on_class",
            "nearest_target",
        ]
        | None
    ) = None
    secondary_parent_preference_class: str | None = None
    secondary_parent_preference_metric: str | None = None
    secondary_parent_version: str | None = None  # resolved by algorithm
    hypothesis: str
    directives: list[EditDirective]
    target_confusion_cell: str | None = None  # Format: "true_route/predicted_route"
    trajectory_id: int | None = None  # leaf branch: source trajectory; set by record_directive_outcomes


class PromotionDecision(BaseModel):
    """Whether a candidate should be promoted, refined, or pruned."""

    model_config = ConfigDict(extra="forbid")

    version: str
    decision: Literal["promote", "prune", "refine"]
    reason: str


class LoopSignal(BaseModel):
    """Whether to continue refining or exit the search loop."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["refine", "exit"]
    reason: str
    suggested_budget: int | None = Field(
        default=None,
        description="Additional rounds to grant beyond current convergence limit (delta, not absolute)",
    )
    suggested_mutation_mode: Literal["targeted", "exploratory"] | None = None


class RegressionFlag(BaseModel):
    """A metric regression that may block promotion."""

    model_config = ConfigDict(extra="forbid")

    version: str
    metric: str
    previous_value: float
    current_value: float
    severity: Literal["warning", "block"]


class DirectiveOutcome(BaseModel):
    """Tracks whether a prior directive was attempted and its effect."""

    model_config = ConfigDict(extra="forbid")

    prior_directive_id: str
    was_attempted: bool
    outcome: Literal["improved", "no_effect", "regressed"]


class BatchOutcome(BaseModel):
    """Links a child variant to the candidate it produced and its eval result."""

    model_config = ConfigDict(extra="forbid")

    variant_id: str
    parent_version: str
    mutation_strategy: Literal["targeted", "exploratory", "structural"]
    directive_ids: list[str] = Field(default_factory=list)
    candidate_version: str | None
    eval_status: Literal["scored", "failed"] | None
    quality_delta_vs_parent: float | None
    is_new_best: bool
    secondary_parent_version: str | None = None
    metric_deltas_vs_parent: dict[str, float] | None = None
    metric_deltas_vs_secondary_parent: dict[str, float] | None = None


class ReviewResult(BaseModel):
    """Complete structured output from the Review Agent LLM."""

    model_config = ConfigDict(extra="forbid")

    candidate_ranking: list[RankedCandidate]
    child_variants: list[ChildVariant]
    promotion_decisions: list[PromotionDecision]
    loop_signal: LoopSignal
    regression_guards: list[RegressionFlag]
    directive_history_update: list[DirectiveOutcome]
