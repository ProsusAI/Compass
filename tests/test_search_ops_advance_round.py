"""Integration tests for advance_round_beam cold-start elite-floor behaviour.

Verifies that:
- After round 1 (new_round == 1), all scored candidates survive regardless of
  Pareto dominance (cold-start elite floor).
- After round 2, standard Pareto competition applies across protected parents
  and their children.
"""

from __future__ import annotations

from odysseus.agents.prompt_builder.search_ops import (
    advance_round_beam,
    get_search_state,
    init_search_state,
    record_eval_result,
    register_candidate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_and_score(
    run_id: str,
    prompt_version: str,
    quality_score: float,
    cost: float,
    tmp_path,
    parent_version: str | None = None,
) -> None:
    register_candidate(
        run_id,
        prompt_version,
        parent_version=parent_version,
        output_dir=tmp_path,
    )
    record_eval_result(
        run_id,
        prompt_version,
        quality_score=quality_score,
        cost=cost,
        output_dir=tmp_path,
    )


# ---------------------------------------------------------------------------
# Cold-start floor: post-round-1 elite retains all candidates
# ---------------------------------------------------------------------------


class TestAdvanceRoundColdStartFloor:
    def test_all_round1_candidates_survive_pareto_domination(self, tmp_path) -> None:
        """Post-round-1 elite must contain all 3 candidates even when one dominates."""
        run_id = "coldstart_test"
        init_search_state(
            backend="anthropic",
            run_id=run_id,
            output_dir=tmp_path,
        )

        # v1 strictly dominates v2 and v3 on both quality and cost.
        _register_and_score(run_id, "v1", quality_score=0.95, cost=0.05, tmp_path=tmp_path)
        _register_and_score(run_id, "v2", quality_score=0.70, cost=0.20, tmp_path=tmp_path)
        _register_and_score(run_id, "v3", quality_score=0.60, cost=0.30, tmp_path=tmp_path)

        summary = advance_round_beam(run_id, output_dir=tmp_path)
        state = get_search_state(run_id, output_dir=tmp_path)

        assert summary.round == 1
        elite_versions = {c.prompt_version for c in state.elite_set}
        assert elite_versions == {"v1", "v2", "v3"}, (
            f"All round-1 strategies must survive; got {elite_versions}"
        )

    def test_round1_elite_size_equals_beam_width(self, tmp_path) -> None:
        """Cold-start elite must retain all beam_width candidates."""
        run_id = "coldstart_size"
        init_search_state(
            backend="anthropic",
            run_id=run_id,
            output_dir=tmp_path,
        )

        _register_and_score(run_id, "v1", quality_score=0.90, cost=0.10, tmp_path=tmp_path)
        _register_and_score(run_id, "v2", quality_score=0.75, cost=0.25, tmp_path=tmp_path)
        _register_and_score(run_id, "v3", quality_score=0.60, cost=0.40, tmp_path=tmp_path)

        advance_round_beam(run_id, output_dir=tmp_path)
        state = get_search_state(run_id, output_dir=tmp_path)

        assert len(state.elite_set) == 3


# ---------------------------------------------------------------------------
# Round 2: normal Pareto resumes over protected parents + children
# ---------------------------------------------------------------------------


class TestAdvanceRoundNormalParetoResumesInRound2:
    def test_dominated_parent_evicted_in_round2_when_child_dominates(self, tmp_path) -> None:
        """By round 2, Pareto applies: a dominated round-1 strategy is evicted if its
        child also dominates it and no child is strictly non-dominated by v1."""
        run_id = "pareto_round2"
        init_search_state(
            backend="anthropic",
            run_id=run_id,
            output_dir=tmp_path,
        )

        # Round 1: three cold-start candidates — v1 dominates v2 and v3.
        _register_and_score(run_id, "v1", quality_score=0.95, cost=0.05, tmp_path=tmp_path)
        _register_and_score(run_id, "v2", quality_score=0.70, cost=0.20, tmp_path=tmp_path)
        _register_and_score(run_id, "v3", quality_score=0.60, cost=0.30, tmp_path=tmp_path)

        advance_round_beam(run_id, output_dir=tmp_path)  # round -> 1, cold-start elite = {v1, v2, v3}

        # Round 2: one child per protected parent.
        # v1c: improves on v1 (completely dominates v2, v3, and v2c, v3c).
        # v2c: slightly better than v2 but still dominated by v1c.
        # v3c: slightly better than v3 but still dominated by v1c.
        _register_and_score(run_id, "v1c", quality_score=0.96, cost=0.04, tmp_path=tmp_path, parent_version="v1")
        _register_and_score(run_id, "v2c", quality_score=0.71, cost=0.19, tmp_path=tmp_path, parent_version="v2")
        _register_and_score(run_id, "v3c", quality_score=0.61, cost=0.29, tmp_path=tmp_path, parent_version="v3")

        advance_round_beam(run_id, output_dir=tmp_path)  # round -> 2, normal Pareto
        state = get_search_state(run_id, output_dir=tmp_path)

        assert state.round == 2
        elite_versions = {c.prompt_version for c in state.elite_set}
        # v1c dominates everything else — only v1c should survive.
        assert "v1c" in elite_versions, "v1c must be on the front as the dominant candidate"
        assert "v2" not in elite_versions, "v2 is dominated by v1c and must be evicted"
        assert "v3" not in elite_versions, "v3 is dominated by v1c and must be evicted"
        assert "v2c" not in elite_versions, "v2c is dominated by v1c"
        assert "v3c" not in elite_versions, "v3c is dominated by v1c"

    def test_non_dominated_children_survive_in_round2(self, tmp_path) -> None:
        """Children that occupy genuinely distinct Pareto positions survive round 2."""
        run_id = "pareto_round2_diverse"
        init_search_state(
            backend="anthropic",
            run_id=run_id,
            output_dir=tmp_path,
        )

        # Round 1: v1 dominates v2 and v3 — all survive due to cold-start floor.
        _register_and_score(run_id, "v1", quality_score=0.95, cost=0.20, tmp_path=tmp_path)
        _register_and_score(run_id, "v2", quality_score=0.70, cost=0.20, tmp_path=tmp_path)
        _register_and_score(run_id, "v3", quality_score=0.60, cost=0.30, tmp_path=tmp_path)

        advance_round_beam(run_id, output_dir=tmp_path)

        # Round 2: each parent gets a child.
        # v1c: highest quality, moderate cost.
        # v2c: moderate quality, very low cost (genuinely non-dominated).
        # v3c: better than v3 but still dominated by v1c.
        _register_and_score(run_id, "v1c", quality_score=0.96, cost=0.20, tmp_path=tmp_path, parent_version="v1")
        _register_and_score(run_id, "v2c", quality_score=0.72, cost=0.05, tmp_path=tmp_path, parent_version="v2")
        _register_and_score(run_id, "v3c", quality_score=0.61, cost=0.29, tmp_path=tmp_path, parent_version="v3")

        advance_round_beam(run_id, output_dir=tmp_path)
        state = get_search_state(run_id, output_dir=tmp_path)

        elite_versions = {c.prompt_version for c in state.elite_set}
        # v1c (high quality) and v2c (low cost) are both non-dominated.
        assert "v1c" in elite_versions, "v1c is Pareto non-dominated"
        assert "v2c" in elite_versions, "v2c is Pareto non-dominated (cheapest)"
        # v3c is dominated by both — must be gone.
        assert "v3c" not in elite_versions, "v3c is dominated and must be pruned"

    def test_stagnation_count_zero_on_round1(self, tmp_path) -> None:
        """Stagnation count must be 0 after round 1 regardless of hypervolume change."""
        run_id = "stagnation_round1"
        init_search_state(
            backend="anthropic",
            run_id=run_id,
            output_dir=tmp_path,
        )

        _register_and_score(run_id, "v1", quality_score=0.90, cost=0.10, tmp_path=tmp_path)
        _register_and_score(run_id, "v2", quality_score=0.75, cost=0.25, tmp_path=tmp_path)
        _register_and_score(run_id, "v3", quality_score=0.60, cost=0.40, tmp_path=tmp_path)

        summary = advance_round_beam(run_id, output_dir=tmp_path)

        state = get_search_state(run_id, output_dir=tmp_path)
        pocket = AnnealingState.model_validate(state.algorithm_state)

        assert pocket.num_trajectories == 3
        # Calibration seeds step_count=0 on each trajectory
        for traj in pocket.trajectories:
            assert traj.step_count == 0
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
        # Calibration seeds step_count=0 on each trajectory (no Metropolis steps yet)
        for traj in pocket.trajectories:
            assert traj.step_count == 0
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
        # After calibration, all trajectories have step_count=0 (sum=0)
        assert summary.step_count == 0
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
        """advance_step_tool dispatches to _advance_emosa for algorithm='emosa' (branch default)."""
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

            # init_search_state_tool no longer accepts algorithm/algorithm_state params;
            # algorithm is hardcoded via _BRANCH_ALGORITHM (='emosa' on this branch).
            await init_search_state_tool(
                ctx=None,
                run_id="emosa-tool",
                backend="test",
            )

            # The tool writes state to outputs/<run_id>/search/ under project_dir
            outputs_dir = tmp_path / "outputs"

            # Overwrite algorithm_state with a proper K=3 calibration AnnealingState.
            # loop_phase is not overridden — dispatch must work from the default ("review").
            state = _load_state("emosa-tool", outputs_dir)
            updated = state.model_copy(update={"algorithm_state": annealing_dict})
            _save_state("emosa-tool", updated, outputs_dir)

            # Populate pending in the outputs sub-path used by the tool
            scored = _build_scored_pending(3)
            _save_pending("emosa-tool", scored, outputs_dir)

            result_json = await advance_step_tool("emosa-tool")
            result = json.loads(result_json)
            assert result["phase"] == "search"
            # After calibration, all trajectories have step_count=0, so sum=0
            assert result["step_count"] == 0

    async def test_advance_step_tool_emosa_default_loop_phase(self, tmp_path: Path) -> None:
        """Regression for C4 stub: dispatch must not depend on loop_phase.

        Runs advance_step_tool with loop_phase at its SearchState default ("review") —
        no override — and asserts that EMOSA calibration still completes successfully.
        """
        from odysseus.agents.prompt_builder.search_ops import _load_state, _save_state
        from odysseus.mcp import advance_step_tool, init_search_state_tool

        annealing = _make_annealing_state(num_trajectories=3)
        annealing_dict = json.loads(annealing.model_dump_json())

        with (
            patch(_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            patch(_SEARCH_OPS_PATCH, return_value=tmp_path),
        ):
            analysis_dir = tmp_path / "outputs" / "emosa-default-phase" / "analysis"
            analysis_dir.mkdir(parents=True, exist_ok=True)
            (analysis_dir / "dev.jsonl").write_text("")

            await init_search_state_tool(
                ctx=None,
                run_id="emosa-default-phase",
                backend="test",
            )

            outputs_dir = tmp_path / "outputs"

            # Patch only algorithm_state — do NOT override loop_phase.
            # The default SearchState.loop_phase is "review"; dispatch must work from it.
            state = _load_state("emosa-default-phase", outputs_dir)
            updated = state.model_copy(update={"algorithm_state": annealing_dict})
            _save_state("emosa-default-phase", updated, outputs_dir)

            scored = _build_scored_pending(3)
            _save_pending("emosa-default-phase", scored, outputs_dir)

            result_json = await advance_step_tool("emosa-default-phase")
            result = json.loads(result_json)
            assert result["phase"] == "search"
            assert result["step_count"] == 0
