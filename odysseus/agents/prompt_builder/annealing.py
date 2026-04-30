"""Decomposition-based multi-objective simulated annealing — pure functions.

The algorithm is EMOSA (Li & Landa-Silva 2011):
- Tchebycheff scalarization per sub-problem (Zhang & Li 2007, MOEA/D) for calibration;
  augmented ASF against per-trajectory reference points for search (Wierzbicki 1980)
- K parallel trajectories, each with its own current_solution and Metropolis acceptance
- EMOSA neighborhood replacement: accepted children replace neighbor trajectories
  if they improve the neighbor's Tchebycheff energy (no Metropolis gate)
- Plain non-dominated archive (dominance filter only, no size limits)

All functions are pure (no file I/O, no side effects except ``metropolis_accept``
which uses ``random``). Stateful file-backed operations live in ``search_ops.py``.

See ``docs/algorithm.md`` for full theory and citations.

References:
    Li, H. & Landa-Silva, D. (2011). An adaptive evolutionary multi-objective
    approach based on simulated annealing. Evolutionary Computation 19(4):561-595.

    Zhang, Q. & Li, H. (2007). MOEA/D: A multiobjective evolutionary algorithm
    based on decomposition. IEEE TEC 11(6):712-731.

    Wierzbicki, A.P. (1980). The use of reference objectives in multiobjective
    optimization. Multiple Criteria Decision Making Theory and Application, pp. 468-486.
"""

from __future__ import annotations

import logging
import math
import random
from typing import Literal

from pydantic import BaseModel, Field

from odysseus.agents.prompt_builder.search import Candidate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TrajectoryState(BaseModel):
    """State for a single SA trajectory (one weight vector / decomposition direction)."""

    trajectory_id: int
    weight_vector: tuple[float, float]
    """(lambda_q, lambda_c), where lambda_c = 1 - lambda_q."""
    current_solution: str | None = None
    """prompt_version of the current candidate held by this trajectory."""
    current_energy: float | None = None
    """Tchebycheff / ASF energy for the current solution under this trajectory's weight vector."""
    current_quality: float | None = None
    """Raw quality score of current_solution; cached so current_energy can be recomputed when ideal/nadir drift."""
    current_cost: float | None = None
    """Raw cost of current_solution; cached so current_energy can be recomputed when ideal/nadir drift."""
    acceptance_history: list[bool] = Field(default_factory=list)
    """Last 5 accept/reject decisions (True = accepted)."""
    quality_reference: float | None = None
    """Active reference on the quality axis for ASF energy (per-trajectory threshold)."""
    cost_reference: float | None = None
    """Active reference on the cost axis for ASF energy (per-trajectory threshold)."""


class AnnealingState(BaseModel):
    """Full mutable state for the simulated-annealing search loop."""

    temperature: float
    """Current annealing temperature."""
    t_initial: float = 1.0
    """Initial temperature — sensible default for [0, 1]-normalised objectives."""
    t_min: float = 0.01
    """Minimum temperature; annealing stops below this threshold."""
    alpha: float
    """Cooling rate, typically auto-computed via ``compute_cooling_rate``."""
    num_trajectories: int = 5
    children_per_trajectory: int = 1
    """Number of child candidates to generate per trajectory per round (M)."""
    step_count: int = 0
    """Total SA steps completed across all trajectories."""
    trajectories: list[TrajectoryState]
    neighborhood_size: int = 4
    """Number of nearest neighbor trajectories for EMOSA neighborhood replacement (B).
    Raised from 2 to 4 per a15b608 to enable full cross-flow among K=5 trajectories."""
    ideal_point: tuple[float, float] = (0.0, 0.0)
    """(best_quality, lowest_cost) — updated as better solutions are found."""
    nadir_point: tuple[float, float] = (0.0, 0.0)
    """(worst_quality, highest_cost) — used for objective normalisation."""
    max_evals: int = 50
    total_evals: int = 0
    convergence_limit: int = 4
    epsilon: float = 0.003
    phase: Literal["calibration", "search", "converged"] = "calibration"
    rho: float = Field(default=1e-3, description="Augmentation coefficient ρ for ASF energy (Wierzbicki 1980).")
    """ρ prevents degenerate solutions by penalising the full weighted sum alongside the Chebyshev max."""


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def normalize_objectives(
    quality: float,
    cost: float,
    ideal_point: tuple[float, float],
    nadir_point: tuple[float, float],
) -> tuple[float, float]:
    """Normalise quality and cost to [0, 1] relative to ideal and nadir points.

    For *quality* (maximised): 0 = at ideal (best), 1 = at nadir (worst).
    For *cost* (minimised): 0 = at ideal (best), 1 = at nadir (worst).

    If the range on either axis is zero, that normalised value is 0.0.
    Output is clamped to [0, 1].

    Args:
        quality: Raw quality score.
        cost: Raw cost value.
        ideal_point: (best_quality, lowest_cost).
        nadir_point: (worst_quality, highest_cost).

    Returns:
        (norm_quality, norm_cost) each in [0, 1].
    """
    ideal_q, ideal_c = ideal_point
    nadir_q, nadir_c = nadir_point

    # Quality: distance from ideal (higher is closer to 0)
    q_range = ideal_q - nadir_q
    norm_q = 0.0 if q_range == 0.0 else (ideal_q - quality) / q_range

    # Cost: distance from ideal (lower cost is closer to 0)
    c_range = nadir_c - ideal_c
    norm_c = 0.0 if c_range == 0.0 else (cost - ideal_c) / c_range

    norm_q = max(0.0, min(1.0, norm_q))
    norm_c = max(0.0, min(1.0, norm_c))
    return norm_q, norm_c


def compute_tchebycheff_energy(
    quality: float,
    cost: float,
    weight_vector: tuple[float, float],
    ideal_point: tuple[float, float],
    nadir_point: tuple[float, float],
) -> float:
    """Compute the weighted Tchebycheff energy for a (quality, cost) point.

    ``E = max(λ_q * norm_q, λ_c * norm_c)``

    Lower energy means the point is closer to the ideal along this weight
    vector's direction.

    Args:
        quality: Raw quality score.
        cost: Raw cost value.
        weight_vector: (lambda_q, lambda_c) with lambda_c = 1 - lambda_q.
        ideal_point: (best_quality, lowest_cost).
        nadir_point: (worst_quality, highest_cost).

    Returns:
        Tchebycheff energy as a non-negative float.
    """
    lambda_q, lambda_c = weight_vector
    norm_q, norm_c = normalize_objectives(quality, cost, ideal_point, nadir_point)
    return max(lambda_q * norm_q, lambda_c * norm_c)


def compute_asf_energy(
    quality: float,
    cost: float,
    weight_vector: tuple[float, float],
    reference_point: tuple[float | None, float | None],
    ideal_point: tuple[float, float],
    nadir_point: tuple[float, float],
    rho: float = 1e-3,
) -> float:
    """Compute the augmented Achievement Scalarizing Function (ASF) energy.

    Formula (Wierzbicki 1980):

    .. code-block:: text

        gap_q = (quality_reference − quality) / (quality_reference − nadir_quality)
        gap_c = (cost − cost_reference)       / (nadir_cost − cost_reference)
        E     = max(λ_q · gap_q, λ_c · gap_c) + ρ · (λ_q · gap_q + λ_c · gap_c)

    Gaps are **signed**: an axis where the current solution overshoots the reference
    contributes a negative term, which naturally drops out of ``max`` but still
    appears in the augmentation sum.

    Fallback rules:
    - If ``reference_point[i]`` is ``None``: use the Tchebycheff-style normalized
      term for that axis (``λ_i · norm_i`` using clamped ideal/nadir normalization,
      consistent with ``compute_tchebycheff_energy``).
    - If ``reference_point[i] == nadir_point[i]`` (denominator zero): fall back to
      ``(ideal_i − nadir_i)`` as denominator. If that is also zero, treat the
      axis gap as 0.0.

    Args:
        quality: Raw quality score (maximised).
        cost: Raw cost value (minimised).
        weight_vector: ``(lambda_q, lambda_c)`` with ``lambda_c = 1 − lambda_q``.
        reference_point: ``(quality_reference, cost_reference)``. Either component
            may be ``None`` to trigger the Tchebycheff fallback on that axis.
        ideal_point: ``(best_quality, lowest_cost)`` for normalisation.
        nadir_point: ``(worst_quality, highest_cost)`` for normalisation.
        rho: Augmentation coefficient (default ``1e-3``).

    Returns:
        ASF energy as a float (may be negative when the current solution exceeds
        the reference on all axes).
    """
    lambda_q, lambda_c = weight_vector
    ideal_q, ideal_c = ideal_point
    nadir_q, nadir_c = nadir_point
    ref_q, ref_c = reference_point

    # --- Quality gap ---
    if ref_q is None:
        # Tchebycheff fallback: λ_q * norm_q (clamped, non-negative)
        norm_q, _ = normalize_objectives(quality, cost, ideal_point, nadir_point)
        term_q = lambda_q * norm_q
    else:
        # Signed gap: (reference − current) / (reference − nadir)
        denom_q = ref_q - nadir_q
        if denom_q == 0.0:
            # Fall back to ideal−nadir span
            denom_q = ideal_q - nadir_q
        if denom_q == 0.0:
            term_q = 0.0
        else:
            gap_q = (ref_q - quality) / denom_q
            term_q = lambda_q * gap_q

    # --- Cost gap ---
    if ref_c is None:
        # Tchebycheff fallback: λ_c * norm_c (clamped, non-negative)
        _, norm_c = normalize_objectives(quality, cost, ideal_point, nadir_point)
        term_c = lambda_c * norm_c
    else:
        # Signed gap: (current − reference) / (nadir − reference)
        denom_c = nadir_c - ref_c
        if denom_c == 0.0:
            # Fall back to nadir−ideal span
            denom_c = nadir_c - ideal_c
        if denom_c == 0.0:
            term_c = 0.0
        else:
            gap_c = (cost - ref_c) / denom_c
            term_c = lambda_c * gap_c

    return max(term_q, term_c) + rho * (term_q + term_c)


def metropolis_accept(
    delta_e: float,
    temperature: float,
    rng: random.Random | None = None,
) -> bool:
    """Metropolis acceptance criterion for simulated annealing.

    Accepts improvements (delta_e <= 0) unconditionally. Worsening moves
    (delta_e > 0) are accepted with probability ``exp(-delta_e / temperature)``.

    Args:
        delta_e: Energy difference (new_energy - current_energy).
        temperature: Current annealing temperature (> 0).
        rng: Optional seeded ``random.Random`` instance for deterministic testing.
            When ``None`` (default) the module-level ``random`` is used.

    Returns:
        True if the move is accepted.
    """
    if delta_e <= 0:
        return True
    probability = math.exp(-delta_e / temperature)
    draw = rng.random() if rng is not None else random.random()
    return draw < probability


def compute_weight_vectors(num_trajectories: int) -> list[tuple[float, float]]:
    """Compute evenly-spaced weight vectors for decomposition-based search.

    Lambda_q values are drawn from [0.1, 0.9]; lambda_c = 1 - lambda_q.
    Quality-focused (high lambda_q) trajectories are listed first.

    Args:
        num_trajectories: Number of weight vectors to generate (>= 1).

    Returns:
        List of (lambda_q, lambda_c) tuples, length == num_trajectories.
    """
    if num_trajectories == 1:
        return [(0.5, 0.5)]
    if num_trajectories == 2:
        return [(0.9, 0.1), (0.1, 0.9)]

    # linspace from 0.9 down to 0.1 (quality-focused first)
    step = (0.9 - 0.1) / (num_trajectories - 1)
    vectors: list[tuple[float, float]] = []
    for i in range(num_trajectories):
        lq = round(0.9 - i * step, 10)
        lq = max(0.1, min(0.9, lq))
        vectors.append((lq, round(1.0 - lq, 10)))
    return vectors


def compute_cooling_rate(t_initial: float, t_min: float, max_steps: int) -> float:
    """Compute geometric cooling rate alpha so T reaches t_min after max_steps.

    ``alpha = (t_min / t_initial) ** (1 / max_steps)``

    Clamped to [0.5, 0.999] for numerical safety.

    Args:
        t_initial: Starting temperature (> 0).
        t_min: Target minimum temperature (> 0, < t_initial).
        max_steps: Total number of cooling steps (>= 1).

    Returns:
        Cooling rate alpha in [0.5, 0.999].
    """
    if max_steps < 1:
        raise ValueError("max_steps must be >= 1")
    alpha = (t_min / t_initial) ** (1.0 / max_steps)
    return max(0.5, min(0.999, alpha))


def _dominates(a: Candidate, b: Candidate) -> bool:
    """Return True if *a* dominates *b* (at least as good on all axes, strictly better on one).

    Quality is maximised; cost is minimised.
    """
    return (
        a.quality_score >= b.quality_score
        and a.cost <= b.cost
        and (a.quality_score > b.quality_score or a.cost < b.cost)
    )


def update_archive(
    current_archive: list[Candidate],
    new_candidate: Candidate,
) -> tuple[list[Candidate], bool]:
    """Attempt to add *new_candidate* to the non-dominated archive.

    Steps:
    1. If *new_candidate* is dominated by any archive member → reject.
    2. Remove archive members dominated by *new_candidate*.
    3. Add *new_candidate*.

    Args:
        current_archive: Current list of non-dominated candidates.
        new_candidate: Candidate to potentially add.

    Returns:
        (updated_archive, added) where *added* is True if the candidate was inserted.
    """
    # Step 1: check if dominated
    for member in current_archive:
        if _dominates(member, new_candidate):
            return list(current_archive), False

    # Step 2: remove dominated members
    survivors = [m for m in current_archive if not _dominates(new_candidate, m)]

    # Step 3: add new candidate
    survivors.append(new_candidate)

    return survivors, True


def compute_neighborhood(
    trajectory_id: int,
    neighborhood_size: int,
    weight_vectors: list[tuple[float, float]],
) -> list[int]:
    """Return the nearest trajectory IDs by L2 distance on weight vectors.

    Args:
        trajectory_id: The trajectory whose neighborhood is being computed.
        neighborhood_size: Number of nearest neighbors to return (B in EMOSA).
        weight_vectors: List of (lambda_q, lambda_c) tuples, indexed by trajectory_id.

    Returns:
        List of up to *neighborhood_size* trajectory IDs (excluding *trajectory_id*
        itself), sorted by ascending L2 distance on the weight-vector space.
    """
    wq, wc = weight_vectors[trajectory_id]
    distances: list[tuple[float, int]] = []
    for i, (oq, oc) in enumerate(weight_vectors):
        if i == trajectory_id:
            continue
        dist = math.sqrt((wq - oq) ** 2 + (wc - oc) ** 2)
        distances.append((dist, i))
    distances.sort()
    return [tid for _, tid in distances[:neighborhood_size]]


def replace_if_better(
    neighbor_state: TrajectoryState,
    child_energy: float,
    child_solution: str,
    child_quality: float,
    child_cost: float,
) -> TrajectoryState:
    """Unconditionally replace neighbor's current solution if child_energy is lower.

    This is EMOSA's neighborhood replacement step — no Metropolis gate.

    Args:
        neighbor_state: The neighbor trajectory's current state.
        child_energy: Tchebycheff energy of the child under the neighbor's weight vector.
        child_solution: prompt_version of the child candidate.
        child_quality: Raw quality score of the child candidate (cached for future re-normalisation).
        child_cost: Raw cost of the child candidate (cached for future re-normalisation).

    Returns:
        Updated TrajectoryState (unchanged if child_energy >= neighbor's current_energy).
    """
    if neighbor_state.current_energy is None or child_energy < neighbor_state.current_energy:
        logger.debug(
            "neighborhood replacement: T%d %.4f -> %.4f (%s)",
            neighbor_state.trajectory_id,
            neighbor_state.current_energy if neighbor_state.current_energy is not None else float("inf"),
            child_energy,
            child_solution,
        )
        return neighbor_state.model_copy(
            update={
                "current_solution": child_solution,
                "current_energy": child_energy,
                "current_quality": child_quality,
                "current_cost": child_cost,
            }
        )
    return neighbor_state
