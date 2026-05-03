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

from odysseus.agents.prompt_builder.search import (
    AlgorithmType,
    Candidate,
    RoundSummary,
    SearchState,
)
from odysseus.agents.prompt_builder.viz import _try_write_viz
from odysseus.agents.review.models import LoopSignal, UserTarget
from odysseus.project_dir import get_project_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def _default_output_dir() -> Path:
    return get_project_dir() / "outputs"


# Branch-level algorithm constants.  On feat/generalize-pipeline this is the
# sentinel "__unset__"; leaf branches override exactly these two lines.
_BRANCH_ALGORITHM: AlgorithmType = "__unset__"
_BRANCH_ALGORITHM_STATE: dict[str, Any] = {}


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
    if _BRANCH_ALGORITHM == "__unset__":
        raise RuntimeError(
            "init_search_state called on the pipeline trunk where _BRANCH_ALGORITHM is '__unset__'. "
            "Run on a leaf branch (feat/generalize-{hill_climb,beam,emosa,sms_emoa}) that sets "
            "_BRANCH_ALGORITHM to a concrete algorithm."
        )
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

    This is an algorithm-specific operation. On the pipeline trunk this function
    raises :exc:`NotImplementedError` — leaf branches supply the implementation
    that matches their search strategy.

    Args:
        run_id: Run identifier used to locate the state on disk.
        output_dir: Root directory for persisted state files.

    Returns:
        A :class:`RoundSummary` for the completed round.

    Raises:
        NotImplementedError: Always on the pipeline trunk.
    """
    raise NotImplementedError(
        "advance_round has no implementation on the pipeline trunk. "
        "Run on a leaf branch (feat/generalize-{hill_climb,beam,emosa,sms_emoa}) "
        "that provides the algorithm-specific advance_round body."
    )


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
