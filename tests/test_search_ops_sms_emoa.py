"""Tests for SMS-EMOA wiring in search_ops.py and prompt_building_tools.py.

Coverage:
1. advance_warmup_batch: scored seeds round-tripped, warm_up_complete flips,
   population == mu, hypervolume_history gets initial value, iteration stays 0,
   evaluations_used reflects mu evals.
2. advance_round_sms_emoa happy path: child + population union -> reduce ->
   population stays size mu; iteration increments; hypervolume_history grows;
   evaluations_used increments; evicted_version recorded; reduce_case is A/B/C.
3. advance_round_sms_emoa budget termination.
4. advance_round_sms_emoa plateau termination.
5. _advance_sms_emoa arm: dispatch routes to the right inner function per
   loop_phase; unsupported phase raises ValueError.
6. advance_step_tool integration: algorithm="sms_emoa" + loop_phase="warmup_reduce"
   returns valid JSON RoundSummary; clear_build_dispatched is invoked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, patch

import pytest

from odysseus.agents.prompt_builder.search import Candidate, RoundSummary, SearchState
from odysseus.agents.prompt_builder.search_ops import (
    _load_pending,
    _save_state,
    advance_round_sms_emoa,
    advance_warmup_batch,
    get_search_state,
    init_search_state,
    record_eval_result,
    register_candidate,
)

_SEARCH_OPS_PATCH = "odysseus.agents.prompt_builder.search_ops.get_project_dir"
_RESOLVE_PROJECT_DIR = "odysseus.project_dir.resolve_project_dir"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_candidate(
    prompt_version: str,
    quality_score: float,
    cost: float,
    round_introduced: int = 1,
    parent_version: str | None = None,
    eval_status: Literal["pending", "running", "complete", "failed"] = "complete",
) -> Candidate:
    return Candidate(
        prompt_version=prompt_version,
        parent_version=parent_version,
        quality_score=quality_score,
        cost=cost,
        round_introduced=round_introduced,
        eval_status=eval_status,
    )


def _init_sms_emoa_state(
    run_id: str,
    tmp_path: Path,
    mu: int = 4,
    evaluation_budget: int = 50,
    stagnation_window: int = 5,
    reference_delta: float = 0.05,
) -> SearchState:
    """Init a SearchState with algorithm=sms_emoa and minimal pocket."""
    return init_search_state(
        backend="anthropic",
        run_id=run_id,
        output_dir=tmp_path,
        algorithm="sms_emoa",
        algorithm_state={
            "mu": mu,
            "evaluation_budget": evaluation_budget,
            "evaluations_used": 0,
            "stagnation_window": stagnation_window,
            "reference_delta": reference_delta,
            "warm_up_complete": False,
            "population": [],
            "hypervolume_history": [],
            "iteration": 0,
        },
    )


def _seed_warmup_population(
    run_id: str,
    tmp_path: Path,
    seeds: list[tuple[str, float, float]],
) -> None:
    """Register and score seeds for warm-up (writes directly to pending)."""
    for version, quality, cost in seeds:
        register_candidate(run_id, version, output_dir=tmp_path)
        record_eval_result(run_id, version, quality_score=quality, cost=cost, output_dir=tmp_path)


def _complete_warmup(
    run_id: str,
    tmp_path: Path,
    mu: int = 4,
    evaluation_budget: int = 50,
) -> tuple[SearchState, RoundSummary]:
    """Run advance_warmup_batch and return (state_after, summary)."""
    summary = advance_warmup_batch(run_id, output_dir=tmp_path)
    state = get_search_state(run_id, output_dir=tmp_path)
    return state, summary


# ---------------------------------------------------------------------------
# 1. advance_warmup_batch
# ---------------------------------------------------------------------------


class TestAdvanceWarmupBatch:
    def test_population_size_equals_mu(self, tmp_path: Path) -> None:
        """After warmup, population size in algorithm_state equals mu."""
        run_id = "wb_popsize"
        mu = 3
        _init_sms_emoa_state(run_id, tmp_path, mu=mu)
        _seed_warmup_population(run_id, tmp_path, [
            ("v1", 0.90, 0.10),
            ("v2", 0.70, 0.20),
            ("v3", 0.60, 0.30),
        ])
        state, summary = _complete_warmup(run_id, tmp_path, mu=mu)
        population = [Candidate.model_validate(c) for c in state.algorithm_state["population"]]
        assert len(population) == mu

    def test_warm_up_complete_flips_true(self, tmp_path: Path) -> None:
        """algorithm_state['warm_up_complete'] must be True after warmup."""
        run_id = "wb_flag"
        _init_sms_emoa_state(run_id, tmp_path, mu=2)
        _seed_warmup_population(run_id, tmp_path, [
            ("v1", 0.80, 0.15),
            ("v2", 0.65, 0.25),
        ])
        state, _ = _complete_warmup(run_id, tmp_path)
        assert state.algorithm_state["warm_up_complete"] is True

    def test_hypervolume_history_gets_initial_value(self, tmp_path: Path) -> None:
        """hypervolume_history must have exactly one entry after warmup."""
        run_id = "wb_hv"
        _init_sms_emoa_state(run_id, tmp_path, mu=2)
        _seed_warmup_population(run_id, tmp_path, [
            ("v1", 0.80, 0.10),
            ("v2", 0.65, 0.20),
        ])
        state, summary = _complete_warmup(run_id, tmp_path)
        hv_history = state.algorithm_state["hypervolume_history"]
        assert len(hv_history) == 1
        assert hv_history[0] == summary.hypervolume

    def test_iteration_stays_zero(self, tmp_path: Path) -> None:
        """iteration counter must remain 0 after warmup (no iterations consumed)."""
        run_id = "wb_iter"
        _init_sms_emoa_state(run_id, tmp_path, mu=2)
        _seed_warmup_population(run_id, tmp_path, [
            ("v1", 0.80, 0.10),
            ("v2", 0.65, 0.20),
        ])
        state, _ = _complete_warmup(run_id, tmp_path)
        assert state.algorithm_state["iteration"] == 0

    def test_evaluations_used_equals_pending_count(self, tmp_path: Path) -> None:
        """evaluations_used must reflect total pending candidates (scored + failed)."""
        run_id = "wb_evals"
        mu = 3
        _init_sms_emoa_state(run_id, tmp_path, mu=mu)
        _seed_warmup_population(run_id, tmp_path, [
            ("v1", 0.80, 0.10),
            ("v2", 0.65, 0.20),
            ("v3", 0.50, 0.30),
        ])
        state, _ = _complete_warmup(run_id, tmp_path)
        assert state.algorithm_state["evaluations_used"] == 3

    def test_pending_cleared_after_warmup(self, tmp_path: Path) -> None:
        """pending_candidates.json must be empty after warmup."""
        run_id = "wb_pending"
        _init_sms_emoa_state(run_id, tmp_path, mu=2)
        _seed_warmup_population(run_id, tmp_path, [
            ("v1", 0.80, 0.10),
            ("v2", 0.65, 0.20),
        ])
        advance_warmup_batch(run_id, output_dir=tmp_path)
        pending = _load_pending(run_id, tmp_path)
        assert pending == []

    def test_summary_reduce_case_is_warmup(self, tmp_path: Path) -> None:
        """RoundSummary.reduce_case must be 'warmup'."""
        run_id = "wb_rc"
        _init_sms_emoa_state(run_id, tmp_path, mu=2)
        _seed_warmup_population(run_id, tmp_path, [
            ("v1", 0.80, 0.10),
            ("v2", 0.65, 0.20),
        ])
        _, summary = _complete_warmup(run_id, tmp_path)
        assert summary.reduce_case == "warmup"
        assert summary.terminated is False

    def test_summary_round_increments(self, tmp_path: Path) -> None:
        """RoundSummary.round must increment by 1."""
        run_id = "wb_round"
        _init_sms_emoa_state(run_id, tmp_path, mu=2)
        _seed_warmup_population(run_id, tmp_path, [
            ("v1", 0.80, 0.10),
            ("v2", 0.65, 0.20),
        ])
        _, summary = _complete_warmup(run_id, tmp_path)
        assert summary.round == 1

    def test_raises_if_already_complete(self, tmp_path: Path) -> None:
        """advance_warmup_batch raises ValueError if warm_up_complete is True."""
        run_id = "wb_dup"
        _init_sms_emoa_state(run_id, tmp_path, mu=2)
        _seed_warmup_population(run_id, tmp_path, [
            ("v1", 0.80, 0.10),
            ("v2", 0.65, 0.20),
        ])
        advance_warmup_batch(run_id, output_dir=tmp_path)
        with pytest.raises(ValueError, match="warm_up_complete"):
            advance_warmup_batch(run_id, output_dir=tmp_path)

    def test_raises_if_too_few_scored(self, tmp_path: Path) -> None:
        """advance_warmup_batch raises ValueError when fewer than 2 scored candidates."""
        run_id = "wb_few"
        _init_sms_emoa_state(run_id, tmp_path, mu=3)
        # Only one candidate
        register_candidate(run_id, "v1", output_dir=tmp_path)
        record_eval_result(run_id, "v1", quality_score=0.8, cost=0.1, output_dir=tmp_path)
        with pytest.raises(ValueError, match="at least 2 scored"):
            advance_warmup_batch(run_id, output_dir=tmp_path)


# ---------------------------------------------------------------------------
# 2. advance_round_sms_emoa happy path
# ---------------------------------------------------------------------------


def _setup_post_warmup_state(
    run_id: str,
    tmp_path: Path,
    mu: int = 3,
    evaluation_budget: int = 50,
    stagnation_window: int = 5,
) -> SearchState:
    """Init state with warm_up_complete=True and a pre-populated population pocket."""
    seeds = [
        ("v1", 0.90, 0.10),
        ("v2", 0.70, 0.20),
        ("v3", 0.50, 0.30),
    ]
    _init_sms_emoa_state(
        run_id, tmp_path,
        mu=mu,
        evaluation_budget=evaluation_budget,
        stagnation_window=stagnation_window,
    )
    _seed_warmup_population(run_id, tmp_path, seeds)
    advance_warmup_batch(run_id, output_dir=tmp_path)
    return get_search_state(run_id, output_dir=tmp_path)


class TestAdvanceRoundSmsEmoaHappyPath:
    def test_population_stays_size_mu_after_reduce(self, tmp_path: Path) -> None:
        """After one iteration, population size remains mu."""
        run_id = "ar_popsize"
        mu = 3
        _setup_post_warmup_state(run_id, tmp_path, mu=mu)
        # Register one child
        register_candidate(run_id, "c1", parent_version="v1", output_dir=tmp_path)
        record_eval_result(run_id, "c1", quality_score=0.95, cost=0.08, output_dir=tmp_path)

        summary = advance_round_sms_emoa(run_id, output_dir=tmp_path)
        state = get_search_state(run_id, output_dir=tmp_path)
        population = [Candidate.model_validate(c) for c in state.algorithm_state["population"]]
        assert len(population) == mu
        assert summary.population_size == mu

    def test_iteration_increments(self, tmp_path: Path) -> None:
        """iteration counter increments by 1 per call."""
        run_id = "ar_iter"
        _setup_post_warmup_state(run_id, tmp_path)
        register_candidate(run_id, "c1", parent_version="v1", output_dir=tmp_path)
        record_eval_result(run_id, "c1", quality_score=0.85, cost=0.12, output_dir=tmp_path)
        advance_round_sms_emoa(run_id, output_dir=tmp_path)
        state = get_search_state(run_id, output_dir=tmp_path)
        assert state.algorithm_state["iteration"] == 1

    def test_hypervolume_history_grows_by_one(self, tmp_path: Path) -> None:
        """hypervolume_history grows by exactly 1 entry per iteration."""
        run_id = "ar_hv"
        state_before = _setup_post_warmup_state(run_id, tmp_path)
        hv_len_before = len(state_before.algorithm_state["hypervolume_history"])
        register_candidate(run_id, "c1", parent_version="v1", output_dir=tmp_path)
        record_eval_result(run_id, "c1", quality_score=0.85, cost=0.12, output_dir=tmp_path)
        advance_round_sms_emoa(run_id, output_dir=tmp_path)
        state_after = get_search_state(run_id, output_dir=tmp_path)
        assert len(state_after.algorithm_state["hypervolume_history"]) == hv_len_before + 1

    def test_evaluations_used_increments_by_one(self, tmp_path: Path) -> None:
        """evaluations_used increments by the number of pending candidates (1 child)."""
        run_id = "ar_evals"
        state_before = _setup_post_warmup_state(run_id, tmp_path)
        evals_before = state_before.algorithm_state["evaluations_used"]
        register_candidate(run_id, "c1", parent_version="v1", output_dir=tmp_path)
        record_eval_result(run_id, "c1", quality_score=0.85, cost=0.12, output_dir=tmp_path)
        advance_round_sms_emoa(run_id, output_dir=tmp_path)
        state_after = get_search_state(run_id, output_dir=tmp_path)
        assert state_after.algorithm_state["evaluations_used"] == evals_before + 1

    def test_evicted_version_recorded(self, tmp_path: Path) -> None:
        """evicted_version in RoundSummary must be a non-empty string."""
        run_id = "ar_evicted"
        _setup_post_warmup_state(run_id, tmp_path, mu=3)
        register_candidate(run_id, "c1", parent_version="v1", output_dir=tmp_path)
        record_eval_result(run_id, "c1", quality_score=0.85, cost=0.12, output_dir=tmp_path)
        summary = advance_round_sms_emoa(run_id, output_dir=tmp_path)
        assert summary.evicted_version  # non-empty
        assert isinstance(summary.evicted_version, str)

    def test_reduce_case_is_valid(self, tmp_path: Path) -> None:
        """reduce_case must be one of the three SMS-EMOA case labels."""
        valid_cases = {"A_singleton", "B_dominated", "C_delta_s"}
        run_id = "ar_rc"
        _setup_post_warmup_state(run_id, tmp_path, mu=3)
        register_candidate(run_id, "c1", parent_version="v1", output_dir=tmp_path)
        record_eval_result(run_id, "c1", quality_score=0.95, cost=0.05, output_dir=tmp_path)
        summary = advance_round_sms_emoa(run_id, output_dir=tmp_path)
        assert summary.reduce_case in valid_cases

    def test_round_increments(self, tmp_path: Path) -> None:
        """RoundSummary.round increments by 1 each call."""
        run_id = "ar_round"
        state_before = _setup_post_warmup_state(run_id, tmp_path)
        round_before = state_before.round
        register_candidate(run_id, "c1", parent_version="v1", output_dir=tmp_path)
        record_eval_result(run_id, "c1", quality_score=0.85, cost=0.12, output_dir=tmp_path)
        summary = advance_round_sms_emoa(run_id, output_dir=tmp_path)
        assert summary.round == round_before + 1

    def test_pending_cleared_after_advance(self, tmp_path: Path) -> None:
        """Pending list must be empty after advance_round_sms_emoa."""
        run_id = "ar_pending"
        _setup_post_warmup_state(run_id, tmp_path)
        register_candidate(run_id, "c1", parent_version="v1", output_dir=tmp_path)
        record_eval_result(run_id, "c1", quality_score=0.85, cost=0.12, output_dir=tmp_path)
        advance_round_sms_emoa(run_id, output_dir=tmp_path)
        assert _load_pending(run_id, tmp_path) == []


# ---------------------------------------------------------------------------
# 3. advance_round_sms_emoa budget termination
# ---------------------------------------------------------------------------


class TestAdvanceRoundSmsBudgetTermination:
    def test_budget_exhausted_sets_terminated(self, tmp_path: Path) -> None:
        """terminated=True and termination_reason='budget' when evaluations_used >= budget."""
        run_id = "budget_term"
        # Set budget very low so first iteration hits it
        _init_sms_emoa_state(
            run_id, tmp_path,
            mu=3,
            evaluation_budget=5,  # budget = 5
        )
        # Warmup uses 3 evals, leaving budget=5 with evaluations_used=3
        _seed_warmup_population(run_id, tmp_path, [
            ("v1", 0.90, 0.10),
            ("v2", 0.70, 0.20),
            ("v3", 0.50, 0.30),
        ])
        advance_warmup_batch(run_id, output_dir=tmp_path)

        # Now inject evaluations_used = 5 (= budget) into the pocket
        state = get_search_state(run_id, output_dir=tmp_path)
        new_ast = {**state.algorithm_state, "evaluations_used": 5, "evaluation_budget": 5}
        updated = state.model_copy(update={"algorithm_state": new_ast})
        _save_state(run_id, updated, tmp_path)

        register_candidate(run_id, "c1", parent_version="v1", output_dir=tmp_path)
        record_eval_result(run_id, "c1", quality_score=0.95, cost=0.05, output_dir=tmp_path)

        summary = advance_round_sms_emoa(run_id, output_dir=tmp_path)
        assert summary.terminated is True
        assert summary.termination_reason == "budget"
        assert summary.converged is True

    def test_loop_phase_set_to_build_on_termination(self, tmp_path: Path) -> None:
        """loop_phase must be 'build' when terminated (mirrors hill_climb converged logic)."""
        run_id = "budget_phase"
        _init_sms_emoa_state(run_id, tmp_path, mu=2, evaluation_budget=2)
        _seed_warmup_population(run_id, tmp_path, [
            ("v1", 0.90, 0.10),
            ("v2", 0.70, 0.20),
        ])
        advance_warmup_batch(run_id, output_dir=tmp_path)

        # Force budget exhausted
        state = get_search_state(run_id, output_dir=tmp_path)
        new_ast = {**state.algorithm_state, "evaluations_used": 2, "evaluation_budget": 2}
        updated = state.model_copy(update={"algorithm_state": new_ast})
        _save_state(run_id, updated, tmp_path)

        register_candidate(run_id, "c1", parent_version="v1", output_dir=tmp_path)
        record_eval_result(run_id, "c1", quality_score=0.95, cost=0.05, output_dir=tmp_path)
        advance_round_sms_emoa(run_id, output_dir=tmp_path)

        state_after = get_search_state(run_id, output_dir=tmp_path)
        assert state_after.loop_phase == "build"


# ---------------------------------------------------------------------------
# 4. advance_round_sms_emoa plateau termination
# ---------------------------------------------------------------------------


class TestAdvanceRoundSmsPlateau:
    def test_check_termination_plateau_fires_on_flat_window(self) -> None:
        """_check_termination returns ('plateau') when max-min of window < epsilon."""
        from odysseus.agents.prompt_builder.search_ops import _check_termination

        # 3 identical values, window=3 → max-min=0 < epsilon=0.05
        terminated, reason = _check_termination(
            evaluations_used=10,
            evaluation_budget=100,
            hv_history=[0.5, 0.5, 0.5],
            stagnation_window=3,
            stagnation_epsilon=0.05,
            iteration=5,
        )
        assert terminated is True
        assert reason == "plateau"

    def test_check_termination_no_plateau_when_hv_varies(self) -> None:
        """_check_termination does not fire plateau when HV varies in window."""
        from odysseus.agents.prompt_builder.search_ops import _check_termination

        terminated, reason = _check_termination(
            evaluations_used=10,
            evaluation_budget=100,
            hv_history=[0.3, 0.5, 0.8],
            stagnation_window=3,
            stagnation_epsilon=0.05,
            iteration=5,
        )
        assert terminated is False
        assert reason is None

    def test_plateau_integration_via_advance_round(self, tmp_path: Path) -> None:
        """advance_round_sms_emoa fires plateau when stagnation_window=1 (window trivially flat)."""
        run_id = "plateau_int"
        # stagnation_window=1 means the window is [new_hv] — max-min=0 < any epsilon
        _init_sms_emoa_state(
            run_id, tmp_path,
            mu=2,
            evaluation_budget=100,
            stagnation_window=1,
            reference_delta=0.05,
        )
        _seed_warmup_population(run_id, tmp_path, [
            ("v1", 0.80, 0.15),
            ("v2", 0.65, 0.25),
        ])
        advance_warmup_batch(run_id, output_dir=tmp_path)

        register_candidate(run_id, "c1", parent_version="v1", output_dir=tmp_path)
        record_eval_result(run_id, "c1", quality_score=0.81, cost=0.14, output_dir=tmp_path)

        summary = advance_round_sms_emoa(run_id, output_dir=tmp_path)
        # stagnation_window=1 → the single-element window always has max-min=0 → plateau
        assert summary.terminated is True
        assert summary.termination_reason == "plateau"


# ---------------------------------------------------------------------------
# 5. _advance_sms_emoa dispatch (loop_phase routing)
# ---------------------------------------------------------------------------


class TestAdvanceSmsEmoaDispatch:
    """Tests for _advance_sms_emoa dispatch logic.

    These tests write state under ``tmp_path / "outputs"`` to match what
    ``_default_output_dir()`` returns when ``get_project_dir`` is patched to
    ``tmp_path``.
    """

    def _out(self, tmp_path: Path) -> Path:
        """Return the output_dir that _default_output_dir() will resolve to."""
        return tmp_path / "outputs"

    def test_warmup_reduce_routes_to_advance_warmup_batch(self, tmp_path: Path) -> None:
        """loop_phase='warmup_reduce' must call advance_warmup_batch."""
        run_id = "disp_warmup"
        out = self._out(tmp_path)
        with patch(_SEARCH_OPS_PATCH, return_value=tmp_path):
            _init_sms_emoa_state(run_id, out, mu=2)
            _seed_warmup_population(run_id, out, [
                ("v1", 0.80, 0.10),
                ("v2", 0.65, 0.20),
            ])
            # Set loop_phase to warmup_reduce
            state = get_search_state(run_id, output_dir=out)
            updated = state.model_copy(update={"loop_phase": "warmup_reduce"})
            _save_state(run_id, updated, out)

            from odysseus.mcp.prompt_building_tools import _advance_sms_emoa

            with patch(
                "odysseus.mcp.prompt_building_tools.advance_warmup_batch",
                wraps=advance_warmup_batch,
            ) as mock_warmup:
                _advance_sms_emoa(run_id)
                mock_warmup.assert_called_once_with(run_id=run_id)

    def test_review_phase_routes_to_advance_round_sms_emoa(self, tmp_path: Path) -> None:
        """loop_phase='review' must call advance_round_sms_emoa."""
        run_id = "disp_review"
        out = self._out(tmp_path)
        with patch(_SEARCH_OPS_PATCH, return_value=tmp_path):
            _setup_post_warmup_state(run_id, out, mu=2)
            state = get_search_state(run_id, output_dir=out)
            updated = state.model_copy(update={"loop_phase": "review"})
            _save_state(run_id, updated, out)

            register_candidate(run_id, "c1", parent_version="v1", output_dir=out)
            record_eval_result(run_id, "c1", quality_score=0.85, cost=0.12, output_dir=out)

            from odysseus.mcp.prompt_building_tools import _advance_sms_emoa

            with patch(
                "odysseus.mcp.prompt_building_tools.advance_round_sms_emoa",
                wraps=advance_round_sms_emoa,
            ) as mock_round:
                _advance_sms_emoa(run_id)
                mock_round.assert_called_once_with(run_id=run_id)

    def test_build_phase_routes_to_advance_round_sms_emoa(self, tmp_path: Path) -> None:
        """loop_phase='build' must also call advance_round_sms_emoa."""
        run_id = "disp_build"
        out = self._out(tmp_path)
        with patch(_SEARCH_OPS_PATCH, return_value=tmp_path):
            _setup_post_warmup_state(run_id, out, mu=2)
            state = get_search_state(run_id, output_dir=out)
            updated = state.model_copy(update={"loop_phase": "build"})
            _save_state(run_id, updated, out)

            register_candidate(run_id, "c1", parent_version="v1", output_dir=out)
            record_eval_result(run_id, "c1", quality_score=0.85, cost=0.12, output_dir=out)

            from odysseus.mcp.prompt_building_tools import _advance_sms_emoa

            with patch(
                "odysseus.mcp.prompt_building_tools.advance_round_sms_emoa",
                wraps=advance_round_sms_emoa,
            ) as mock_round:
                _advance_sms_emoa(run_id)
                mock_round.assert_called_once_with(run_id=run_id)

    def test_unsupported_phase_raises_tool_error(self, tmp_path: Path) -> None:
        """loop_phase='warmup_seed' raises a ToolError wrapping ValueError."""
        from mcp.server.fastmcp.exceptions import ToolError

        run_id = "disp_unsupported"
        out = self._out(tmp_path)
        with patch(_SEARCH_OPS_PATCH, return_value=tmp_path):
            _init_sms_emoa_state(run_id, out, mu=2)
            # Inject an unsupported phase by writing raw JSON directly
            state_path = out / run_id / "search" / "search_state.json"
            raw = json.loads(state_path.read_text())
            raw["loop_phase"] = "warmup_seed"  # valid Literal but not handled by _advance_sms_emoa
            state_path.write_text(json.dumps(raw))

            from odysseus.mcp.prompt_building_tools import _advance_sms_emoa

            with pytest.raises(ToolError, match="unsupported loop_phase"):
                _advance_sms_emoa(run_id)


# ---------------------------------------------------------------------------
# 6. advance_step_tool integration for sms_emoa
# ---------------------------------------------------------------------------


class TestAdvanceStepToolSmsEmoa:
    @pytest.mark.asyncio
    async def test_sms_emoa_warmup_returns_valid_round_summary(self, tmp_path: Path) -> None:
        """advance_step_tool with algorithm='sms_emoa' and loop_phase='warmup_reduce'
        returns a valid JSON RoundSummary."""
        from odysseus.mcp import advance_step_tool, init_search_state_tool

        with (
            patch(_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            patch(_SEARCH_OPS_PATCH, return_value=tmp_path),
        ):
            run_id = "st_sms_wb"
            analysis_dir = tmp_path / "outputs" / run_id / "analysis"
            analysis_dir.mkdir(parents=True, exist_ok=True)
            (analysis_dir / "dev.jsonl").write_text("")

            await init_search_state_tool(
                ctx=None,
                run_id=run_id,
                backend="test",
                algorithm="sms_emoa",
                algorithm_state={
                    "mu": 2,
                    "evaluation_budget": 50,
                    "warm_up_complete": False,
                    "population": [],
                    "hypervolume_history": [],
                    "iteration": 0,
                    "evaluations_used": 0,
                    "stagnation_window": 5,
                    "reference_delta": 0.05,
                },
            )

            # init_search_state_tool writes to project_dir / "outputs" = tmp_path / "outputs"
            out = tmp_path / "outputs"

            # Seed the warmup pending
            _seed_warmup_population(run_id, out, [
                ("v1", 0.80, 0.10),
                ("v2", 0.65, 0.20),
            ])

            # Set loop_phase to warmup_reduce
            state = get_search_state(run_id, output_dir=out)
            updated = state.model_copy(update={"loop_phase": "warmup_reduce"})
            _save_state(run_id, updated, out)

            result_json = await advance_step_tool(run_id)
            result = json.loads(result_json)
            assert result["round"] == 1
            assert result["reduce_case"] == "warmup"
            assert result["terminated"] is False

    @pytest.mark.asyncio
    async def test_clear_build_dispatched_called(self, tmp_path: Path) -> None:
        """advance_step_tool must call clear_build_dispatched after SMS-EMOA advance."""
        from odysseus.mcp import advance_step_tool, init_search_state_tool

        with (
            patch(_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
            patch(_SEARCH_OPS_PATCH, return_value=tmp_path),
            patch(
                "odysseus.mcp.prompt_building_tools.clear_build_dispatched",
            ) as mock_clear,
        ):
            run_id = "st_sms_cbd"
            analysis_dir = tmp_path / "outputs" / run_id / "analysis"
            analysis_dir.mkdir(parents=True, exist_ok=True)
            (analysis_dir / "dev.jsonl").write_text("")

            await init_search_state_tool(
                ctx=None,
                run_id=run_id,
                backend="test",
                algorithm="sms_emoa",
                algorithm_state={
                    "mu": 2,
                    "evaluation_budget": 50,
                    "warm_up_complete": False,
                    "population": [],
                    "hypervolume_history": [],
                    "iteration": 0,
                    "evaluations_used": 0,
                    "stagnation_window": 5,
                    "reference_delta": 0.05,
                },
            )

            out = tmp_path / "outputs"
            _seed_warmup_population(run_id, out, [
                ("v1", 0.80, 0.10),
                ("v2", 0.65, 0.20),
            ])

            state = get_search_state(run_id, output_dir=out)
            updated = state.model_copy(update={"loop_phase": "warmup_reduce"})
            _save_state(run_id, updated, out)

            await advance_step_tool(run_id)
            mock_clear.assert_called_once_with(run_id)
