"""File-backed persistence for Review Agent state.

Follows the same pattern as prompt_builder_search_ops.py:
pure functions, file-backed, no in-memory state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from odysseus.agents.review.models import (
    ChildVariant,
    DirectiveOutcome,
    EditDirective,
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


def _edit_directives_path(run_id: str, output_dir: Path) -> Path:
    return _search_dir(run_id, output_dir) / "edit_directives.json"


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


def save_edit_directives(
    run_id: str,
    directives: list[EditDirective],
    *,
    output_dir: Path | None = None,
) -> None:
    """Persist edit directives from the Review Agent for the Prompt Builder to consume."""
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _edit_directives_path(run_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [d.model_dump(mode="json") for d in directives]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_edit_directives(
    run_id: str,
    *,
    output_dir: Path | None = None,
) -> list[EditDirective]:
    """Load the most recently persisted edit directives."""
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _edit_directives_path(run_id, output_dir)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [EditDirective.model_validate(d) for d in data]


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
