"""File-backed persistence for Review Agent state.

Follows the same pattern as prompt_builder_search_ops.py:
pure functions, file-backed, no in-memory state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from odysseus.agents.review_models import (
    DirectiveOutcome,
    MutationRecord,
)
from odysseus.project_dir import get_project_dir


def _default_output_dir() -> Path:
    return get_project_dir() / "outputs"


def _search_dir(search_state_id: str, output_dir: Path) -> Path:
    return output_dir / search_state_id


def _directive_history_path(search_state_id: str, output_dir: Path) -> Path:
    return _search_dir(search_state_id, output_dir) / "directive_history.json"


def _mutation_log_path(search_state_id: str, output_dir: Path) -> Path:
    return _search_dir(search_state_id, output_dir) / "mutation_log.json"


def _round_reports_dir(search_state_id: str, output_dir: Path) -> Path:
    return _search_dir(search_state_id, output_dir) / "round_reports"


def save_directive_history(
    search_state_id: str,
    history: list[DirectiveOutcome],
    *,
    output_dir: Path | None = None,
) -> None:
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _directive_history_path(search_state_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [h.model_dump(mode="json") for h in history]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_directive_history(
    search_state_id: str,
    *,
    output_dir: Path | None = None,
) -> list[DirectiveOutcome]:
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _directive_history_path(search_state_id, output_dir)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [DirectiveOutcome.model_validate(d) for d in data]


def save_mutation_log(
    search_state_id: str,
    log: list[MutationRecord],
    *,
    output_dir: Path | None = None,
) -> None:
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _mutation_log_path(search_state_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [r.model_dump(mode="json") for r in log]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_mutation_log(
    search_state_id: str,
    *,
    output_dir: Path | None = None,
) -> list[MutationRecord]:
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _mutation_log_path(search_state_id, output_dir)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [MutationRecord.model_validate(d) for d in data]


def save_round_report(
    search_state_id: str,
    round_num: int,
    reports: dict[str, dict[str, Any]],
    *,
    output_dir: Path | None = None,
) -> None:
    if output_dir is None:
        output_dir = _default_output_dir()
    dir_path = _round_reports_dir(search_state_id, output_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / f"round_{round_num}.json"
    path.write_text(json.dumps(reports, indent=2), encoding="utf-8")


def load_round_reports(
    search_state_id: str,
    *,
    output_dir: Path | None = None,
) -> dict[int, dict[str, dict[str, Any]]]:
    if output_dir is None:
        output_dir = _default_output_dir()
    dir_path = _round_reports_dir(search_state_id, output_dir)
    if not dir_path.exists():
        return {}
    result: dict[int, dict[str, dict[str, Any]]] = {}
    for path in sorted(dir_path.glob("round_*.json")):
        round_num = int(path.stem.split("_")[1])
        result[round_num] = json.loads(path.read_text(encoding="utf-8"))
    return result
