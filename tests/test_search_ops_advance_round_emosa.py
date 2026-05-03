"""Tests for advance_round_emosa steady-state path (phase == 'search').

Covers the full EMOSA advance loop implemented in C4 commit 1/4:
- Per-trajectory Metropolis-then-best-of-accepted
- Drift-cache refresh under expanded ideal/nadir
- EMOSA neighborhood replacement
- Three-way convergence (temperature_floor, eval_budget, review_exit)
- Calibration->search transition (unconditional first acceptance)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odysseus.agents.prompt_builder.annealing import (
    AnnealingState,
    TrajectorySnapshot,
    TrajectoryState,
    compute_tchebycheff_energy,
    compute_weight_vectors,
)
from odysseus.agents.prompt_builder.search import Candidate, SearchState
from odysseus.agents.prompt_builder.search_ops import (
    _load_pending,
    _load_state,
    _save_pending,
    _save_state,
    advance_round_emosa,
    get_search_state,
    init_search_state,
)
from odysseus.agents.review.models import LoopSignal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_annealing_state(
    num_trajectories: int = 5,
    phase: str = "search",
    temperature: float = 1.0,
    alpha: float = 0.95,
    t_min: float = 0.01,
    max_evals: int = 50,
    step_count: int = 1,
    total_evals: int = 5,
    ideal_point: tuple[float, float] = (0.9, 0.01),
    nadir_point: tuple[float, float] = (0.5, 0.09),
    with_seeded_trajectories: bool = True,
    seeded_candidates: list[Candidate] | None = None,
) -> AnnealingState:
    """Build an AnnealingState in search phase with optionally seeded trajectories.

    ``temperature``, ``alpha``, and ``step_count`` are applied uniformly to all
    trajectories (per-trajectory fields since Commit 2).
    """
    weight_vectors = compute_weight_vectors(num_trajectories)
    trajectories: list[TrajectoryState] = []
    for i in range(num_trajectories):
        if with_seeded_trajectories and seeded_candidates is not None:
            cand = seeded_candidates[i]
            energy = compute_tchebycheff_energy(
                cand.quality_score,
                cand.cost,
                weight_vectors[i],
                ideal_point,
                nadir_point,
            )
            traj = TrajectoryState(
                trajectory_id=i,
                weight_vector=weight_vectors[i],
                current_solution=cand.prompt_version,
                current_quality=cand.quality_score,
                current_cost=cand.cost,
                current_energy=energy,
                acceptance_history=[True],
                temperature=temperature,
                alpha=alpha,
                step_count=step_count,
            )
        elif with_seeded_trajectories:
            # Seed with a synthetic solution
            q = 0.9 - i * 0.08
            c = 0.01 + i * 0.02
            energy = compute_tchebycheff_energy(q, c, weight_vectors[i], ideal_point, nadir_point)
            traj = TrajectoryState(
                trajectory_id=i,
                weight_vector=weight_vectors[i],
                current_solution=f"seed_v{i}",
                current_quality=q,
                current_cost=c,
                current_energy=energy,
                acceptance_history=[True],
                temperature=temperature,
                alpha=alpha,
                step_count=step_count,
            )
        else:
            traj = TrajectoryState(
                trajectory_id=i,
                weight_vector=weight_vectors[i],
                temperature=temperature,
                alpha=alpha,
                step_count=step_count,
            )
        trajectories.append(traj)

    return AnnealingState(
        t_min=t_min,
        num_trajectories=num_trajectories,
        trajectories=trajectories,
        phase=phase,  # type: ignore[arg-type]
        total_evals=total_evals,
        ideal_point=ideal_point,
        nadir_point=nadir_point,
        max_evals=max_evals,
    )


def _make_emosa_search_state(
    tmp_path: Path,
    run_id: str,
    num_trajectories: int = 5,
    temperature: float = 1.0,
    alpha: float = 0.95,
    t_min: float = 0.01,
    max_evals: int = 50,
    step_count: int = 1,
    total_evals: int = 5,
    ideal_point: tuple[float, float] = (0.9, 0.01),
    nadir_point: tuple[float, float] = (0.5, 0.09),
    with_seeded_trajectories: bool = True,
    seeded_candidates: list[Candidate] | None = None,
) -> SearchState:
    """Init an emosa SearchState already in search phase with seeded trajectories.

    Since Wave 2, init_search_state uses _BRANCH_ALGORITHM / _BRANCH_ALGORITHM_STATE
    and no longer accepts algorithm / algorithm_state params.  We init, then patch the
    persisted state to overwrite algorithm_state with the full AnnealingState required
    by the steady-state search arm tests.
    """
    from odysseus.agents.prompt_builder.search_ops import _save_state

    annealing = _make_annealing_state(
        num_trajectories=num_trajectories,
        phase="search",
        temperature=temperature,
        alpha=alpha,
        t_min=t_min,
        max_evals=max_evals,
        step_count=step_count,
        total_evals=total_evals,
        ideal_point=ideal_point,
        nadir_point=nadir_point,
        with_seeded_trajectories=with_seeded_trajectories,
        seeded_candidates=seeded_candidates,
    )
    state = init_search_state(
        backend="test",
        run_id=run_id,
        output_dir=tmp_path,
    )
    # Overwrite algorithm_state with the fully populated search-phase AnnealingState
    # and set loop_phase='review' to match steady-state EMOSA operation.
    patched = state.model_copy(
        update={
            "algorithm_state": json.loads(annealing.model_dump_json()),
            "loop_phase": "review",
        }
    )
    _save_state(run_id, patched, tmp_path)
    return patched


def _init_emosa_with_annealing(
    run_id: str,
    output_dir: Path,
    annealing: AnnealingState,
    loop_phase: str = "review",
) -> SearchState:
    """Init a SearchState and overwrite algorithm_state with a full AnnealingState pocket.

    Since Wave 2, init_search_state uses _BRANCH_ALGORITHM / _BRANCH_ALGORITHM_STATE
    and no longer accepts algorithm / algorithm_state params.  This helper creates the
    state and patches it to match the annealing pocket required by each individual test.
    """
    state = init_search_state(
        backend="test",
        run_id=run_id,
        output_dir=output_dir,
    )
    patched = state.model_copy(
        update={
            "algorithm_state": json.loads(annealing.model_dump_json()),
            "loop_phase": loop_phase,
        }
    )
    _save_state(run_id, patched, output_dir)
    return patched


def _build_child_candidates(
    parent_versions: list[str],
    quality_scores: list[float],
    costs: list[float],
) -> list[Candidate]:
    """Build scored child Candidates with explicit parent linkage."""
    assert len(parent_versions) == len(quality_scores) == len(costs)
    return [
        Candidate(
            prompt_version=f"child_v{i + 1}",
            parent_version=parent_versions[i],
            quality_score=quality_scores[i],
            cost=costs[i],
            round_introduced=2,
            eval_status="complete",
        )
        for i in range(len(parent_versions))
    ]


# ---------------------------------------------------------------------------
# TestAdvanceRoundEmosaSearch
# ---------------------------------------------------------------------------


class TestAdvanceRoundEmosaSearch:
    """Tests for advance_round_emosa steady-state path (phase == 'search')."""

    def test_single_trajectory_accept(self, tmp_path: Path) -> None:
        """Single trajectory with 1 child that improves energy is accepted."""
        run_id = "emosa-ss-single-accept"
        ideal = (0.9, 0.01)
        nadir = (0.5, 0.09)
        weight_vectors = compute_weight_vectors(1)
        wv = weight_vectors[0]

        # Seed trajectory with a moderate solution
        seed_energy = compute_tchebycheff_energy(0.7, 0.05, wv, ideal, nadir)
        traj = TrajectoryState(
            trajectory_id=0,
            weight_vector=wv,
            current_solution="seed_v0",
            current_quality=0.7,
            current_cost=0.05,
            current_energy=seed_energy,
            acceptance_history=[True],
            temperature=10.0,  # Very high T -> near-always accept
            alpha=0.95,
            step_count=1,
        )
        annealing = AnnealingState(
            t_min=0.01,
            num_trajectories=1,
            trajectories=[traj],
            phase="search",
            total_evals=1,
            ideal_point=ideal,
            nadir_point=nadir,
        )
        _init_emosa_with_annealing(run_id=run_id, output_dir=tmp_path, annealing=annealing)
        # Child improves on seed
        child = Candidate(
            prompt_version="child_v1",
            parent_version="seed_v0",
            quality_score=0.85,
            cost=0.03,
            round_introduced=2,
            eval_status="complete",
        )
        _save_pending(run_id, [child], tmp_path)

        summary = advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        updated = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(updated.algorithm_state)
        traj_after = pocket.trajectories[0]

        assert traj_after.current_solution == "child_v1"
        assert traj_after.current_quality == pytest.approx(0.85)
        assert traj_after.acceptance_history[-1] is True
        assert summary.phase == "search"

    def test_multi_child_best_of_accepted(self, tmp_path: Path) -> None:
        """1 trajectory, 3 children: lowest-energy accepted child wins."""
        run_id = "emosa-ss-multi-child"
        ideal = (0.9, 0.01)
        nadir = (0.5, 0.09)
        weight_vectors = compute_weight_vectors(1)
        wv = weight_vectors[0]

        seed_energy = compute_tchebycheff_energy(0.7, 0.05, wv, ideal, nadir)
        traj = TrajectoryState(
            trajectory_id=0,
            weight_vector=wv,
            current_solution="seed_v0",
            current_quality=0.7,
            current_cost=0.05,
            current_energy=seed_energy,
            acceptance_history=[True],
            temperature=100.0,  # Very high T -> accept all
            alpha=0.95,
            step_count=1,
        )
        annealing = AnnealingState(
            t_min=0.01,
            num_trajectories=1,
            trajectories=[traj],
            phase="search",
            total_evals=1,
            ideal_point=ideal,
            nadir_point=nadir,
        )
        _init_emosa_with_annealing(run_id=run_id, output_dir=tmp_path, annealing=annealing)

        # 3 children with different quality/cost; best = lowest Tchebycheff energy
        children = [
            Candidate(
                prompt_version="child_v1",
                parent_version="seed_v0",
                quality_score=0.80,
                cost=0.04,
                round_introduced=2,
                eval_status="complete",
            ),
            Candidate(
                prompt_version="child_v2",
                parent_version="seed_v0",
                quality_score=0.88,  # Best quality
                cost=0.02,  # Best cost
                round_introduced=2,
                eval_status="complete",
            ),
            Candidate(
                prompt_version="child_v3",
                parent_version="seed_v0",
                quality_score=0.75,
                cost=0.06,
                round_introduced=2,
                eval_status="complete",
            ),
        ]
        _save_pending(run_id, children, tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        updated = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(updated.algorithm_state)
        traj_after = pocket.trajectories[0]

        # Compute which child has lowest energy under wv + new ideal/nadir
        # (new_ideal expands to include children; seed has q=0.7, c=0.05)
        child_q = [c.quality_score for c in children]
        child_c = [c.cost for c in children]
        new_ideal_q = max(child_q + [ideal[0]])
        new_ideal_c = min(child_c + [ideal[1]])
        new_nadir_q = min(child_q + [nadir[0]])
        new_nadir_c = max(child_c + [nadir[1]])
        new_ideal_point = (new_ideal_q, new_ideal_c)
        new_nadir_point = (new_nadir_q, new_nadir_c)

        energies = {
            c.prompt_version: compute_tchebycheff_energy(c.quality_score, c.cost, wv, new_ideal_point, new_nadir_point)
            for c in children
        }
        best_version = min(energies, key=lambda k: energies[k])
        assert traj_after.current_solution == best_version

    def test_drift_cache_refresh(self, tmp_path: Path) -> None:
        """Energies recomputed under expanded ideal/nadir before Metropolis."""
        run_id = "emosa-ss-drift"
        # Narrow initial ideal/nadir
        narrow_ideal = (0.7, 0.05)
        narrow_nadir = (0.6, 0.07)
        weight_vectors = compute_weight_vectors(1)
        wv = weight_vectors[0]

        # Seed with energy computed under narrow normalization
        narrow_energy = compute_tchebycheff_energy(0.65, 0.06, wv, narrow_ideal, narrow_nadir)
        traj = TrajectoryState(
            trajectory_id=0,
            weight_vector=wv,
            current_solution="seed_v0",
            current_quality=0.65,
            current_cost=0.06,
            current_energy=narrow_energy,
            acceptance_history=[True],
            temperature=1.0,
            alpha=0.95,
            step_count=1,
        )
        annealing = AnnealingState(
            t_min=0.01,
            num_trajectories=1,
            trajectories=[traj],
            phase="search",
            total_evals=1,
            ideal_point=narrow_ideal,
            nadir_point=narrow_nadir,
        )
        _init_emosa_with_annealing(run_id=run_id, output_dir=tmp_path, annealing=annealing)

        # New child with significantly better quality — expands ideal/nadir
        child = Candidate(
            prompt_version="child_v1",
            parent_version="seed_v0",
            quality_score=0.90,  # Much better quality
            cost=0.02,  # Much lower cost
            round_introduced=2,
            eval_status="complete",
        )
        _save_pending(run_id, [child], tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        updated = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(updated.algorithm_state)
        traj_after = pocket.trajectories[0]

        # Child should be accepted since it is better under the expanded normalization.
        # If drift-cache refresh were missing, the stale narrow energy would cause wrong Metropolis.
        assert traj_after.current_solution == "child_v1"
        # Verify ideal/nadir were updated
        assert pocket.ideal_point[0] == pytest.approx(0.90)
        assert pocket.ideal_point[1] == pytest.approx(0.02)

    def test_neighborhood_replacement(self, tmp_path: Path) -> None:
        """Accepted child replaces neighbor if it scalarizes better under neighbor's weight."""
        run_id = "emosa-ss-nbr"
        ideal = (0.9, 0.01)
        nadir = (0.5, 0.09)
        num_traj = 5
        weight_vectors = compute_weight_vectors(num_traj)

        # All trajectories seeded
        trajectories: list[TrajectoryState] = []
        for i in range(num_traj):
            q = 0.7 - i * 0.03
            c = 0.05 + i * 0.01
            e = compute_tchebycheff_energy(q, c, weight_vectors[i], ideal, nadir)
            trajectories.append(
                TrajectoryState(
                    trajectory_id=i,
                    weight_vector=weight_vectors[i],
                    current_solution=f"seed_v{i}",
                    current_quality=q,
                    current_cost=c,
                    current_energy=e,
                    acceptance_history=[True],
                    temperature=100.0,  # Very high T -> near-always accept
                    alpha=0.95,
                    step_count=1,
                )
            )

        annealing = AnnealingState(
            t_min=0.01,
            num_trajectories=num_traj,
            trajectories=trajectories,
            phase="search",
            total_evals=num_traj,
            ideal_point=ideal,
            nadir_point=nadir,
            neighborhood_size=4,
        )
        _init_emosa_with_annealing(run_id=run_id, output_dir=tmp_path, annealing=annealing)

        # Only trajectory 0 gets a child (very good quality/cost)
        children = [
            Candidate(
                prompt_version="child_v1",
                parent_version="seed_v0",
                quality_score=0.92,
                cost=0.01,
                round_introduced=2,
                eval_status="complete",
            )
        ]
        # Remaining trajectories have no new children
        _save_pending(run_id, children, tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        updated = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(updated.algorithm_state)

        # Trajectory 0 accepted child_v1
        traj0 = next(t for t in pocket.trajectories if t.trajectory_id == 0)
        assert traj0.current_solution == "child_v1"

        # At least one neighbor should have also been replaced
        # (neighborhood_size=4 means all other 4 trajectories are neighbors of traj 0)
        # child_v1 (0.92, 0.01) is highly dominant — should replace all neighbors
        neighbor_ids = {1, 2, 3, 4}
        replaced = [
            t for t in pocket.trajectories if t.trajectory_id in neighbor_ids and t.current_solution == "child_v1"
        ]
        assert len(replaced) > 0, "Expected at least one neighbor to be replaced"

    def test_neighborhood_replacement_propagates_rejected_child(self, tmp_path: Path) -> None:
        """Neighborhood replacement fires even when the originator's Metropolis rejected the child.

        T0 weight (0.9, 0.1) — quality-heavy.
        T1 weight (0.1, 0.9) — cost-heavy.
        ideal=(1.0, 0.0), nadir=(0.0, 1.0) — full unit range for simple energy arithmetic.

        Child generated from T0's current (q=0.95, c=0.5):
          - energy under T0: max(0.9*0.05, 0.1*0.5) = 0.05  (T0 current is already 0.05 — same; child
            at q=0.6,c=0.05: energy = max(0.9*0.4, 0.1*0.05) = max(0.36, 0.005) = 0.36 — WORSE)
          - energy under T1: max(0.1*0.4, 0.9*0.05) = max(0.04, 0.045) = 0.045 — BETTER than T1 current

        Temperature = 0.001 -> Metropolis rejects Δ=0.31 on T0 deterministically.
        neighborhood_size=1: T1 is in T0's neighborhood (only 2 trajectories).

        Expected: T0 unchanged (Metropolis rejected), T1 == child (neighborhood replacement fired).
        """
        import random

        random.seed(0)

        run_id = "emosa-nbr-rejected-child"
        ideal: tuple[float, float] = (1.0, 0.0)
        nadir: tuple[float, float] = (0.0, 1.0)

        # T0: quality-heavy weight
        # T0 current: q=0.95, c=0.5  -> energy = max(0.9*(1-0.95), 0.1*0.5) = max(0.045, 0.05) = 0.05
        e_t0 = compute_tchebycheff_energy(0.95, 0.5, (0.9, 0.1), ideal, nadir)
        # T1: cost-heavy weight
        # T1 current: q=0.6, c=0.1   -> energy = max(0.1*(1-0.6), 0.9*0.1) = max(0.04, 0.09) = 0.09
        e_t1 = compute_tchebycheff_energy(0.6, 0.1, (0.1, 0.9), ideal, nadir)

        trajectories = [
            TrajectoryState(
                trajectory_id=0,
                weight_vector=(0.9, 0.1),
                current_solution="seed_t0",
                current_quality=0.95,
                current_cost=0.5,
                current_energy=e_t0,
                acceptance_history=[True],
                temperature=0.001,  # Very low T -> Metropolis deterministically rejects worsening moves
                alpha=0.95,
                step_count=1,
            ),
            TrajectoryState(
                trajectory_id=1,
                weight_vector=(0.1, 0.9),
                current_solution="seed_t1",
                current_quality=0.6,
                current_cost=0.1,
                current_energy=e_t1,
                acceptance_history=[True],
                temperature=0.001,
                alpha=0.95,
                step_count=1,
            ),
        ]

        annealing = AnnealingState(
            t_min=0.0001,
            num_trajectories=2,
            trajectories=trajectories,
            phase="search",
            total_evals=2,
            ideal_point=ideal,
            nadir_point=nadir,
            neighborhood_size=1,
        )
        _init_emosa_with_annealing(run_id=run_id, output_dir=tmp_path, annealing=annealing)

        # Child from T0's seed:
        # q=0.6, c=0.05
        # energy under T0 = max(0.9*0.4, 0.1*0.05) = max(0.36, 0.005) = 0.36 >> T0 current 0.05 -> REJECTED
        # energy under T1 = max(0.1*0.4, 0.9*0.05) = max(0.04, 0.045) = 0.045 < T1 current 0.09 -> BETTER
        child = Candidate(
            prompt_version="child_cost_lean",
            parent_version="seed_t0",
            quality_score=0.6,
            cost=0.05,
            round_introduced=2,
            eval_status="complete",
        )
        _save_pending(run_id, [child], tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        updated = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(updated.algorithm_state)

        traj0 = next(t for t in pocket.trajectories if t.trajectory_id == 0)
        traj1 = next(t for t in pocket.trajectories if t.trajectory_id == 1)

        # T0 Metropolis rejected the worsening child — current unchanged
        assert traj0.current_solution == "seed_t0", (
            f"T0 should stay at seed_t0 (Metropolis rejected), got {traj0.current_solution}"
        )
        # T1 received the child via neighborhood replacement despite T0's rejection
        assert traj1.current_solution == "child_cost_lean", (
            f"T1 should adopt child_cost_lean via neighborhood replacement, got {traj1.current_solution}"
        )

    def test_neighborhood_replacement_shared_current(self, tmp_path: Path) -> None:
        """Neighborhood replacement propagates via union of all co-originating trajectories.

        T0 weight (0.9, 0.1), T1 weight (0.7, 0.3), T2 weight (0.1, 0.9).
        T0 and T1 share the same current_solution ("shared_v"), T2 has "t2_v".
        neighborhood_size=2: each trajectory's neighborhood includes both others.

        Child generated from "shared_v":
          - Worse under T0's weight -> Metropolis rejects (low T)
          - Worse under T1's weight -> Metropolis rejects (low T)
          - Better under T2's weight -> neighborhood replacement fires

        After advance_round_emosa:
          - T0 unchanged (in origins, excluded from nbr_ids)
          - T1 unchanged (in origins, excluded from nbr_ids)
          - T2 == child (received via neighborhood replacement)
        """
        import random

        random.seed(0)

        run_id = "emosa-nbr-shared-current"
        ideal: tuple[float, float] = (1.0, 0.0)
        nadir: tuple[float, float] = (0.0, 1.0)

        # Shared current: q=0.85, c=0.3
        # Energy under T0 (0.9, 0.1): max(0.9*0.15, 0.1*0.3) = max(0.135, 0.03) = 0.135
        # Energy under T1 (0.7, 0.3): max(0.7*0.15, 0.3*0.3) = max(0.105, 0.09) = 0.105
        e_shared_t0 = compute_tchebycheff_energy(0.85, 0.3, (0.9, 0.1), ideal, nadir)
        e_shared_t1 = compute_tchebycheff_energy(0.85, 0.3, (0.7, 0.3), ideal, nadir)

        # T2 current: q=0.4, c=0.8
        # Energy under T2 (0.1, 0.9): max(0.1*0.6, 0.9*0.8) = max(0.06, 0.72) = 0.72
        e_t2 = compute_tchebycheff_energy(0.4, 0.8, (0.1, 0.9), ideal, nadir)

        trajectories = [
            TrajectoryState(
                trajectory_id=0,
                weight_vector=(0.9, 0.1),
                current_solution="shared_v",
                current_quality=0.85,
                current_cost=0.3,
                current_energy=e_shared_t0,
                acceptance_history=[True],
                temperature=0.001,  # Very low T -> Metropolis deterministically rejects worsening moves
                alpha=0.95,
                step_count=1,
            ),
            TrajectoryState(
                trajectory_id=1,
                weight_vector=(0.7, 0.3),
                current_solution="shared_v",
                current_quality=0.85,
                current_cost=0.3,
                current_energy=e_shared_t1,
                acceptance_history=[True],
                temperature=0.001,
                alpha=0.95,
                step_count=1,
            ),
            TrajectoryState(
                trajectory_id=2,
                weight_vector=(0.1, 0.9),
                current_solution="t2_v",
                current_quality=0.4,
                current_cost=0.8,
                current_energy=e_t2,
                acceptance_history=[True],
                temperature=0.001,
                alpha=0.95,
                step_count=1,
            ),
        ]

        annealing = AnnealingState(
            t_min=0.0001,
            num_trajectories=3,
            trajectories=trajectories,
            phase="search",
            total_evals=3,
            ideal_point=ideal,
            nadir_point=nadir,
            neighborhood_size=2,  # Each trajectory's neighborhood = both others
        )
        _init_emosa_with_annealing(run_id=run_id, output_dir=tmp_path, annealing=annealing)

        # Child from shared_v:
        # q=0.3, c=0.05  (strongly cost-leaning)
        # Energy under T0 (0.9, 0.1): max(0.9*0.7, 0.1*0.05) = max(0.63, 0.005) = 0.63 >> 0.135 -> WORSE
        # Energy under T1 (0.7, 0.3): max(0.7*0.7, 0.3*0.05) = max(0.49, 0.015) = 0.49 >> 0.105 -> WORSE
        # Energy under T2 (0.1, 0.9): max(0.1*0.7, 0.9*0.05) = max(0.07, 0.045) = 0.07 << 0.72 -> BETTER
        child = Candidate(
            prompt_version="child_ultra_cheap",
            parent_version="shared_v",
            quality_score=0.3,
            cost=0.05,
            round_introduced=2,
            eval_status="complete",
        )
        _save_pending(run_id, [child], tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        updated = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(updated.algorithm_state)

        traj0 = next(t for t in pocket.trajectories if t.trajectory_id == 0)
        traj1 = next(t for t in pocket.trajectories if t.trajectory_id == 1)
        traj2 = next(t for t in pocket.trajectories if t.trajectory_id == 2)

        # T0 and T1 are originators — Metropolis rejected and they are excluded from nbr_ids
        assert traj0.current_solution == "shared_v", (
            f"T0 should remain at shared_v (originator, excluded), got {traj0.current_solution}"
        )
        assert traj1.current_solution == "shared_v", (
            f"T1 should remain at shared_v (originator, excluded), got {traj1.current_solution}"
        )
        # T2 is in both T0's and T1's neighborhoods; child is better under T2's weight
        assert traj2.current_solution == "child_ultra_cheap", (
            f"T2 should adopt child_ultra_cheap via neighborhood replacement, got {traj2.current_solution}"
        )

    def test_convergence_temperature_floor(self, tmp_path: Path) -> None:
        """Convergence via temperature_floor when T * alpha < t_min."""
        run_id = "emosa-ss-conv-temp"
        t_min = 0.1
        alpha = 0.5
        temperature = 0.19  # After one step: 0.19 * 0.5 = 0.095 < t_min=0.1

        _make_emosa_search_state(
            tmp_path,
            run_id,
            num_trajectories=1,
            temperature=temperature,
            alpha=alpha,
            t_min=t_min,
        )

        child = Candidate(
            prompt_version="child_v1",
            parent_version="seed_v0",
            quality_score=0.85,
            cost=0.03,
            round_introduced=2,
            eval_status="complete",
        )
        _save_pending(run_id, [child], tmp_path)

        summary = advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        assert summary.converged is True
        assert summary.convergence_reason == "temperature_floor"
        assert summary.phase == "converged"

        pocket = AnnealingState.model_validate(get_search_state(run_id, output_dir=tmp_path).algorithm_state)
        assert pocket.phase == "converged"

    def test_convergence_eval_budget(self, tmp_path: Path) -> None:
        """Convergence via eval_budget when total_evals >= max_evals after step."""
        run_id = "emosa-ss-conv-evals"
        max_evals = 6

        _make_emosa_search_state(
            tmp_path,
            run_id,
            num_trajectories=1,
            max_evals=max_evals,
            total_evals=5,  # After adding 1 scored child: 5+1=6 >= max_evals
        )

        child = Candidate(
            prompt_version="child_v1",
            parent_version="seed_v0",
            quality_score=0.85,
            cost=0.03,
            round_introduced=2,
            eval_status="complete",
        )
        _save_pending(run_id, [child], tmp_path)

        summary = advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        assert summary.converged is True
        assert summary.convergence_reason == "eval_budget"

    def test_convergence_review_exit(self, tmp_path: Path) -> None:
        """Convergence via review_exit when LoopSignal(action='exit') is present."""
        run_id = "emosa-ss-conv-exit"

        _make_emosa_search_state(
            tmp_path,
            run_id,
            num_trajectories=1,
        )

        child = Candidate(
            prompt_version="child_v1",
            parent_version="seed_v0",
            quality_score=0.85,
            cost=0.03,
            round_introduced=2,
            eval_status="complete",
        )
        _save_pending(run_id, [child], tmp_path)

        # Write a loop signal with action="exit"
        signal = LoopSignal(action="exit", reason="test exit")
        signal_path = tmp_path / run_id / "search" / "loop_signal.json"
        signal_path.parent.mkdir(parents=True, exist_ok=True)
        signal_path.write_text(signal.model_dump_json(), encoding="utf-8")

        summary = advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        assert summary.converged is True
        assert summary.convergence_reason == "review_exit"
        # Signal file should have been consumed (deleted)
        assert not signal_path.exists()

    def test_calibration_to_search_transition(self, tmp_path: Path) -> None:
        """Calibration-edge case: trajectory with current_solution=None gets unconditional first accept."""
        run_id = "emosa-ss-calib-edge"
        ideal = (0.9, 0.01)
        nadir = (0.5, 0.09)
        weight_vectors = compute_weight_vectors(1)
        wv = weight_vectors[0]

        # Trajectory has no current_solution — simulates calibration→search edge
        traj = TrajectoryState(
            trajectory_id=0,
            weight_vector=wv,
            current_solution=None,
            current_quality=None,
            current_cost=None,
            current_energy=None,
            temperature=0.001,  # Very low T -> Metropolis would reject almost anything
            alpha=0.95,
            step_count=1,
        )
        annealing = AnnealingState(
            t_min=0.0001,
            num_trajectories=1,
            trajectories=[traj],
            phase="search",
            total_evals=0,
            ideal_point=ideal,
            nadir_point=nadir,
        )
        _init_emosa_with_annealing(run_id=run_id, output_dir=tmp_path, annealing=annealing)

        # Candidate has no parent_version (unmatched -> round-robin assignment)
        child = Candidate(
            prompt_version="child_v1",
            parent_version=None,
            quality_score=0.75,
            cost=0.04,
            round_introduced=2,
            eval_status="complete",
        )
        _save_pending(run_id, [child], tmp_path)

        # Even with very low temperature, calibration edge always accepts
        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        updated = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(updated.algorithm_state)
        traj_after = pocket.trajectories[0]

        assert traj_after.current_solution == "child_v1"
        assert traj_after.acceptance_history[-1] is True

    def test_step_count_and_total_evals_incremented(self, tmp_path: Path) -> None:
        """Per-trajectory step_count and global total_evals are incremented after a steady-state advance."""
        run_id = "emosa-ss-counters"

        _make_emosa_search_state(
            tmp_path,
            run_id,
            num_trajectories=2,
            step_count=3,
            total_evals=10,
        )

        children = [
            Candidate(
                prompt_version="child_v1",
                parent_version="seed_v0",
                quality_score=0.85,
                cost=0.03,
                round_introduced=2,
                eval_status="complete",
            ),
            Candidate(
                prompt_version="child_v2",
                parent_version="seed_v1",
                quality_score=0.75,
                cost=0.05,
                round_introduced=2,
                eval_status="complete",
            ),
        ]
        _save_pending(run_id, children, tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        pocket = AnnealingState.model_validate(get_search_state(run_id, output_dir=tmp_path).algorithm_state)
        # Both trajectories had children → each step_count increments from 3 to 4
        for traj in pocket.trajectories:
            assert traj.step_count == 4, f"T{traj.trajectory_id} expected step_count=4, got {traj.step_count}"
        assert pocket.total_evals == 12  # 10 + 2 scored children

    def test_temperature_cooled_by_alpha(self, tmp_path: Path) -> None:
        """Per-trajectory temperature is adjusted after each steady-state step (adaptive cool).

        With acceptance_history=[True] (seed) + new accept, rate = 1.0 > target_high=0.6
        → fast cooling: T_new = T * alpha ** cooling_exp_fast.
        """
        run_id = "emosa-ss-temp-cool"
        initial_temp = 0.8
        alpha = 0.9

        _make_emosa_search_state(
            tmp_path,
            run_id,
            num_trajectories=1,
            temperature=initial_temp,
            alpha=alpha,
        )

        child = Candidate(
            prompt_version="child_v1",
            parent_version="seed_v0",
            quality_score=0.85,
            cost=0.03,
            round_introduced=2,
            eval_status="complete",
        )
        _save_pending(run_id, [child], tmp_path)

        summary = advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        # After update: history is [True, True] (seed accept + child accept), rate=1.0
        # rate > target_high=0.6 → T_new = T * alpha**1.5
        expected_temp = initial_temp * (alpha**1.5)
        pocket = AnnealingState.model_validate(get_search_state(run_id, output_dir=tmp_path).algorithm_state)
        traj_after = pocket.trajectories[0]
        assert traj_after.temperature == pytest.approx(expected_temp)
        assert summary.temperatures is not None
        assert summary.temperatures[0] == pytest.approx(expected_temp)

    def test_acceptance_rates_populated(self, tmp_path: Path) -> None:
        """acceptance_rates in RoundSummary contains per-trajectory rates."""
        run_id = "emosa-ss-acc-rates"

        _make_emosa_search_state(
            tmp_path,
            run_id,
            num_trajectories=2,
        )

        children = [
            Candidate(
                prompt_version="child_v1",
                parent_version="seed_v0",
                quality_score=0.85,
                cost=0.03,
                round_introduced=2,
                eval_status="complete",
            ),
            Candidate(
                prompt_version="child_v2",
                parent_version="seed_v1",
                quality_score=0.75,
                cost=0.05,
                round_introduced=2,
                eval_status="complete",
            ),
        ]
        _save_pending(run_id, children, tmp_path)

        summary = advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        assert summary.acceptance_rates is not None
        # Both trajectories had children, so both should have rates
        assert 0 in summary.acceptance_rates
        assert 1 in summary.acceptance_rates

    def test_archive_updated_with_non_dominated(self, tmp_path: Path) -> None:
        """Elite set is updated with non-dominated candidates from scored_pending."""
        run_id = "emosa-ss-archive"

        state = _make_emosa_search_state(
            tmp_path,
            run_id,
            num_trajectories=1,
        )
        # Elite set starts empty
        assert state.elite_set == []

        child = Candidate(
            prompt_version="child_v1",
            parent_version="seed_v0",
            quality_score=0.85,
            cost=0.03,
            round_introduced=2,
            eval_status="complete",
        )
        _save_pending(run_id, [child], tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        updated = get_search_state(run_id, output_dir=tmp_path)
        assert len(updated.elite_set) >= 1
        elite_versions = {c.prompt_version for c in updated.elite_set}
        assert "child_v1" in elite_versions

    def test_pending_cleared_after_advance(self, tmp_path: Path) -> None:
        """Pending candidates are cleared after a steady-state advance."""
        run_id = "emosa-ss-clear-pending"

        _make_emosa_search_state(tmp_path, run_id, num_trajectories=1)

        child = Candidate(
            prompt_version="child_v1",
            parent_version="seed_v0",
            quality_score=0.85,
            cost=0.03,
            round_introduced=2,
            eval_status="complete",
        )
        _save_pending(run_id, [child], tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        pending = _load_pending(run_id, tmp_path)
        assert pending == []

    def test_active_evals_non_empty_raises(self, tmp_path: Path) -> None:
        """advance_round_emosa raises ValueError if active_evals is non-empty."""
        run_id = "emosa-ss-active-evals"

        _make_emosa_search_state(tmp_path, run_id, num_trajectories=1)

        # Inject active_evals
        state = _load_state(run_id, tmp_path)
        updated = state.model_copy(update={"active_evals": ["child_v_inflight"]})
        _save_state(run_id, updated, tmp_path)

        child = Candidate(
            prompt_version="child_v1",
            parent_version="seed_v0",
            quality_score=0.85,
            cost=0.03,
            round_introduced=2,
            eval_status="complete",
        )
        _save_pending(run_id, [child], tmp_path)

        with pytest.raises(ValueError, match="active_evals"):
            advance_round_emosa(run_id=run_id, output_dir=tmp_path)

    def test_adaptive_cooling_per_trajectory_diverges(self, tmp_path: Path) -> None:
        """Trajectories with different acceptance histories cool at different rates.

        T0: acceptance_history=[True]*5 (100% accept > target_high=0.6) → cools faster.
        T1: acceptance_history=[False]*5 (0% accept < target_low=0.4)   → cools slower.

        After advance_round_emosa, T0.temperature < T1.temperature.
        """
        run_id = "emosa-adaptive-diverge"
        ideal = (0.9, 0.01)
        nadir = (0.5, 0.09)
        t_initial = 0.5
        alpha = 0.9
        weight_vectors = compute_weight_vectors(2)

        e0 = compute_tchebycheff_energy(0.85, 0.02, weight_vectors[0], ideal, nadir)
        e1 = compute_tchebycheff_energy(0.55, 0.08, weight_vectors[1], ideal, nadir)

        trajectories = [
            TrajectoryState(
                trajectory_id=0,
                weight_vector=weight_vectors[0],
                current_solution="seed_t0",
                current_quality=0.85,
                current_cost=0.02,
                current_energy=e0,
                acceptance_history=[True] * 5,  # rate = 1.0 > target_high → fast cooling
                temperature=t_initial,
                alpha=alpha,
                step_count=5,
            ),
            TrajectoryState(
                trajectory_id=1,
                weight_vector=weight_vectors[1],
                current_solution="seed_t1",
                current_quality=0.55,
                current_cost=0.08,
                current_energy=e1,
                acceptance_history=[False] * 5,  # rate = 0.0 < target_low → slow cooling
                temperature=t_initial,
                alpha=alpha,
                step_count=5,
            ),
        ]
        annealing = AnnealingState(
            t_min=0.001,
            num_trajectories=2,
            trajectories=trajectories,
            phase="search",
            total_evals=10,
            ideal_point=ideal,
            nadir_point=nadir,
        )
        _init_emosa_with_annealing(run_id=run_id, output_dir=tmp_path, annealing=annealing)

        # Give each trajectory one child so both participate in Metropolis
        children = [
            Candidate(
                prompt_version="child_t0",
                parent_version="seed_t0",
                quality_score=0.86,
                cost=0.02,
                round_introduced=2,
                eval_status="complete",
            ),
            Candidate(
                prompt_version="child_t1",
                parent_version="seed_t1",
                quality_score=0.56,
                cost=0.07,
                round_introduced=2,
                eval_status="complete",
            ),
        ]
        _save_pending(run_id, children, tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        pocket = AnnealingState.model_validate(get_search_state(run_id, output_dir=tmp_path).algorithm_state)
        t0_after = next(t for t in pocket.trajectories if t.trajectory_id == 0)
        t1_after = next(t for t in pocket.trajectories if t.trajectory_id == 1)

        # T0 had all-True history → rate > target_high → cooled faster (alpha**1.5)
        # T1 had all-False history → rate < target_low → cooled slower (alpha**0.5)
        # After the round, T0.temperature < T1.temperature
        assert t0_after.temperature < t1_after.temperature, (
            f"Expected T0 ({t0_after.temperature:.4f}) < T1 ({t1_after.temperature:.4f}) "
            f"(T0 had all-True history, T1 had all-False)"
        )


# ---------------------------------------------------------------------------
# C.3: round_report persistence tests
# ---------------------------------------------------------------------------


class TestRoundReportPersistenceEmosa:
    """_advance_emosa_search and _calibration_complete must write round_N.json."""

    def _make_report(self, version: str) -> dict:
        return {
            "metrics": {"accuracy": 0.8},
            "errors": [],
            "diff": None,
            "report_path": f"/fake/{version}/report.json",
            "results_path": f"/fake/{version}/results.jsonl",
        }

    def _write_report(self, tmp_path: Path, run_id: str, version: str) -> None:
        eval_dir = tmp_path / run_id / "eval" / version
        eval_dir.mkdir(parents=True, exist_ok=True)
        (eval_dir / "report.json").write_text(json.dumps(self._make_report(version)), encoding="utf-8")

    def test_advance_emosa_search_writes_round_report(self, tmp_path: Path) -> None:
        """_advance_emosa_search writes round_reports/round_2.json with both candidates."""
        run_id = "emosa-rr-search"
        ideal = (0.9, 0.01)
        nadir = (0.5, 0.09)
        weight_vectors = compute_weight_vectors(2)

        trajectories = [
            TrajectoryState(
                trajectory_id=i,
                weight_vector=weight_vectors[i],
                current_solution=f"seed_v{i}",
                current_quality=0.7 - i * 0.05,
                current_cost=0.05 + i * 0.02,
                current_energy=compute_tchebycheff_energy(
                    0.7 - i * 0.05, 0.05 + i * 0.02, weight_vectors[i], ideal, nadir
                ),
                acceptance_history=[True],
                temperature=10.0,
                alpha=0.95,
                step_count=1,
            )
            for i in range(2)
        ]
        annealing = AnnealingState(
            t_min=0.01,
            num_trajectories=2,
            trajectories=trajectories,
            phase="search",
            total_evals=2,
            ideal_point=ideal,
            nadir_point=nadir,
        )
        state = _init_emosa_with_annealing(run_id=run_id, output_dir=tmp_path, annealing=annealing)
        # round starts at 0; advance_round uses state.round as the key before incrementing
        assert state.round == 0

        children = [
            Candidate(
                prompt_version="child_a",
                parent_version="seed_v0",
                quality_score=0.82,
                cost=0.03,
                round_introduced=2,
                eval_status="complete",
            ),
            Candidate(
                prompt_version="child_b",
                parent_version="seed_v1",
                quality_score=0.68,
                cost=0.06,
                round_introduced=2,
                eval_status="complete",
            ),
        ]
        _save_pending(run_id, children, tmp_path)

        # Write eval reports for both candidates
        for v in ("child_a", "child_b"):
            self._write_report(tmp_path, run_id, v)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        round_report_path = tmp_path / run_id / "search" / "round_reports" / "round_0.json"
        assert round_report_path.exists(), "round_0.json must be written by _advance_emosa_search"
        data = json.loads(round_report_path.read_text(encoding="utf-8"))
        assert "child_a" in data, "round_0.json must contain child_a"
        assert "child_b" in data, "round_0.json must contain child_b"


# ---------------------------------------------------------------------------
# C.4: trajectory_history snapshot persistence
# ---------------------------------------------------------------------------


class TestTrajectorySnapshotPersistence:
    """trajectory_history is populated by _calibration_complete and _advance_emosa_search."""

    def test_calibration_complete_adds_snapshot(self, tmp_path: Path) -> None:
        """After _calibration_complete, trajectory_history has 1 entry with correct round and currents."""
        run_id = "traj-snap-calib"
        num_traj = 5
        wvs = compute_weight_vectors(num_traj)
        trajs = [TrajectoryState(trajectory_id=i, weight_vector=wvs[i]) for i in range(num_traj)]
        annealing = AnnealingState(
            num_trajectories=num_traj,
            trajectories=trajs,
            phase="calibration",
            total_evals=0,
        )
        state = init_search_state(backend="test", run_id=run_id, output_dir=tmp_path)
        patched = state.model_copy(
            update={
                "algorithm_state": json.loads(annealing.model_dump_json()),
                "loop_phase": "review",
                "round": 0,
            }
        )
        _save_state(run_id, patched, tmp_path)

        # Write K cold-start candidates as pending
        versions = [f"cold_v{i}" for i in range(num_traj)]
        pending = [
            Candidate(
                prompt_version=versions[i],
                parent_version=None,
                quality_score=0.7 + i * 0.05,
                cost=0.09 - i * 0.01,
                round_introduced=0,
                eval_status="complete",
            )
            for i in range(num_traj)
        ]
        _save_pending(run_id, pending, tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        updated = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(updated.algorithm_state)

        # Exactly 1 snapshot after calibration
        assert len(pocket.trajectory_history) == 1
        snap = pocket.trajectory_history[0]
        assert isinstance(snap, TrajectorySnapshot)
        assert snap.round == 1  # state.round was 0, advanced to 1
        # Each trajectory seeded with its cold_v{i}
        assert len(snap.currents) == num_traj
        for i in range(num_traj):
            assert snap.currents[i] == f"cold_v{i}"

    def test_advance_emosa_search_adds_snapshot(self, tmp_path: Path) -> None:
        """After calibration + 1 steady-state advance, trajectory_history has 2 entries."""
        run_id = "traj-snap-search"
        num_traj = 5
        wvs = compute_weight_vectors(num_traj)
        trajs = [TrajectoryState(trajectory_id=i, weight_vector=wvs[i]) for i in range(num_traj)]
        annealing = AnnealingState(
            num_trajectories=num_traj,
            trajectories=trajs,
            phase="calibration",
            total_evals=0,
        )
        state = init_search_state(backend="test", run_id=run_id, output_dir=tmp_path)
        patched = state.model_copy(
            update={
                "algorithm_state": json.loads(annealing.model_dump_json()),
                "loop_phase": "review",
                "round": 0,
            }
        )
        _save_state(run_id, patched, tmp_path)

        # Calibration round: K cold-start candidates
        cold_versions = [f"cold_v{i}" for i in range(num_traj)]
        cold_pending = [
            Candidate(
                prompt_version=cold_versions[i],
                parent_version=None,
                quality_score=0.7 + i * 0.05,
                cost=0.09 - i * 0.01,
                round_introduced=0,
                eval_status="complete",
            )
            for i in range(num_traj)
        ]
        _save_pending(run_id, cold_pending, tmp_path)
        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        # Steady-state round: each trajectory generates one child
        after_calib = get_search_state(run_id, output_dir=tmp_path)
        pocket_after_calib = AnnealingState.model_validate(after_calib.algorithm_state)
        child_versions = [f"child_v{i}" for i in range(num_traj)]
        child_pending = [
            Candidate(
                prompt_version=child_versions[i],
                parent_version=pocket_after_calib.trajectories[i].current_solution,
                quality_score=0.75 + i * 0.02,
                cost=0.08 - i * 0.01,
                round_introduced=2,
                eval_status="complete",
            )
            for i in range(num_traj)
        ]
        _save_pending(run_id, child_pending, tmp_path)
        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        updated = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(updated.algorithm_state)

        # 2 snapshots total: round 1 (calibration) and round 2 (steady-state)
        assert len(pocket.trajectory_history) == 2

        snap1 = pocket.trajectory_history[0]
        assert snap1.round == 1
        assert set(snap1.currents.values()) == set(cold_versions)

        snap2 = pocket.trajectory_history[1]
        assert snap2.round == 2
        # All currents are strings (either child_v* or cold_v* if rejected/replaced)
        assert all(isinstance(v, str) for v in snap2.currents.values())
        assert len(snap2.currents) == num_traj


# ---------------------------------------------------------------------------
# C.3: round_report persistence tests
# ---------------------------------------------------------------------------


class TestRoundReportPersistenceEmosa:
    """_advance_emosa_search and _calibration_complete must write round_N.json."""

    def _make_report(self, version: str) -> dict:
        return {
            "metrics": {"accuracy": 0.8},
            "errors": [],
            "diff": None,
            "report_path": f"/fake/{version}/report.json",
            "results_path": f"/fake/{version}/results.jsonl",
        }

    def _write_report(self, tmp_path: Path, run_id: str, version: str) -> None:
        eval_dir = tmp_path / run_id / "eval" / version
        eval_dir.mkdir(parents=True, exist_ok=True)
        (eval_dir / "report.json").write_text(json.dumps(self._make_report(version)), encoding="utf-8")

    def test_advance_emosa_search_writes_round_report(self, tmp_path: Path) -> None:
        """_advance_emosa_search writes round_reports/round_2.json with both candidates."""
        run_id = "emosa-rr-search"
        ideal = (0.9, 0.01)
        nadir = (0.5, 0.09)
        weight_vectors = compute_weight_vectors(2)

        trajectories = [
            TrajectoryState(
                trajectory_id=i,
                weight_vector=weight_vectors[i],
                current_solution=f"seed_v{i}",
                current_quality=0.7 - i * 0.05,
                current_cost=0.05 + i * 0.02,
                current_energy=compute_tchebycheff_energy(
                    0.7 - i * 0.05, 0.05 + i * 0.02, weight_vectors[i], ideal, nadir
                ),
                acceptance_history=[True],
                temperature=10.0,
                alpha=0.95,
                step_count=1,
            )
            for i in range(2)
        ]
        annealing = AnnealingState(
            t_min=0.01,
            num_trajectories=2,
            trajectories=trajectories,
            phase="search",
            total_evals=2,
            ideal_point=ideal,
            nadir_point=nadir,
        )
        state = _init_emosa_with_annealing(run_id=run_id, output_dir=tmp_path, annealing=annealing)
        # round starts at 0; advance_round uses state.round as the key before incrementing
        assert state.round == 0

        children = [
            Candidate(
                prompt_version="child_a",
                parent_version="seed_v0",
                quality_score=0.82,
                cost=0.03,
                round_introduced=2,
                eval_status="complete",
            ),
            Candidate(
                prompt_version="child_b",
                parent_version="seed_v1",
                quality_score=0.68,
                cost=0.06,
                round_introduced=2,
                eval_status="complete",
            ),
        ]
        _save_pending(run_id, children, tmp_path)

        # Write eval reports for both candidates
        for v in ("child_a", "child_b"):
            self._write_report(tmp_path, run_id, v)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        round_report_path = tmp_path / run_id / "search" / "round_reports" / "round_0.json"
        assert round_report_path.exists(), "round_0.json must be written by _advance_emosa_search"
        data = json.loads(round_report_path.read_text(encoding="utf-8"))
        assert "child_a" in data, "round_0.json must contain child_a"
        assert "child_b" in data, "round_0.json must contain child_b"

    def test_calibration_complete_writes_round_report(self, tmp_path: Path) -> None:
        """_calibration_complete writes round_reports/round_0.json with calibration candidates."""
        run_id = "emosa-rr-calib"
        num_traj = 2
        weight_vectors = compute_weight_vectors(num_traj)
        trajectories = [TrajectoryState(trajectory_id=i, weight_vector=weight_vectors[i]) for i in range(num_traj)]
        annealing = AnnealingState(
            num_trajectories=num_traj,
            trajectories=trajectories,
            phase="calibration",
            total_evals=0,
        )
        state = init_search_state(backend="test", run_id=run_id, output_dir=tmp_path)
        patched = state.model_copy(
            update={
                "algorithm_state": json.loads(annealing.model_dump_json()),
                "loop_phase": "calibration",
            }
        )
        _save_state(run_id, patched, tmp_path)

        calib_candidates = [
            Candidate(
                prompt_version=f"seed_v{i}",
                parent_version=None,
                quality_score=0.5 + i * 0.1,
                cost=0.1 + i * 0.05,
                round_introduced=1,
                eval_status="complete",
            )
            for i in range(num_traj)
        ]
        _save_pending(run_id, calib_candidates, tmp_path)

        # Write eval reports for calibration candidates
        for c in calib_candidates:
            self._write_report(tmp_path, run_id, c.prompt_version)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        # _calibration_complete uses state.round (which is 0 before increment) as key
        round_report_path = tmp_path / run_id / "search" / "round_reports" / "round_0.json"
        assert round_report_path.exists(), "round_0.json must be written by _calibration_complete"
        data = json.loads(round_report_path.read_text(encoding="utf-8"))
        assert "seed_v0" in data, "round_0.json must contain seed_v0"
        assert "seed_v1" in data, "round_0.json must contain seed_v1"
