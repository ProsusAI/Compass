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
from typing import Any, Literal, cast

from odysseus.agents.prompt_builder.search import (
    Candidate,
    RoundSummary,
    SearchState,
    compute_front_improvement,
    compute_hypervolume,
    compute_pareto_front,
    dynamic_reference_point,
    reduce_population,
    update_pareto_front,
)
from odysseus.agents.prompt_builder.viz import _try_write_viz
from odysseus.agents.review.models import LoopSignal
from odysseus.project_dir import get_project_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Safety cap on iterations (prevents runaway SMS-EMOA loops)
_MAX_ITERATIONS = 500


def _default_output_dir() -> Path:
    return get_project_dir() / "outputs"


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
    algorithm: Literal["hill_climb", "beam", "sms_emoa", "emosa"] = "hill_climb",
    algorithm_state: dict[str, Any] | None = None,
) -> SearchState:
    """Create and persist a new SearchState.

    Args:
        backend: Backend identifier (e.g. ``"anthropic"``).
        run_id: Run identifier used as the top-level directory key for storage.
        output_dir: Root directory for persisted state files.
        max_rounds: Maximum number of search rounds before forced convergence.
        stagnation_limit: Stagnation rounds before switching to exploratory mode.
        convergence_limit: Stagnation rounds that trigger convergence.
        primary_metric_name: Optional name of the primary quality metric.
        algorithm: Search algorithm discriminator.  Defaults to ``"hill_climb"``.
        algorithm_state: Optional free-form pocket for strategy-specific sub-state.

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
        algorithm=algorithm,
        algorithm_state=algorithm_state or {},
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
        raise ValueError(
            f"Cannot advance round while active_evals is non-empty: {state.active_evals}"
        )

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
        new_mutation_mode = (
            "exploratory" if new_stagnation_count >= state.stagnation_limit else state.mutation_mode
        )
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
# SMS-EMOA: _check_termination
# ---------------------------------------------------------------------------


def _check_termination(
    evaluations_used: int,
    evaluation_budget: int,
    hv_history: list[float],
    stagnation_window: int,
    stagnation_epsilon: float,
    iteration: int,
) -> tuple[bool, Literal["budget", "plateau", "max_iterations"] | None]:
    """Return (terminated, reason) based on budget, plateau, and max-iteration checks.

    Plateau uses max-min over the rolling window (tolerates non-monotonicity).
    Stagnation epsilon is reference_delta; plateau fires when HV variation in
    the window falls below this threshold.
    """
    if evaluations_used >= evaluation_budget:
        return True, "budget"

    if iteration >= _MAX_ITERATIONS:
        return True, "max_iterations"

    if len(hv_history) >= stagnation_window:
        window = hv_history[-stagnation_window:]
        if (max(window) - min(window)) < stagnation_epsilon:
            return True, "plateau"

    return False, None


# ---------------------------------------------------------------------------
# SMS-EMOA: advance_warmup_batch
# ---------------------------------------------------------------------------


def advance_warmup_batch(
    run_id: str,
    output_dir: Path | None = None,
) -> RoundSummary:
    """Complete warm-up: set population from the μ scored seeds.

    Called once, when ``warm_up_complete`` is ``False`` and μ children are all
    scored in pending.  Reads algorithm-specific config from the
    ``algorithm_state`` pocket (with safe defaults) and writes the resulting
    population state back.

    Args:
        run_id: Run identifier used to locate the state on disk.
        output_dir: Root directory for persisted state files.

    Returns:
        A :class:`RoundSummary` with ``reduce_case="warmup"``.

    Raises:
        ValueError: If warm-up is already complete, active_evals is non-empty,
            pending is empty, or fewer than 2 scored candidates are available.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    state = _load_state(run_id, output_dir)
    pending = _load_pending(run_id, output_dir)

    # --- Read algorithm_state pocket with safe defaults ---
    ast = state.algorithm_state
    mu = int(ast.get("mu", 8))
    warm_up_complete = bool(ast.get("warm_up_complete", False))
    reference_delta = float(ast.get("reference_delta", 0.05))

    if warm_up_complete:
        raise ValueError("advance_warmup_batch called but warm_up_complete is already True")

    if not pending:
        raise ValueError("No pending candidates to advance_warmup_batch with")

    if state.active_evals:
        raise ValueError(
            f"Cannot advance_warmup_batch while active_evals is non-empty: {state.active_evals}"
        )

    scored_pending = [c for c in pending if c.eval_status in ("complete", None)]
    failed_pending = [c for c in pending if c.eval_status == "failed"]

    if len(scored_pending) < 2:
        raise ValueError(
            f"advance_warmup_batch requires at least 2 scored candidates; "
            f"got {len(scored_pending)} scored, {len(failed_pending)} failed"
        )

    # Sort deterministically by prompt_version for reproducibility
    population = sorted(scored_pending[:mu], key=lambda c: c.prompt_version)

    # Compute initial dynamic reference point and hypervolume
    front = compute_pareto_front(population)
    r = dynamic_reference_point(front, delta=reference_delta)
    hv = compute_hypervolume(front, r)

    # Build updated algorithm_state pocket
    new_ast = {**ast}
    new_ast["population"] = [c.model_dump() for c in population]
    new_ast["warm_up_complete"] = True
    new_ast["iteration"] = 0
    new_ast["evaluations_used"] = len(pending)
    new_ast["hypervolume_history"] = [hv]
    new_ast["reference_point"] = list(r)

    # Represent warmup as round 0 in the summary
    new_round = state.round + 1

    # Use first/last population members as nominal parents for traceability
    parent_a = population[0].prompt_version
    parent_b = population[-1].prompt_version if len(population) > 1 else parent_a

    summary = RoundSummary(
        round=new_round,
        candidates_evaluated=[c.prompt_version for c in pending],
        new_elite_entries=len(population),
        elite_size=len(population),
        converged=False,
        hypervolume=hv,
        hypervolume_delta=0.0,
        reference_point=r,
        reduce_case="warmup",
        evicted_version="",
        parent_a_version=parent_a,
        parent_b_version=parent_b,
        population_size=len(population),
        terminated=False,
        termination_reason=None,
    )

    updated_state = state.model_copy(
        update={
            "round": new_round,
            "elite_set": list(population),
            "round_history": [*state.round_history, summary],
            "loop_phase": "review",
            "algorithm_state": new_ast,
        }
    )
    _save_state(run_id, updated_state, output_dir)
    _save_pending(run_id, [], output_dir)
    _try_write_viz(run_id, output_dir)

    return summary


# ---------------------------------------------------------------------------
# SMS-EMOA: advance_round_sms_emoa
# ---------------------------------------------------------------------------


def advance_round_sms_emoa(
    run_id: str,
    output_dir: Path | None = None,
) -> RoundSummary:
    """Advance the SMS-EMOA loop by one steady-state iteration.

    Expects exactly one scored pending candidate (the child from the current
    build phase). Updates population via reduce_population, checks termination,
    and persists state.  Algorithm-specific state lives in the
    ``algorithm_state`` pocket.

    Args:
        run_id: Run identifier used to locate the state on disk.
        output_dir: Root directory for persisted state files.

    Returns:
        A :class:`RoundSummary` with termination information.

    Raises:
        ValueError: If pending is empty or active_evals is non-empty.
        RuntimeError: If called before warm-up is complete.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    state = _load_state(run_id, output_dir)
    pending = _load_pending(run_id, output_dir)

    if not pending:
        raise ValueError("No pending candidates to advance_round_sms_emoa with")

    if state.active_evals:
        raise ValueError(
            f"Cannot advance_round_sms_emoa while active_evals is non-empty: {state.active_evals}"
        )

    # --- Read algorithm_state pocket with safe defaults ---
    ast = state.algorithm_state
    mu = int(ast.get("mu", 8))
    warm_up_complete = bool(ast.get("warm_up_complete", False))
    population_raw = ast.get("population", [])
    population: list[Candidate] = [Candidate.model_validate(c) for c in population_raw]
    hypervolume_history: list[float] = list(ast.get("hypervolume_history", []))
    iteration = int(ast.get("iteration", 0))
    evaluation_budget = int(ast.get("evaluation_budget", 50))
    evaluations_used = int(ast.get("evaluations_used", 0))
    reference_delta = float(ast.get("reference_delta", 0.05))
    stagnation_window = int(ast.get("stagnation_window", 5))

    if not warm_up_complete:
        raise RuntimeError(
            "advance_round_sms_emoa called before warm-up complete — use advance_warmup_batch"
        )

    scored_pending = [c for c in pending if c.eval_status in ("complete", None)]
    failed_pending = [c for c in pending if c.eval_status == "failed"]

    if failed_pending:
        logger.warning(
            "advance_round_sms_emoa: %d candidate(s) failed evaluation: %s",
            len(failed_pending),
            [c.prompt_version for c in failed_pending],
        )

    prev_hv = hypervolume_history[-1] if hypervolume_history else 0.0
    new_round = state.round + 1
    candidates_evaluated = [c.prompt_version for c in pending]

    if not scored_pending:
        # All-failed: carry population forward; still consume budget
        new_iteration = iteration + 1
        new_evaluations_used = evaluations_used + len(pending)
        new_hv_history = hypervolume_history + [prev_hv]

        terminated, termination_reason = _check_termination(
            new_evaluations_used,
            evaluation_budget,
            new_hv_history,
            stagnation_window,
            reference_delta,
            new_iteration,
        )

        new_ast = {**ast}
        new_ast["iteration"] = new_iteration
        new_ast["evaluations_used"] = new_evaluations_used
        new_ast["hypervolume_history"] = new_hv_history

        rep_parent = population[0].prompt_version if population else ""

        summary = RoundSummary(
            round=new_round,
            candidates_evaluated=candidates_evaluated,
            new_elite_entries=0,
            elite_size=len(population),
            converged=terminated,
            hypervolume=prev_hv,
            hypervolume_delta=0.0,
            reference_point=tuple(ast.get("reference_point", [0.0, 0.0])),
            reduce_case="A_singleton",
            evicted_version="",
            parent_a_version=rep_parent,
            parent_b_version=rep_parent,
            population_size=len(population),
            terminated=terminated,
            termination_reason=termination_reason,
        )

        updated_state = state.model_copy(
            update={
                "round": new_round,
                "round_history": [*state.round_history, summary],
                "converged": terminated,
                "loop_phase": "build" if terminated else "review",
                "algorithm_state": new_ast,
            }
        )
        _save_state(run_id, updated_state, output_dir)
        _save_pending(run_id, [], output_dir)
        _try_write_viz(run_id, output_dir)

        return summary

    # Exactly one scored child expected post-warmup
    child = scored_pending[0]
    if len(scored_pending) > 1:
        logger.warning(
            "advance_round_sms_emoa: expected 1 scored child, got %d; using first by prompt_version",
            len(scored_pending),
        )
        child = min(scored_pending, key=lambda c: c.prompt_version)

    # Compute dynamic reference point from current front before reduce
    current_front = compute_pareto_front(population)
    r = dynamic_reference_point(current_front, delta=reference_delta)

    new_population, evicted, reduce_case_str = reduce_population(population, child, mu, reference_delta)
    reduce_case = cast(
        Literal["A_singleton", "B_dominated", "C_delta_s"],
        reduce_case_str,
    )

    new_front = compute_pareto_front(new_population)
    new_hv = compute_hypervolume(new_front, r)
    hv_delta = new_hv - prev_hv

    new_iteration = iteration + 1
    new_evaluations_used = evaluations_used + len(pending)
    new_hv_history = hypervolume_history + [new_hv]

    terminated, termination_reason = _check_termination(
        new_evaluations_used,
        evaluation_budget,
        new_hv_history,
        stagnation_window,
        reference_delta,
        new_iteration,
    )

    # Derive parent versions from child metadata
    parent_a = child.parent_version or ""
    parent_b = child.secondary_parent_version or parent_a

    # Count how many new elite entries were introduced (child entered population)
    child_in_pop = any(c.prompt_version == child.prompt_version for c in new_population)
    new_elite_entries = 1 if child_in_pop else 0

    summary = RoundSummary(
        round=new_round,
        candidates_evaluated=candidates_evaluated,
        new_elite_entries=new_elite_entries,
        elite_size=len(new_population),
        converged=terminated,
        hypervolume=new_hv,
        hypervolume_delta=hv_delta,
        reference_point=r,
        reduce_case=reduce_case,
        evicted_version=evicted.prompt_version,
        parent_a_version=parent_a,
        parent_b_version=parent_b,
        population_size=len(new_population),
        terminated=terminated,
        termination_reason=termination_reason,
    )

    new_ast = {**ast}
    new_ast["population"] = [c.model_dump() for c in new_population]
    new_ast["iteration"] = new_iteration
    new_ast["evaluations_used"] = new_evaluations_used
    new_ast["hypervolume_history"] = new_hv_history
    new_ast["reference_point"] = list(r)

    updated_state = state.model_copy(
        update={
            "round": new_round,
            "elite_set": list(new_front),
            "round_history": [*state.round_history, summary],
            "converged": terminated,
            "loop_phase": "build" if terminated else "review",
            "algorithm_state": new_ast,
        }
    )
    _save_state(run_id, updated_state, output_dir)
    _save_pending(run_id, [], output_dir)
    _try_write_viz(run_id, output_dir)

    return summary


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
        "build", "review",
        "warmup_seed", "warmup_build", "warmup_reduce",
        "calibration", "build_recovering",
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
