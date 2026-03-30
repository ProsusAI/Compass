"""Tests for odysseus.agents.prompt_builder_search_ops."""

from __future__ import annotations

import pytest

from odysseus.agents.prompt_builder_search_ops import (
    _load_pending,
    advance_round,
    get_search_state,
    init_search_state,
    record_eval_result,
    register_candidate,
    set_loop_phase,
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
    """Register a candidate and record its eval result in one call."""
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
# Task 6: init_search_state / get_search_state
# ---------------------------------------------------------------------------


class TestInitSearchState:
    def test_creates_state_with_defaults(self, tmp_path) -> None:
        state = init_search_state("anthropic", run_id="run001", output_dir=tmp_path)
        assert state.backend == "anthropic"
        assert state.max_rounds == 50
        assert state.stagnation_limit == 3
        assert state.convergence_limit == 5
        assert state.primary_metric_name is None
        assert state.round == 0
        assert state.pareto_front == []
        assert state.converged is False

    def test_creates_state_with_custom_params(self, tmp_path) -> None:
        state = init_search_state(
            "openai",
            run_id="run002",
            output_dir=tmp_path,
            max_rounds=10,
            stagnation_limit=2,
            convergence_limit=4,
            primary_metric_name="f1_macro",
        )
        assert state.backend == "openai"
        assert state.max_rounds == 10
        assert state.stagnation_limit == 2
        assert state.convergence_limit == 4
        assert state.primary_metric_name == "f1_macro"

    def test_persists_to_disk(self, tmp_path) -> None:
        state = init_search_state("anthropic", run_id="run003", output_dir=tmp_path)
        state_file = tmp_path / "run003" / "search" / "search_state.json"
        assert state_file.exists()
        # search_state_id in the file is the internal ID, not run_id
        assert state.search_state_id != "run003"

    def test_generates_unique_ids(self, tmp_path) -> None:
        s1 = init_search_state("anthropic", run_id="run-a", output_dir=tmp_path)
        s2 = init_search_state("anthropic", run_id="run-b", output_dir=tmp_path)
        assert s1.search_state_id != s2.search_state_id

    def test_id_is_12_hex_chars(self, tmp_path) -> None:
        state = init_search_state("anthropic", run_id="run004", output_dir=tmp_path)
        assert len(state.search_state_id) == 12
        assert all(c in "0123456789abcdef" for c in state.search_state_id)


class TestGetSearchState:
    def test_loads_persisted_state(self, tmp_path) -> None:
        original = init_search_state("anthropic", run_id="run005", output_dir=tmp_path)
        loaded = get_search_state(run_id="run005", output_dir=tmp_path)
        assert loaded.search_state_id == original.search_state_id
        assert loaded.backend == original.backend

    def test_raises_for_missing_state(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            get_search_state("nonexistent", output_dir=tmp_path)


# ---------------------------------------------------------------------------
# Run ID paths (dual identity)
# ---------------------------------------------------------------------------


class TestRunIdPaths:
    def test_init_uses_run_id_for_path(self, tmp_path) -> None:
        state = init_search_state(backend="mock", run_id="abc12345", output_dir=tmp_path)
        assert (tmp_path / "abc12345" / "search" / "search_state.json").is_file()
        # search_state_id is a DIFFERENT internal field
        assert state.search_state_id != "abc12345"
        assert len(state.search_state_id) == 12

    def test_get_search_state_reads_from_run_id(self, tmp_path) -> None:
        init_search_state(backend="mock", run_id="abc12345", output_dir=tmp_path)
        loaded = get_search_state(run_id="abc12345", output_dir=tmp_path)
        assert loaded.backend == "mock"


# ---------------------------------------------------------------------------
# Task 7: register_candidate
# ---------------------------------------------------------------------------


class TestRegisterCandidate:
    def test_writes_to_pending_candidates_json(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run010", output_dir=tmp_path)
        register_candidate("run010", "v1", output_dir=tmp_path)
        pending_file = tmp_path / "run010" / "search" / "pending_candidates.json"
        assert pending_file.exists()

    def test_candidate_appears_in_pending(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run011", output_dir=tmp_path)
        register_candidate("run011", "v1", output_dir=tmp_path)
        pending = _load_pending("run011", tmp_path)
        assert len(pending) == 1
        assert pending[0].prompt_version == "v1"
        assert pending[0].quality_score == 0.0
        assert pending[0].cost == 0.0

    def test_multiple_candidates_in_pending(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run012", output_dir=tmp_path)
        register_candidate("run012", "v1", output_dir=tmp_path)
        register_candidate("run012", "v2", output_dir=tmp_path)
        pending = _load_pending("run012", tmp_path)
        assert len(pending) == 2

    def test_parent_version_stored(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run013", output_dir=tmp_path)
        register_candidate("run013", "v2", parent_version="v1", output_dir=tmp_path)
        pending = _load_pending("run013", tmp_path)
        assert pending[0].parent_version == "v1"

    def test_returns_current_state(self, tmp_path) -> None:
        state = init_search_state("anthropic", run_id="run014", output_dir=tmp_path)
        returned = register_candidate("run014", "v1", output_dir=tmp_path)
        assert returned.search_state_id == state.search_state_id

    def test_duplicate_in_pending_raises(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run015", output_dir=tmp_path)
        register_candidate("run015", "v1", output_dir=tmp_path)
        with pytest.raises(ValueError, match="v1"):
            register_candidate("run015", "v1", output_dir=tmp_path)

    def test_duplicate_in_front_raises(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run016", output_dir=tmp_path)
        _register_and_score("run016", "v1", 0.9, 0.01, tmp_path)
        advance_round("run016", output_dir=tmp_path)
        with pytest.raises(ValueError, match="v1"):
            register_candidate("run016", "v1", output_dir=tmp_path)

    def test_duplicate_in_history_raises(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run017", output_dir=tmp_path)
        # Register v1 and advance — v1 moves to history candidates_evaluated
        _register_and_score("run017", "v1", 0.9, 0.01, tmp_path)
        advance_round("run017", output_dir=tmp_path)
        # Register v2 (low quality so v1 stays on front), advance again
        _register_and_score("run017", "v2", 0.5, 0.5, tmp_path)
        advance_round("run017", output_dir=tmp_path)
        # v2 appeared in round_history[1].candidates_evaluated — duplicate
        with pytest.raises(ValueError, match="v2"):
            register_candidate("run017", "v2", output_dir=tmp_path)


# ---------------------------------------------------------------------------
# Task 8: record_eval_result
# ---------------------------------------------------------------------------


class TestRecordEvalResult:
    def test_updates_quality_and_cost(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run020", output_dir=tmp_path)
        register_candidate("run020", "v1", output_dir=tmp_path)
        record_eval_result("run020", "v1", quality_score=0.85, cost=0.02, output_dir=tmp_path)
        pending = _load_pending("run020", tmp_path)
        assert pending[0].quality_score == 0.85
        assert pending[0].cost == 0.02

    def test_returns_correct_dict(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run021", output_dir=tmp_path)
        register_candidate("run021", "v1", output_dir=tmp_path)
        result = record_eval_result("run021", "v1", quality_score=0.9, cost=0.05, output_dir=tmp_path)
        assert result == {"prompt_version": "v1", "quality_score": 0.9, "cost": 0.05}

    def test_unknown_version_raises(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run022", output_dir=tmp_path)
        with pytest.raises(ValueError, match="unknown_v"):
            record_eval_result(
                "run022",
                "unknown_v",
                quality_score=0.5,
                cost=0.1,
                output_dir=tmp_path,
            )

    def test_only_target_candidate_updated(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run023", output_dir=tmp_path)
        register_candidate("run023", "v1", output_dir=tmp_path)
        register_candidate("run023", "v2", output_dir=tmp_path)
        record_eval_result("run023", "v1", quality_score=0.9, cost=0.01, output_dir=tmp_path)
        pending = _load_pending("run023", tmp_path)
        v2 = next(c for c in pending if c.prompt_version == "v2")
        assert v2.quality_score == 0.0
        assert v2.cost == 0.0


# ---------------------------------------------------------------------------
# Task 9: advance_round
# ---------------------------------------------------------------------------


class TestAdvanceRound:
    def test_first_round_adds_to_front(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run030", output_dir=tmp_path)
        _register_and_score("run030", "v1", 0.9, 0.01, tmp_path)
        summary = advance_round("run030", output_dir=tmp_path)
        assert summary.round == 1
        assert summary.new_pareto_points == 1
        assert summary.front_size == 1
        assert "v1" in summary.candidates_evaluated

    def test_state_round_incremented(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run031", output_dir=tmp_path)
        _register_and_score("run031", "v1", 0.9, 0.01, tmp_path)
        advance_round("run031", output_dir=tmp_path)
        updated = get_search_state("run031", output_dir=tmp_path)
        assert updated.round == 1

    def test_pending_cleared_after_advance(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run032", output_dir=tmp_path)
        _register_and_score("run032", "v1", 0.9, 0.01, tmp_path)
        advance_round("run032", output_dir=tmp_path)
        pending = _load_pending("run032", tmp_path)
        assert pending == []

    def test_stagnation_increments_when_no_improvement(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run033", output_dir=tmp_path)
        # Round 1: add v1 to front
        _register_and_score("run033", "v1", 0.9, 0.01, tmp_path)
        advance_round("run033", output_dir=tmp_path)
        # Round 2: dominated candidate — no improvement
        _register_and_score("run033", "v2", 0.5, 0.5, tmp_path)
        summary = advance_round("run033", output_dir=tmp_path)
        assert summary.stagnation_count == 1
        assert summary.new_pareto_points == 0

    def test_stagnation_resets_on_improvement(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run034", output_dir=tmp_path)
        # Round 1: add v1 to front
        _register_and_score("run034", "v1", 0.9, 0.01, tmp_path)
        advance_round("run034", output_dir=tmp_path)
        # Round 2: no improvement
        _register_and_score("run034", "v2", 0.5, 0.5, tmp_path)
        advance_round("run034", output_dir=tmp_path)
        # Round 3: improvement (incomparable — new pareto point)
        _register_and_score("run034", "v3", 0.95, 0.1, tmp_path)
        summary = advance_round("run034", output_dir=tmp_path)
        assert summary.stagnation_count == 0
        assert summary.new_pareto_points > 0

    def test_switches_to_exploratory_at_stagnation_limit(self, tmp_path) -> None:
        # stagnation_limit=3, convergence_limit=5
        init_search_state("anthropic", run_id="run035", output_dir=tmp_path, stagnation_limit=2, convergence_limit=4)
        # Round 1: seed front
        _register_and_score("run035", "v1", 0.9, 0.01, tmp_path)
        advance_round("run035", output_dir=tmp_path)
        # Rounds 2-3: no improvement → stagnation_count reaches 2 (== stagnation_limit)
        for i in range(2, 4):
            _register_and_score("run035", f"dominated-v{i}", 0.1, 10.0, tmp_path)
            summary = advance_round("run035", output_dir=tmp_path)
        assert summary.mutation_mode == "exploratory"

    def test_mutation_mode_resets_to_targeted_after_improvement(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run036", output_dir=tmp_path, stagnation_limit=2, convergence_limit=4)
        # Seed
        _register_and_score("run036", "v1", 0.9, 0.01, tmp_path)
        advance_round("run036", output_dir=tmp_path)
        # Two rounds of stagnation → exploratory
        for i in range(2, 4):
            _register_and_score("run036", f"dominated-{i}", 0.1, 10.0, tmp_path)
            advance_round("run036", output_dir=tmp_path)
        # Verify exploratory before improvement
        s = get_search_state("run036", output_dir=tmp_path)
        assert s.mutation_mode == "exploratory"
        # Now an incomparable improvement
        _register_and_score("run036", "v-improve", 0.95, 0.1, tmp_path)
        summary = advance_round("run036", output_dir=tmp_path)
        assert summary.mutation_mode == "targeted"

    def test_converges_at_convergence_limit(self, tmp_path) -> None:
        # convergence_limit=3, stagnation_limit=2
        init_search_state("anthropic", run_id="run037", output_dir=tmp_path, stagnation_limit=2, convergence_limit=3)
        # Seed front
        _register_and_score("run037", "v1", 0.9, 0.01, tmp_path)
        advance_round("run037", output_dir=tmp_path)
        # 3 stagnating rounds → convergence_limit reached
        converged_summary = None
        for i in range(2, 5):
            _register_and_score("run037", f"stag-{i}", 0.1, 10.0, tmp_path)
            converged_summary = advance_round("run037", output_dir=tmp_path)
        assert converged_summary is not None
        updated = get_search_state("run037", output_dir=tmp_path)
        assert updated.converged is True

    def test_max_rounds_forces_convergence(self, tmp_path) -> None:
        init_search_state(
            "anthropic", run_id="run038", output_dir=tmp_path, max_rounds=2, stagnation_limit=3, convergence_limit=5
        )
        # Round 1
        _register_and_score("run038", "v1", 0.9, 0.01, tmp_path)
        advance_round("run038", output_dir=tmp_path)
        # Round 2 — hits max_rounds
        _register_and_score("run038", "v2", 0.95, 0.005, tmp_path)
        advance_round("run038", output_dir=tmp_path)
        updated = get_search_state("run038", output_dir=tmp_path)
        assert updated.converged is True

    def test_raises_with_no_pending_candidates(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run039", output_dir=tmp_path)
        with pytest.raises(ValueError, match="[Nn]o pending"):
            advance_round("run039", output_dir=tmp_path)

    def test_round_summary_appended_to_history(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run040", output_dir=tmp_path)
        _register_and_score("run040", "v1", 0.9, 0.01, tmp_path)
        advance_round("run040", output_dir=tmp_path)
        updated = get_search_state("run040", output_dir=tmp_path)
        assert len(updated.round_history) == 1
        assert updated.round_history[0].round == 1

    def test_pareto_front_updated_in_state(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run041", output_dir=tmp_path)
        _register_and_score("run041", "v1", 0.9, 0.01, tmp_path)
        advance_round("run041", output_dir=tmp_path)
        updated = get_search_state("run041", output_dir=tmp_path)
        assert len(updated.pareto_front) == 1
        assert updated.pareto_front[0].prompt_version == "v1"


# ---------------------------------------------------------------------------
# advance_round loop_phase behavior
# ---------------------------------------------------------------------------


class TestAdvanceRoundLoopPhase:
    def test_sets_loop_phase_review_when_not_converged(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="r1", output_dir=tmp_path, convergence_limit=5, stagnation_limit=3)
        _register_and_score("r1", "v1", 0.8, 0.5, tmp_path)
        summary = advance_round("r1", output_dir=tmp_path)
        state = get_search_state(run_id="r1", output_dir=tmp_path)
        assert not summary.converged
        assert state.loop_phase == "review"

    def test_sets_loop_phase_build_when_converged(self, tmp_path) -> None:
        # convergence_limit=2, stagnation_limit=1: converges after 2 stagnation rounds
        init_search_state("anthropic", run_id="r1", output_dir=tmp_path, convergence_limit=2, stagnation_limit=1)
        # Round 1: v1 added to empty front → new_pareto_points=1, stagnation_count=0
        _register_and_score("r1", "v1", 0.8, 0.5, tmp_path)
        advance_round("r1", output_dir=tmp_path)
        # Round 2: dominated → stagnation_count=1
        _register_and_score("r1", "v2", 0.7, 0.6, tmp_path, parent_version="v1")
        advance_round("r1", output_dir=tmp_path)
        # Round 3: dominated → stagnation_count=2 >= convergence_limit → converged
        _register_and_score("r1", "v3", 0.6, 0.7, tmp_path, parent_version="v1")
        summary = advance_round("r1", output_dir=tmp_path)
        state = get_search_state(run_id="r1", output_dir=tmp_path)
        assert summary.converged
        assert state.loop_phase == "build"


# ---------------------------------------------------------------------------
# set_loop_phase
# ---------------------------------------------------------------------------


class TestSetLoopPhase:
    def test_sets_phase(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="r1", output_dir=tmp_path)
        set_loop_phase("r1", "review", output_dir=tmp_path)
        state = get_search_state(run_id="r1", output_dir=tmp_path)
        assert state.loop_phase == "review"

    def test_raises_if_no_state(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            set_loop_phase("no_such_run", "build", output_dir=tmp_path)
