"""Data models for the Review Agent.

See docs/superpowers/specs/2026-03-25-review-agent-design.md for the full spec.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from odysseus.agents.prompt_builder.search import Candidate
from odysseus.eval.models import ScoreReport

# ---------------------------------------------------------------------------
# ReviewBriefing components
# ---------------------------------------------------------------------------


class MetricDeltas(BaseModel):
    """Metric differences between two candidates or a candidate and a reference."""

    quality_delta: float
    cost_delta: float
    per_class_recall_deltas: dict[str, float]


class FrontComparison(BaseModel):
    """How a candidate compares to a specific Pareto front member."""

    front_candidate_version: str
    quality_delta: float
    cost_delta: float


class CandidateAnalysis(BaseModel):
    """Pre-processed analysis of a single candidate in the current round."""

    candidate_version: str
    parent_version: str | None
    mutation_description: str
    score_report: ScoreReport
    delta_vs_parent: MetricDeltas
    delta_vs_front: list[FrontComparison]


class ClassRecallEntry(BaseModel):
    """Per-route recall with historical trend and regression detection."""

    recall: float
    support: int
    trend: list[float]
    regression_flag: bool


class DiversityMetrics(BaseModel):
    """Measures of search diversity across the Pareto front."""

    example_overlap_ratio: float
    prompt_similarity: float
    mutation_type_distribution: dict[str, int]


class DiminishingReturns(BaseModel):
    """Score trajectory analysis for detecting stagnation."""

    score_trajectory: list[float]
    improvement_trend: float
    stagnation_flag: bool


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

    child_version: str
    parent_version: str
    mutation_type: MutationType
    description: str
    directive_ids: list[str] | None = None


class MutationHistory(BaseModel):
    """Aggregated mutation effectiveness data."""

    effective_mutations: list[MutationRecord]
    ineffective_mutations: list[MutationRecord]
    untried_mutation_types: list[str]


class ExampleSummary(BaseModel):
    """Lightweight reference to a holdout example for the exemplar bank."""

    example_id: str
    route: str
    ambiguity_tags: list[str]


class OracleMetrics(BaseModel):
    """How much of the theoretical routing improvement has been captured."""

    oracle_cost_reduction: float
    oracle_quality_reduction: float
    candidate_cost_captured: float | None = None
    candidate_quality_captured: float | None = None


class ReviewBriefing(BaseModel):
    """Complete pre-processed input for the Review Agent LLM."""

    round: int
    candidates: list[CandidateAnalysis]
    pareto_front: list[Candidate]
    per_class_recall: dict[str, ClassRecallEntry]
    diversity_metrics: DiversityMetrics
    diminishing_returns: DiminishingReturns
    mutation_history: MutationHistory
    oracle_metrics: OracleMetrics
    prompt_versions: dict[str, str]
    holdout_examples: list[ExampleSummary]


# ---------------------------------------------------------------------------
# ReviewResult components (LLM output)
# ---------------------------------------------------------------------------


class RankedCandidate(BaseModel):
    """A candidate with its rank and ranking rationale."""

    version: str
    rank: int
    rationale: str


class EditDirective(BaseModel):
    """A localized, block-level edit instruction for the Prompt Builder."""

    directive_id: str
    target_version: str
    block_type: Literal["rule", "example", "output_schema", "assembly_policy"]
    block_identifier: str
    granularity: Literal["macro", "micro"]
    directive: str
    priority: Literal["high", "medium", "low"]


class PromotionDecision(BaseModel):
    """Whether a candidate should be promoted, refined, or pruned."""

    version: str
    decision: Literal["promote", "prune", "refine"]
    reason: str


class LoopSignal(BaseModel):
    """Whether to continue refining or exit the search loop."""

    action: Literal["refine", "exit"]
    reason: str
    suggested_budget: int | None = None
    suggested_mutation_mode: Literal["targeted", "exploratory"] | None = None


class RegressionFlag(BaseModel):
    """A metric regression that may block promotion."""

    version: str
    metric: str
    previous_value: float
    current_value: float
    severity: Literal["warning", "block"]


class DirectiveOutcome(BaseModel):
    """Tracks whether a prior directive was attempted and its effect."""

    prior_directive_id: str
    was_attempted: bool
    outcome: Literal["improved", "no_effect", "regressed"]


class ReviewResult(BaseModel):
    """Complete structured output from the Review Agent LLM."""

    candidate_ranking: list[RankedCandidate]
    edit_directives: list[EditDirective]
    promotion_decisions: list[PromotionDecision]
    loop_signal: LoopSignal
    regression_guards: list[RegressionFlag]
    directive_history_update: list[DirectiveOutcome]
