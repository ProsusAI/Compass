"""Unit tests for odysseus.agents.prompt_builder.annealing."""

from __future__ import annotations

import math
import random

import pytest

from odysseus.agents.prompt_builder.annealing import (
    AnnealingState,
    TrajectoryState,
    adaptive_cool,
    compute_asf_energy,
    compute_cooling_rate,
    compute_neighborhood,
    compute_tchebycheff_energy,
    compute_weight_vectors,
    metropolis_accept,
    normalize_objectives,
    replace_if_better,
    update_archive,
)
from odysseus.agents.prompt_builder.search import Candidate

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_candidate(
    version: str,
    quality: float,
    cost: float,
    round_num: int = 1,
) -> Candidate:
    return Candidate(
        prompt_version=version,
        parent_version=None,
        quality_score=quality,
        cost=cost,
        round_introduced=round_num,
        eval_status="complete",
    )


# ---------------------------------------------------------------------------
# TestNormalizeObjectives
# ---------------------------------------------------------------------------


class TestNormalizeObjectives:
    IDEAL = (0.9, -0.2)
    NADIR = (0.5, 0.1)

    def test_normal_case(self):
        # quality=0.8 → (0.9 - 0.8) / 0.4 = 0.25
        # cost=-0.1 → (-0.1 - (-0.2)) / 0.3 = 0.1/0.3 ≈ 0.333
        norm_q, norm_c = normalize_objectives(0.8, -0.1, self.IDEAL, self.NADIR)
        assert math.isclose(norm_q, 0.25, abs_tol=1e-9)
        assert math.isclose(norm_c, 1 / 3, abs_tol=1e-9)

    def test_at_ideal_point(self):
        norm_q, norm_c = normalize_objectives(0.9, -0.2, self.IDEAL, self.NADIR)
        assert norm_q == pytest.approx(0.0, abs=1e-9)
        assert norm_c == pytest.approx(0.0, abs=1e-9)

    def test_at_nadir_point(self):
        norm_q, norm_c = normalize_objectives(0.5, 0.1, self.IDEAL, self.NADIR)
        assert norm_q == pytest.approx(1.0, abs=1e-9)
        assert norm_c == pytest.approx(1.0, abs=1e-9)

    def test_zero_range_quality(self):
        # ideal_q == nadir_q → zero range → norm_q = 0.0
        norm_q, norm_c = normalize_objectives(0.7, 0.0, (0.7, -0.2), (0.7, 0.1))
        assert norm_q == 0.0
        assert 0.0 <= norm_c <= 1.0

    def test_zero_range_cost(self):
        # ideal_c == nadir_c → zero range → norm_c = 0.0
        norm_q, norm_c = normalize_objectives(0.7, 0.05, (0.9, 0.05), (0.5, 0.05))
        assert norm_c == 0.0
        assert 0.0 <= norm_q <= 1.0

    def test_clamped_below_ideal(self):
        # quality above ideal → would be negative → clamped to 0.0
        norm_q, norm_c = normalize_objectives(1.0, -0.2, self.IDEAL, self.NADIR)
        assert norm_q == 0.0

    def test_clamped_below_nadir_cost(self):
        # cost far below nadir → would be negative → clamped to 0.0
        norm_q, norm_c = normalize_objectives(0.9, -1.0, self.IDEAL, self.NADIR)
        assert norm_c == 0.0

    def test_clamped_above_nadir(self):
        # quality well below nadir → would exceed 1.0 → clamped to 1.0
        norm_q, norm_c = normalize_objectives(0.0, -0.2, self.IDEAL, self.NADIR)
        assert norm_q == 1.0

    def test_output_always_in_0_1(self):
        for q, c in [(0.95, 0.5), (0.2, -0.5), (0.7, 0.05)]:
            nq, nc = normalize_objectives(q, c, self.IDEAL, self.NADIR)
            assert 0.0 <= nq <= 1.0
            assert 0.0 <= nc <= 1.0


# ---------------------------------------------------------------------------
# TestTchebycheffEnergy
# ---------------------------------------------------------------------------


class TestTchebycheffEnergy:
    IDEAL = (0.9, -0.2)
    NADIR = (0.5, 0.1)

    def test_at_ideal_point(self):
        energy = compute_tchebycheff_energy(0.9, -0.2, (0.5, 0.5), self.IDEAL, self.NADIR)
        assert energy == pytest.approx(0.0, abs=1e-9)

    def test_quality_focused_weight_dominates(self):
        # norm_q = 0.5, norm_c = 0.0 → max(0.8*0.5, 0.2*0.0) = 0.4
        energy = compute_tchebycheff_energy(0.7, -0.2, (0.8, 0.2), self.IDEAL, self.NADIR)
        norm_q, _ = normalize_objectives(0.7, -0.2, self.IDEAL, self.NADIR)
        assert energy == pytest.approx(0.8 * norm_q, abs=1e-9)

    def test_cost_focused_weight_dominates(self):
        # norm_q = 0.0, norm_c = 0.5 → max(0.2*0.0, 0.8*0.5) = 0.4
        energy = compute_tchebycheff_energy(0.9, -0.05, (0.2, 0.8), self.IDEAL, self.NADIR)
        _, norm_c = normalize_objectives(0.9, -0.05, self.IDEAL, self.NADIR)
        assert energy == pytest.approx(0.8 * norm_c, abs=1e-9)

    def test_equal_weights(self):
        energy = compute_tchebycheff_energy(0.7, 0.0, (0.5, 0.5), self.IDEAL, self.NADIR)
        norm_q, norm_c = normalize_objectives(0.7, 0.0, self.IDEAL, self.NADIR)
        assert energy == pytest.approx(max(0.5 * norm_q, 0.5 * norm_c), abs=1e-9)

    def test_nadir_point_energy(self):
        # At nadir, norm_q=1, norm_c=1 → energy = max(lq*1, lc*1) = max(lq, lc)
        energy = compute_tchebycheff_energy(0.5, 0.1, (0.5, 0.5), self.IDEAL, self.NADIR)
        assert energy == pytest.approx(0.5, abs=1e-9)

    def test_energy_non_negative(self):
        for q, c, wq, wc in [(0.6, 0.05, 0.3, 0.7), (0.8, -0.1, 0.9, 0.1)]:
            assert compute_tchebycheff_energy(q, c, (wq, wc), self.IDEAL, self.NADIR) >= 0.0


# ---------------------------------------------------------------------------
# TestASFEnergy
# ---------------------------------------------------------------------------


class TestASFEnergy:
    IDEAL = (1.0, 0.0)
    NADIR = (0.0, 1.0)

    def test_typical_case(self):
        # ref=(0.8, 0.2), quality=0.6, cost=0.4, weight=(0.5,0.5)
        # gap_q = (0.8-0.6)/(0.8-0.0) = 0.2/0.8 = 0.25
        # gap_c = (0.4-0.2)/(1.0-0.2) = 0.2/0.8 = 0.25
        # E = max(0.5*0.25, 0.5*0.25) + 1e-3*(0.5*0.25 + 0.5*0.25)
        #   = 0.125 + 1e-3*0.25 = 0.12525
        energy = compute_asf_energy(0.6, 0.4, (0.5, 0.5), (0.8, 0.2), self.IDEAL, self.NADIR)
        assert energy == pytest.approx(0.125 + 1e-3 * 0.25, abs=1e-9)

    def test_augmentation_contributes_when_both_gaps_positive(self):
        # Without rho=0, energy = max(term_q, term_c)
        # With rho>0, energy = max + rho*(term_q+term_c) > max
        energy_no_rho = compute_asf_energy(0.6, 0.4, (0.5, 0.5), (0.8, 0.2), self.IDEAL, self.NADIR, rho=0.0)
        energy_with_rho = compute_asf_energy(0.6, 0.4, (0.5, 0.5), (0.8, 0.2), self.IDEAL, self.NADIR, rho=1e-3)
        assert energy_with_rho > energy_no_rho

    def test_none_reference_falls_back_to_tchebycheff_norm(self):
        # Both refs None → pure Tchebycheff-style normalized terms
        energy_asf = compute_asf_energy(0.7, 0.3, (0.5, 0.5), (None, None), self.IDEAL, self.NADIR, rho=0.0)
        energy_tch = compute_tchebycheff_energy(0.7, 0.3, (0.5, 0.5), self.IDEAL, self.NADIR)
        assert energy_asf == pytest.approx(energy_tch, abs=1e-9)

    def test_quality_ref_none_cost_ref_set(self):
        # quality axis → Tchebycheff fallback; cost axis → ASF gap
        energy = compute_asf_energy(0.7, 0.3, (0.5, 0.5), (None, 0.2), self.IDEAL, self.NADIR, rho=0.0)
        norm_q, _ = normalize_objectives(0.7, 0.3, self.IDEAL, self.NADIR)
        term_q = 0.5 * norm_q
        # gap_c = (0.3 - 0.2) / (1.0 - 0.2) = 0.1/0.8 = 0.125
        term_c = 0.5 * (0.1 / 0.8)
        assert energy == pytest.approx(max(term_q, term_c), abs=1e-9)

    def test_zero_denominator_fallback_quality(self):
        # ref_q == nadir_q → denom_q = 0 → fallback to ideal-nadir span
        # ideal_q - nadir_q = 1.0 - 0.0 = 1.0
        # gap_q = (0.0 - 0.7) / 1.0 = -0.7
        energy = compute_asf_energy(0.7, 0.5, (0.5, 0.5), (0.0, 0.5), self.IDEAL, self.NADIR, rho=0.0)
        term_q = 0.5 * ((0.0 - 0.7) / 1.0)
        term_c = 0.5 * ((0.5 - 0.5) / (1.0 - 0.5))
        assert energy == pytest.approx(max(term_q, term_c), abs=1e-9)

    def test_monotone_higher_cost_worsens_energy(self):
        # Higher actual cost → larger gap_c → higher energy
        ref = (0.8, 0.2)
        e1 = compute_asf_energy(0.7, 0.3, (0.5, 0.5), ref, self.IDEAL, self.NADIR)
        e2 = compute_asf_energy(0.7, 0.5, (0.5, 0.5), ref, self.IDEAL, self.NADIR)
        assert e2 > e1

    def test_solution_exceeds_reference_negative_gap(self):
        # quality > ref_q → negative gap_q → term_q negative; only cost matters
        # gap_q = (0.5 - 0.9) / (0.5 - 0.0) = -0.4/0.5 = -0.8 → term_q = 0.5*-0.8 = -0.4
        # gap_c = (0.1 - 0.6) / (1.0 - 0.6) = -0.5/0.4 = -1.25 → term_c = 0.5*-1.25 = -0.625
        energy = compute_asf_energy(0.9, 0.1, (0.5, 0.5), (0.5, 0.6), self.IDEAL, self.NADIR)
        term_q = 0.5 * ((0.5 - 0.9) / (0.5 - 0.0))
        term_c = 0.5 * ((0.1 - 0.6) / (1.0 - 0.6))
        expected = max(term_q, term_c) + 1e-3 * (term_q + term_c)
        assert energy == pytest.approx(expected, abs=1e-9)


# ---------------------------------------------------------------------------
# TestMetropolisAccept
# ---------------------------------------------------------------------------


class TestMetropolisAccept:
    def test_improvement_always_accepted(self):
        for delta_e in [-1.0, -0.001, -100.0]:
            assert metropolis_accept(delta_e, 1.0) is True

    def test_zero_delta_e_accepted(self):
        assert metropolis_accept(0.0, 1.0) is True

    def test_worsening_high_temperature_mostly_accepted(self):
        rng = random.Random(42)
        accepted = sum(metropolis_accept(0.01, 1000.0, rng=rng) for _ in range(100))
        assert accepted >= 90  # near certainty at very high T

    def test_worsening_low_temperature_mostly_rejected(self):
        rng = random.Random(42)
        accepted = sum(metropolis_accept(1.0, 0.001, rng=rng) for _ in range(100))
        assert accepted <= 5  # near certainty of rejection at very low T

    def test_seeded_rng_deterministic(self):
        # Same seed → same sequence of accept/reject decisions
        delta_e, temp = 0.5, 0.5
        results_a = [metropolis_accept(delta_e, temp, rng=random.Random(0)) for _ in range(10)]
        results_b = [metropolis_accept(delta_e, temp, rng=random.Random(0)) for _ in range(10)]
        assert results_a == results_b

    def test_probability_matches_formula(self):
        delta_e = 0.5
        temperature = 0.5
        expected_prob = math.exp(-delta_e / temperature)

        rng = random.Random(0)
        trials = 10_000
        accepted = sum(metropolis_accept(delta_e, temperature, rng=rng) for _ in range(trials))
        empirical = accepted / trials
        assert abs(empirical - expected_prob) < 0.02

    def test_temperature_zero_limit_rejects_worsening(self):
        # As T→0, exp(-Δ/T) → 0 for Δ>0, so very low T should almost always reject
        rng = random.Random(42)
        accepted = sum(metropolis_accept(0.5, 1e-10, rng=rng) for _ in range(100))
        assert accepted == 0


# ---------------------------------------------------------------------------
# TestWeightVectors
# ---------------------------------------------------------------------------


class TestWeightVectors:
    def test_k1(self):
        vecs = compute_weight_vectors(1)
        assert vecs == [(0.5, 0.5)]

    def test_k2(self):
        vecs = compute_weight_vectors(2)
        assert len(vecs) == 2
        for lq, lc in vecs:
            assert math.isclose(lq + lc, 1.0, abs_tol=1e-9)

    def test_k3(self):
        vecs = compute_weight_vectors(3)
        assert len(vecs) == 3
        for lq, lc in vecs:
            assert math.isclose(lq + lc, 1.0, abs_tol=1e-9)
            assert 0.1 <= lq <= 0.9

    def test_k5(self):
        vecs = compute_weight_vectors(5)
        assert len(vecs) == 5
        # Quality-focused first
        assert vecs[0][0] > vecs[-1][0]
        for lq, lc in vecs:
            assert math.isclose(lq + lc, 1.0, abs_tol=1e-9)
            assert 0.1 <= lq <= 0.9

    def test_k5_endpoints(self):
        vecs = compute_weight_vectors(5)
        assert math.isclose(vecs[0][0], 0.9, abs_tol=1e-9)
        assert math.isclose(vecs[-1][0], 0.1, abs_tol=1e-9)

    def test_sum_to_one(self):
        for k in [1, 2, 3, 4, 6, 10]:
            for lq, lc in compute_weight_vectors(k):
                assert math.isclose(lq + lc, 1.0, abs_tol=1e-9)

    def test_monotone_decreasing_lq(self):
        vecs = compute_weight_vectors(5)
        lqs = [v[0] for v in vecs]
        assert lqs == sorted(lqs, reverse=True)

    def test_evenly_spaced_k3(self):
        vecs = compute_weight_vectors(3)
        lqs = [v[0] for v in vecs]
        assert math.isclose(lqs[0], 0.9, abs_tol=1e-9)
        assert math.isclose(lqs[1], 0.5, abs_tol=1e-9)
        assert math.isclose(lqs[2], 0.1, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# TestCoolingRate
# ---------------------------------------------------------------------------


class TestCoolingRate:
    def test_standard_case(self):
        alpha = compute_cooling_rate(1.0, 0.01, 10)
        assert math.isclose(1.0 * alpha**10, 0.01, rel_tol=1e-6)

    def test_large_budget_gives_larger_alpha(self):
        alpha_small = compute_cooling_rate(1.0, 0.01, 10)
        alpha_large = compute_cooling_rate(1.0, 0.01, 50)
        assert alpha_large > alpha_small

    def test_clamped_below(self):
        # Extremely aggressive cooling → clamp at 0.5
        alpha = compute_cooling_rate(1.0, 1e-100, 1)
        assert alpha >= 0.5

    def test_clamped_above(self):
        # Very slow cooling → clamp at 0.999
        alpha = compute_cooling_rate(1.0, 0.9999, 1_000_000)
        assert alpha <= 0.999

    def test_max_steps_zero_raises(self):
        with pytest.raises(ValueError, match="max_steps must be >= 1"):
            compute_cooling_rate(1.0, 0.01, 0)

    def test_result_in_valid_range(self):
        for t0, t_min, steps in [(1.0, 0.01, 20), (2.0, 0.1, 5), (0.5, 0.05, 100)]:
            alpha = compute_cooling_rate(t0, t_min, steps)
            assert 0.5 <= alpha <= 0.999


# ---------------------------------------------------------------------------
# TestUpdateArchive
# ---------------------------------------------------------------------------


class TestUpdateArchive:
    def test_dominated_candidate_not_added(self):
        archive = [_make_candidate("v1", 0.9, 0.1)]
        new = _make_candidate("new", 0.8, 0.2)  # dominated by v1
        result, added = update_archive(archive, new)
        assert not added
        assert len(result) == 1
        assert result[0].prompt_version == "v1"

    def test_dominant_candidate_removes_dominated(self):
        archive = [
            _make_candidate("v1", 0.7, 0.3),
            _make_candidate("v2", 0.6, 0.5),
        ]
        new = _make_candidate("new", 0.9, 0.1)  # dominates both
        result, added = update_archive(archive, new)
        assert added
        versions = {c.prompt_version for c in result}
        assert "new" in versions
        assert "v1" not in versions
        assert "v2" not in versions

    def test_non_dominated_candidate_added(self):
        archive = [_make_candidate("v1", 0.9, 0.5)]
        new = _make_candidate("new", 0.7, 0.1)  # neither dominates the other
        result, added = update_archive(archive, new)
        assert added
        assert len(result) == 2

    def test_no_domination_just_added(self):
        archive = [
            _make_candidate("v1", 0.9, 0.8),  # high quality, high cost
            _make_candidate("v2", 0.1, 0.1),  # low quality, low cost
        ]
        new = _make_candidate("new", 0.5, 0.5)
        result, added = update_archive(archive, new)
        assert added
        versions = {c.prompt_version for c in result}
        assert "new" in versions

    def test_empty_archive_accepts_any(self):
        new = _make_candidate("new", 0.7, 0.3)
        result, added = update_archive([], new)
        assert added
        assert len(result) == 1

    def test_returns_false_when_strictly_dominated(self):
        archive = [_make_candidate("v1", 0.9, 0.3)]
        new = _make_candidate("new", 0.8, 0.3)
        _, added = update_archive(archive, new)
        assert not added

    def test_no_size_limit(self):
        # Plain dominance filter — no cap on archive size
        archive = [_make_candidate(f"v{i}", i * 0.1, i * 0.1) for i in range(10)]
        new = _make_candidate("new", 0.95, 0.95)
        result, added = update_archive(archive, new)
        assert added
        assert len(result) == 11

    def test_archive_unchanged_on_rejection(self):
        archive = [_make_candidate("v1", 0.9, 0.1)]
        new = _make_candidate("new", 0.8, 0.2)
        result, _ = update_archive(archive, new)
        # Original archive object not mutated
        assert len(archive) == 1
        assert result[0].prompt_version == "v1"


# ---------------------------------------------------------------------------
# TestComputeNeighborhood
# ---------------------------------------------------------------------------


class TestComputeNeighborhood:
    def test_k5_trajectory_2_balanced_neighbors(self):
        # K=5: vecs = [(0.9,0.1), (0.7,0.3), (0.5,0.5), (0.3,0.7), (0.1,0.9)]
        vecs = compute_weight_vectors(5)
        neighbors = compute_neighborhood(2, 2, vecs)
        assert set(neighbors) == {1, 3}

    def test_k5_trajectory_0_neighbors(self):
        vecs = compute_weight_vectors(5)
        neighbors = compute_neighborhood(0, 2, vecs)
        assert set(neighbors) == {1, 2}

    def test_trajectory_excluded_from_own_neighborhood(self):
        vecs = compute_weight_vectors(5)
        for tid in range(5):
            neighbors = compute_neighborhood(tid, 2, vecs)
            assert tid not in neighbors

    def test_neighborhood_size_respected(self):
        vecs = compute_weight_vectors(5)
        for b in [1, 2, 3, 4]:
            neighbors = compute_neighborhood(0, b, vecs)
            assert len(neighbors) == b

    def test_k2_b1_returns_other(self):
        vecs = compute_weight_vectors(2)
        assert compute_neighborhood(0, 1, vecs) == [1]
        assert compute_neighborhood(1, 1, vecs) == [0]

    def test_sorted_by_ascending_distance(self):
        vecs = compute_weight_vectors(5)
        wq0, wc0 = vecs[0]
        neighbors = compute_neighborhood(0, 4, vecs)

        def dist(i: int) -> float:
            wq, wc = vecs[i]
            return math.sqrt((wq0 - wq) ** 2 + (wc0 - wc) ** 2)

        distances = [dist(i) for i in neighbors]
        assert distances == sorted(distances)


# ---------------------------------------------------------------------------
# TestReplaceIfBetter
# ---------------------------------------------------------------------------


class TestReplaceIfBetter:
    def _make_traj(self, tid: int, wv: tuple[float, float], energy: float, solution: str) -> TrajectoryState:
        return TrajectoryState(
            trajectory_id=tid,
            weight_vector=wv,
            current_solution=solution,
            current_energy=energy,
        )

    def test_replaces_when_child_energy_lower(self):
        neighbor = self._make_traj(1, (0.7, 0.3), 0.5, "v1")
        updated = replace_if_better(neighbor, child_energy=0.3, child_solution="v2", child_quality=0.8, child_cost=0.2)
        assert updated.current_solution == "v2"
        assert updated.current_energy == pytest.approx(0.3)
        assert updated.current_quality == pytest.approx(0.8)
        assert updated.current_cost == pytest.approx(0.2)

    def test_no_replacement_when_child_energy_higher(self):
        neighbor = self._make_traj(1, (0.7, 0.3), 0.5, "v1")
        updated = replace_if_better(neighbor, child_energy=0.8, child_solution="v2", child_quality=0.5, child_cost=0.7)
        assert updated.current_solution == "v1"
        assert updated.current_energy == pytest.approx(0.5)

    def test_no_replacement_when_equal_energy(self):
        neighbor = self._make_traj(1, (0.7, 0.3), 0.5, "v1")
        updated = replace_if_better(neighbor, child_energy=0.5, child_solution="v2", child_quality=0.6, child_cost=0.4)
        assert updated.current_solution == "v1"

    def test_replaces_when_current_energy_is_none(self):
        neighbor = TrajectoryState(trajectory_id=1, weight_vector=(0.7, 0.3))
        updated = replace_if_better(neighbor, child_energy=0.4, child_solution="v3", child_quality=0.7, child_cost=0.3)
        assert updated.current_solution == "v3"
        assert updated.current_energy == pytest.approx(0.4)

    def test_unconditional_deterministic(self):
        # Replacement is deterministic — no random draw
        neighbor = self._make_traj(1, (0.7, 0.3), 0.5, "v1")
        results = set()
        for _ in range(20):
            updated = replace_if_better(
                neighbor, child_energy=0.3, child_solution="v2", child_quality=0.8, child_cost=0.2
            )
            results.add(updated.current_solution)
        assert results == {"v2"}

    def test_trajectory_id_unchanged(self):
        neighbor = self._make_traj(3, (0.3, 0.7), 0.6, "v5")
        updated = replace_if_better(neighbor, child_energy=0.2, child_solution="v6", child_quality=0.9, child_cost=0.1)
        assert updated.trajectory_id == 3
        assert updated.weight_vector == (0.3, 0.7)

    def test_original_state_not_mutated(self):
        neighbor = self._make_traj(1, (0.7, 0.3), 0.5, "v1")
        _ = replace_if_better(neighbor, child_energy=0.2, child_solution="v2", child_quality=0.8, child_cost=0.2)
        # Original should remain unchanged (model_copy creates new object)
        assert neighbor.current_solution == "v1"
        assert neighbor.current_energy == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# TestModels
# ---------------------------------------------------------------------------


class TestModels:
    def test_trajectory_state_defaults(self):
        ts = TrajectoryState(trajectory_id=0, weight_vector=(0.5, 0.5))
        assert ts.current_solution is None
        assert ts.current_energy is None
        assert ts.current_quality is None
        assert ts.current_cost is None
        assert ts.acceptance_history == []
        assert ts.quality_reference is None
        assert ts.cost_reference is None

    def test_trajectory_state_mutable_default_independent(self):
        # Each instance gets its own list — no shared mutable default
        ts1 = TrajectoryState(trajectory_id=0, weight_vector=(0.5, 0.5))
        ts2 = TrajectoryState(trajectory_id=1, weight_vector=(0.7, 0.3))
        ts1.acceptance_history.append(True)
        assert ts2.acceptance_history == []

    def test_trajectory_state_new_fields_defaults(self):
        ts = TrajectoryState(trajectory_id=0, weight_vector=(0.5, 0.5))
        assert ts.temperature == pytest.approx(1.0)
        assert ts.alpha == pytest.approx(0.95)
        assert ts.step_count == 0

    def test_annealing_state_construction(self):
        trajectories = [
            TrajectoryState(trajectory_id=i, weight_vector=wv) for i, wv in enumerate(compute_weight_vectors(3))
        ]
        state = AnnealingState(trajectories=trajectories)
        assert state.phase == "calibration"
        assert state.total_evals == 0
        assert len(state.trajectories) == 3

    def test_annealing_state_neighborhood_size_default(self):
        trajectories = [TrajectoryState(trajectory_id=0, weight_vector=(0.5, 0.5))]
        state = AnnealingState(trajectories=trajectories)
        assert state.neighborhood_size == 4

    def test_annealing_state_rho_default(self):
        trajectories = [TrajectoryState(trajectory_id=0, weight_vector=(0.5, 0.5))]
        state = AnnealingState(trajectories=trajectories)
        assert state.rho == pytest.approx(1e-3)

    def test_annealing_state_phase_literal(self):
        trajectories = [TrajectoryState(trajectory_id=0, weight_vector=(0.5, 0.5))]
        state = AnnealingState(trajectories=trajectories, phase="search")
        assert state.phase == "search"

    def test_annealing_state_adaptive_cooling_defaults(self):
        trajectories = [TrajectoryState(trajectory_id=0, weight_vector=(0.5, 0.5))]
        state = AnnealingState(trajectories=trajectories)
        assert state.target_acceptance_low == pytest.approx(0.4)
        assert state.target_acceptance_high == pytest.approx(0.6)
        assert state.cooling_exp_fast == pytest.approx(1.5)
        assert state.cooling_exp_slow == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# TestNeighborhoodReplacementLogic (integration)
# ---------------------------------------------------------------------------


class TestNeighborhoodReplacementLogic:
    """Verify replace_if_better produces correct neighborhood replacement behavior."""

    def test_child_improves_neighbor_is_replaced(self):
        vecs = compute_weight_vectors(3)
        ideal = (1.0, 0.0)
        nadir = (0.0, 1.0)

        t1_weight = vecs[1]  # (0.5, 0.5)
        t1_current_energy = compute_tchebycheff_energy(0.6, 0.5, t1_weight, ideal, nadir)
        child_energy_under_t1 = compute_tchebycheff_energy(0.8, 0.2, t1_weight, ideal, nadir)

        assert child_energy_under_t1 < t1_current_energy

        t1_state = TrajectoryState(
            trajectory_id=1,
            weight_vector=t1_weight,
            current_solution="old_v",
            current_energy=t1_current_energy,
        )
        updated_t1 = replace_if_better(t1_state, child_energy_under_t1, "new_v", child_quality=0.8, child_cost=0.2)
        assert updated_t1.current_solution == "new_v"
        assert updated_t1.current_energy == pytest.approx(child_energy_under_t1)

    def test_child_does_not_improve_neighbor_stays(self):
        vecs = compute_weight_vectors(3)
        ideal = (1.0, 0.0)
        nadir = (0.0, 1.0)

        t2_weight = vecs[2]  # (0.1, 0.9) — cost-heavy
        t2_current_energy = compute_tchebycheff_energy(0.2, 0.05, t2_weight, ideal, nadir)
        child_energy_under_t2 = compute_tchebycheff_energy(0.9, 0.8, t2_weight, ideal, nadir)

        assert child_energy_under_t2 > t2_current_energy

        t2_state = TrajectoryState(
            trajectory_id=2,
            weight_vector=t2_weight,
            current_solution="good_cost_v",
            current_energy=t2_current_energy,
        )
        updated_t2 = replace_if_better(t2_state, child_energy_under_t2, "new_v", child_quality=0.9, child_cost=0.8)
        assert updated_t2.current_solution == "good_cost_v"
        assert updated_t2.current_energy == pytest.approx(t2_current_energy)


# ---------------------------------------------------------------------------
# TestAdaptiveCool
# ---------------------------------------------------------------------------


class TestAdaptiveCool:
    """Tests for adaptive_cool — per-trajectory temperature adjustment."""

    T = 0.5
    ALPHA = 0.9
    TARGET_LOW = 0.4
    TARGET_HIGH = 0.6
    EXP_FAST = 1.5
    EXP_SLOW = 0.5

    def test_empty_history_returns_geometric_step(self):
        result = adaptive_cool(self.T, self.ALPHA, [], self.TARGET_LOW, self.TARGET_HIGH, self.EXP_FAST, self.EXP_SLOW)
        assert result == pytest.approx(self.T * self.ALPHA)

    def test_high_acceptance_rate_cools_faster(self):
        # rate = 1.0 > target_high → alpha ** exp_fast
        history = [True] * 5
        result = adaptive_cool(
            self.T, self.ALPHA, history, self.TARGET_LOW, self.TARGET_HIGH, self.EXP_FAST, self.EXP_SLOW
        )
        assert result == pytest.approx(self.T * (self.ALPHA**self.EXP_FAST))

    def test_low_acceptance_rate_cools_slower(self):
        # rate = 0.0 < target_low → alpha ** exp_slow
        history = [False] * 5
        result = adaptive_cool(
            self.T, self.ALPHA, history, self.TARGET_LOW, self.TARGET_HIGH, self.EXP_FAST, self.EXP_SLOW
        )
        assert result == pytest.approx(self.T * (self.ALPHA**self.EXP_SLOW))

    def test_rate_in_band_returns_geometric_step(self):
        # rate = 0.5 in [0.4, 0.6] → default alpha
        history = [True, True, True, False, False]  # 3/5 = 0.6 — exactly at boundary
        result = adaptive_cool(
            self.T, self.ALPHA, history, self.TARGET_LOW, self.TARGET_HIGH, self.EXP_FAST, self.EXP_SLOW
        )
        # 0.6 is NOT > 0.6, so stays in band → default step
        assert result == pytest.approx(self.T * self.ALPHA)

    def test_rate_exactly_at_target_low_stays_geometric(self):
        # rate = 0.4 == target_low → NOT < target_low → default step
        history = [True, True, False, False, False]  # 2/5 = 0.4
        result = adaptive_cool(
            self.T, self.ALPHA, history, self.TARGET_LOW, self.TARGET_HIGH, self.EXP_FAST, self.EXP_SLOW
        )
        assert result == pytest.approx(self.T * self.ALPHA)

    def test_rate_just_above_target_high_triggers_fast_cooling(self):
        # Construct a rate just above 0.6: 4/5=0.8 > 0.6
        history = [True, True, True, True, False]  # 4/5 = 0.8
        result = adaptive_cool(
            self.T, self.ALPHA, history, self.TARGET_LOW, self.TARGET_HIGH, self.EXP_FAST, self.EXP_SLOW
        )
        assert result == pytest.approx(self.T * (self.ALPHA**self.EXP_FAST))

    def test_rate_just_below_target_low_triggers_slow_cooling(self):
        # rate = 1/5 = 0.2 < 0.4
        history = [True, False, False, False, False]
        result = adaptive_cool(
            self.T, self.ALPHA, history, self.TARGET_LOW, self.TARGET_HIGH, self.EXP_FAST, self.EXP_SLOW
        )
        assert result == pytest.approx(self.T * (self.ALPHA**self.EXP_SLOW))

    def test_result_is_always_positive(self):
        for history in [[], [True] * 5, [False] * 5, [True, False, True, False, True]]:
            result = adaptive_cool(
                self.T, self.ALPHA, history, self.TARGET_LOW, self.TARGET_HIGH, self.EXP_FAST, self.EXP_SLOW
            )
            assert result > 0.0

    def test_fast_cooling_lower_than_slow_cooling(self):
        """alpha**1.5 < alpha**0.5 for 0 < alpha < 1."""
        fast = adaptive_cool(self.T, self.ALPHA, [True] * 5, 0.4, 0.6, 1.5, 0.5)
        slow = adaptive_cool(self.T, self.ALPHA, [False] * 5, 0.4, 0.6, 1.5, 0.5)
        assert fast < slow
