"""Data models for the Review Agent.

See docs/superpowers/specs/2026-03-25-review-agent-design.md for the full spec.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from odysseus.agents.prompt_builder.search import Candidate
from odysseus.agents.routing_context import RoutingContext
from odysseus.eval.models import ScoreReport

# ---------------------------------------------------------------------------
# ReviewBriefing components
# ---------------------------------------------------------------------------


class MetricDeltas(BaseModel):
    """Metric differences between two candidates or a candidate and a reference."""

    model_config = ConfigDict(extra="forbid")

    quality_delta: float | None
    cost_delta: float | None
    per_class_recall_deltas: dict[str, float]


class FrontComparison(BaseModel):
    """How a candidate compares to a specific Pareto front member."""

    model_config = ConfigDict(extra="forbid")

    front_candidate_version: str
    quality_delta: float | None
    cost_delta: float | None


class CandidateAnalysis(BaseModel):
    """Pre-processed analysis of a single candidate in the current round."""

    model_config = ConfigDict(extra="forbid")

    candidate_version: str
    parent_version: str | None
    mutation_description: str
    score_report: ScoreReport
    delta_vs_parent: MetricDeltas
    delta_vs_front: list[FrontComparison]


class ClassRecallEntry(BaseModel):
    """Per-route recall with historical trend and regression detection."""

    model_config = ConfigDict(extra="forbid")

    recall: float = Field(ge=0.0, le=1.0)
    support: int
    trend: list[float]
    regression_flag: bool


class DiversityMetrics(BaseModel):
    """Measures of search diversity across the Pareto front."""

    model_config = ConfigDict(extra="forbid")

    example_overlap_ratio: float = Field(ge=0.0, le=1.0)
    prompt_similarity: float = Field(ge=0.0, le=1.0)
    mutation_type_distribution: dict[str, int]


class DiminishingReturns(BaseModel):
    """Score trajectory analysis for detecting stagnation."""

    model_config = ConfigDict(extra="forbid")

    score_trajectory: list[float]
    improvement_trend: float
    stagnation_flag: bool
    improvement_stddev: float = 0.0
    effective_threshold: float = 0.005


MutationType = Literal[
    "example_swap",
    "rule_edit",
    "schema_change",
    "rule_add",
    "rule_remove",
    "assembly_policy",
]


class MutationRecord(BaseModel):
    """What the Prompt Builder changed and why."""

    model_config = ConfigDict(extra="forbid")

    child_version: str
    parent_version: str
    mutation_type: MutationType
    description: str
    directive_ids: list[str] | None = None


class MutationHistory(BaseModel):
    """Aggregated mutation effectiveness data."""

    model_config = ConfigDict(extra="forbid")

    effective_mutations: list[MutationRecord]
    ineffective_mutations: list[MutationRecord]
    untried_mutation_types: list[str]
    unscored_mutations: list[MutationRecord] = Field(default_factory=list)


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


class NearMissCandidate(BaseModel):
    """A dominated candidate that was close to the Pareto front."""

    model_config = ConfigDict(extra="forbid")

    version: str
    domination_gap_quality: float
    domination_gap_cost: float


class ReviewBriefing(BaseModel):
    """Complete pre-processed input for the Review Agent LLM."""

    model_config = ConfigDict(extra="forbid")

    round: int
    candidates: list[CandidateAnalysis]
    pareto_front: list[Candidate]
    per_class_recall: dict[str, ClassRecallEntry]
    diversity_metrics: DiversityMetrics
    diminishing_returns: DiminishingReturns
    mutation_history: MutationHistory
    oracle_metrics: OracleMetrics | None = None
    prompt_versions: dict[str, str]
    holdout_examples: list[ExampleSummary]
    routing_context: RoutingContext | None = None
    near_miss_candidates: list[NearMissCandidate] = []
    directive_history: list[DirectiveOutcome] = Field(default_factory=list)
    executive_summary: str = ""


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
    block_type: Literal["rule", "example", "output_schema", "assembly_policy"]
    block_identifier: str
    granularity: Literal["macro", "micro"]
    directive: str
    priority: Literal["high", "medium", "low"]
    example_content: ExampleContent | None = None


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


class ReviewResult(BaseModel):
    """Complete structured output from the Review Agent LLM."""

    model_config = ConfigDict(extra="forbid")

    candidate_ranking: list[RankedCandidate]
    edit_directives: list[EditDirective]
    promotion_decisions: list[PromotionDecision]
    loop_signal: LoopSignal
    regression_guards: list[RegressionFlag]
    directive_history_update: list[DirectiveOutcome]
