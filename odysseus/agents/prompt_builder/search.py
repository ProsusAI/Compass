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
# Type alias for algorithm discriminator
# ---------------------------------------------------------------------------

AlgorithmType = Literal["hill_climb", "beam", "sms_emoa", "emosa"]

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
    hypervolume: float | None = None
    hypervolume_delta: float | None = None
    reference_point: tuple[float, float] | None = None
    acceptance_rates: dict[int, float] | None = None
    # reduce_case covers both beam ("singleton"/"dominated"/"delta_s_argmin") and
    # SMS-EMOA ("A_singleton"/"B_dominated"/"C_delta_s"/"warmup") case labels.
    reduce_case: Literal[
        "singleton", "dominated", "delta_s_argmin",
        "A_singleton", "B_dominated", "C_delta_s", "warmup",
    ] | None = None
    evicted_version: str | None = None
    temperature: float | None = None
    # SMS-EMOA specific
    parent_a_version: str | None = None
    parent_b_version: str | None = None
    population_size: int | None = None
    terminated: bool = False
    termination_reason: Literal["budget", "plateau", "max_iterations"] | None = None

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
    sub-state (e.g. beam_width for beam, AnnealingState dict for EMOSA).
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
    mutation_mode: Literal["targeted", "exploratory"] = "targeted"
    converged: bool = False
    loop_phase: Literal[
        "build", "review",
        "warmup_seed", "warmup_build", "warmup_reduce",
        "calibration",
        "build_recovering",
    ] = "review"
    epsilon: float = 0.001
    total_routing_cost: float = 0.0
    # Cross-branch generalization fields
    algorithm: AlgorithmType = "hill_climb"
    algorithm_state: dict[str, Any] = Field(default_factory=dict)
    # Batch eval tracking — versions currently in flight (pending or running).
    # Used by _detect_stage_4_phase to detect build_recovering and by
    # advance_round to guard against advancing while evals are in flight.
    active_evals: list[str] = Field(default_factory=list)

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
            "build", "review",
            "warmup_seed", "warmup_build", "warmup_reduce",
            "calibration", "build_recovering",
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


# ---------------------------------------------------------------------------
# Multi-objective Pareto utilities and SMS-EMOA algorithm primitives
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
            if (
                other.quality_score >= candidate.quality_score
                and other.cost <= candidate.cost
                and (other.quality_score > candidate.quality_score or other.cost < candidate.cost)
            ):
                dominated = True
                break
        if not dominated:
            front.append(candidate)
    return front


def _sweepline_hypervolume(
    points: list[tuple[float, float]],
    ref_quality: float,
    ref_cost: float,
) -> float:
    """2D hypervolume sweepline over normalised (quality, cost) pairs."""
    if not points:
        return 0.0
    sorted_pts = sorted(points, key=lambda p: p[0])
    hv = 0.0
    prev_q = ref_quality
    for q, c in sorted_pts:
        width = q - prev_q
        height = ref_cost - c
        if width > 0 and height > 0:
            hv += width * height
        prev_q = q
    return hv


def compute_hypervolume(
    points: list[Candidate],
    reference_point: tuple[float, float],
    _bounds: tuple[float, float, float, float] | None = None,
) -> float:
    """Compute the 2D hypervolume with internal [0,1] normalisation.

    Normalises (quality, cost) using observed min/max before computing the sweepline.
    Pass *_bounds* = (q_min, q_max, c_min, c_max) to fix the normalisation frame
    (used by exclusive_hypervolume_contribution for consistent comparisons).
    """
    if not points:
        return 0.0

    if _bounds is not None:
        q_min, q_max, c_min, c_max = _bounds
    else:
        qualities = [p.quality_score for p in points]
        costs = [p.cost for p in points]
        q_min, q_max = min(qualities), max(qualities)
        c_min, c_max = min(costs), max(costs)

    q_range = q_max - q_min if q_max != q_min else 1.0
    c_range = c_max - c_min if c_max != c_min else 1.0

    def norm_q(q: float) -> float:
        return (q - q_min) / q_range

    def norm_c(c: float) -> float:
        return (c - c_min) / c_range

    ref_q = norm_q(reference_point[0])
    ref_c = norm_c(reference_point[1])

    normalised = [(norm_q(p.quality_score), norm_c(p.cost)) for p in points]
    return _sweepline_hypervolume(normalised, ref_q, ref_c)


def fast_non_dominated_sort(candidates: list[Candidate]) -> list[list[Candidate]]:
    """Return fronts F1..Fv in non-domination order (Deb et al. 2002)."""
    n = len(candidates)
    if n == 0:
        return []

    domination_count: list[int] = [0] * n
    dominated_by: list[list[int]] = [[] for _ in range(n)]

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            ci, cj = candidates[i], candidates[j]
            # Does cj dominate ci?
            if (
                cj.quality_score >= ci.quality_score
                and cj.cost <= ci.cost
                and (cj.quality_score > ci.quality_score or cj.cost < ci.cost)
            ):
                domination_count[i] += 1
                dominated_by[j].append(i)

    fronts: list[list[Candidate]] = []
    current_front_indices: list[int] = [i for i in range(n) if domination_count[i] == 0]

    while current_front_indices:
        fronts.append([candidates[i] for i in current_front_indices])
        next_front_indices: list[int] = []
        for i in current_front_indices:
            for j in dominated_by[i]:
                domination_count[j] -= 1
                if domination_count[j] == 0:
                    next_front_indices.append(j)
        current_front_indices = next_front_indices

    return fronts


def dynamic_reference_point(front: list[Candidate], delta: float = 0.05) -> tuple[float, float]:
    """Compute a dynamic reference point from the current front.

    Returns (min_q - delta*range_q, max_c + delta*range_c).
    """
    if not front:
        return (0.0, 0.0)
    qualities = [c.quality_score for c in front]
    costs = [c.cost for c in front]
    q_min, q_max = min(qualities), max(qualities)
    c_min, c_max = min(costs), max(costs)
    range_q = q_max - q_min
    range_c = c_max - c_min
    return (q_min - delta * range_q, c_max + delta * range_c)


def exclusive_hypervolume_contribution(
    point: Candidate,
    front: list[Candidate],
    reference_point: tuple[float, float],
) -> float:
    """HV(front, r) - HV(front \\ {point}, r).

    Uses a fixed normalisation frame derived from *front* for both calls so
    removing a point does not shift the coordinate system.
    """
    if not front:
        return 0.0
    qualities = [p.quality_score for p in front]
    costs = [p.cost for p in front]
    bounds = (min(qualities), max(qualities), min(costs), max(costs))
    hv_full = compute_hypervolume(front, reference_point, _bounds=bounds)
    front_without = [c for c in front if c.prompt_version != point.prompt_version]
    hv_without = compute_hypervolume(front_without, reference_point, _bounds=bounds)
    return hv_full - hv_without


def reduce_population(
    population: list[Candidate],
    child: Candidate,
    mu: int,
    delta: float,
) -> tuple[list[Candidate], Candidate, str]:
    """SMS-EMOA steady-state reduce: union -> non-dominated sort -> evict one.

    Returns (new_population_of_size_mu, evicted_candidate, reduce_case).
    reduce_case in {"A_singleton", "B_dominated", "C_delta_s"}.
    Raises ValueError on duplicate prompt_version.
    """
    all_versions = [c.prompt_version for c in population] + [child.prompt_version]
    if len(all_versions) != len(set(all_versions)):
        raise ValueError(f"Duplicate prompt_version in population + child: {child.prompt_version}")

    union = list(population) + [child]
    fronts = fast_non_dominated_sort(union)
    last_front = fronts[-1]

    # Case A: singleton last front — evict it immediately
    if len(last_front) == 1:
        evicted = last_front[0]
        new_pop = [c for c in union if c.prompt_version != evicted.prompt_version]
        return new_pop, evicted, "A_singleton"

    # Count dominators for each member of the last front (number of candidates in union
    # that dominate them)
    def dominator_count(candidate: Candidate) -> int:
        count = 0
        for other in union:
            if other.prompt_version == candidate.prompt_version:
                continue
            if (
                other.quality_score >= candidate.quality_score
                and other.cost <= candidate.cost
                and (other.quality_score > candidate.quality_score or other.cost < candidate.cost)
            ):
                count += 1
        return count

    dominator_counts = {c.prompt_version: dominator_count(c) for c in last_front}
    max_dominators = max(dominator_counts.values())

    # Case B: at least one member has more dominators than others — evict that one
    most_dominated = [c for c in last_front if dominator_counts[c.prompt_version] == max_dominators]
    if len(most_dominated) == 1:
        evicted = most_dominated[0]
        new_pop = [c for c in union if c.prompt_version != evicted.prompt_version]
        return new_pop, evicted, "B_dominated"

    # Case B tie or Case C: all in last front have equal domination count (== 0 if last_front
    # == F1, else equal positive). Use exclusive HV contribution on last_front.
    ref = dynamic_reference_point(last_front, delta)

    delta_s: dict[str, float] = {}
    for c in last_front:
        delta_s[c.prompt_version] = exclusive_hypervolume_contribution(c, last_front, ref)

    min_delta = min(delta_s.values())
    min_candidates = [c for c in last_front if delta_s[c.prompt_version] == min_delta]

    # Deterministic tie-break: evict lex-later by (quality, cost, prompt_version)
    evicted = max(min_candidates, key=lambda c: (c.quality_score, c.cost, c.prompt_version))
    new_pop = [c for c in union if c.prompt_version != evicted.prompt_version]

    # Determine case: B if unequal dominator counts triggered us here (tie among max), C otherwise
    # Since Case B is only unambiguous when exactly one candidate has the most dominators (handled
    # above), anything reaching here is Case C (ΔS argmin).
    return new_pop, evicted, "C_delta_s"


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
