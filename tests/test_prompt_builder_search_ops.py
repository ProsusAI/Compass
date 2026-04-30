"""Tests for odysseus.agents.prompt_builder_search_ops."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from odysseus.agents.prompt_builder.search import Candidate
from odysseus.agents.prompt_builder.search_ops import (
    _load_pending,
    _loop_signal_path,
    _save_loop_signal,
    _save_pending,
    _save_state,
    advance_round,
    get_candidate_example_ids,
    get_search_state,
    init_search_state,
    record_eval_result,
    register_candidate,
    set_loop_phase,
)
from odysseus.agents.review.models import LoopSignal

_RESOLVE_PROJECT_DIR = "odysseus.project_dir.resolve_project_dir"
_SEARCH_OPS_PATCH = "odysseus.agents.prompt_builder.search_ops.get_project_dir"


@contextmanager
def _patch_project_dir(tmp_path: Path):
    """Patch project dir resolution in the search ops module."""
    with patch(_SEARCH_OPS_PATCH, return_value=tmp_path):
        yield

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
        assert state.elite_set == []
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

    def test_stores_example_ids_in_pending(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run-ex1", output_dir=tmp_path)
        register_candidate("run-ex1", "v1", example_ids=["ex-a", "ex-b"], output_dir=tmp_path)
        pending = _load_pending("run-ex1", tmp_path)
        assert pending[0].example_ids == ["ex-a", "ex-b"]

    def test_example_ids_default_empty_in_pending(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run-ex2", output_dir=tmp_path)
        register_candidate("run-ex2", "v1", output_dir=tmp_path)
        pending = _load_pending("run-ex2", tmp_path)
        assert pending[0].example_ids == []


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
        assert summary.new_elite_entries == 1
        assert summary.elite_size == 1
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
        assert summary.new_elite_entries == 0

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
        assert summary.new_elite_entries > 0

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

    def test_elite_set_updated_in_state(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run041", output_dir=tmp_path)
        _register_and_score("run041", "v1", 0.9, 0.01, tmp_path)
        advance_round("run041", output_dir=tmp_path)
        updated = get_search_state("run041", output_dir=tmp_path)
        assert len(updated.elite_set) == 1
        assert updated.elite_set[0].prompt_version == "v1"


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
        # Round 1: v1 added to empty elite set → new_elite_entries=1, stagnation_count=0
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


# ---------------------------------------------------------------------------
# advance_round + loop_signal integration
# ---------------------------------------------------------------------------


class TestAdvanceRoundLoopSignal:
    def test_refine_signal_resets_stagnation(self, tmp_path) -> None:
        """A refine signal with suggested_budget prevents convergence by resetting stagnation."""
        # convergence_limit=5, stagnation_limit=3 — would converge at stagnation_count=5
        init_search_state("anthropic", run_id="r1", output_dir=tmp_path, stagnation_limit=3, convergence_limit=5)
        _register_and_score("r1", "v1", 0.9, 0.01, tmp_path)
        advance_round("r1", output_dir=tmp_path)
        # 4 stagnating rounds → stagnation_count=4, one away from convergence
        for i in range(2, 6):
            _register_and_score("r1", f"stag-{i}", 0.1, 10.0, tmp_path)
            advance_round("r1", output_dir=tmp_path)
        state = get_search_state("r1", output_dir=tmp_path)
        assert state.stagnation_count == 4
        assert not state.converged

        # Write refine signal with budget extension
        _save_loop_signal("r1", LoopSignal(action="refine", reason="untried mutations", suggested_budget=3), tmp_path)

        # Next stagnating round would normally hit convergence_limit=5
        _register_and_score("r1", "stag-6", 0.1, 10.0, tmp_path)
        summary = advance_round("r1", output_dir=tmp_path)
        assert not summary.converged
        assert summary.stagnation_count == 0
        state = get_search_state("r1", output_dir=tmp_path)
        assert state.convergence_limit == 8  # max(convergence_limit(5)+suggested_budget(3), stagnation_limit+1=4)

    def test_refine_signal_overrides_mutation_mode(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="r1", output_dir=tmp_path)
        _register_and_score("r1", "v1", 0.9, 0.01, tmp_path)
        advance_round("r1", output_dir=tmp_path)

        _save_loop_signal(
            "r1",
            LoopSignal(action="refine", reason="diversity collapse", suggested_mutation_mode="exploratory"),
            tmp_path,
        )

        _register_and_score("r1", "v2", 0.95, 0.005, tmp_path)
        summary = advance_round("r1", output_dir=tmp_path)
        assert summary.mutation_mode == "exploratory"

    def test_refine_signal_consumed_once(self, tmp_path) -> None:
        """Signal file is deleted after advance_round consumes it."""
        init_search_state("anthropic", run_id="r1", output_dir=tmp_path)
        _register_and_score("r1", "v1", 0.9, 0.01, tmp_path)
        advance_round("r1", output_dir=tmp_path)

        _save_loop_signal(
            "r1", LoopSignal(action="refine", reason="test", suggested_mutation_mode="exploratory"), tmp_path
        )
        assert _loop_signal_path("r1", tmp_path).exists()

        _register_and_score("r1", "v2", 0.95, 0.005, tmp_path)
        advance_round("r1", output_dir=tmp_path)
        assert not _loop_signal_path("r1", tmp_path).exists()

    def test_max_rounds_hard_cap_not_overridable(self, tmp_path) -> None:
        """max_rounds is a hard cap — refine signal cannot prevent it."""
        init_search_state(
            "anthropic", run_id="r1", output_dir=tmp_path, max_rounds=2, stagnation_limit=3, convergence_limit=5
        )
        _register_and_score("r1", "v1", 0.9, 0.01, tmp_path)
        advance_round("r1", output_dir=tmp_path)

        _save_loop_signal("r1", LoopSignal(action="refine", reason="keep going", suggested_budget=10), tmp_path)

        # Round 2 = max_rounds → must converge regardless of signal
        _register_and_score("r1", "v2", 0.95, 0.005, tmp_path)
        summary = advance_round("r1", output_dir=tmp_path)
        assert summary.converged

    def test_no_signal_file_uses_mechanical_logic(self, tmp_path) -> None:
        """Without a signal file, advance_round behaves identically to before."""
        init_search_state("anthropic", run_id="r1", output_dir=tmp_path, stagnation_limit=2, convergence_limit=3)
        _register_and_score("r1", "v1", 0.9, 0.01, tmp_path)
        advance_round("r1", output_dir=tmp_path)
        # 3 stagnating rounds → converges mechanically
        for i in range(2, 5):
            _register_and_score("r1", f"stag-{i}", 0.1, 10.0, tmp_path)
            summary = advance_round("r1", output_dir=tmp_path)
        assert summary.converged


# ---------------------------------------------------------------------------
# get_candidate_example_ids
# ---------------------------------------------------------------------------


class TestGetCandidateExampleIds:
    def test_returns_ids_for_front_candidate(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run-gce1", output_dir=tmp_path)
        register_candidate("run-gce1", "v1", example_ids=["ex-1", "ex-2"], output_dir=tmp_path)
        record_eval_result("run-gce1", "v1", quality_score=0.9, cost=0.01, output_dir=tmp_path)
        advance_round("run-gce1", output_dir=tmp_path)
        ids = get_candidate_example_ids("run-gce1", "v1", output_dir=tmp_path)
        assert ids == ["ex-1", "ex-2"]

    def test_returns_empty_when_no_example_ids(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run-gce2", output_dir=tmp_path)
        register_candidate("run-gce2", "v1", output_dir=tmp_path)
        record_eval_result("run-gce2", "v1", quality_score=0.9, cost=0.01, output_dir=tmp_path)
        advance_round("run-gce2", output_dir=tmp_path)
        ids = get_candidate_example_ids("run-gce2", "v1", output_dir=tmp_path)
        assert ids == []

    def test_raises_for_unknown_version(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run-gce3", output_dir=tmp_path)
        register_candidate("run-gce3", "v1", output_dir=tmp_path)
        record_eval_result("run-gce3", "v1", quality_score=0.9, cost=0.01, output_dir=tmp_path)
        advance_round("run-gce3", output_dir=tmp_path)
        with pytest.raises(ValueError, match="v99"):
            get_candidate_example_ids("run-gce3", "v99", output_dir=tmp_path)

    def test_example_ids_survive_advance_round(self, tmp_path) -> None:
        init_search_state("anthropic", run_id="run-gce4", output_dir=tmp_path)
        register_candidate("run-gce4", "v1", example_ids=["ex-a"], output_dir=tmp_path)
        record_eval_result("run-gce4", "v1", quality_score=0.9, cost=0.01, output_dir=tmp_path)
        advance_round("run-gce4", output_dir=tmp_path)
        # Register and advance a second round to verify persistence
        register_candidate("run-gce4", "v2", example_ids=["ex-b", "ex-c"], output_dir=tmp_path)
        record_eval_result("run-gce4", "v2", quality_score=0.85, cost=0.005, output_dir=tmp_path)
        advance_round("run-gce4", output_dir=tmp_path)
        # Both should still be on front (incomparable: v1 higher quality, v2 lower cost)
        ids_v1 = get_candidate_example_ids("run-gce4", "v1", output_dir=tmp_path)
        assert ids_v1 == ["ex-a"]


# ---------------------------------------------------------------------------
# convergence_reason on RoundSummary via advance_round
# ---------------------------------------------------------------------------


class TestConvergenceReason:
    def test_max_rounds_sets_convergence_reason(self, tmp_path) -> None:
        """Convergence triggered by hitting max_rounds → convergence_reason='max_rounds'."""
        init_search_state(
            "anthropic",
            run_id="cr-run1",
            output_dir=tmp_path,
            max_rounds=2,
            stagnation_limit=3,
            convergence_limit=5,
        )
        # Round 1
        _register_and_score("cr-run1", "v1", 0.9, 0.01, tmp_path)
        advance_round("cr-run1", output_dir=tmp_path)
        # Round 2 — hits max_rounds=2
        _register_and_score("cr-run1", "v2", 0.95, 0.005, tmp_path)
        summary = advance_round("cr-run1", output_dir=tmp_path)
        assert summary.converged is True
        assert summary.convergence_reason == "max_rounds"

    def test_stagnation_sets_convergence_reason(self, tmp_path) -> None:
        """Convergence triggered by stagnation_count >= convergence_limit → 'stagnation'."""
        init_search_state(
            "anthropic",
            run_id="cr-run2",
            output_dir=tmp_path,
            max_rounds=50,
            stagnation_limit=2,
            convergence_limit=3,
        )
        # Round 1: seed front
        _register_and_score("cr-run2", "v1", 0.9, 0.01, tmp_path)
        advance_round("cr-run2", output_dir=tmp_path)
        # 3 stagnating rounds → convergence_limit=3 reached
        last_summary = None
        for i in range(2, 5):
            _register_and_score("cr-run2", f"stag-{i}", 0.1, 10.0, tmp_path)
            last_summary = advance_round("cr-run2", output_dir=tmp_path)
        assert last_summary is not None
        assert last_summary.converged is True
        assert last_summary.convergence_reason == "stagnation"

    def test_no_convergence_reason_is_none(self, tmp_path) -> None:
        """Non-converged round → convergence_reason is None."""
        init_search_state(
            "anthropic",
            run_id="cr-run3",
            output_dir=tmp_path,
            max_rounds=50,
            stagnation_limit=3,
            convergence_limit=5,
        )
        _register_and_score("cr-run3", "v1", 0.9, 0.01, tmp_path)
        summary = advance_round("cr-run3", output_dir=tmp_path)
        assert summary.converged is False
        assert summary.convergence_reason is None


# ---------------------------------------------------------------------------
# advance_step_tool dispatch
# ---------------------------------------------------------------------------


class TestAdvanceStepTool:
    """Tests for the advance_step_tool strategy-dispatch shape."""

    async def test_hill_climb_arm_behaves_like_advance_round(self, tmp_path: Path) -> None:
        """advance_step_tool with algorithm='hill_climb' produces a valid RoundSummary."""
        from odysseus.mcp import (
            advance_step_tool,
            init_search_state_tool,
            record_eval_result_tool,
            register_candidate_tool,
        )

        with (
            patch(_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            patch(_SEARCH_OPS_PATCH, return_value=tmp_path),
        ):
            # Set up stage 4 guard artifact
            analysis_dir = tmp_path / "outputs" / "run-st1" / "analysis"
            analysis_dir.mkdir(parents=True, exist_ok=True)
            (analysis_dir / "dev.jsonl").write_text("")

            # Init with default algorithm="hill_climb"
            state_json = await init_search_state_tool(
                ctx=None,
                run_id="run-st1",
                backend="test",
                algorithm="hill_climb",
            )
            state_data = json.loads(state_json)
            assert state_data["algorithm"] == "hill_climb"

            await register_candidate_tool("run-st1", "v1")
            await record_eval_result_tool("run-st1", "v1", 0.85, 0.12)

            result_json = await advance_step_tool("run-st1")
            result = json.loads(result_json)
            assert result["round"] == 1
            assert result["new_elite_entries"] == 1

    async def test_non_hill_climb_raises_not_implemented(self, tmp_path: Path) -> None:
        """advance_step_tool raises NotImplementedError for algorithms not yet implemented."""
        from odysseus.mcp import advance_step_tool, init_search_state_tool

        with (
            patch(_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            patch(_SEARCH_OPS_PATCH, return_value=tmp_path),
        ):
            analysis_dir = tmp_path / "outputs" / "run-st2" / "analysis"
            analysis_dir.mkdir(parents=True, exist_ok=True)
            (analysis_dir / "dev.jsonl").write_text("")

            await init_search_state_tool(
                ctx=None,
                run_id="run-st2",
                backend="test",
                # Force an unimplemented algorithm into the state
                algorithm="emosa",
            )

            with pytest.raises(NotImplementedError, match="emosa"):
                await advance_step_tool("run-st2")


# ---------------------------------------------------------------------------
# eval_status lifecycle (Commit 1 — A2)
# ---------------------------------------------------------------------------


class TestEvalStatusLifecycle:
    """Tests for active_evals guard and eval_status filtering in advance_round."""

    def test_advance_round_blocked_by_active_evals(self, tmp_path: Path) -> None:
        """advance_round raises ValueError when active_evals is non-empty."""
        init_search_state("anthropic", run_id="aes-run1", output_dir=tmp_path)
        _register_and_score("aes-run1", "v1", 0.9, 0.01, tmp_path)

        # Inject active_evals into the persisted state to simulate in-flight eval.
        state = get_search_state("aes-run1", output_dir=tmp_path)
        updated = state.model_copy(update={"active_evals": ["v3"]})
        _save_state("aes-run1", updated, tmp_path)

        with pytest.raises(ValueError, match="v3"):
            advance_round("aes-run1", output_dir=tmp_path)

    def test_advance_round_filters_failed_from_elite_update(self, tmp_path: Path) -> None:
        """Failed candidates are excluded; only scored candidates enter the elite set."""
        init_search_state("anthropic", run_id="aes-run2", output_dir=tmp_path)

        # Build pending list manually: v2 scored, v3 failed.
        pending = [
            Candidate(
                prompt_version="v2",
                parent_version=None,
                quality_score=0.9,
                cost=0.01,
                round_introduced=1,
                eval_status="complete",
            ),
            Candidate(
                prompt_version="v3",
                parent_version=None,
                quality_score=0.0,
                cost=0.0,
                round_introduced=1,
                eval_status="failed",
            ),
        ]
        _save_pending("aes-run2", pending, tmp_path)

        advance_round("aes-run2", output_dir=tmp_path)
        state = get_search_state("aes-run2", output_dir=tmp_path)

        versions_on_elite = {c.prompt_version for c in state.elite_set}
        assert "v2" in versions_on_elite
        assert "v3" not in versions_on_elite
        assert len(state.elite_set) == 1

    def test_advance_round_all_failed_increments_stagnation(self, tmp_path: Path) -> None:
        """When all pending candidates failed, stagnation increments and elite is unchanged."""
        init_search_state("anthropic", run_id="aes-run3", output_dir=tmp_path)

        # Seed the elite set via a normal first round.
        _register_and_score("aes-run3", "v1", 0.9, 0.01, tmp_path)
        advance_round("aes-run3", output_dir=tmp_path)
        state_after_r1 = get_search_state("aes-run3", output_dir=tmp_path)
        assert len(state_after_r1.elite_set) == 1

        # Round 2: both candidates failed.
        pending = [
            Candidate(
                prompt_version="v2",
                parent_version=None,
                quality_score=0.0,
                cost=0.0,
                round_introduced=2,
                eval_status="failed",
            ),
            Candidate(
                prompt_version="v3",
                parent_version=None,
                quality_score=0.0,
                cost=0.0,
                round_introduced=2,
                eval_status="failed",
            ),
        ]
        _save_pending("aes-run3", pending, tmp_path)

        summary = advance_round("aes-run3", output_dir=tmp_path)
        state = get_search_state("aes-run3", output_dir=tmp_path)

        assert state.stagnation_count == 1
        assert len(state.elite_set) == 1
        assert state.elite_set[0].prompt_version == "v1"
        assert summary.round_routing_cost == 0.0

    def test_register_candidate_sets_eval_status_pending(self, tmp_path: Path) -> None:
        """register_candidate without explicit eval_status sets it to 'pending'."""
        init_search_state("anthropic", run_id="aes-run4", output_dir=tmp_path)
        register_candidate("aes-run4", "v1", output_dir=tmp_path)
        pending = _load_pending("aes-run4", tmp_path)
        assert len(pending) == 1
        assert pending[0].eval_status == "pending"

    def test_record_eval_result_sets_eval_status_complete(self, tmp_path: Path) -> None:
        """record_eval_result transitions eval_status from 'pending' to 'complete'."""
        init_search_state("anthropic", run_id="aes-run5", output_dir=tmp_path)
        register_candidate("aes-run5", "v1", output_dir=tmp_path)
        record_eval_result("aes-run5", "v1", quality_score=0.85, cost=0.02, output_dir=tmp_path)
        pending = _load_pending("aes-run5", tmp_path)
        assert pending[0].eval_status == "complete"

    def test_advance_round_treats_none_eval_status_as_complete(self, tmp_path: Path) -> None:
        """Backward compat: eval_status=None (old state files) is treated as 'complete'."""
        init_search_state("anthropic", run_id="aes-run6", output_dir=tmp_path)

        # Simulate an old-format candidate with eval_status=None and a real score.
        pending = [
            Candidate(
                prompt_version="v1",
                parent_version=None,
                quality_score=0.9,
                cost=0.01,
                round_introduced=1,
                eval_status=None,  # old state file — no eval_status field
            ),
        ]
        _save_pending("aes-run6", pending, tmp_path)

        advance_round("aes-run6", output_dir=tmp_path)
        state = get_search_state("aes-run6", output_dir=tmp_path)

        # v1 should be on the elite set — None treated as "complete".
        assert any(c.prompt_version == "v1" for c in state.elite_set)
