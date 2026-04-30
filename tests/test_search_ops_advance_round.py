"""Tests for advance_round_emosa in odysseus.agents.prompt_builder.search_ops.

Covers the calibration arm introduced in C3 commit 2/4.  Steady-state
(``phase == "search"``) is deferred to C4 and tested here only via
NotImplementedError assertions.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from odysseus.agents.prompt_builder.annealing import (
    AnnealingState,
    TrajectoryState,
    compute_tchebycheff_energy,
    compute_weight_vectors,
)
from odysseus.agents.prompt_builder.search import Candidate, RoundSummary, SearchState
from odysseus.agents.prompt_builder.search_ops import (
    _load_pending,
    _load_state,
    _save_pending,
    _save_state,
    advance_round_emosa,
    get_search_state,
    init_search_state,
)

_SEARCH_OPS_PATCH = "odysseus.agents.prompt_builder.search_ops.get_project_dir"
_RESOLVE_PROJECT_DIR = "odysseus.project_dir.resolve_project_dir"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_annealing_state(num_trajectories: int = 5) -> AnnealingState:
    """Build an AnnealingState in calibration phase with K unseeded trajectories."""
    weight_vectors = compute_weight_vectors(num_trajectories)
    trajectories = [
        TrajectoryState(trajectory_id=i, weight_vector=weight_vectors[i])
        for i in range(num_trajectories)
    ]
    return AnnealingState(
        temperature=1.0,
        alpha=0.95,
        num_trajectories=num_trajectories,
        trajectories=trajectories,
        phase="calibration",
        step_count=0,
        total_evals=0,
    )


def _make_emosa_state(tmp_path: Path, run_id: str, num_trajectories: int = 5) -> SearchState:
    """Init an emosa SearchState with a calibration-phase AnnealingState pocket."""
    annealing = _make_annealing_state(num_trajectories)
    state = init_search_state(
        backend="test",
        run_id=run_id,
        output_dir=tmp_path,
        algorithm="emosa",
        algorithm_state=json.loads(annealing.model_dump_json()),
    )
    return state


def _build_scored_pending(num: int) -> list[Candidate]:
    """Build *num* scored Candidate objects with distinct quality/cost values."""
    candidates = []
    for i in range(num):
        quality = 0.9 - i * 0.1  # 0.9, 0.8, 0.7, ... (decreasing)
        cost = 0.01 + i * 0.02   # 0.01, 0.03, 0.05, ... (increasing)
        candidates.append(
            Candidate(
                prompt_version=f"v{i + 1}",
                parent_version=None,
                quality_score=quality,
                cost=cost,
                round_introduced=1,
                eval_status="complete",
            )
        )
    return candidates


# ---------------------------------------------------------------------------
# TestAdvanceRoundEmosaCalibration
# ---------------------------------------------------------------------------


class TestAdvanceRoundEmosaCalibration:
    """Tests for advance_round_emosa calibration arm (phase == 'calibration')."""

    def test_k5_full_seed_phase_flip(self, tmp_path: Path) -> None:
        """K=5: calibration flips pocket phase to 'search' and loop_phase to 'review'."""
        run_id = "emosa-c5-phase"
        _make_emosa_state(tmp_path, run_id, num_trajectories=5)
        scored = _build_scored_pending(5)
        _save_pending(run_id, scored, tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        state = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(state.algorithm_state)
        assert pocket.phase == "search"
        assert state.loop_phase == "review"

    def test_k5_step_count_bumped_to_one(self, tmp_path: Path) -> None:
        """K=5: step_count is incremented from 0 to 1 by calibration."""
        run_id = "emosa-c5-step"
        _make_emosa_state(tmp_path, run_id, num_trajectories=5)
        _save_pending(run_id, _build_scored_pending(5), tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        state = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(state.algorithm_state)
        assert pocket.step_count == 1

    def test_k5_total_evals_equals_k(self, tmp_path: Path) -> None:
        """K=5: total_evals in pocket equals K after calibration."""
        run_id = "emosa-c5-evals"
        _make_emosa_state(tmp_path, run_id, num_trajectories=5)
        _save_pending(run_id, _build_scored_pending(5), tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        state = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(state.algorithm_state)
        assert pocket.total_evals == 5

    def test_k5_ideal_nadir_computed_correctly(self, tmp_path: Path) -> None:
        """K=5: ideal=(best_quality, lowest_cost), nadir=(worst_quality, highest_cost)."""
        run_id = "emosa-c5-ideal"
        _make_emosa_state(tmp_path, run_id, num_trajectories=5)
        scored = _build_scored_pending(5)
        _save_pending(run_id, scored, tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        state = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(state.algorithm_state)

        expected_ideal_q = max(c.quality_score for c in scored)
        expected_ideal_c = min(c.cost for c in scored)
        expected_nadir_q = min(c.quality_score for c in scored)
        expected_nadir_c = max(c.cost for c in scored)

        assert pocket.ideal_point == (expected_ideal_q, expected_ideal_c)
        assert pocket.nadir_point == (expected_nadir_q, expected_nadir_c)

    def test_k5_per_trajectory_current_energy_matches_tchebycheff(self, tmp_path: Path) -> None:
        """Each trajectory's current_energy equals compute_tchebycheff_energy on its weight vector."""
        run_id = "emosa-c5-energy"
        _make_emosa_state(tmp_path, run_id, num_trajectories=5)
        scored = _build_scored_pending(5)
        _save_pending(run_id, scored, tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        state = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(state.algorithm_state)

        ideal = pocket.ideal_point
        nadir = pocket.nadir_point

        for traj in pocket.trajectories:
            i = traj.trajectory_id
            expected_energy = compute_tchebycheff_energy(
                scored[i].quality_score,
                scored[i].cost,
                traj.weight_vector,
                ideal,
                nadir,
            )
            assert traj.current_energy == pytest.approx(expected_energy, rel=1e-9)

    def test_k5_acceptance_history_is_true_for_all(self, tmp_path: Path) -> None:
        """Calibration seeds each trajectory with acceptance_history=[True]."""
        run_id = "emosa-c5-accept"
        _make_emosa_state(tmp_path, run_id, num_trajectories=5)
        _save_pending(run_id, _build_scored_pending(5), tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        state = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(state.algorithm_state)
        for traj in pocket.trajectories:
            assert traj.acceptance_history == [True], (
                f"trajectory {traj.trajectory_id} has acceptance_history={traj.acceptance_history!r}"
            )

    def test_k3_seeds_correctly_smaller_k(self, tmp_path: Path) -> None:
        """K=3: smaller K still seeds all 3 trajectories correctly (K read from pocket)."""
        run_id = "emosa-c3-small"
        _make_emosa_state(tmp_path, run_id, num_trajectories=3)
        scored = _build_scored_pending(3)
        _save_pending(run_id, scored, tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        state = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(state.algorithm_state)

        assert pocket.num_trajectories == 3
        assert pocket.step_count == 1
        assert pocket.total_evals == 3
        assert pocket.phase == "search"
        # All 3 trajectories seeded
        for traj in pocket.trajectories:
            assert traj.current_solution is not None
            assert traj.current_energy is not None

    def test_insufficient_scored_raises(self, tmp_path: Path) -> None:
        """Fewer scored candidates than K raises ValueError with a clear message."""
        run_id = "emosa-insuf"
        _make_emosa_state(tmp_path, run_id, num_trajectories=5)
        # Only 3 scored for a K=5 run
        _save_pending(run_id, _build_scored_pending(3), tmp_path)

        with pytest.raises(ValueError, match="num_trajectories"):
            advance_round_emosa(run_id=run_id, output_dir=tmp_path)

    def test_search_phase_with_no_pending_raises_value_error(self, tmp_path: Path) -> None:
        """phase == 'search' with no pending candidates raises ValueError (C4 implemented)."""
        run_id = "emosa-search-no-pending"
        _make_emosa_state(tmp_path, run_id, num_trajectories=5)

        # Manually flip phase to "search" in pocket (no pending saved)
        state = _load_state(run_id, tmp_path)
        pocket = dict(state.algorithm_state)
        pocket["phase"] = "search"
        updated = state.model_copy(update={"algorithm_state": pocket})
        _save_state(run_id, updated, tmp_path)

        with pytest.raises(ValueError, match="No pending candidates"):
            advance_round_emosa(run_id=run_id, output_dir=tmp_path)

    def test_invalid_phase_raises_value_error(self, tmp_path: Path) -> None:
        """An unrecognised phase value raises ValueError mentioning the bad phase."""
        run_id = "emosa-bad-phase"
        _make_emosa_state(tmp_path, run_id, num_trajectories=5)

        state = _load_state(run_id, tmp_path)
        pocket = dict(state.algorithm_state)
        pocket["phase"] = "bogus_phase"
        updated = state.model_copy(update={"algorithm_state": pocket})
        _save_state(run_id, updated, tmp_path)

        with pytest.raises(ValueError, match="bogus_phase"):
            advance_round_emosa(run_id=run_id, output_dir=tmp_path)

    def test_state_file_persisted_and_round_trippable(self, tmp_path: Path) -> None:
        """After calibration, state file is readable and shows pocket updates."""
        run_id = "emosa-persist"
        _make_emosa_state(tmp_path, run_id, num_trajectories=5)
        _save_pending(run_id, _build_scored_pending(5), tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        # Round-trip: read state file directly and revalidate
        state_path = tmp_path / run_id / "search" / "search_state.json"
        assert state_path.exists(), "state file missing after calibration"
        loaded = SearchState.model_validate_json(state_path.read_text(encoding="utf-8"))
        pocket = AnnealingState.model_validate(loaded.algorithm_state)
        assert pocket.phase == "search"
        assert pocket.step_count == 1
        assert loaded.loop_phase == "review"
        assert loaded.round == 1

    def test_round_summary_fields_populated(self, tmp_path: Path) -> None:
        """RoundSummary returned has phase='search', ideal/nadir/step_count set."""
        run_id = "emosa-summary"
        _make_emosa_state(tmp_path, run_id, num_trajectories=5)
        scored = _build_scored_pending(5)
        _save_pending(run_id, scored, tmp_path)

        summary = advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        assert isinstance(summary, RoundSummary)
        assert summary.phase == "search"
        assert summary.step_count == 1
        assert summary.ideal_point is not None
        assert summary.nadir_point is not None
        # Verify ideal_point matches expected values
        assert summary.ideal_point[0] == pytest.approx(max(c.quality_score for c in scored))
        assert summary.ideal_point[1] == pytest.approx(min(c.cost for c in scored))

    def test_pending_cleared_after_calibration(self, tmp_path: Path) -> None:
        """Pending candidate list is emptied after calibration completes."""
        run_id = "emosa-clear-pending"
        _make_emosa_state(tmp_path, run_id, num_trajectories=5)
        _save_pending(run_id, _build_scored_pending(5), tmp_path)

        advance_round_emosa(run_id=run_id, output_dir=tmp_path)

        pending = _load_pending(run_id, tmp_path)
        assert pending == []

    async def test_advance_step_tool_emosa_calibration_arm(self, tmp_path: Path) -> None:
        """advance_step_tool dispatches to _advance_emosa for algorithm='emosa'."""
        from odysseus.agents.prompt_builder.search_ops import _load_state, _save_state
        from odysseus.mcp import advance_step_tool, init_search_state_tool

        annealing = _make_annealing_state(num_trajectories=3)
        annealing_dict = json.loads(annealing.model_dump_json())

        with (
            patch(_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            patch(_SEARCH_OPS_PATCH, return_value=tmp_path),
        ):
            analysis_dir = tmp_path / "outputs" / "emosa-tool" / "analysis"
            analysis_dir.mkdir(parents=True, exist_ok=True)
            (analysis_dir / "dev.jsonl").write_text("")

            await init_search_state_tool(
                ctx=None,
                run_id="emosa-tool",
                backend="test",
                algorithm="emosa",
                algorithm_state=annealing_dict,
            )

            # The tool writes state to outputs/<run_id>/search/ under project_dir
            outputs_dir = tmp_path / "outputs"

            # Flip loop_phase to "calibration" (init defaults to "review")
            state = _load_state("emosa-tool", outputs_dir)
            updated = state.model_copy(update={"loop_phase": "calibration"})
            _save_state("emosa-tool", updated, outputs_dir)

            # Populate pending in the outputs sub-path used by the tool
            scored = _build_scored_pending(3)
            _save_pending("emosa-tool", scored, outputs_dir)

            result_json = await advance_step_tool("emosa-tool")
            result = json.loads(result_json)
            assert result["phase"] == "search"
            assert result["step_count"] == 1
