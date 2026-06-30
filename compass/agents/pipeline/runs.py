# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Pipeline run discovery and rerun-config helpers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from compass.agents.pipeline.checks import (
    _check_stage,
    _check_stage_2,
    _check_stage_3,
    _check_stage_4,
    _check_stage_5,
)

logger = logging.getLogger(__name__)


def discover_runs(outputs_dir: Path) -> list[str]:
    """Scan outputs_dir for pipeline runs, sorted most-recent-first by mtime.

    A valid run directory contains ``<run_id>/input/input_report.md``.
    """
    runs: list[tuple[float, str]] = []
    if not outputs_dir.is_dir():
        return []
    try:
        entries = list(outputs_dir.iterdir())
    except (PermissionError, OSError) as exc:
        logger.warning("Cannot read outputs directory %s: %s", outputs_dir, exc)
        return []
    for candidate in entries:
        if not candidate.is_dir():
            continue
        report = candidate / "input" / "input_report.md"
        if report.is_file():
            runs.append((report.stat().st_mtime, candidate.name))
    runs.sort(key=lambda x: x[0], reverse=True)
    return [run_id for _, run_id in runs]


def _run_summary_for(run_id: str, outputs_dir: Path, project_dir: Path) -> dict:
    """Return a minimal summary dict for a single run_id.

    Used to populate the discovered_runs array in get_pipeline_status responses.
    """
    run_dir = outputs_dir / run_id

    s1_status, _, _ = _check_stage(
        {"stage": 1, "name": "Input Report", "subfolder": "input", "files": ["input_report.md"]},
        run_dir,
        project_dir,
    )
    if s1_status != "complete":
        return {"run_id": run_id, "current_stage": 1, "has_converged_prompt": False}

    s2_status, _, _ = _check_stage_2(run_dir)
    if s2_status != "complete":
        return {"run_id": run_id, "current_stage": 2, "has_converged_prompt": False}

    s3_status, _, _ = _check_stage_3(project_dir, run_dir, rerun_config=_read_rerun_config(run_dir))
    if s3_status != "complete":
        return {"run_id": run_id, "current_stage": 3, "has_converged_prompt": False}

    s4_status, _, _ = _check_stage_4(run_dir)
    has_converged = s4_status == "complete"
    if not has_converged:
        return {"run_id": run_id, "current_stage": 4, "has_converged_prompt": False}

    s5_status, _, _ = _check_stage_5(run_dir)
    if s5_status != "complete":
        return {"run_id": run_id, "current_stage": 5, "has_converged_prompt": True}

    return {"run_id": run_id, "current_stage": 6, "has_converged_prompt": True}


def _validate_rerun_config(config: dict[str, Any]) -> tuple[bool, str]:
    """Validate rerun config structure. Returns (is_valid, detail)."""
    if config.get("mode") != "rerun":
        return False, "rerun_config_invalid_mode"
    if not config.get("source_prompt_version"):
        return False, "rerun_config_missing_source_version"
    return True, ""


def _read_rerun_config(run_dir: Path) -> dict[str, Any] | None:
    """Read and validate rerun_config.json, or None if absent/invalid."""
    config_path = run_dir / "rerun_config.json"
    if not config_path.is_file():
        return None
    try:
        config = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read rerun_config.json in %s: %s", run_dir, exc)
        return None
    valid, detail = _validate_rerun_config(config)
    if not valid:
        logger.warning("Invalid rerun_config.json in %s: %s", run_dir, detail)
        return None
    return config
