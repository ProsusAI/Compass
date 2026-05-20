"""Tests for the idempotent / guard behaviour of init_search_state.

``init_search_state`` on the pipeline trunk requires ``_BRANCH_ALGORITHM`` to
be set to a concrete algorithm (it is ``"__unset__"`` here).  All tests that
call the function directly patch ``_BRANCH_ALGORITHM`` to ``"hill_climb"`` so
the RuntimeError guard does not fire — we are testing the FileExistsError
guard, not the branch-sentinel guard.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from compass.agents.prompt_builder.search import SearchState
from compass.agents.prompt_builder.search_ops import (
    _append_archive,
    _load_pending,
    _load_state,
    _save_state,
    init_search_state,
    register_candidate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RUN_ID = "test-run"
_BACKEND = "anthropic"

_ALGO_PATCH = "compass.agents.prompt_builder.search_ops._BRANCH_ALGORITHM"
_ALGO_STATE_PATCH = "compass.agents.prompt_builder.search_ops._BRANCH_ALGORITHM_STATE"


def _init(tmp_path: Path, run_id: str = _RUN_ID) -> SearchState:
    """Call init_search_state with _BRANCH_ALGORITHM patched to 'hill_climb'."""
    with patch(_ALGO_PATCH, "hill_climb"), patch(_ALGO_STATE_PATCH, {}):
        return init_search_state(backend=_BACKEND, run_id=run_id, output_dir=tmp_path)


def _make_search_state(tmp_path: Path, run_id: str = _RUN_ID, **kwargs) -> SearchState:
    """Write a minimal search_state.json directly (bypasses init guard)."""
    state = SearchState(search_state_id=run_id, backend=_BACKEND, algorithm="hill_climb", **kwargs)
    _save_state(run_id, state, tmp_path)
    return state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_init_on_fresh_state_creates_file(tmp_path: Path) -> None:
    """No prior state file — init_search_state creates one with round == 0."""
    state_path = tmp_path / _RUN_ID / "search" / "search_state.json"
    assert not state_path.exists()

    state = _init(tmp_path)

    assert state.round == 0
    assert state_path.exists()


def test_init_on_pristine_existing_state_is_noop(tmp_path: Path) -> None:
    """Second init_search_state call on a pristine file returns the same state (no-op)."""
    first = _init(tmp_path)
    second = _init(tmp_path)

    assert first.search_state_id == second.search_state_id

    # On-disk file should still carry the original search_state_id.
    on_disk = _load_state(_RUN_ID, tmp_path)
    assert on_disk.search_state_id == first.search_state_id


def test_init_after_round_advance_raises(tmp_path: Path) -> None:
    """init_search_state raises FileExistsError after a round has been advanced."""
    from compass.agents.prompt_builder.search import Candidate, RoundSummary

    state = _init(tmp_path)

    # Synthesise post-advance state directly — avoids calling advance_round, which
    # is algorithm-specific (stub on beam/emosa/sms-emoa leaves).
    elite_candidate = Candidate(
        prompt_version="v1",
        parent_version="base",
        quality_score=0.5,
        cost=-0.1,
        round_introduced=0,
    )
    summary = RoundSummary(
        round=1,
        candidates_evaluated=["v1"],
        new_elite_entries=1,
        elite_size=1,
        mutation_mode="targeted",
        stagnation_count=0,
        converged=False,
        target_improvement=0.5,
        front_quality_spread=0.0,
        round_routing_cost=0.1,
    )
    updated = state.model_copy(update={"round": 1, "elite_set": [elite_candidate], "round_history": [summary]})
    _save_state(_RUN_ID, updated, tmp_path)

    # State now has round == 1 and a non-empty elite_set.
    state_before = _load_state(_RUN_ID, tmp_path)
    assert state_before.round == 1
    assert len(state_before.elite_set) > 0

    with pytest.raises(FileExistsError, match="already has progress"):
        _init(tmp_path)

    # State must be unchanged.
    state_after = _load_state(_RUN_ID, tmp_path)
    assert state_after.round == 1
    assert len(state_after.elite_set) > 0


def test_init_with_pending_only_raises(tmp_path: Path) -> None:
    """init_search_state raises when there are pending candidates (round still 0)."""
    _init(tmp_path)

    register_candidate(
        run_id=_RUN_ID,
        prompt_version="v1",
        parent_version="base",
        output_dir=tmp_path,
    )

    # State is still round 0 but pending is non-empty.
    pending = _load_pending(_RUN_ID, tmp_path)
    assert len(pending) == 1

    with pytest.raises(FileExistsError, match="already has progress"):
        _init(tmp_path)


def test_append_archive_writes_candidate_archive_on_normal_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """candidate_archive.json remains unconditional because search-tree viz reads it."""
    from compass.agents.prompt_builder.search import Candidate

    monkeypatch.delenv("COMPASS_DEBUG", raising=False)
    candidate = Candidate(
        prompt_version="v1",
        parent_version="base",
        quality_score=0.8,
        cost=0.02,
        round_introduced=1,
    )

    _append_archive(_RUN_ID, [candidate], tmp_path)

    archive_path = tmp_path / _RUN_ID / "search" / "candidate_archive.json"
    assert archive_path.exists()
    assert archive_path.read_text(encoding="utf-8")


def test_init_with_history_only_raises(tmp_path: Path) -> None:
    """init_search_state raises when round_history is non-empty (even if elite_set is empty)."""
    from compass.agents.prompt_builder.search import RoundSummary

    state = _make_search_state(tmp_path)

    # Inject a synthetic round_history entry without any real candidates.
    summary = RoundSummary(
        round=1,
        candidates_evaluated=["v0"],
        new_elite_entries=0,
        elite_size=0,
        mutation_mode="targeted",
        stagnation_count=1,
        converged=False,
        target_improvement=0.0,
        front_quality_spread=0.0,
        round_routing_cost=0.0,
    )
    updated = state.model_copy(update={"round": 1, "round_history": [summary]})
    _save_state(_RUN_ID, updated, tmp_path)

    with pytest.raises(FileExistsError, match="already has progress"):
        _init(tmp_path)


@pytest.mark.asyncio
async def test_mcp_init_tool_surfaces_tool_error(tmp_path: Path) -> None:
    """The MCP wrapper converts FileExistsError into ToolError on the second call."""
    from mcp.server.fastmcp.exceptions import ToolError

    from compass.mcp.prompt_building_tools import init_search_state

    resolve_project_dir_patch = "compass.project_dir.resolve_project_dir"
    search_ops_project_dir_patch = "compass.agents.prompt_builder.search_ops.get_project_dir"
    guards_check_patch = "compass.mcp.prompt_building_tools.check_artifacts"

    # get_project_dir() returns tmp_path; _default_output_dir() -> tmp_path / "outputs"
    output_dir = tmp_path / "outputs"

    with (
        patch(resolve_project_dir_patch, new_callable=AsyncMock, return_value=tmp_path),
        patch(search_ops_project_dir_patch, return_value=tmp_path),
        patch(guards_check_patch),
        patch(_ALGO_PATCH, "hill_climb"),
        patch(_ALGO_STATE_PATCH, {}),
    ):
        # First call: should succeed.
        await init_search_state(ctx=None, run_id=_RUN_ID, backend=_BACKEND)

        # Second call on pristine state: no-op (not an error).
        await init_search_state(ctx=None, run_id=_RUN_ID, backend=_BACKEND)

        # Advance state so it is no longer pristine — synthesised directly to
        # avoid calling advance_round, which is algorithm-specific (stub on
        # beam/emosa/sms-emoa leaves).
        from compass.agents.prompt_builder.search import Candidate, RoundSummary

        state = _load_state(_RUN_ID, output_dir)
        elite_candidate = Candidate(
            prompt_version="v1",
            parent_version="base",
            quality_score=0.5,
            cost=-0.1,
            round_introduced=0,
        )
        summary = RoundSummary(
            round=1,
            candidates_evaluated=["v1"],
            new_elite_entries=1,
            elite_size=1,
            mutation_mode="targeted",
            stagnation_count=0,
            converged=False,
            target_improvement=0.5,
            front_quality_spread=0.0,
            round_routing_cost=0.1,
        )
        updated = state.model_copy(update={"round": 1, "elite_set": [elite_candidate], "round_history": [summary]})
        _save_state(_RUN_ID, updated, output_dir)

        # Third call: state has progress — must raise ToolError.
        with pytest.raises(ToolError) as exc_info:
            await init_search_state(ctx=None, run_id=_RUN_ID, backend=_BACKEND)

    assert "already has progress" in str(exc_info.value)


# ---------------------------------------------------------------------------
# InputReport evaluation_budget auto-read
# ---------------------------------------------------------------------------

_BEAM_ALGO_PATCH = "compass.agents.prompt_builder.search_ops._BRANCH_ALGORITHM"
_BEAM_ALGO_STATE_PATCH = "compass.agents.prompt_builder.search_ops._BRANCH_ALGORITHM_STATE"
_BEAM_ALGO_STATE = {"beam_width": 3}


def _init_beam(tmp_path: Path, run_id: str = _RUN_ID, **kwargs) -> SearchState:
    with patch(_BEAM_ALGO_PATCH, "beam"), patch(_BEAM_ALGO_STATE_PATCH, _BEAM_ALGO_STATE):
        return init_search_state(backend=_BACKEND, run_id=run_id, output_dir=tmp_path, **kwargs)


def test_budget_read_from_input_report(tmp_path: Path) -> None:
    """When input_report.md contains ### Evaluation Budget, that value overrides the default."""
    report_dir = tmp_path / _RUN_ID / "input"
    report_dir.mkdir(parents=True)
    (report_dir / "input_report.md").write_text("### Evaluation Budget\n9\n", encoding="utf-8")

    state = _init_beam(tmp_path)

    assert state.evaluation_budget == 9
    assert state.max_rounds == 3  # ceil(9/3) == 3


def test_budget_defaults_when_no_report(tmp_path: Path) -> None:
    """Without an input_report.md the parameter default of 60 is used."""
    state = _init_beam(tmp_path)

    assert state.evaluation_budget == 60


def test_report_budget_wins_over_explicit_parameter(tmp_path: Path) -> None:
    """The InputReport value takes precedence over an explicit evaluation_budget argument."""
    report_dir = tmp_path / _RUN_ID / "input"
    report_dir.mkdir(parents=True)
    (report_dir / "input_report.md").write_text("### Evaluation Budget\n9\n", encoding="utf-8")

    state = _init_beam(tmp_path, evaluation_budget=30)

    assert state.evaluation_budget == 9
