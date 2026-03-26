# odysseus/agents/prompt_builder_search_ops.py
"""File-backed state operations for the Prompt Builder Agent search loop.

Provides pure functions for initialising, loading, and mutating SearchState
and pending Candidate lists.  All state is persisted to files — there is no
module-level mutable state, making the module safe across MCP server restarts.

Persistence layout:
    outputs/<search_state_id>/search_state.json
    outputs/<search_state_id>/pending_candidates.json

See: docs/superpowers/specs/2026-03-24-thp-77-prompt-builder-agent-design.md
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from odysseus.agents.prompt_builder_search import (
    Candidate,
    RoundSummary,
    SearchState,
    update_pareto_front,
)
from odysseus.project_dir import get_project_dir

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def _default_output_dir() -> Path:
    return get_project_dir() / "outputs"

# ---------------------------------------------------------------------------
# Private path / IO helpers
# ---------------------------------------------------------------------------


def _state_path(search_state_id: str, output_dir: Path) -> Path:
    return output_dir / search_state_id / "search_state.json"


def _pending_path(search_state_id: str, output_dir: Path) -> Path:
    return output_dir / search_state_id / "pending_candidates.json"


def _save_state(state: SearchState, output_dir: Path) -> None:
    path = _state_path(state.search_state_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def _load_state(search_state_id: str, output_dir: Path) -> SearchState:
    path = _state_path(search_state_id, output_dir)
    if not path.exists():
        raise FileNotFoundError(f"Search state not found: {path}")
    return SearchState.model_validate_json(path.read_text(encoding="utf-8"))


def _save_pending(
    search_state_id: str,
    pending: list[Candidate],
    output_dir: Path,
) -> None:
    path = _pending_path(search_state_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [c.model_dump() for c in pending]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_pending(search_state_id: str, output_dir: Path) -> list[Candidate]:
    path = _pending_path(search_state_id, output_dir)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Candidate.model_validate(item) for item in data]


# ---------------------------------------------------------------------------
# Task 6: init_search_state / get_search_state
# ---------------------------------------------------------------------------


def init_search_state(
    backend: str,
    output_dir: Path | None = None,
    max_rounds: int = 50,
    stagnation_limit: int = 3,
    convergence_limit: int = 5,
    primary_metric_name: str | None = None,
) -> SearchState:
    """Create and persist a new SearchState.

    Args:
        backend: Backend identifier (e.g. ``"anthropic"``).
        output_dir: Root directory for persisted state files.
        max_rounds: Maximum number of search rounds before forced convergence.
        stagnation_limit: Stagnation rounds before switching to exploratory mode.
        convergence_limit: Stagnation rounds that trigger convergence.
        primary_metric_name: Optional name of the primary quality metric.

    Returns:
        The newly created :class:`SearchState`.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    search_state_id = uuid.uuid4().hex[:12]
    state = SearchState(
        search_state_id=search_state_id,
        backend=backend,
        max_rounds=max_rounds,
        stagnation_limit=stagnation_limit,
        convergence_limit=convergence_limit,
        primary_metric_name=primary_metric_name,
    )
    _save_state(state, output_dir)
    return state


def get_search_state(
    search_state_id: str,
    output_dir: Path | None = None,
) -> SearchState:
    """Load and return a persisted SearchState.

    Args:
        search_state_id: ID returned by :func:`init_search_state`.
        output_dir: Root directory for persisted state files.

    Returns:
        The loaded :class:`SearchState`.

    Raises:
        FileNotFoundError: If no state exists for *search_state_id*.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    return _load_state(search_state_id, output_dir)


# ---------------------------------------------------------------------------
# Task 7: register_candidate
# ---------------------------------------------------------------------------


def register_candidate(
    search_state_id: str,
    prompt_version: str,
    parent_version: str | None = None,
    output_dir: Path | None = None,
) -> SearchState:
    """Register a new candidate for the current round.

    The candidate is appended to the pending list on disk.  No quality score
    or cost is recorded yet — those are filled in by :func:`record_eval_result`.

    Args:
        search_state_id: Search state to update.
        prompt_version: Unique version identifier for the prompt.
        parent_version: Parent prompt version, if any.
        output_dir: Root directory for persisted state files.

    Returns:
        The current (unchanged) :class:`SearchState`.

    Raises:
        FileNotFoundError: If the search state does not exist.
        ValueError: If *prompt_version* already exists on the front, in
            history, or in the pending list.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    state = _load_state(search_state_id, output_dir)
    pending = _load_pending(search_state_id, output_dir)

    # Collect all known versions
    front_versions = {c.prompt_version for c in state.pareto_front}
    history_versions: set[str] = set()
    for summary in state.round_history:
        history_versions.update(summary.candidates_evaluated)
    pending_versions = {c.prompt_version for c in pending}

    all_known = front_versions | history_versions | pending_versions
    if prompt_version in all_known:
        raise ValueError(
            f"prompt_version '{prompt_version}' is already registered "
            f"(front={prompt_version in front_versions}, "
            f"history={prompt_version in history_versions}, "
            f"pending={prompt_version in pending_versions})"
        )

    candidate = Candidate(
        prompt_version=prompt_version,
        parent_version=parent_version,
        quality_score=0.0,
        cost=0.0,
        round_introduced=state.round + 1,
    )
    pending.append(candidate)
    _save_pending(search_state_id, pending, output_dir)
    return state


# ---------------------------------------------------------------------------
# Task 8: record_eval_result
# ---------------------------------------------------------------------------


def record_eval_result(
    search_state_id: str,
    prompt_version: str,
    quality_score: float,
    cost: float,
    output_dir: Path | None = None,
) -> dict[str, object]:
    """Record evaluation results for a pending candidate.

    Args:
        search_state_id: Search state to update.
        prompt_version: Version identifier of the candidate to update.
        quality_score: Evaluation quality score.
        cost: Evaluation cost.
        output_dir: Root directory for persisted state files.

    Returns:
        Dict with keys ``prompt_version``, ``quality_score``, ``cost``.

    Raises:
        FileNotFoundError: If the search state does not exist.
        ValueError: If *prompt_version* is not found in the pending list.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    pending = _load_pending(search_state_id, output_dir)

    found_index: int | None = None
    for i, c in enumerate(pending):
        if c.prompt_version == prompt_version:
            found_index = i
            break

    if found_index is None:
        raise ValueError(f"prompt_version '{prompt_version}' not found in pending candidates")

    updated = pending[found_index].model_copy(update={"quality_score": quality_score, "cost": cost})
    pending[found_index] = updated
    _save_pending(search_state_id, pending, output_dir)

    return {
        "prompt_version": prompt_version,
        "quality_score": quality_score,
        "cost": cost,
    }


# ---------------------------------------------------------------------------
# Task 9: advance_round
# ---------------------------------------------------------------------------


def advance_round(
    search_state_id: str,
    output_dir: Path | None = None,
) -> RoundSummary:
    """Advance the search loop by one round.

    Processes all pending candidates: updates the Pareto front, adjusts
    stagnation tracking, switches mutation mode, and checks for convergence.

    Args:
        search_state_id: Search state to advance.
        output_dir: Root directory for persisted state files.

    Returns:
        A :class:`RoundSummary` for the completed round.

    Raises:
        FileNotFoundError: If the search state does not exist.
        ValueError: If there are no pending candidates.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    state = _load_state(search_state_id, output_dir)
    pending = _load_pending(search_state_id, output_dir)

    if not pending:
        raise ValueError("No pending candidates to advance round with")

    new_round = state.round + 1

    # Update Pareto front
    new_front, new_pareto_points = update_pareto_front(state.pareto_front, pending)

    # Update stagnation
    new_stagnation_count = 0 if new_pareto_points > 0 else state.stagnation_count + 1

    # Determine mutation mode
    if new_stagnation_count == 0 and state.stagnation_count > 0:
        # Improvement after stagnation — reset to targeted
        new_mutation_mode = "targeted"
    elif new_stagnation_count >= state.stagnation_limit:
        new_mutation_mode = "exploratory"
    else:
        new_mutation_mode = state.mutation_mode

    # Check convergence
    converged = new_stagnation_count >= state.convergence_limit or new_round >= state.max_rounds

    candidates_evaluated = [c.prompt_version for c in pending]

    summary = RoundSummary(
        round=new_round,
        candidates_evaluated=candidates_evaluated,
        new_pareto_points=new_pareto_points,
        front_size=len(new_front),
        mutation_mode=new_mutation_mode,
        stagnation_count=new_stagnation_count,
    )

    # Persist updated state
    updated_state = state.model_copy(
        update={
            "round": new_round,
            "pareto_front": new_front,
            "round_history": [*state.round_history, summary],
            "stagnation_count": new_stagnation_count,
            "mutation_mode": new_mutation_mode,
            "converged": converged,
        }
    )
    _save_state(updated_state, output_dir)

    # Clear pending
    _save_pending(search_state_id, [], output_dir)

    return summary
