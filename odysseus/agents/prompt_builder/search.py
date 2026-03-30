# odysseus/agents/prompt_builder_search.py
"""Search state models and Pareto dominance logic for the Prompt Builder Agent.

Tracks the tournament-selection optimization loop with Pareto tracking across
quality and cost dimensions.

See: docs/superpowers/specs/2026-03-24-thp-77-prompt-builder-agent-design.md
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Candidate(BaseModel):
    """A single prompt candidate with quality and cost metrics."""

    prompt_version: str
    parent_version: str | None
    quality_score: float
    cost: float
    round_introduced: int
    dominated: bool = False

    @field_validator("prompt_version")
    @classmethod
    def prompt_version_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("prompt_version must be non-empty")
        return v


class RoundSummary(BaseModel):
    """Summary of a single search round."""

    round: int = Field(ge=1)
    candidates_evaluated: list[str]
    new_pareto_points: int
    front_size: int
    mutation_mode: Literal["targeted", "exploratory"]
    stagnation_count: int
    converged: bool = False


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
    loop_phase: Literal["build", "review"] = "build"

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
