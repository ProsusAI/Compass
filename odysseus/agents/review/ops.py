"""File-backed persistence for Review Agent state.

Follows the same pattern as prompt_builder_search_ops.py:
pure functions, file-backed, no in-memory state.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from odysseus.agents.review.models import (
    ChildVariant,
    DirectiveOutcome,
)
from odysseus.project_dir import get_project_dir


def _default_output_dir() -> Path:
    return get_project_dir() / "outputs"


def _search_dir(run_id: str, output_dir: Path) -> Path:
    return output_dir / run_id / "search"


def _directive_history_path(run_id: str, output_dir: Path) -> Path:
    return _search_dir(run_id, output_dir) / "directive_history.json"


def _child_variants_path(run_id: str, output_dir: Path) -> Path:
    return _search_dir(run_id, output_dir) / "child_variants.json"


def _round_reports_dir(run_id: str, output_dir: Path) -> Path:
    return _search_dir(run_id, output_dir) / "round_reports"


def _review_result_path(run_id: str, output_dir: Path) -> Path:
    return _search_dir(run_id, output_dir) / "review_result.json"


def save_review_result(
    run_id: str,
    result: dict[str, Any],
    *,
    output_dir: Path | None = None,
) -> None:
    """Persist the full ReviewResult for debugging/auditing."""
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _review_result_path(run_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")


def save_directive_history(
    run_id: str,
    history: list[DirectiveOutcome],
    *,
    output_dir: Path | None = None,
) -> None:
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _directive_history_path(run_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [h.model_dump(mode="json") for h in history]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_directive_history(
    run_id: str,
    *,
    output_dir: Path | None = None,
) -> list[DirectiveOutcome]:
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _directive_history_path(run_id, output_dir)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [DirectiveOutcome.model_validate(d) for d in data]


def save_child_variants(
    run_id: str,
    variants: list[ChildVariant],
    *,
    output_dir: Path | None = None,
) -> None:
    """Persist child variants from the Review Agent for the Prompt Builder to consume."""
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _child_variants_path(run_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [v.model_dump(mode="json") for v in variants]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_child_variants(
    run_id: str,
    *,
    output_dir: Path | None = None,
) -> list[ChildVariant]:
    """Load the most recently persisted child variants."""
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _child_variants_path(run_id, output_dir)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ChildVariant.model_validate(v) for v in data]


# ---------------------------------------------------------------------------
# Per-trajectory K-way fanout helpers (EMOSA)
# ---------------------------------------------------------------------------


def _trajectory_child_variants_path(run_id: str, trajectory_id: int, output_dir: Path) -> Path:
    return _search_dir(run_id, output_dir) / f"child_variants_t{trajectory_id}.json"


def save_trajectory_child_variants(
    run_id: str,
    trajectory_id: int,
    variants: list[ChildVariant],
    *,
    output_dir: Path | None = None,
) -> None:
    """Persist child variants for a specific EMOSA trajectory slot.

    Writes ``child_variants_t<trajectory_id>.json`` in the search directory.
    The trajectory_id is appended to ``review_dispatched.json`` via
    :func:`record_trajectory_dispatched` so the dispatcher can track in-flight
    and completed slots independently.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _trajectory_child_variants_path(run_id, trajectory_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [v.model_dump(mode="json") for v in variants]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_all_trajectory_child_variants(
    run_id: str,
    *,
    output_dir: Path | None = None,
) -> list[ChildVariant]:
    """Load and merge child variants from all per-trajectory files, sorted by trajectory_id.

    The trajectory_id is derived from the filename (``child_variants_t<N>.json``)
    and used only for ordering; the loaded :class:`ChildVariant` objects are returned
    sorted from lowest to highest trajectory_id.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    search_dir = _search_dir(run_id, output_dir)
    if not search_dir.exists():
        return []
    pairs: list[tuple[int, ChildVariant]] = []
    for path in search_dir.glob("child_variants_t*.json"):
        stem = path.stem  # e.g. "child_variants_t3"
        file_tid = int(stem.split("child_variants_t", 1)[1])
        raw = json.loads(path.read_text(encoding="utf-8"))
        for v in raw:
            variant = ChildVariant.model_validate(v)
            pairs.append((file_tid, variant))
    pairs.sort(key=lambda p: p[0])
    return [variant for _, variant in pairs]


def clear_trajectory_child_variants(
    run_id: str,
    *,
    output_dir: Path | None = None,
) -> None:
    """Delete all per-trajectory child variant files for a run."""
    if output_dir is None:
        output_dir = _default_output_dir()
    search_dir = _search_dir(run_id, output_dir)
    if not search_dir.exists():
        return
    for path in search_dir.glob("child_variants_t*.json"):
        path.unlink()


@dataclass
class FanoutStatus:
    """Result of a trajectory fanout completeness check.

    ``missing`` is the union of ``not_dispatched`` and ``in_flight``, preserved
    for backwards compatibility with callers that only need "what's still outstanding".
    """

    num_trajectories: int
    missing: list[int]         # not_dispatched ∪ in_flight (backwards compat)
    completed: list[int]       # child_variants_t<N>.json present on disk
    dispatched: list[int]      # from review_dispatched.json (current round only)
    in_flight: list[int]       # dispatched \ completed
    not_dispatched: list[int]  # all_ids \ dispatched \ completed


def _dispatched_path(run_id: str, output_dir: Path) -> Path:
    return _search_dir(run_id, output_dir) / "review_dispatched.json"


def _current_round(run_id: str, output_dir: Path) -> int | None:
    """Read the current round from search_state.json; return None if unreadable."""
    state_path = _search_dir(run_id, output_dir) / "search_state.json"
    if not state_path.exists():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return int(data["round"])
    except Exception:
        return None


def record_trajectory_dispatched(
    run_id: str,
    trajectory_id: int,
    *,
    output_dir: Path | None = None,
) -> None:
    """Record that a Review Agent sub-agent was dispatched for trajectory_id.

    Reads the current round from search_state.json and resets the file when the
    stored round differs (stale entries from a previous review round).  Writes are
    atomic (tmp + rename) and idempotent (set semantics).
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    search_dir = _search_dir(run_id, output_dir)
    search_dir.mkdir(parents=True, exist_ok=True)
    path = _dispatched_path(run_id, output_dir)

    current_round = _current_round(run_id, output_dir) or 0

    existing_ids: set[int] = set()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("round") == current_round:
                existing_ids = set(data.get("trajectory_ids", []))
        except Exception:
            pass  # treat as absent

    existing_ids.add(trajectory_id)
    payload = json.dumps(
        {"round": current_round, "trajectory_ids": sorted(existing_ids)},
        indent=2,
    )

    tmp = path.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def load_dispatched_trajectories(
    run_id: str,
    *,
    output_dir: Path | None = None,
) -> list[int]:
    """Return sorted dispatched trajectory_ids for the current round.

    Returns ``[]`` when the file is absent, unreadable, or from a stale round.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _dispatched_path(run_id, output_dir)
    if not path.exists():
        return []
    current_round = _current_round(run_id, output_dir) or 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("round") != current_round:
            return []
        return sorted(int(t) for t in data.get("trajectory_ids", []))
    except Exception:
        return []


def clear_dispatched_trajectories(
    run_id: str,
    *,
    output_dir: Path | None = None,
) -> None:
    """Delete review_dispatched.json; no-op when file is absent."""
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _dispatched_path(run_id, output_dir)
    if path.exists():
        path.unlink()


def trajectory_fanout_missing(
    run_id: str,
    *,
    output_dir: Path | None = None,
) -> FanoutStatus | None:
    """Check which trajectory IDs have not yet saved child variants.

    Reads ``num_trajectories`` from the ``algorithm_state`` pocket of
    ``search_state.json`` (canonical layout on this branch).  Returns ``None``
    when the state is absent or contains no ``num_trajectories`` field (preserves
    legacy single-slot behaviour — callers should treat ``None`` as "complete for
    non-EMOSA runs").

    Returns a :class:`FanoutStatus` with per-trajectory dispatch state otherwise.
    ``missing`` is kept as ``not_dispatched ∪ in_flight`` for backwards
    compatibility.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    search_dir = _search_dir(run_id, output_dir)
    state_path = search_dir / "search_state.json"
    if not state_path.exists():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        pocket = data.get("algorithm_state") or {}
        num_trajectories = pocket.get("num_trajectories")
        if num_trajectories is None:
            return None
        num_trajectories = int(num_trajectories)
    except Exception:
        return None

    completed: set[int] = set()
    for path in search_dir.glob("child_variants_t*.json"):
        m = re.search(r"child_variants_t(\d+)\.json$", path.name)
        if m:
            completed.add(int(m.group(1)))

    dispatched: set[int] = set(load_dispatched_trajectories(run_id, output_dir=output_dir))
    all_ids = set(range(num_trajectories))
    in_flight = sorted(dispatched - completed)
    not_dispatched = sorted(all_ids - dispatched - completed)
    missing = sorted(all_ids - completed)  # backwards compat

    return FanoutStatus(
        num_trajectories=num_trajectories,
        missing=missing,
        completed=sorted(completed),
        dispatched=sorted(dispatched),
        in_flight=in_flight,
        not_dispatched=not_dispatched,
    )


def save_round_report(
    run_id: str,
    round_num: int,
    reports: dict[str, dict[str, Any]],
    *,
    output_dir: Path | None = None,
) -> None:
    if output_dir is None:
        output_dir = _default_output_dir()
    dir_path = _round_reports_dir(run_id, output_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / f"round_{round_num}.json"
    path.write_text(json.dumps(reports, indent=2), encoding="utf-8")


def load_round_reports(
    run_id: str,
    *,
    output_dir: Path | None = None,
) -> dict[int, dict[str, dict[str, Any]]]:
    if output_dir is None:
        output_dir = _default_output_dir()
    dir_path = _round_reports_dir(run_id, output_dir)
    if not dir_path.exists():
        return {}
    result: dict[int, dict[str, dict[str, Any]]] = {}
    for path in sorted(dir_path.glob("round_*.json")):
        round_num = int(path.stem.split("_")[1])
        result[round_num] = json.loads(path.read_text(encoding="utf-8"))
    return result


def _cell_attempt_history_path(run_id: str, output_dir: Path) -> Path:
    return _search_dir(run_id, output_dir) / "cell_attempt_history.json"


def load_cell_attempt_history(
    run_id: str,
    *,
    output_dir: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Load cell attempt history from disk."""
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _cell_attempt_history_path(run_id, output_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_cell_attempt_history(
    run_id: str,
    history: dict[str, list[dict[str, Any]]],
    *,
    output_dir: Path | None = None,
) -> None:
    """Persist cell attempt history to disk."""
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _cell_attempt_history_path(run_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def update_cell_attempt_history(
    run_id: str,
    batch_outcomes: list[Any],
    child_variants: list[Any],
    confusion_analysis: list[Any],
    *,
    current_round: int,
    output_dir: Path | None = None,
) -> None:
    """Update cell attempt history based on batch outcomes.

    For each batch outcome whose source variant targeted a confusion cell,
    determine the outcome and append to that cell's history.
    """
    if output_dir is None:
        output_dir = _default_output_dir()

    # Build variant_id -> target_confusion_cell lookup
    variant_cells: dict[str, str] = {}
    for cv in child_variants:
        vid = cv.variant_id if hasattr(cv, "variant_id") else None
        cell = cv.target_confusion_cell if hasattr(cv, "target_confusion_cell") else None
        if vid and cell:
            variant_cells[vid] = cell

    if not variant_cells:
        return

    # Build confusion cell -> (cost_impact, quality_impact) for metric dimension selection
    cell_impacts: dict[str, tuple[float, float]] = {}
    for ci in confusion_analysis:
        key = f"{ci.true_route}/{ci.predicted_route}"
        cell_impacts[key] = (ci.cost_impact, ci.quality_impact)

    history = load_cell_attempt_history(run_id, output_dir=output_dir)

    for bo in batch_outcomes:
        vid = bo.variant_id if hasattr(bo, "variant_id") else None
        cell = variant_cells.get(vid or "")
        if not cell:
            continue

        cost_imp, quality_imp = cell_impacts.get(cell, (0.0, 0.0))
        deltas = bo.metric_deltas_vs_parent if hasattr(bo, "metric_deltas_vs_parent") else None

        if deltas and abs(cost_imp) > abs(quality_imp):
            # Cost-dominated cell: negative delta = candidate is cheaper = improved
            cost_delta = deltas.get("cost_change_with_overhead", 0.0)
            if cost_delta < -0.005:
                outcome = "improved"
            elif cost_delta > 0.005:
                outcome = "regressed"
            else:
                outcome = "no_effect"
        else:
            # Quality-dominated cell (default)
            quality_delta = bo.quality_delta_vs_parent if hasattr(bo, "quality_delta_vs_parent") else None
            if quality_delta is not None and quality_delta > 0.005:
                outcome = "improved"
            elif quality_delta is not None and quality_delta < -0.005:
                outcome = "regressed"
            else:
                outcome = "no_effect"

        history.setdefault(cell, []).append({
            "round": current_round,
            "variant_id": vid,
            "outcome": outcome,
        })

    save_cell_attempt_history(run_id, history, output_dir=output_dir)
