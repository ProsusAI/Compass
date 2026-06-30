# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Search state models and Pareto dominance logic for the Prompt Builder Agent.

Tracks the tournament-selection optimization loop with Pareto tracking across
quality and cost dimensions.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type alias for algorithm discriminator
# ---------------------------------------------------------------------------

AlgorithmType = Literal["beam"]

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Candidate(BaseModel):
    """A single prompt candidate with quality and cost metrics.

    Optional fields default to ``None`` / empty; hill-climb code never has to
    set them.

    Serialisation note: old state files may contain a ``dominated`` field.
    ``extra="ignore"`` ensures they load without error — the field is discarded.

    Alias note: ``iteration_introduced`` is accepted as an alias for
    ``round_introduced`` for back-compat with older state files.
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

        Enables older state files to load without a migration step.
        If both keys are present, ``round_introduced`` wins.
        """
        if isinstance(data, dict) and "iteration_introduced" in data and "round_introduced" not in data:
            data = dict(data)
            data["round_introduced"] = data.pop("iteration_introduced")
        return data


class RoundSummary(BaseModel):
    """Summary of a single search round.

    Field names follow the unified cross-branch schema:
    - ``new_elite_entries`` (was ``new_pareto_points`` on main)
    - ``elite_size`` (was ``front_size`` on main)
    - ``target_improvement`` (was ``front_improvement`` on main)

    Backward-compat: a ``model_validator(mode="before")`` maps the old names to
    the new ones so that state files produced before this rename still load
    without a migration step.

    Strategy-specific optional fields default to ``None``; each strategy fills
    only what is meaningful for its algorithm.
    """

    model_config = ConfigDict(extra="ignore")

    round: int = Field(ge=1)
    candidates_evaluated: list[str]
    new_elite_entries: int
    elite_size: int
    # Hill-climb specific — Optional since other strategies do not populate them
    mutation_mode: Literal["targeted", "exploratory"] | None = None
    stagnation_count: int | None = None
    converged: bool = False
    target_improvement: float = 0.0
    front_quality_spread: float = 0.0
    round_routing_cost: float = 0.0
    convergence_reason: str | None = None
    # Strategy-specific optional fields
    backtracking: bool = False
    hypervolume: float | None = None
    reference_point: tuple[float, float] | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_old_field_names(cls, data: Any) -> Any:
        """Map old serialised field names to the new canonical names.

        Handles state files written before the cross-branch rename:
        - ``new_pareto_points`` → ``new_elite_entries``
        - ``front_size`` → ``elite_size``
        - ``front_improvement`` → ``target_improvement``
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "new_pareto_points" in data and "new_elite_entries" not in data:
            data["new_elite_entries"] = data.pop("new_pareto_points")
        if "front_size" in data and "elite_size" not in data:
            data["elite_size"] = data.pop("front_size")
        if "front_improvement" in data and "target_improvement" not in data:
            data["target_improvement"] = data.pop("front_improvement")
        return data


class SearchState(BaseModel):
    """Full mutable state for the Prompt Builder search loop.

    The ``elite_set`` field (formerly ``pareto_front`` on main) holds the
    current non-dominated candidate set.  It is renamed to match the three
    feature branches and to be algorithm-agnostic.

    Backward-compat: a ``model_validator(mode="before")`` maps old
    ``pareto_front`` keys to ``elite_set`` so that state files written before
    this rename still load without error.

    The ``algorithm`` discriminator records which search strategy produced this
    state; ``algorithm_state`` is a free-form pocket for strategy-specific
    sub-state (empty for hill_climb; feature branches may populate it).
    """

    model_config = ConfigDict(extra="ignore")

    search_state_id: str
    backend: str
    primary_metric_name: str | None = None
    round: int = 0
    elite_set: list[Candidate] = Field(default_factory=list)
    round_history: list[RoundSummary] = Field(default_factory=list)
    stagnation_count: int = 0
    stagnation_limit: int = 3
    convergence_limit: int = 5
    max_rounds: int = 50
    evaluation_budget: int = 60
    mutation_mode: Literal["targeted", "exploratory"] = "targeted"
    converged: bool = False
    loop_phase: Literal[
        "build",
        "review",
        "warmup_seed",
        "warmup_build",
        "warmup_reduce",
        "calibration",
        "build_recovering",
    ] = "review"
    epsilon: float = 0.001
    total_routing_cost: float = 0.0
    # Cross-branch generalization fields.
    # ``algorithm`` is typed as ``str`` so persisted leaf-branch state files
    # (which may carry values like "hill_climb", "beam", "emosa") load without
    # Pydantic validation errors.  ``AlgorithmType`` constrains only the
    # module-level ``_BRANCH_ALGORITHM`` constant in ``search_ops.py``.
    algorithm: str = "beam"
    algorithm_state: dict[str, Any] = Field(default_factory=dict)
    # Batch eval tracking — versions currently in flight (pending or running).
    # Used by _detect_stage_4_phase to detect build_recovering and by
    # advance_round to guard against advancing while evals are in flight.
    active_evals: list[str] = Field(default_factory=list)
    # Global monotonic counter for sequential vN variant ids (v1, v2, …).
    next_variant_seq: int = 1

    @field_validator("search_state_id")
    @classmethod
    def search_state_id_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("search_state_id must be non-empty")
        return v

    @model_validator(mode="before")
    @classmethod
    def _migrate_pareto_front(cls, data: Any) -> Any:
        """Map old ``pareto_front`` key to ``elite_set`` and coerce unknown
        ``loop_phase`` values to ``"review"``.

        State files written before the cross-branch rename carry
        ``"pareto_front": [...]`` instead of ``"elite_set": [...]``.
        This validator transparently promotes the old key so those files
        load without a migration step.

        Unknown ``loop_phase`` strings (e.g. phases introduced on a feature
        branch that are not yet part of the widened enum) are mapped to
        ``"review"`` so that legacy state files do not cause a validation error.
        ``extra="ignore"`` already drops unknown *keys*; this handles unknown
        *values* on the Literal field.
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "pareto_front" in data and "elite_set" not in data:
            data["elite_set"] = data.pop("pareto_front")
        _valid_phases = {
            "build",
            "review",
            "warmup_seed",
            "warmup_build",
            "warmup_reduce",
            "calibration",
            "build_recovering",
        }
        raw_phase = data.get("loop_phase")
        if raw_phase is not None and raw_phase not in _valid_phases:
            data["loop_phase"] = "review"
        return data

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
# Beam search elite set primitives
# ---------------------------------------------------------------------------


def compute_pareto_front(candidates: list[Candidate]) -> list[Candidate]:
    """Return the non-dominated subset of candidates (Pareto front).

    Quality is maximized, cost is minimized. Candidate A dominates B when
    A has >= quality AND <= cost, with at least one strict inequality.
    """
    front: list[Candidate] = []
    for candidate in candidates:
        dominated = False
        for other in candidates:
            if other is candidate:
                continue
            if dominates(other, candidate):
                dominated = True
                break
        if not dominated:
            front.append(candidate)
    return front


def crowding_distance(front: list[Candidate]) -> dict[str, float]:
    """Compute NSGA-II crowding distance for each candidate on the front.

    Endpoints (best quality, lowest cost) always receive infinite distance.
    Interior points receive the normalized sum of neighbor distances on each axis.

    Returns:
        Mapping from prompt_version to crowding distance.
    """
    if not front:
        return {}
    if len(front) <= 2:
        return {c.prompt_version: float("inf") for c in front}

    distances: dict[str, float] = {c.prompt_version: 0.0 for c in front}

    for key, reverse in [("quality_score", True), ("cost", False)]:
        sorted_front = sorted(front, key=lambda c: getattr(c, key), reverse=reverse)
        values = [getattr(c, key) for c in sorted_front]
        span = max(values) - min(values)

        # Endpoints always get infinite distance
        distances[sorted_front[0].prompt_version] = float("inf")
        distances[sorted_front[-1].prompt_version] = float("inf")

        if span == 0.0:
            continue

        for i in range(1, len(sorted_front) - 1):
            prev_val = getattr(sorted_front[i - 1], key)
            next_val = getattr(sorted_front[i + 1], key)
            normalized = abs(prev_val - next_val) / span
            if distances[sorted_front[i].prompt_version] != float("inf"):
                distances[sorted_front[i].prompt_version] += normalized

    return distances


def compute_hypervolume(front: list[Candidate], reference_point: tuple[float, float]) -> float:
    """Compute the 2D hypervolume indicator for the front relative to a reference point.

    Quality is maximized (x-axis), cost is minimized (y-axis). The reference point
    is (min_quality_bound, max_cost_bound). Uses a sweepline over quality.

    Args:
        front: Non-dominated candidates.
        reference_point: (min_quality, max_cost) lower-left reference corner.

    Returns:
        Hypervolume as a float (0.0 for empty front).
    """
    if not front:
        return 0.0

    ref_quality, ref_cost = reference_point
    # Sort by quality ascending for left-to-right sweep
    sorted_front = sorted(front, key=lambda c: c.quality_score)

    hypervolume = 0.0
    prev_quality = ref_quality
    for candidate in sorted_front:
        width = candidate.quality_score - prev_quality
        height = ref_cost - candidate.cost
        if width > 0 and height > 0:
            hypervolume += width * height
        prev_quality = candidate.quality_score

    return hypervolume


def find_knee_point(front: list[Candidate]) -> str:
    """Return the prompt_version of the knee point on the Pareto front.

    The knee point is the candidate with the maximum perpendicular distance
    to the line connecting the two endpoints of the front (highest quality
    and lowest cost). For fronts with <=2 candidates, returns the highest
    quality candidate.

    Raises:
        ValueError: If front is empty.
    """
    if not front:
        raise ValueError("Cannot find knee point of an empty front")

    if len(front) == 1:
        return front[0].prompt_version

    # Sort by quality ascending so index 0 is lowest quality
    sorted_front = sorted(front, key=lambda c: c.quality_score)

    if len(front) == 2:
        # Return highest quality
        return sorted_front[-1].prompt_version

    # Endpoints of the front diagonal: lowest quality (index 0) and highest quality (index -1)
    low_end = sorted_front[0]  # low quality, high cost end
    high_end = sorted_front[-1]  # high quality, low cost end

    q_min = low_end.quality_score
    q_max = high_end.quality_score
    c_min = high_end.cost
    c_max = low_end.cost

    q_range = q_max - q_min if q_max != q_min else 1.0
    c_range = c_max - c_min if c_max != c_min else 1.0

    # Normalize to [0, 1]: x = (quality - q_min) / q_range, y = (cost - c_min) / c_range
    # High-quality end maps to (1, 0), low-quality end maps to (0, 1)
    # Line from (0, 1) to (1, 0) has equation x + y = 1, or x + y - 1 = 0
    # Perpendicular distance = |x + y - 1| / sqrt(2)
    best_version = high_end.prompt_version
    best_dist = -1.0

    for candidate in front:
        x = (candidate.quality_score - q_min) / q_range
        y = (candidate.cost - c_min) / c_range
        dist = abs(x + y - 1.0)
        if dist > best_dist:
            best_dist = dist
            best_version = candidate.prompt_version

    return best_version


def prune_to_size(front: list[Candidate], max_size: int) -> list[Candidate]:
    """Reduce front to at most max_size candidates by removing least-diverse members.

    Iteratively removes the candidate with the smallest crowding distance,
    protecting the endpoints (highest quality and lowest cost) each iteration.

    Args:
        front: List of candidates on the Pareto front.
        max_size: Maximum number of candidates to retain.

    Returns:
        Pruned list with at most max_size candidates.
    """
    result = list(front)

    while len(result) > max_size:
        distances = crowding_distance(result)

        # Identify endpoints to protect
        best_quality = max(result, key=lambda c: c.quality_score).prompt_version
        best_cost = min(result, key=lambda c: c.cost).prompt_version
        protected = {best_quality, best_cost}

        # Find non-endpoint candidate with smallest crowding distance
        candidates_to_consider = [c for c in result if c.prompt_version not in protected]
        if not candidates_to_consider:
            # All remaining are endpoints; can't prune further
            break

        to_remove = min(candidates_to_consider, key=lambda c: distances.get(c.prompt_version, 0.0))
        result = [c for c in result if c.prompt_version != to_remove.prompt_version]

    return result


def update_elite_set(
    current_elite: list[Candidate],
    new_candidates: list[Candidate],
    max_size: int = 10,  # callers should pass 2*beam_width+1; this is a safe fallback
    is_cold_start_round: bool = False,
) -> tuple[list[Candidate], int]:
    """Update the elite set using Pareto dominance on (quality, cost).

    Combines existing front with new scored candidates, computes the
    non-dominated set, and prunes to max_size using crowding distance.

    When is_cold_start_round is True (round 1 only), Pareto filtering and
    crowding-distance pruning are bypassed: all new_candidates are retained
    as-is so every initial strategy survives to produce at least one child
    in round 2.
    """
    if is_cold_start_round:
        scored = [c for c in new_candidates if c.quality_score != 0.0 or c.cost != 0.0]
        by_version: dict[str, Candidate] = {}
        for c in list(current_elite) + scored:
            by_version[c.prompt_version] = c
        result = list(by_version.values())
        old_versions = {c.prompt_version for c in current_elite}
        new_entries = sum(1 for c in result if c.prompt_version not in old_versions)
        return result, new_entries

    all_candidates = list(current_elite) + [
        c
        for c in new_candidates
        if c.quality_score != 0.0 or c.cost != 0.0  # skip placeholder (0.0, 0.0); signed deltas may be negative
    ]
    if not all_candidates:
        return [], 0

    by_version_pareto: dict[str, Candidate] = {}
    for c in all_candidates:
        by_version_pareto[c.prompt_version] = c
    all_candidates = list(by_version_pareto.values())

    new_front = compute_pareto_front(all_candidates)
    new_front = prune_to_size(new_front, max_size)

    old_versions = {c.prompt_version for c in current_elite}
    new_entries = sum(1 for c in new_front if c.prompt_version not in old_versions)

    return new_front, new_entries


def validate_elite_set(elite_set: list[Candidate]) -> list[Candidate]:
    """Recompute Pareto front from the elite set, removing any dominated members.

    Defensive check: if the elite is correctly maintained, this is a no-op.
    Logs a warning if dominated candidates are found and removed.
    """
    if not elite_set:
        return []
    recomputed = compute_pareto_front(elite_set)
    if len(recomputed) < len(elite_set):
        removed = {c.prompt_version for c in elite_set} - {c.prompt_version for c in recomputed}
        logger.warning(
            "validate_elite_set: removed %d dominated candidate(s): %s",
            len(removed),
            removed,
        )
    return recomputed
