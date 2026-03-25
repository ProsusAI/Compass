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
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_and_score(
    search_state_id: str,
    prompt_version: str,
    quality_score: float,
    cost: float,
    tmp_path,
    parent_version: str | None = None,
) -> None:
    """Register a candidate and record its eval result in one call."""
    register_candidate(
        search_state_id,
        prompt_version,
        parent_version=parent_version,
        output_dir=tmp_path,
    )
    record_eval_result(
        search_state_id,
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
        state = init_search_state("anthropic", output_dir=tmp_path)
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
        state = init_search_state("anthropic", output_dir=tmp_path)
        state_file = tmp_path / state.search_state_id / "search_state.json"
        assert state_file.exists()

    def test_generates_unique_ids(self, tmp_path) -> None:
        s1 = init_search_state("anthropic", output_dir=tmp_path)
        s2 = init_search_state("anthropic", output_dir=tmp_path)
        assert s1.search_state_id != s2.search_state_id

    def test_id_is_12_hex_chars(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        assert len(state.search_state_id) == 12
        assert all(c in "0123456789abcdef" for c in state.search_state_id)


class TestGetSearchState:
    def test_loads_persisted_state(self, tmp_path) -> None:
        original = init_search_state("anthropic", output_dir=tmp_path)
        loaded = get_search_state(original.search_state_id, output_dir=tmp_path)
        assert loaded.search_state_id == original.search_state_id
        assert loaded.backend == original.backend

    def test_raises_for_missing_state(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            get_search_state("nonexistent", output_dir=tmp_path)


# ---------------------------------------------------------------------------
# Task 7: register_candidate
# ---------------------------------------------------------------------------


class TestRegisterCandidate:
    def test_writes_to_pending_candidates_json(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        register_candidate(state.search_state_id, "v1", output_dir=tmp_path)
        pending_file = tmp_path / state.search_state_id / "pending_candidates.json"
        assert pending_file.exists()

    def test_candidate_appears_in_pending(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        register_candidate(state.search_state_id, "v1", output_dir=tmp_path)
        pending = _load_pending(state.search_state_id, tmp_path)
        assert len(pending) == 1
        assert pending[0].prompt_version == "v1"
        assert pending[0].quality_score == 0.0
        assert pending[0].cost == 0.0

    def test_multiple_candidates_in_pending(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        register_candidate(state.search_state_id, "v1", output_dir=tmp_path)
        register_candidate(state.search_state_id, "v2", output_dir=tmp_path)
        pending = _load_pending(state.search_state_id, tmp_path)
        assert len(pending) == 2

    def test_parent_version_stored(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        register_candidate(state.search_state_id, "v2", parent_version="v1", output_dir=tmp_path)
        pending = _load_pending(state.search_state_id, tmp_path)
        assert pending[0].parent_version == "v1"

    def test_returns_current_state(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        returned = register_candidate(state.search_state_id, "v1", output_dir=tmp_path)
        assert returned.search_state_id == state.search_state_id

    def test_duplicate_in_pending_raises(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        register_candidate(state.search_state_id, "v1", output_dir=tmp_path)
        with pytest.raises(ValueError, match="v1"):
            register_candidate(state.search_state_id, "v1", output_dir=tmp_path)

    def test_duplicate_in_front_raises(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        _register_and_score(state.search_state_id, "v1", 0.9, 0.01, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        with pytest.raises(ValueError, match="v1"):
            register_candidate(state.search_state_id, "v1", output_dir=tmp_path)

    def test_duplicate_in_history_raises(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        # Register v1 and advance — v1 moves to history candidates_evaluated
        _register_and_score(state.search_state_id, "v1", 0.9, 0.01, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        # Register v2 (low quality so v1 stays on front), advance again
        _register_and_score(state.search_state_id, "v2", 0.5, 0.5, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        # v2 appeared in round_history[1].candidates_evaluated — duplicate
        with pytest.raises(ValueError, match="v2"):
            register_candidate(state.search_state_id, "v2", output_dir=tmp_path)


# ---------------------------------------------------------------------------
# Task 8: record_eval_result
# ---------------------------------------------------------------------------


class TestRecordEvalResult:
    def test_updates_quality_and_cost(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        register_candidate(state.search_state_id, "v1", output_dir=tmp_path)
        record_eval_result(state.search_state_id, "v1", quality_score=0.85, cost=0.02, output_dir=tmp_path)
        pending = _load_pending(state.search_state_id, tmp_path)
        assert pending[0].quality_score == 0.85
        assert pending[0].cost == 0.02

    def test_returns_correct_dict(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        register_candidate(state.search_state_id, "v1", output_dir=tmp_path)
        result = record_eval_result(state.search_state_id, "v1", quality_score=0.9, cost=0.05, output_dir=tmp_path)
        assert result == {"prompt_version": "v1", "quality_score": 0.9, "cost": 0.05}

    def test_unknown_version_raises(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        with pytest.raises(ValueError, match="unknown_v"):
            record_eval_result(
                state.search_state_id,
                "unknown_v",
                quality_score=0.5,
                cost=0.1,
                output_dir=tmp_path,
            )

    def test_only_target_candidate_updated(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        register_candidate(state.search_state_id, "v1", output_dir=tmp_path)
        register_candidate(state.search_state_id, "v2", output_dir=tmp_path)
        record_eval_result(state.search_state_id, "v1", quality_score=0.9, cost=0.01, output_dir=tmp_path)
        pending = _load_pending(state.search_state_id, tmp_path)
        v2 = next(c for c in pending if c.prompt_version == "v2")
        assert v2.quality_score == 0.0
        assert v2.cost == 0.0


# ---------------------------------------------------------------------------
# Task 9: advance_round
# ---------------------------------------------------------------------------


class TestAdvanceRound:
    def test_first_round_adds_to_front(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        _register_and_score(state.search_state_id, "v1", 0.9, 0.01, tmp_path)
        summary = advance_round(state.search_state_id, output_dir=tmp_path)
        assert summary.round == 1
        assert summary.new_pareto_points == 1
        assert summary.front_size == 1
        assert "v1" in summary.candidates_evaluated

    def test_state_round_incremented(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        _register_and_score(state.search_state_id, "v1", 0.9, 0.01, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        updated = get_search_state(state.search_state_id, output_dir=tmp_path)
        assert updated.round == 1

    def test_pending_cleared_after_advance(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        _register_and_score(state.search_state_id, "v1", 0.9, 0.01, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        pending = _load_pending(state.search_state_id, tmp_path)
        assert pending == []

    def test_stagnation_increments_when_no_improvement(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        # Round 1: add v1 to front
        _register_and_score(state.search_state_id, "v1", 0.9, 0.01, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        # Round 2: dominated candidate — no improvement
        _register_and_score(state.search_state_id, "v2", 0.5, 0.5, tmp_path)
        summary = advance_round(state.search_state_id, output_dir=tmp_path)
        assert summary.stagnation_count == 1
        assert summary.new_pareto_points == 0

    def test_stagnation_resets_on_improvement(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        # Round 1: add v1 to front
        _register_and_score(state.search_state_id, "v1", 0.9, 0.01, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        # Round 2: no improvement
        _register_and_score(state.search_state_id, "v2", 0.5, 0.5, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        # Round 3: improvement (incomparable — new pareto point)
        _register_and_score(state.search_state_id, "v3", 0.95, 0.1, tmp_path)
        summary = advance_round(state.search_state_id, output_dir=tmp_path)
        assert summary.stagnation_count == 0
        assert summary.new_pareto_points > 0

    def test_switches_to_exploratory_at_stagnation_limit(self, tmp_path) -> None:
        # stagnation_limit=3, convergence_limit=5
        state = init_search_state("anthropic", output_dir=tmp_path, stagnation_limit=2, convergence_limit=4)
        # Round 1: seed front
        _register_and_score(state.search_state_id, "v1", 0.9, 0.01, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        # Rounds 2-3: no improvement → stagnation_count reaches 2 (== stagnation_limit)
        for i in range(2, 4):
            _register_and_score(state.search_state_id, f"dominated-v{i}", 0.1, 10.0, tmp_path)
            summary = advance_round(state.search_state_id, output_dir=tmp_path)
        assert summary.mutation_mode == "exploratory"

    def test_mutation_mode_resets_to_targeted_after_improvement(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path, stagnation_limit=2, convergence_limit=4)
        # Seed
        _register_and_score(state.search_state_id, "v1", 0.9, 0.01, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        # Two rounds of stagnation → exploratory
        for i in range(2, 4):
            _register_and_score(state.search_state_id, f"dominated-{i}", 0.1, 10.0, tmp_path)
            advance_round(state.search_state_id, output_dir=tmp_path)
        # Verify exploratory before improvement
        s = get_search_state(state.search_state_id, output_dir=tmp_path)
        assert s.mutation_mode == "exploratory"
        # Now an incomparable improvement
        _register_and_score(state.search_state_id, "v-improve", 0.95, 0.1, tmp_path)
        summary = advance_round(state.search_state_id, output_dir=tmp_path)
        assert summary.mutation_mode == "targeted"

    def test_converges_at_convergence_limit(self, tmp_path) -> None:
        # convergence_limit=3, stagnation_limit=2
        state = init_search_state("anthropic", output_dir=tmp_path, stagnation_limit=2, convergence_limit=3)
        # Seed front
        _register_and_score(state.search_state_id, "v1", 0.9, 0.01, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        # 3 stagnating rounds → convergence_limit reached
        converged_summary = None
        for i in range(2, 5):
            _register_and_score(state.search_state_id, f"stag-{i}", 0.1, 10.0, tmp_path)
            converged_summary = advance_round(state.search_state_id, output_dir=tmp_path)
        assert converged_summary is not None
        updated = get_search_state(state.search_state_id, output_dir=tmp_path)
        assert updated.converged is True

    def test_max_rounds_forces_convergence(self, tmp_path) -> None:
        state = init_search_state(
            "anthropic", output_dir=tmp_path, max_rounds=2, stagnation_limit=3, convergence_limit=5
        )
        # Round 1
        _register_and_score(state.search_state_id, "v1", 0.9, 0.01, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        # Round 2 — hits max_rounds
        _register_and_score(state.search_state_id, "v2", 0.95, 0.005, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        updated = get_search_state(state.search_state_id, output_dir=tmp_path)
        assert updated.converged is True

    def test_raises_with_no_pending_candidates(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        with pytest.raises(ValueError, match="[Nn]o pending"):
            advance_round(state.search_state_id, output_dir=tmp_path)

    def test_round_summary_appended_to_history(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        _register_and_score(state.search_state_id, "v1", 0.9, 0.01, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        updated = get_search_state(state.search_state_id, output_dir=tmp_path)
        assert len(updated.round_history) == 1
        assert updated.round_history[0].round == 1

    def test_pareto_front_updated_in_state(self, tmp_path) -> None:
        state = init_search_state("anthropic", output_dir=tmp_path)
        _register_and_score(state.search_state_id, "v1", 0.9, 0.01, tmp_path)
        advance_round(state.search_state_id, output_dir=tmp_path)
        updated = get_search_state(state.search_state_id, output_dir=tmp_path)
        assert len(updated.pareto_front) == 1
        assert updated.pareto_front[0].prompt_version == "v1"
