# odysseus/agents/prompt_builder_search_ops.py
"""File-backed state operations for the Prompt Builder Agent search loop.

Provides pure functions for initialising, loading, and mutating SearchState
and pending Candidate lists.  All state is persisted to files — there is no
module-level mutable state, making the module safe across MCP server restarts.

Persistence layout:
    outputs/<run_id>/search/search_state.json
    outputs/<run_id>/search/pending_candidates.json

See: docs/superpowers/specs/2026-03-24-thp-77-prompt-builder-agent-design.md
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Literal

from odysseus.agents.prompt_builder.annealing import (
    AnnealingState,
    TrajectoryState,
    adaptive_cool,
    compute_cooling_rate,
    compute_neighborhood,
    compute_tchebycheff_energy,
    metropolis_accept,
    replace_if_better,
    update_archive,
)
from odysseus.agents.prompt_builder.search import (
    AlgorithmType,
    Candidate,
    RoundSummary,
    SearchState,
    compute_front_improvement,
    compute_hypervolume,
    update_pareto_front,
    validate_elite_set,
)
from odysseus.agents.prompt_builder.viz import _try_write_viz
from odysseus.agents.review.models import LoopSignal
from odysseus.project_dir import get_project_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def _default_output_dir() -> Path:
    return get_project_dir() / "outputs"


# Branch-level algorithm constants.  On feat/generalize-pipeline (and main)
# these default to hill_climb / {}.  Search-specific branches (Wave 2) flip
# exactly these two lines and nothing else.
_BRANCH_ALGORITHM: AlgorithmType = "emosa"
_BRANCH_ALGORITHM_STATE: dict[str, Any] = {"num_trajectories": 5}


# ---------------------------------------------------------------------------
# Private path / IO helpers
# ---------------------------------------------------------------------------


def _state_path(run_id: str, output_dir: Path) -> Path:
    return output_dir / run_id / "search" / "search_state.json"


def _pending_path(run_id: str, output_dir: Path) -> Path:
    return output_dir / run_id / "search" / "pending_candidates.json"


def _save_state(run_id: str, state: SearchState, output_dir: Path) -> None:
    path = _state_path(run_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def _load_state(run_id: str, output_dir: Path) -> SearchState:
    path = _state_path(run_id, output_dir)
    if not path.exists():
        raise FileNotFoundError(f"Search state not found: {path}")
    return SearchState.model_validate_json(path.read_text(encoding="utf-8"))


def _loop_signal_path(run_id: str, output_dir: Path) -> Path:
    return output_dir / run_id / "search" / "loop_signal.json"


def _save_loop_signal(run_id: str, signal: LoopSignal, output_dir: Path) -> None:
    path = _loop_signal_path(run_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(signal.model_dump_json(indent=2), encoding="utf-8")


def _consume_loop_signal(run_id: str, output_dir: Path) -> LoopSignal | None:
    """Read and delete the loop signal file (consume-once semantics)."""
    path = _loop_signal_path(run_id, output_dir)
    if not path.exists():
        return None
    signal = LoopSignal.model_validate_json(path.read_text(encoding="utf-8"))
    path.unlink()
    return signal


def _save_pending(
    run_id: str,
    pending: list[Candidate],
    output_dir: Path,
) -> None:
    path = _pending_path(run_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [c.model_dump() for c in pending]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_pending(run_id: str, output_dir: Path) -> list[Candidate]:
    path = _pending_path(run_id, output_dir)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Candidate.model_validate(item) for item in data]


# ---------------------------------------------------------------------------
# Task 6: init_search_state / get_search_state
# ---------------------------------------------------------------------------


def init_search_state(
    backend: str,
    run_id: str,
    output_dir: Path | None = None,
    max_rounds: int = 50,
    stagnation_limit: int = 3,
    convergence_limit: int = 5,
    primary_metric_name: str | None = None,
) -> SearchState:
    """Create and persist a new SearchState.

    The search algorithm is hardcoded per-branch via ``_BRANCH_ALGORITHM`` /
    ``_BRANCH_ALGORITHM_STATE``; callers do not choose it.

    Args:
        backend: Backend identifier (e.g. ``"anthropic"``).
        run_id: Run identifier used as the top-level directory key for storage.
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
        algorithm=_BRANCH_ALGORITHM,
        algorithm_state=_BRANCH_ALGORITHM_STATE,
    )
    _save_state(run_id, state, output_dir)
    _try_write_viz(run_id, output_dir)
    return state


def get_search_state(
    run_id: str,
    output_dir: Path | None = None,
) -> SearchState:
    """Load and return a persisted SearchState.

    Args:
        run_id: Run identifier used to locate the state on disk.
        output_dir: Root directory for persisted state files.

    Returns:
        The loaded :class:`SearchState`.

    Raises:
        FileNotFoundError: If no state exists for *run_id*.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    return _load_state(run_id, output_dir)


# ---------------------------------------------------------------------------
# Task 7: register_candidate
# ---------------------------------------------------------------------------


def register_candidate(
    run_id: str,
    prompt_version: str,
    parent_version: str | None = None,
    example_ids: list[str] | None = None,
    output_dir: Path | None = None,
    eval_status: Literal["pending", "running", "complete", "failed"] | None = "pending",
) -> SearchState:
    """Register a new candidate for the current round.

    The candidate is appended to the pending list on disk.  No quality score
    or cost is recorded yet — those are filled in by :func:`record_eval_result`.

    Args:
        run_id: Run identifier used to locate the state on disk.
        prompt_version: Unique version identifier for the prompt.
        parent_version: Parent prompt version, if any.
        example_ids: Holdout example IDs used as few-shots in this prompt version.
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
    state = _load_state(run_id, output_dir)
    pending = _load_pending(run_id, output_dir)

    # Collect all known versions
    front_versions = {c.prompt_version for c in state.elite_set}
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
        example_ids=example_ids or [],
        eval_status=eval_status,
    )
    pending.append(candidate)
    _save_pending(run_id, pending, output_dir)
    _try_write_viz(run_id, output_dir)
    return state


def get_candidate_example_ids(
    run_id: str,
    prompt_version: str,
    output_dir: Path | None = None,
) -> list[str]:
    """Return the example_ids for a candidate on the Pareto front.

    Args:
        run_id: Run identifier used to locate the state on disk.
        prompt_version: Version identifier of the candidate.
        output_dir: Root directory for persisted state files.

    Returns:
        List of holdout example IDs used in the candidate's prompt.

    Raises:
        FileNotFoundError: If the search state does not exist.
        ValueError: If *prompt_version* is not on the Pareto front.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    state = _load_state(run_id, output_dir)
    for candidate in state.elite_set:
        if candidate.prompt_version == prompt_version:
            return candidate.example_ids
    raise ValueError(f"prompt_version '{prompt_version}' not found on elite set")


# ---------------------------------------------------------------------------
# Task 8: record_eval_result
# ---------------------------------------------------------------------------


def record_eval_result(
    run_id: str,
    prompt_version: str,
    quality_score: float,
    cost: float,
    output_dir: Path | None = None,
) -> dict[str, object]:
    """Record evaluation results for a pending candidate.

    Args:
        run_id: Run identifier used to locate the state on disk.
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
    pending = _load_pending(run_id, output_dir)

    found_index: int | None = None
    for i, c in enumerate(pending):
        if c.prompt_version == prompt_version:
            found_index = i
            break

    if found_index is None:
        raise ValueError(f"prompt_version '{prompt_version}' not found in pending candidates")

    updated = pending[found_index].model_copy(
        update={"quality_score": quality_score, "cost": cost, "eval_status": "complete"}
    )
    pending[found_index] = updated
    _save_pending(run_id, pending, output_dir)
    _try_write_viz(run_id, output_dir)

    return {
        "prompt_version": prompt_version,
        "quality_score": quality_score,
        "cost": cost,
    }


# ---------------------------------------------------------------------------
# Task 9: advance_round
# ---------------------------------------------------------------------------


def advance_round(
    run_id: str,
    output_dir: Path | None = None,
) -> RoundSummary:
    """Advance the search loop by one round.

    Processes all pending candidates: updates the Pareto front, adjusts
    stagnation tracking, switches mutation mode, and checks for convergence.

    Args:
        run_id: Run identifier used to locate the state on disk.
        output_dir: Root directory for persisted state files.

    Returns:
        A :class:`RoundSummary` for the completed round.

    Raises:
        FileNotFoundError: If the search state does not exist.
        ValueError: If there are no pending candidates.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    state = _load_state(run_id, output_dir)

    # Guard: do not advance while batch evals are still in flight.
    if state.active_evals:
        raise ValueError(f"Cannot advance round while active_evals is non-empty: {state.active_evals}")

    pending = _load_pending(run_id, output_dir)

    if not pending:
        raise ValueError("No pending candidates to advance round with")

    new_round = state.round + 1

    # Split pending into scored and failed candidates.
    # Backward-compat: candidates from old state files have eval_status=None
    # (the field didn't exist); treat None as "complete" since we have no
    # evidence they failed.
    scored = [c for c in pending if c.eval_status in ("complete", None)]
    failed_evals = [c for c in pending if c.eval_status == "failed"]

    for c in failed_evals:
        logger.warning(
            "Candidate %s has eval_status='failed' and will be excluded from elite-set update",
            c.prompt_version,
        )

    candidates_evaluated = [c.prompt_version for c in pending]

    if not scored:
        # All candidates failed — carry elite set forward unchanged, increment stagnation.
        new_front = state.elite_set
        new_elite_entries = 0
        improvement = 0.0
        new_stagnation_count = state.stagnation_count + 1
        round_routing_cost = 0.0
        new_mutation_mode = "exploratory" if new_stagnation_count >= state.stagnation_limit else state.mutation_mode
    else:
        # Normal path — use only scored candidates.
        new_front, new_elite_entries = update_pareto_front(state.elite_set, scored)

        # Update stagnation
        improvement = compute_front_improvement(state.elite_set, new_front)
        new_stagnation_count = 0 if improvement > state.epsilon else state.stagnation_count + 1

        # Determine mutation mode
        if new_stagnation_count == 0 and state.stagnation_count > 0:
            # Improvement after stagnation — reset to targeted
            new_mutation_mode = "targeted"
        elif new_stagnation_count >= state.stagnation_limit:
            new_mutation_mode = "exploratory"
        else:
            new_mutation_mode = state.mutation_mode

        round_routing_cost = sum(c.cost for c in scored)

    # Check convergence
    converged = new_stagnation_count >= state.convergence_limit or new_round >= state.max_rounds
    new_convergence_limit = state.convergence_limit

    # Apply Review Agent loop signal (if present)
    signal = _consume_loop_signal(run_id, output_dir)
    if signal is not None and signal.action == "refine":
        if signal.suggested_budget is not None and signal.suggested_budget > 0:
            new_stagnation_count = 0
            new_convergence_limit = max(
                state.convergence_limit + signal.suggested_budget,
                state.stagnation_limit + 1,
            )
            # Re-check: only max_rounds is a hard cap
            converged = new_round >= state.max_rounds
        if signal.suggested_mutation_mode is not None:
            new_mutation_mode = signal.suggested_mutation_mode

    qualities = [c.quality_score for c in new_front]
    front_quality_spread = max(qualities) - min(qualities) if len(new_front) > 1 else 0.0
    convergence_reason: str | None = None
    if converged:
        if new_round >= state.max_rounds:
            convergence_reason = "max_rounds"
        elif new_stagnation_count >= new_convergence_limit:
            convergence_reason = "stagnation"

    summary = RoundSummary(
        round=new_round,
        candidates_evaluated=candidates_evaluated,
        new_elite_entries=new_elite_entries,
        elite_size=len(new_front),
        mutation_mode=new_mutation_mode,
        stagnation_count=new_stagnation_count,
        converged=converged,
        target_improvement=improvement,
        front_quality_spread=front_quality_spread,
        round_routing_cost=round_routing_cost,
        convergence_reason=convergence_reason,
    )

    # Persist updated state
    updated_state = state.model_copy(
        update={
            "round": new_round,
            "elite_set": new_front,
            "round_history": [*state.round_history, summary],
            "stagnation_count": new_stagnation_count,
            "convergence_limit": new_convergence_limit,
            "mutation_mode": new_mutation_mode,
            "converged": converged,
            "loop_phase": "build" if converged else "review",
            "total_routing_cost": state.total_routing_cost + round_routing_cost,
        }
    )
    _save_state(run_id, updated_state, output_dir)
    _try_write_viz(run_id, output_dir)

    # Clear pending
    _save_pending(run_id, [], output_dir)

    return summary


# ---------------------------------------------------------------------------
# EMOSA helpers
# ---------------------------------------------------------------------------


def _compute_reference_point(
    elite_set: list[Candidate],
    scored_pending: list[Candidate],
) -> tuple[float, float]:
    """Compute a hypervolume reference point from all-ever seen candidates."""
    all_ever = list(elite_set) + list(scored_pending)
    if not all_ever:
        return (0.0, 0.0)
    worst_quality = min(c.quality_score for c in all_ever)
    worst_cost = max(c.cost for c in all_ever)
    return (
        worst_quality * 0.9 if worst_quality > 0 else -0.1,
        worst_cost * 1.1 if worst_cost > 0 else 0.1,
    )


# ---------------------------------------------------------------------------
# EMOSA: advance_round_emosa + _calibration_complete
# ---------------------------------------------------------------------------


def _calibration_complete(
    run_id: str,
    state: SearchState,
    output_dir: Path,
) -> RoundSummary:
    """Seed K trajectories from K cold-start scored candidates.

    Called when ``algorithm_state.phase == "calibration"``.  Reads the K
    scored pending candidates (one per trajectory), computes round-1 ideal /
    nadir from their quality/cost values, seeds each trajectory's
    ``current_solution``, ``current_quality``, ``current_cost``, and
    ``current_energy`` via Tchebycheff scalarization, then:

    - Flips pocket ``phase`` → ``"search"`` and increments ``step_count``.
    - Adds ``total_evals += K``.
    - Updates ``ideal_point`` / ``nadir_point`` in the pocket.
    - Adds scored candidates to the elite set (if not already present).
    - Sets top-level ``loop_phase`` → ``"review"``.
    - Persists updated state and clears pending.

    Args:
        run_id: Run identifier used to locate the state on disk.
        state: Currently-loaded SearchState (caller has already read it).
        output_dir: Root directory for persisted state files.

    Returns:
        A :class:`RoundSummary` with EMOSA optional fields populated.

    Raises:
        ValueError: If pending contains fewer scored candidates than ``num_trajectories``.
    """
    pocket = state.algorithm_state
    annealing = AnnealingState.model_validate(pocket)
    num_traj = annealing.num_trajectories

    pending = _load_pending(run_id, output_dir)
    scored = [c for c in pending if c.eval_status in ("complete", None)]

    if len(scored) < num_traj:
        raise ValueError(
            f"EMOSA calibration requires {num_traj} scored candidates "
            f"(num_trajectories={num_traj}), but only {len(scored)} are scored. "
            f"Ensure all {num_traj} cold-start candidates are evaluated before "
            f"calling advance_round_emosa."
        )

    # Use exactly num_traj — the first num_traj scored candidates
    calibration_scored = scored[:num_traj]

    # Compute round-1 ideal/nadir from the K scored candidates.
    # ideal = (best_quality, lowest_cost); nadir = (worst_quality, highest_cost)
    ideal_q = max(c.quality_score for c in calibration_scored)
    ideal_c = min(c.cost for c in calibration_scored)
    nadir_q = min(c.quality_score for c in calibration_scored)
    nadir_c = max(c.cost for c in calibration_scored)
    new_ideal: tuple[float, float] = (ideal_q, ideal_c)
    new_nadir: tuple[float, float] = (nadir_q, nadir_c)

    # Seed each trajectory: trajectory i gets calibration_scored[i]
    traj_steps = max(1, annealing.max_evals // annealing.num_trajectories)
    updated_trajectories: list[TrajectoryState] = []
    for traj in annealing.trajectories:
        idx = traj.trajectory_id
        cand = calibration_scored[idx]
        energy = compute_tchebycheff_energy(
            cand.quality_score,
            cand.cost,
            traj.weight_vector,
            new_ideal,
            new_nadir,
        )
        traj_alpha = compute_cooling_rate(annealing.t_initial, annealing.t_min, traj_steps)
        updated_traj = traj.model_copy(
            update={
                "current_solution": cand.prompt_version,
                "current_quality": cand.quality_score,
                "current_cost": cand.cost,
                "current_energy": energy,
                "acceptance_history": [True],
                "temperature": annealing.t_initial,
                "alpha": traj_alpha,
                "step_count": 0,
            }
        )
        updated_trajectories.append(updated_traj)

    # Update elite set: add scored candidates not already present
    new_elite = list(state.elite_set)
    for cand in calibration_scored:
        new_elite, _ = update_archive(new_elite, cand)

    # Update annealing pocket: flip phase and total_evals (step_count is now per-trajectory)
    new_annealing = annealing.model_copy(
        update={
            "trajectories": updated_trajectories,
            "ideal_point": new_ideal,
            "nadir_point": new_nadir,
            "phase": "search",
            "total_evals": annealing.total_evals + num_traj,
        }
    )

    new_round = state.round + 1
    summary = RoundSummary(
        round=new_round,
        candidates_evaluated=[c.prompt_version for c in calibration_scored],
        new_elite_entries=len(new_elite) - len(state.elite_set),
        elite_size=len(new_elite),
        temperatures={t.trajectory_id: t.temperature for t in updated_trajectories},
        ideal_point=new_ideal,
        nadir_point=new_nadir,
        step_count=sum(t.step_count for t in updated_trajectories),
        phase="search",
    )

    updated_state = state.model_copy(
        update={
            "round": new_round,
            "elite_set": new_elite,
            "round_history": [*state.round_history, summary],
            "algorithm_state": new_annealing.model_dump(),
            "loop_phase": "review",
        }
    )
    _save_state(run_id, updated_state, output_dir)
    _try_write_viz(run_id, output_dir)

    # Clear pending candidates
    _save_pending(run_id, [], output_dir)

    return summary


def _advance_emosa_search(
    run_id: str,
    state: SearchState,
    output_dir: Path,
) -> RoundSummary:
    """Execute one EMOSA steady-state advance step (phase == 'search').

    Implements per-trajectory Metropolis-then-best-of-accepted acceptance,
    EMOSA neighborhood replacement (B=4 nearest weight-vector neighbors),
    archive update, geometric cooling, and three-way convergence detection.

    Steps:
        a. Load AnnealingState from algorithm_state pocket; assert active_evals empty.
        b. Load pending; split scored / failed.
        c. Update ideal/nadir from scored candidates.
        d. Drift-cache refresh: recompute trajectory current_energy under new ideal/nadir.
        e. Per-trajectory Metropolis-then-best-of-accepted.
        f. EMOSA neighborhood replacement for each accepted child.
        g. Update archive (elite_set) with all scored candidates.
        h. Compute hypervolume.
        i. Cool temperature; increment step_count and total_evals.
        j. Check convergence: temperature_floor, eval_budget, review_exit.
        k. Build RoundSummary.
        l. Save state (AnnealingState back into algorithm_state pocket).

    Args:
        run_id: Run identifier.
        state: Currently-loaded SearchState.
        output_dir: Root directory for persisted state files.

    Returns:
        A :class:`RoundSummary` with EMOSA optional fields populated.

    Raises:
        ValueError: If active_evals is non-empty or no pending candidates.
    """
    if state.active_evals:
        raise ValueError(f"Cannot advance round while active_evals is non-empty: {state.active_evals}")

    sa_state = AnnealingState.model_validate(state.algorithm_state)

    pending = _load_pending(run_id, output_dir)
    if not pending:
        raise ValueError("No pending candidates to advance round with")

    # Split into scored and failed
    scored_pending = [c for c in pending if c.eval_status in ("complete", None)]
    failed_pending = [c for c in pending if c.eval_status == "failed"]

    if failed_pending:
        logger.warning(
            "_advance_emosa_search: %d candidate(s) failed evaluation: %s",
            len(failed_pending),
            [c.prompt_version for c in failed_pending],
        )

    new_round = state.round + 1

    # Update ideal/nadir from scored candidates
    new_ideal = sa_state.ideal_point
    new_nadir = sa_state.nadir_point

    if scored_pending:
        ideal_q, ideal_c = new_ideal
        nadir_q, nadir_c = new_nadir

        for c in scored_pending:
            ideal_q = max(ideal_q, c.quality_score)
            ideal_c = min(ideal_c, c.cost)
            nadir_q = min(nadir_q, c.quality_score)
            nadir_c = max(nadir_c, c.cost)

        new_ideal = (ideal_q, ideal_c)
        new_nadir = (nadir_q, nadir_c)

    # Drift-cache refresh (a15b608): recompute trajectory current_energy under new
    # ideal/nadir before Metropolis. Without this, trajectories holding solutions
    # from rounds with narrower normalization have stale-low energies that make
    # Metropolis systematically reject genuine improvements.
    refreshed_trajectories: list[TrajectoryState] = []
    for traj in sa_state.trajectories:
        if traj.current_solution is not None and traj.current_quality is not None and traj.current_cost is not None:
            refreshed_energy = compute_tchebycheff_energy(
                traj.current_quality,
                traj.current_cost,
                traj.weight_vector,
                new_ideal,
                new_nadir,
            )
            refreshed_trajectories.append(traj.model_copy(update={"current_energy": refreshed_energy}))
        else:
            refreshed_trajectories.append(traj)

    # Per-trajectory Metropolis acceptance (Metropolis-then-best-of-accepted)
    updated_trajectories: list[TrajectoryState] = []
    participating_ids: set[int] = set()

    # Separate candidates that match a live trajectory from unmatched ones
    # (unmatched arise when current_solution is None, calibration→search edge).
    matched_versions: set[str | None] = {
        traj.current_solution for traj in refreshed_trajectories if traj.current_solution is not None
    }
    unmatched_pending = [c for c in scored_pending if c.parent_version not in matched_versions]
    unmatched_iter = iter(unmatched_pending)

    for traj in refreshed_trajectories:
        if traj.current_solution is not None:
            traj_candidates = [c for c in scored_pending if c.parent_version == traj.current_solution]
        else:
            # Calibration→search edge: assign unmatched candidates round-robin
            cand = next(unmatched_iter, None)
            traj_candidates = [cand] if cand is not None else []

        if not traj_candidates:
            updated_trajectories.append(traj)
            continue

        # Track trajectories that attempted a Metropolis step this round
        participating_ids.add(traj.trajectory_id)

        calibration = traj.current_solution is None or traj.current_energy is None

        best_accepted_cand = None
        best_accepted_energy: float | None = None

        for cand in traj_candidates:
            energy = compute_tchebycheff_energy(
                cand.quality_score,
                cand.cost,
                traj.weight_vector,
                new_ideal,
                new_nadir,
            )

            if calibration:
                # First step after calibration: always accept
                accepted = True
            else:
                delta_e = energy - traj.current_energy  # type: ignore[operator]
                accepted = metropolis_accept(delta_e, traj.temperature)

            if accepted and (best_accepted_energy is None or energy < best_accepted_energy):
                best_accepted_cand = cand
                best_accepted_energy = energy

        any_accepted = best_accepted_cand is not None
        new_history = (traj.acceptance_history + [any_accepted])[-5:]

        if any_accepted:
            updated_traj = traj.model_copy(
                update={
                    "current_solution": best_accepted_cand.prompt_version,  # type: ignore[union-attr]
                    "current_energy": best_accepted_energy,
                    "current_quality": best_accepted_cand.quality_score,  # type: ignore[union-attr]
                    "current_cost": best_accepted_cand.cost,  # type: ignore[union-attr]
                    "acceptance_history": new_history,
                }
            )
        else:
            updated_traj = traj.model_copy(update={"acceptance_history": new_history})

        updated_trajectories.append(updated_traj)

    # EMOSA neighborhood replacement: every generated child is offered to its
    # originating trajectory's neighborhood, regardless of whether the originator's
    # Metropolis accepted it. Originators are excluded from the replacement target
    # set so the SA decision is not overridden on the trajectory that made the
    # child. Reference: Li & Landa-Silva 2011 (canonical EMOSA / MOEA/D-SA).
    weight_vectors = [t.weight_vector for t in refreshed_trajectories]
    traj_by_id = {
        t.trajectory_id: updated_traj
        for t, updated_traj in zip(refreshed_trajectories, updated_trajectories, strict=True)
    }

    # Map parent_version -> list of trajectory IDs whose pre-update current is
    # that parent. List, not single value, because multiple trajectories may
    # share a current_solution (e.g. T0/T1/T2 converged on the same v).
    parent_to_origins: dict[str, list[int]] = {}
    for traj in refreshed_trajectories:
        if traj.current_solution is not None:
            parent_to_origins.setdefault(traj.current_solution, []).append(traj.trajectory_id)

    for cand in scored_pending:
        if cand.parent_version is None:
            continue
        origins = parent_to_origins.get(cand.parent_version, [])
        if not origins:
            continue  # unmatched (calibration leftover) — skip
        nbr_ids: set[int] = set()
        for orig_id in origins:
            nbr_ids.update(compute_neighborhood(orig_id, sa_state.neighborhood_size, weight_vectors))
        nbr_ids -= set(origins)  # don't override Metropolis on the originators
        for nbr_id in nbr_ids:
            nbr = traj_by_id[nbr_id]
            e_nbr = compute_tchebycheff_energy(
                cand.quality_score,
                cand.cost,
                nbr.weight_vector,
                new_ideal,
                new_nadir,
            )
            traj_by_id[nbr_id] = replace_if_better(
                nbr,
                e_nbr,
                cand.prompt_version,
                cand.quality_score,
                cand.cost,
            )

    updated_trajectories = [traj_by_id[t.trajectory_id] for t in refreshed_trajectories]

    # Update archive (elite_set) with all non-dominated new candidates
    new_elite = list(state.elite_set)
    for cand in scored_pending:
        new_elite, _ = update_archive(new_elite, cand)

    new_elite = validate_elite_set(new_elite)

    # Compute hypervolume
    ref_point = _compute_reference_point(new_elite, scored_pending)
    new_hv = compute_hypervolume(new_elite, ref_point)

    # Per-trajectory adaptive cooling: trajectories that attempted a Metropolis
    # step this round adjust their T_i based on recent acceptance rate.
    cooled_trajectories: list[TrajectoryState] = []
    for traj in updated_trajectories:
        if traj.trajectory_id in participating_ids:
            new_temp = adaptive_cool(
                traj.temperature,
                traj.alpha,
                traj.acceptance_history,
                sa_state.target_acceptance_low,
                sa_state.target_acceptance_high,
                sa_state.cooling_exp_fast,
                sa_state.cooling_exp_slow,
            )
            cooled_trajectories.append(
                traj.model_copy(update={"temperature": new_temp, "step_count": traj.step_count + 1})
            )
        else:
            cooled_trajectories.append(traj)
    updated_trajectories = cooled_trajectories

    # Update counters
    new_total_evals = sa_state.total_evals + len(scored_pending)

    # Check convergence: temperature_floor when ALL trajectories are below t_min.
    converged = False
    convergence_reason: str | None = None

    if all(t.temperature < sa_state.t_min for t in updated_trajectories):
        converged = True
        convergence_reason = "temperature_floor"
    elif new_total_evals >= sa_state.max_evals:
        converged = True
        convergence_reason = "eval_budget"

    # Consume loop signal (Review Agent exit)
    signal = _consume_loop_signal(run_id, output_dir)
    if signal is not None and signal.action == "exit":
        converged = True
        convergence_reason = "review_exit"

    # Build RoundSummary
    candidates_evaluated = [c.prompt_version for c in pending]
    qualities = [c.quality_score for c in new_elite] if new_elite else [0.0]
    quality_spread = max(qualities) - min(qualities) if len(new_elite) > 1 else 0.0
    round_routing_cost = sum(c.cost for c in scored_pending)

    old_versions = {c.prompt_version for c in state.elite_set}
    new_elite_entries = sum(1 for c in new_elite if c.prompt_version not in old_versions)

    # Per-trajectory acceptance rates (last-5 ring)
    acceptance_rates_dict: dict[int, float] = {}
    for traj in updated_trajectories:
        if traj.acceptance_history:
            acceptance_rates_dict[traj.trajectory_id] = sum(traj.acceptance_history) / len(traj.acceptance_history)

    summary = RoundSummary(
        round=new_round,
        candidates_evaluated=candidates_evaluated,
        new_elite_entries=new_elite_entries,
        elite_size=len(new_elite),
        stagnation_count=0,
        converged=converged,
        target_improvement=0.0,
        front_quality_spread=quality_spread,
        round_routing_cost=round_routing_cost,
        convergence_reason=convergence_reason,
        temperatures={t.trajectory_id: t.temperature for t in updated_trajectories},
        hypervolume=new_hv,
        reference_point=ref_point,
        acceptance_rates=acceptance_rates_dict if acceptance_rates_dict else None,
        ideal_point=new_ideal,
        nadir_point=new_nadir,
        step_count=sum(t.step_count for t in updated_trajectories),
        phase="converged" if converged else "search",
    )

    # Save updated AnnealingState back into algorithm_state pocket
    updated_sa = sa_state.model_copy(
        update={
            "trajectories": updated_trajectories,
            "ideal_point": new_ideal,
            "nadir_point": new_nadir,
            "total_evals": new_total_evals,
            "phase": "converged" if converged else sa_state.phase,
        }
    )

    updated_state = state.model_copy(
        update={
            "round": new_round,
            "elite_set": new_elite,
            "round_history": [*state.round_history, summary],
            "converged": converged,
            "total_routing_cost": state.total_routing_cost + round_routing_cost,
            "algorithm_state": updated_sa.model_dump(),
            "loop_phase": "review",
        }
    )

    _save_state(run_id, updated_state, output_dir)
    _try_write_viz(run_id, output_dir)

    # Archive pending, clear
    _save_pending(run_id, [], output_dir)

    return summary


def advance_round_emosa(
    run_id: str,
    output_dir: Path | None = None,
) -> RoundSummary:
    """Advance the EMOSA search loop by one step.

    Dispatches on the current ``algorithm_state.phase``:

    - ``"calibration"``: seed K trajectories from cold-start scored candidates
      via :func:`_calibration_complete`.
    - ``"search"``: run per-trajectory Metropolis acceptance, neighborhood
      replacement, archive update, cooling, and convergence detection.

    Args:
        run_id: Run identifier used to locate the state on disk.
        output_dir: Root directory for persisted state files.

    Returns:
        A :class:`RoundSummary` with EMOSA optional fields populated.

    Raises:
        FileNotFoundError: If the search state does not exist.
        ValueError: If the phase is unrecognised or preconditions are not met.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    state = _load_state(run_id, output_dir)

    pocket = state.algorithm_state
    phase = pocket.get("phase", "calibration")

    if phase == "calibration":
        return _calibration_complete(run_id, state, output_dir)
    elif phase == "search":
        return _advance_emosa_search(run_id, state, output_dir)
    else:
        raise ValueError(f"unsupported emosa phase '{phase}'")


def _clear_active_evals(run_id: str, output_dir: Path) -> None:
    """Reset ``active_evals`` to an empty list and persist the state.

    Defensive utility used by batch-eval machinery (commits 2–4) to drain the
    in-flight tracker after all candidates have settled.  Not called from
    ``advance_round`` itself.
    """
    state = _load_state(run_id, output_dir)
    updated = state.model_copy(update={"active_evals": []})
    _save_state(run_id, updated, output_dir)


def set_loop_phase(
    run_id: str,
    phase: Literal[
        "build",
        "review",
        "warmup_seed",
        "warmup_build",
        "warmup_reduce",
        "calibration",
        "build_recovering",
    ],
    output_dir: Path | None = None,
) -> None:
    """Set the loop_phase on the search state.

    Called by record_directive_outcomes_tool to signal that the Review Agent
    has finished and the Prompt Builder should be spawned next.  Accepts the
    full widened enum so feature branches can drive additional phases.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    state = _load_state(run_id, output_dir)
    updated = state.model_copy(update={"loop_phase": phase})
    _save_state(run_id, updated, output_dir)
