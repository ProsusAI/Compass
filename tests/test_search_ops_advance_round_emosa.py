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
    """Build an AnnealingState in search phase with optionally seeded trajectories."""
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
            )
        else:
            traj = TrajectoryState(trajectory_id=i, weight_vector=weight_vectors[i])
        trajectories.append(traj)

    return AnnealingState(
        temperature=temperature,
        alpha=alpha,
        t_min=t_min,
        num_trajectories=num_trajectories,
        trajectories=trajectories,
        phase=phase,  # type: ignore[arg-type]
        step_count=step_count,
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
    """Init an emosa SearchState already in search phase with seeded trajectories."""
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
        algorithm="emosa",
        algorithm_state=json.loads(annealing.model_dump_json()),
    )
    return state


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
        )
        annealing = AnnealingState(
            temperature=10.0,  # Very high T -> near-always accept
            alpha=0.95,
            t_min=0.01,
            num_trajectories=1,
            trajectories=[traj],
            phase="search",
            step_count=1,
            total_evals=1,
            ideal_point=ideal,
            nadir_point=nadir,
        )
        init_search_state(
            backend="test",
            run_id=run_id,
            output_dir=tmp_path,
            algorithm="emosa",
            algorithm_state=json.loads(annealing.model_dump_json()),
        )
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
        )
        annealing = AnnealingState(
            temperature=100.0,  # Very high T -> accept all
            alpha=0.95,
            t_min=0.01,
            num_trajectories=1,
            trajectories=[traj],
            phase="search",
            step_count=1,
            total_evals=1,
            ideal_point=ideal,
            nadir_point=nadir,
        )
        init_search_state(
            backend="test",
            run_id=run_id,
            output_dir=tmp_path,
            algorithm="emosa",
            algorithm_state=json.loads(annealing.model_dump_json()),
        )

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
                cost=0.02,           # Best cost
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
            c.prompt_version: compute_tchebycheff_energy(
                c.quality_score, c.cost, wv, new_ideal_point, new_nadir_point
            )
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
        )
        annealing = AnnealingState(
            temperature=1.0,
            alpha=0.95,
            t_min=0.01,
            num_trajectories=1,
            trajectories=[traj],
            phase="search",
            step_count=1,
            total_evals=1,
            ideal_point=narrow_ideal,
            nadir_point=narrow_nadir,
        )
        init_search_state(
            backend="test",
            run_id=run_id,
            output_dir=tmp_path,
            algorithm="emosa",
            algorithm_state=json.loads(annealing.model_dump_json()),
        )

        # New child with significantly better quality — expands ideal/nadir
        child = Candidate(
            prompt_version="child_v1",
            parent_version="seed_v0",
            quality_score=0.90,  # Much better quality
            cost=0.02,           # Much lower cost
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
            trajectories.append(TrajectoryState(
                trajectory_id=i,
                weight_vector=weight_vectors[i],
                current_solution=f"seed_v{i}",
                current_quality=q,
                current_cost=c,
                current_energy=e,
                acceptance_history=[True],
            ))

        annealing = AnnealingState(
            temperature=100.0,  # Very high T -> near-always accept
            alpha=0.95,
            t_min=0.01,
            num_trajectories=num_traj,
            trajectories=trajectories,
            phase="search",
            step_count=1,
            total_evals=num_traj,
            ideal_point=ideal,
            nadir_point=nadir,
            neighborhood_size=4,
        )
        init_search_state(
            backend="test",
            run_id=run_id,
            output_dir=tmp_path,
            algorithm="emosa",
            algorithm_state=json.loads(annealing.model_dump_json()),
        )

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
            t for t in pocket.trajectories
            if t.trajectory_id in neighbor_ids and t.current_solution == "child_v1"
        ]
        assert len(replaced) > 0, "Expected at least one neighbor to be replaced"

    def test_convergence_temperature_floor(self, tmp_path: Path) -> None:
        """Convergence via temperature_floor when T * alpha < t_min."""
        run_id = "emosa-ss-conv-temp"
        t_min = 0.1
        alpha = 0.5
        temperature = 0.19  # After one step: 0.19 * 0.5 = 0.095 < t_min=0.1

        _make_emosa_search_state(
            tmp_path, run_id,
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

        pocket = AnnealingState.model_validate(
            get_search_state(run_id, output_dir=tmp_path).algorithm_state
        )
        assert pocket.phase == "converged"

    def test_convergence_eval_budget(self, tmp_path: Path) -> None:
        """Convergence via eval_budget when total_evals >= max_evals after step."""
        run_id = "emosa-ss-conv-evals"
        max_evals = 6

        _make_emosa_search_state(
            tmp_path, run_id,
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
            tmp_path, run_id,
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
        )
        annealing = AnnealingState(
            temperature=0.001,  # Very low T -> Metropolis would reject almost anything
            alpha=0.95,
            t_min=0.0001,
            num_trajectories=1,
            trajectories=[traj],
            phase="search",
            step_count=1,
            total_evals=0,
            ideal_point=ideal,
            nadir_point=nadir,
        )
        init_search_state(
            backend="test",
            run_id=run_id,
            output_dir=tmp_path,
            algorithm="emosa",
            algorithm_state=json.loads(annealing.model_dump_json()),
        )

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
        """step_count and total_evals are incremented after a steady-state advance."""
        run_id = "emosa-ss-counters"

        _make_emosa_search_state(
            tmp_path, run_id,
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

        pocket = AnnealingState.model_validate(
            get_search_state(run_id, output_dir=tmp_path).algorithm_state
        )
        assert pocket.step_count == 4
        assert pocket.total_evals == 12  # 10 + 2 scored children

    def test_temperature_cooled_by_alpha(self, tmp_path: Path) -> None:
        """Temperature is multiplied by alpha after each steady-state step."""
        run_id = "emosa-ss-temp-cool"
        initial_temp = 0.8
        alpha = 0.9

        _make_emosa_search_state(
            tmp_path, run_id,
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

        assert summary.temperature == pytest.approx(initial_temp * alpha)

        pocket = AnnealingState.model_validate(
            get_search_state(run_id, output_dir=tmp_path).algorithm_state
        )
        assert pocket.temperature == pytest.approx(initial_temp * alpha)

    def test_acceptance_rates_populated(self, tmp_path: Path) -> None:
        """acceptance_rates in RoundSummary contains per-trajectory rates."""
        run_id = "emosa-ss-acc-rates"

        _make_emosa_search_state(
            tmp_path, run_id,
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
            tmp_path, run_id,
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
