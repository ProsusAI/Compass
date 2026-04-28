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
