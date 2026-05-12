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
import math
import uuid
from pathlib import Path
from typing import Any, Literal

from odysseus.agents.prompt_builder.search import (
    AlgorithmType,
    Candidate,
    RoundSummary,
    SearchState,
    compute_hypervolume,
    update_elite_set,
    validate_elite_set,
)
from odysseus.agents.prompt_builder.viz import _try_write_viz
from odysseus.agents.review.models import INITIAL_PARENT_VERSION, LoopSignal, UserTarget
from odysseus.project_dir import get_project_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def _default_output_dir() -> Path:
    return get_project_dir() / "outputs"


# Branch-level algorithm constants.  On feat/generalize-pipeline (and main)
# these default to "__unset__".  Search-specific branches (Wave 2) flip
# exactly these two lines and nothing else.
_BRANCH_ALGORITHM: AlgorithmType = "beam"
_BRANCH_ALGORITHM_STATE: dict[str, Any] = {"beam_width": 3}


# ---------------------------------------------------------------------------
# Private path / IO helpers
# ---------------------------------------------------------------------------


def _search_dir(run_id: str, output_dir: Path) -> Path:
    return output_dir / run_id / "search"


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


def _archive_path(run_id: str, output_dir: Path) -> Path:
    return output_dir / run_id / "search" / "candidate_archive.json"


def _load_archive(run_id: str, output_dir: Path) -> list[dict[str, Any]]:
    path = _archive_path(run_id, output_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _append_archive(run_id: str, candidates: list[Candidate], output_dir: Path) -> None:
    if not candidates:
        return
    path = _archive_path(run_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    archive = _load_archive(run_id, output_dir)
    seen = {e["prompt_version"] for e in archive}
    archive.extend(c.model_dump() for c in candidates if c.prompt_version not in seen)
    path.write_text(json.dumps(archive, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Beam strategy helpers
# ---------------------------------------------------------------------------


def _load_user_targets(run_id: str, output_dir: Path) -> list[UserTarget]:
    """Load user targets from the input report."""
    from odysseus.agents.review.preprocessor import parse_user_targets

    input_report_path = output_dir / run_id / "input" / "input_report.md"
    if not input_report_path.exists():
        return []
    return parse_user_targets(input_report_path.read_text(encoding="utf-8"))


def _load_candidate_metrics(candidates: list[Candidate], run_id: str, output_dir: Path) -> dict[str, dict[str, float]]:
    """Read each candidate's eval report.json and extract the metrics dict."""
    metrics: dict[str, dict[str, float]] = {}
    for c in candidates:
        report_path = output_dir / run_id / "eval" / c.prompt_version / "report.json"
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            metrics[c.prompt_version] = report.get("metrics", {})
    return metrics


def _reshape_route_metrics(metrics: dict[str, float]) -> dict[str, dict[str, float]]:
    """Split ``recall/route_X`` style flat keys into nested ``{route_X: {recall: …}}``."""
    route_data: dict[str, dict[str, float]] = {}
    for key, value in metrics.items():
        if "/" in key:
            metric_type, route = key.split("/", 1)
            if metric_type in ("recall", "precision", "f1"):
                route_data.setdefault(route, {})[metric_type] = value
    return route_data


def _check_all_targets_met(
    elite: list[Candidate],
    user_targets: list[UserTarget],
    candidate_metrics: dict[str, dict[str, float]],
) -> bool:
    """Return True if at least one elite candidate satisfies every user target."""
    _ops: dict[str, Any] = {
        ">=": lambda v, t: v >= t,
        ">": lambda v, t: v > t,
        "<=": lambda v, t: v <= t,
        "<": lambda v, t: v < t,
        "==": lambda v, t: v == t,
    }
    for c in elite:
        metrics = candidate_metrics.get(c.prompt_version, {})
        met_all = True
        for target in user_targets:
            value = metrics.get(target.metric)
            if value is None:
                met_all = False
                break
            op_fn = _ops.get(target.operator)
            if op_fn is None or not op_fn(value, target.threshold):
                met_all = False
                break
        if met_all:
            return True
    return False


# ---------------------------------------------------------------------------
# Task 6: init_search_state / get_search_state
# ---------------------------------------------------------------------------


def init_search_state(
    backend: str,
    run_id: str,
    output_dir: Path | None = None,
    evaluation_budget: int = 60,
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
        evaluation_budget: Total prompt versions to evaluate before the search terminates.
        stagnation_limit: Stagnation rounds before switching to exploratory mode.
        convergence_limit: Stagnation rounds that trigger convergence.
        primary_metric_name: Optional name of the primary quality metric.

    Returns:
        The newly created :class:`SearchState`.
    """
    if _BRANCH_ALGORITHM == "__unset__":
        raise RuntimeError(
            "init_search_state called on the pipeline trunk where _BRANCH_ALGORITHM is '__unset__'. "
            "Run on a leaf branch (feat/generalize-{hill_climb,beam,emosa,sms_emoa}) that sets "
            "_BRANCH_ALGORITHM to a concrete algorithm."
        )

    # Derive max_rounds from evaluation_budget based on algorithm's K
    if _BRANCH_ALGORITHM == "hill_climb":
        max_rounds = evaluation_budget
    elif _BRANCH_ALGORITHM == "beam":
        k = int(_BRANCH_ALGORITHM_STATE.get("beam_width", 3))
        max_rounds = math.ceil(evaluation_budget / k)
    elif _BRANCH_ALGORITHM == "sms_emoa":
        max_rounds = 500  # SMS-EMOA uses algorithm_state["evaluation_budget"] as its budget
    else:
        max_rounds = evaluation_budget

    if output_dir is None:
        output_dir = _default_output_dir()

    # Guard: refuse to overwrite a state that already has progress.
    # This prevents a re-dispatched round-2+ prompt-builder sub-agent from
    # resetting round/elite_set/round_history back to zero.
    try:
        existing = _load_state(run_id, output_dir)
        pending = _load_pending(run_id, output_dir)
    except FileNotFoundError:
        pass  # Normal cold-start: fall through to creation logic.
    else:
        # Pristine state: pre-initialised by _ensure_stage4_search_state but not
        # yet touched by any sub-agent.  Safe to return as a no-op so the race
        # between _ensure_stage4_search_state and the first cold-start sub-agent
        # is idempotent (init_search_state raises on progress, no-ops on pristine).
        if existing.round == 0 and not existing.round_history and not existing.elite_set and not pending:
            return existing
        raise FileExistsError(
            f"search_state for run_id={run_id!r} already has progress "
            f"(round={existing.round}, elites={len(existing.elite_set)}, "
            f"history={len(existing.round_history)}, pending={len(pending)}); "
            "call get_search_state_tool instead of re-initialising"
        )

    algorithm_state = dict(_BRANCH_ALGORITHM_STATE)
    if _BRANCH_ALGORITHM == "sms_emoa":
        algorithm_state["evaluation_budget"] = evaluation_budget

    search_state_id = uuid.uuid4().hex[:12]
    state = SearchState(
        search_state_id=search_state_id,
        backend=backend,
        max_rounds=max_rounds,
        evaluation_budget=evaluation_budget,
        stagnation_limit=stagnation_limit,
        convergence_limit=convergence_limit,
        primary_metric_name=primary_metric_name,
        algorithm=_BRANCH_ALGORITHM,
        algorithm_state=algorithm_state,
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
    trajectory_id: int | None = None,
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

    # Beam cold-start (round == 0): overlay mandates parent_version == "base"
    # for every seed. Coerce here because the Review LLM doesn't always comply,
    # and the search-tree viz lineage depends on this invariant.
    if state.algorithm == "beam" and state.round == 0:
        parent_version = INITIAL_PARENT_VERSION

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
        trajectory_id=trajectory_id,
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

    Beam-branch implementation: delegates to :func:`advance_round_beam`.
    """
    return advance_round_beam(run_id=run_id, output_dir=output_dir)


# ---------------------------------------------------------------------------
# Beam advance_round
# ---------------------------------------------------------------------------


def advance_round_beam(
    run_id: str,
    output_dir: Path | None = None,
) -> RoundSummary:
    """Advance the beam search loop by one round.

    Processes all pending candidates using multi-objective (hypervolume-based)
    elite-set management.  Key behaviour:

    - Round 1 (cold-start): all scored candidates are retained regardless of
      Pareto dominance so every initial strategy gets a second data point.
    - Round 2+: standard Pareto + crowding-distance pruning applies.
    - Stagnation is measured by relative hypervolume improvement.
    - Epsilon is tightened once when all user targets are first met.
    - Backtracking flag is set when stagnation_count >= backtrack_threshold.

    Algorithm-specific sub-state (beam_width, epsilon_min,
    backtrack_threshold, hypervolume, reference_point,
    targets_met_epsilon_tightened) is stored in the
    ``state.algorithm_state`` pocket.

    Args:
        run_id: Run identifier used to locate the state on disk.
        output_dir: Root directory for persisted state files.

    Returns:
        A :class:`RoundSummary` for the completed round.

    Raises:
        FileNotFoundError: If the search state does not exist.
        ValueError: If there are no pending candidates or active evals exist.
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

    # Read beam-specific config from algorithm_state pocket (read-only; not written back)
    ast = state.algorithm_state
    beam_width = int(ast.get("beam_width", 3))
    epsilon_min = float(ast.get("epsilon_min", 0.0005))
    backtrack_threshold = int(ast.get("backtrack_threshold", 2))
    hypervolume_prev = float(ast.get("hypervolume", 0.0))
    reference_point_prev_raw = ast.get("reference_point", [0.0, 0.0])
    reference_point_prev: tuple[float, float] = (
        float(reference_point_prev_raw[0]),
        float(reference_point_prev_raw[1]),
    )
    targets_met_epsilon_tightened = bool(ast.get("targets_met_epsilon_tightened", False))

    # Split pending into scored and failed
    scored_pending = [c for c in pending if c.eval_status in ("complete", None)]
    failed_pending = [c for c in pending if c.eval_status == "failed"]

    for c in failed_pending:
        logger.warning(
            "advance_round_beam: candidate %s has eval_status='failed' and will be excluded",
            c.prompt_version,
        )

    candidates_evaluated = [c.prompt_version for c in pending]

    if not scored_pending:
        # All-fail stagnation: carry elite set forward unchanged
        new_elite: list[Candidate] = list(state.elite_set)
        new_elite_entries = 0
        new_stagnation_count = state.stagnation_count + 1
        new_hypervolume = hypervolume_prev
        new_reference_point = reference_point_prev
        new_epsilon = state.epsilon
    else:
        user_targets = _load_user_targets(run_id, output_dir)
        all_for_metrics: list[Candidate] = list(state.elite_set) + list(scored_pending)
        candidate_metrics = _load_candidate_metrics(all_for_metrics, run_id, output_dir)

        new_elite, new_elite_entries = update_elite_set(
            state.elite_set,
            scored_pending,
            max_size=2 * beam_width + 1,
            is_cold_start_round=(new_round == 1),
        )

        # Annotate route_metrics on elite candidates from their score reports
        new_elite_annotated: list[Candidate] = []
        for c in new_elite:
            metrics = candidate_metrics.get(c.prompt_version, {})
            route_m = _reshape_route_metrics(metrics)
            if route_m and not c.route_metrics:
                c = c.model_copy(update={"route_metrics": route_m})
            new_elite_annotated.append(c)
        new_elite = new_elite_annotated

        # Compute hypervolume using worst-seen reference point
        all_ever: list[Candidate] = list(state.elite_set) + list(scored_pending)
        if all_ever:
            worst_quality = min(c.quality_score for c in all_ever)
            worst_cost = max(c.cost for c in all_ever)
            new_reference_point = (
                worst_quality * 0.9 if worst_quality > 0 else -0.1,
                worst_cost * 1.1 if worst_cost > 0 else 0.1,
            )
        else:
            new_reference_point = reference_point_prev

        new_hypervolume = compute_hypervolume(new_elite, new_reference_point)

        # Stagnation detection (skip on round 1 — front still forming)
        if new_round == 1:
            new_stagnation_count = 0
        else:
            if hypervolume_prev > 0:
                relative_improvement = (new_hypervolume - hypervolume_prev) / hypervolume_prev
            else:
                relative_improvement = new_hypervolume
            new_stagnation_count = 0 if relative_improvement > state.epsilon else state.stagnation_count + 1

        # Epsilon tightening: one-time when all user targets first met
        new_epsilon = state.epsilon
        if user_targets and not targets_met_epsilon_tightened:
            all_met = _check_all_targets_met(new_elite, user_targets, candidate_metrics)
            if all_met:
                new_epsilon = max(state.epsilon / 2.0, epsilon_min)
                new_stagnation_count = 0  # fresh runway
                targets_met_epsilon_tightened = True
                logger.info(
                    "advance_round_beam: all user targets met — tightening epsilon %.4f -> %.4f",
                    state.epsilon,
                    new_epsilon,
                )

    # Backtracking flag
    backtracking = new_stagnation_count >= backtrack_threshold

    # Check convergence
    total_evaluated = sum(len(r.candidates_evaluated) for r in state.round_history) + len(candidates_evaluated)
    budget_reached = total_evaluated >= state.evaluation_budget
    converged = (budget_reached and new_stagnation_count >= state.convergence_limit) or new_round >= state.max_rounds
    new_convergence_limit = state.convergence_limit

    qualities = [c.quality_score for c in new_elite]
    front_quality_spread = max(qualities) - min(qualities) if len(new_elite) > 1 else 0.0
    round_routing_cost = sum(c.cost for c in scored_pending)
    improvement = max(0.0, new_hypervolume - hypervolume_prev)

    convergence_reason: str | None = None
    if converged:
        if new_round >= state.max_rounds:
            convergence_reason = "max_rounds"
        elif new_stagnation_count >= state.convergence_limit:
            convergence_reason = "stagnation"

    summary = RoundSummary(
        round=new_round,
        candidates_evaluated=candidates_evaluated,
        new_elite_entries=new_elite_entries,
        elite_size=len(new_elite),
        stagnation_count=new_stagnation_count,
        converged=converged,
        target_improvement=improvement,
        front_quality_spread=front_quality_spread,
        round_routing_cost=round_routing_cost,
        convergence_reason=convergence_reason,
        backtracking=backtracking,
        hypervolume=new_hypervolume,
        reference_point=new_reference_point,
    )

    # Skip Pareto validation in round 1 — cold-start candidates are retained
    # regardless of dominance so each strategy gets a second data point.
    if new_round != 1:
        new_elite = validate_elite_set(new_elite)

    # Persist updated state
    new_ast = {**state.algorithm_state}
    new_ast["hypervolume"] = new_hypervolume
    new_ast["prev_hypervolume"] = hypervolume_prev
    new_ast["reference_point"] = list(new_reference_point)  # JSON serializable
    new_ast["targets_met_epsilon_tightened"] = targets_met_epsilon_tightened

    updated_state = state.model_copy(
        update={
            "round": new_round,
            "elite_set": new_elite,
            "round_history": [*state.round_history, summary],
            "stagnation_count": new_stagnation_count,
            "converged": converged,
            "loop_phase": "build" if converged else "review",
            "total_routing_cost": state.total_routing_cost + round_routing_cost,
            "epsilon": new_epsilon,
            "algorithm_state": new_ast,
        }
    )
    _save_state(run_id, updated_state, output_dir)

    # Save round report from each pending candidate's eval report on disk
    from odysseus.agents.review.ops import save_round_report

    round_reports: dict[str, dict] = {}
    eval_dir = output_dir / run_id / "eval"
    for candidate in pending:
        report_path = eval_dir / candidate.prompt_version / "report.json"
        if report_path.exists():
            round_reports[candidate.prompt_version] = json.loads(report_path.read_text(encoding="utf-8"))
    if round_reports:
        save_round_report(run_id, state.round, round_reports, output_dir=output_dir)

    # Persist scored candidates to archive before clearing pending.
    _append_archive(run_id, scored_pending, output_dir)

    # Clear pending
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
