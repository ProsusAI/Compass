# odysseus/agents/prompt_builder_search.py
"""Search state models and Pareto dominance logic for the Prompt Builder Agent.

Tracks the tournament-selection optimization loop with Pareto tracking across
quality and cost dimensions.

See: docs/superpowers/specs/2026-03-24-thp-77-prompt-builder-agent-design.md
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Candidate(BaseModel):
    """A single prompt candidate with quality and cost metrics.

    Optional fields cover strategy-specific metadata used by feature branches
    (parallel-beam, SMS-EMOA, EMOSA).  All default to ``None`` / empty so that
    main-branch (hill-climb) code never has to set them.

    Serialisation note: old state files may contain a ``dominated`` field
    (removed in the cross-branch generalisation).  ``extra="ignore"`` ensures
    they load without error — the field is simply discarded.

    Alias note: ``iteration_introduced`` is accepted as an input key and mapped
    to ``round_introduced`` (the canonical name).  This makes SMS-EMOA state
    files round-trippable without a migration step.
    """

    model_config = ConfigDict(extra="ignore")

    prompt_version: str
    parent_version: str | None
    quality_score: float
    cost: float
    round_introduced: int
    example_ids: list[str] = Field(default_factory=list)

    # Strategy-specific optional fields
    secondary_parent_version: str | None = None
    eval_status: Literal["pending", "running", "complete", "failed"] | None = None
    mutation_strategy: str | None = None
    route_metrics: dict[str, Any] | None = None
    trajectory_id: int | None = None

    @field_validator("prompt_version")
    @classmethod
    def prompt_version_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("prompt_version must be non-empty")
        return v

    @model_validator(mode="before")
    @classmethod
    def _alias_iteration_introduced(cls, data: Any) -> Any:
        """Accept ``iteration_introduced`` as an alias for ``round_introduced``.

        Enables SMS-EMOA state files (which use ``iteration_introduced``) to
        round-trip without a migration step.  If both keys are present,
        ``round_introduced`` wins.
        """
        if isinstance(data, dict) and "iteration_introduced" in data and "round_introduced" not in data:
            data = dict(data)
            data["round_introduced"] = data.pop("iteration_introduced")
        return data


class RoundSummary(BaseModel):
    """Summary of a single search round."""

    round: int = Field(ge=1)
    candidates_evaluated: list[str]
    new_pareto_points: int
    front_size: int
    mutation_mode: Literal["targeted", "exploratory"]
    stagnation_count: int
    converged: bool = False
    front_improvement: float = 0.0
    front_quality_spread: float = 0.0
    round_routing_cost: float = 0.0
    convergence_reason: str | None = None


class SearchState(BaseModel):
    """Full mutable state for the Prompt Builder search loop."""

    search_state_id: str
    backend: str
    primary_metric_name: str | None = None
    round: int = 0
    pareto_front: list[Candidate] = Field(default_factory=list)
    round_history: list[RoundSummary] = Field(default_factory=list)
    stagnation_count: int = 0
    stagnation_limit: int = 3
    convergence_limit: int = 5
    max_rounds: int = 50
    mutation_mode: Literal["targeted", "exploratory"] = "targeted"
    converged: bool = False
    loop_phase: Literal["build", "review"] = "review"
    epsilon: float = 0.001
    total_routing_cost: float = 0.0

    @field_validator("search_state_id")
    @classmethod
    def search_state_id_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("search_state_id must be non-empty")
        return v

    @model_validator(mode="after")
    def convergence_limit_gt_stagnation_limit(self) -> SearchState:
        if self.convergence_limit <= self.stagnation_limit:
            raise ValueError(
                f"convergence_limit ({self.convergence_limit}) must be greater than "
                f"stagnation_limit ({self.stagnation_limit})"
            )
        return self


def compute_front_improvement(
    old_front: list[Candidate],
    new_front: list[Candidate],
) -> float:
    """Measure improvement as best quality gain across the front.

    Uses quality dimension only to avoid scale mixing with cost.
    Returns 0.0 if no improvement or fronts are empty.
    """
    if not new_front:
        return 0.0
    new_best_quality = max(c.quality_score for c in new_front)
    if not old_front:
        return new_best_quality
    old_best_quality = max(c.quality_score for c in old_front)
    return max(0.0, new_best_quality - old_best_quality)


# ---------------------------------------------------------------------------
# Pareto dominance logic
# ---------------------------------------------------------------------------


def dominates(a: Candidate, b: Candidate) -> bool:
    """Return True iff candidate a Pareto-dominates candidate b.

    a dominates b iff:
    - a.quality_score >= b.quality_score AND a.cost <= b.cost
    - with at least one strict inequality
    """
    better_quality = a.quality_score >= b.quality_score
    better_cost = a.cost <= b.cost
    strictly_better_quality = a.quality_score > b.quality_score
    strictly_better_cost = a.cost < b.cost
    return better_quality and better_cost and (strictly_better_quality or strictly_better_cost)


def update_pareto_front(
    front: list[Candidate],
    new_candidates: list[Candidate],
) -> tuple[list[Candidate], int]:
    """Add new candidates to the Pareto front, removing dominated ones.

    Deduplication: candidates with identical (quality_score, cost) pairs are
    rejected if an equivalent point already exists on the front.

    Args:
        front: Current Pareto front (may be mutated — pass a copy if needed).
        new_candidates: Candidates to consider adding.

    Returns:
        A tuple of (updated_front, new_pareto_points_count).
    """
    new_pareto_points = 0

    for candidate in new_candidates:
        # Reject if dominated by any existing front member
        if any(dominates(existing, candidate) for existing in front):
            continue

        # Reject duplicates: identical (quality_score, cost)
        is_duplicate = any(
            existing.quality_score == candidate.quality_score and existing.cost == candidate.cost for existing in front
        )
        if is_duplicate:
            continue

        # Remove any front members dominated by this new candidate
        front = [existing for existing in front if not dominates(candidate, existing)]

        front.append(candidate)
        new_pareto_points += 1

    return front, new_pareto_points


# ---------------------------------------------------------------------------
# Selection helper
# ---------------------------------------------------------------------------


def select_best(front: list[Candidate]) -> str:
    """Return the prompt_version of the best candidate on the Pareto front.

    Best is defined as highest quality_score; ties broken by lowest cost.

    Args:
        front: Non-empty list of Pareto-front candidates.

    Returns:
        The prompt_version string of the best candidate.

    Raises:
        ValueError: If front is empty.
    """
    if not front:
        raise ValueError("Cannot select best from an empty Pareto front")
    best = max(front, key=lambda c: (c.quality_score, -c.cost))
    return best.prompt_version
