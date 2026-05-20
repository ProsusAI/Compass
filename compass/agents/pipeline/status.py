"""Stateless pipeline progress detection module.

Derives stage completion from artifact existence on disk.
Never writes files — pure queries only.
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Any

# Re-export sub-module symbols so existing importers continue to work.
from compass.agents.pipeline.checks import (  # noqa: F401
    _check_stage,
    _check_stage_2,
    _check_stage_3,
    _check_stage_4,
    _check_stage_5,
    _has_critical_schema_failure,
)
from compass.agents.pipeline.instructions import (
    STAGE_1_INSTRUCTION,
    STAGE_2_INSTRUCTION,
    STAGE_3_INSTRUCTION,
    STAGE_5_INSTRUCTION,
)
from compass.agents.pipeline.runs import (  # noqa: F401
    _read_rerun_config,
    _run_summary_for,
    _validate_rerun_config,
    discover_runs,
)
from compass.agents.pipeline.stage4 import (  # noqa: F401
    _STAGE_4_BUILD_ACTION_FIRST,
    _STAGE_4_BUILD_ACTION_RECOVER,
    _STAGE_4_BUILD_ACTION_STEADY,
    _STAGE_4_PHASE_CONFIG,
    _detect_stage_4_phase,
    _detect_stage_4_phase_beam,
    _ensure_stage4_search_state,
    _next_action_for_stage_4,
    _read_algorithm_from_state,
)
from compass.agents.pipeline.status_types import StageDetail  # noqa: F401
from compass.project_dir import get_project_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

_STAGES: list[dict[str, Any]] = [
    {"stage": 1, "name": "Input Report", "subfolder": "input", "files": ["input_report.md"]},
    {"stage": 2, "name": "Data Validated", "subfolder": None, "files": []},
    {"stage": 3, "name": "Backend Configured", "subfolder": None, "files": []},
    {"stage": 4, "name": "Refinement Loop", "subfolder": "search", "files": []},
    {"stage": 5, "name": "Final Report", "subfolder": None, "files": []},
]

# ---------------------------------------------------------------------------
# Next-action mapping
# ---------------------------------------------------------------------------

_NEXT_ACTION: dict[int, tuple[str, list[str], list[str], str | None]] = {
    1: (
        "Submit an input report to start the pipeline. "
        "REQUIRED: activate prompt 'compass_routing_input' before calling any stage 1 tools.",
        ["submit_input_report"],
        ["compass_routing_input"],
        STAGE_1_INSTRUCTION,
    ),
    2: (
        "Validate and transform the dataset, then produce the dev/holdout split. "
        "REQUIRED: activate prompt 'compass_data_validation' before calling any stage 2 tools.",
        [
            "validate_dataset",
            "detect_and_parse_dataset",
            "transform_dataset",
            "save_routing_context",
            "stratified_split",
        ],
        ["compass_data_validation"],
        STAGE_2_INSTRUCTION,
    ),
    3: (
        "Configure at least one routing backend (create a backends/*.yaml file). "
        "REQUIRED: activate prompt 'compass_backend_setup' for guided configuration.",
        [],
        ["compass_backend_setup"],
        STAGE_3_INSTRUCTION,
    ),
    # Stage 4 is handled dynamically by _next_action_for_stage_4
    5: (
        "The refinement loop has converged. Run holdout evaluation and generate the final report. "
        "REQUIRED: activate prompt 'compass_final_report' before calling any stage 5 tools.",
        [
            "filter_holdout_dataset",
            "list_pareto_candidates",
            "run_holdout_eval",
            "build_final_report_briefing",
            "save_final_report",
        ],
        ["compass_final_report"],
        STAGE_5_INSTRUCTION,
    ),
    6: (
        "Pipeline complete. Present exactly these three options to the user:\n"
        "1. **Continue** — resume the most recent run at its current stage.\n"
        "2. **Rerun with different backend** — take the converged prompt and "
        "re-evaluate against a new backend (format restructure only, no re-optimization). "
        "To execute: call initiate_rerun(run_id=<run_id>), then guide through Stage 3 backend setup.\n"
        "3. **Start again** — new run from scratch.\n\n"
        "Do NOT invent additional options. Present only these three.",
        [],
        [],
        None,
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_pipeline_status(
    outputs_dir: Path,
    run_id: str | None,
    project_dir: Path | None = None,
) -> dict[str, Any]:
    """Return pipeline status for the given run.

    If ``run_id`` is None, uses the most recent run. Returns a minimal
    response when no runs exist at all.
    """
    if project_dir is None:
        project_dir = get_project_dir()

    # Capture whether the caller explicitly supplied a run_id before the
    # resolve-to-most-recent step may rewrite it.  When the caller supplied one,
    # discovered_runs is skipped entirely — the orchestrator only needs it during
    # the Stage 1 entry-point call (where run_id is None).
    caller_run_id = run_id

    # Resolve run_id
    if run_id is None:
        runs = discover_runs(outputs_dir)
        if not runs:
            action, tools, prompts, subagent_instruction = _next_action_for_stage(1)
            return {
                "run_id": None,
                "stages": [],
                "current_stage": 1,
                "current_stage_name": _STAGES[0]["name"],
                "next_action": "No pipeline runs found. Call submit_input_report to start.",
                "available_tools": tools,
                "activate_prompt": prompts[0] if prompts else None,
                "subagent_instruction": subagent_instruction,
                "discovered_runs": [],
            }
        run_id = runs[0]

    run_dir = outputs_dir / run_id

    # Read rerun config once and pass through to avoid repeated file I/O
    rerun_config = _read_rerun_config(run_dir)

    stage_results: list[dict[str, Any]] = []
    current_stage = 1
    found_incomplete = False

    for stage_def in _STAGES:
        stage_num: int = stage_def["stage"]
        stage_name: str = stage_def["name"]

        if found_incomplete:
            stage_results.append(
                {
                    "stage": stage_num,
                    "name": stage_name,
                    "status": "blocked",
                    "artifacts": [],
                }
            )
            continue

        status, artifacts, detail = _check_stage(
            stage_def,
            run_dir,
            project_dir,
            rerun_config=rerun_config,
        )

        entry: dict[str, Any] = {
            "stage": stage_num,
            "name": stage_name,
            "status": status,
            "artifacts": artifacts,
        }
        if detail is not None:
            entry["detail"] = dataclasses.asdict(detail)

        stage_results.append(entry)

        if status == "complete":
            current_stage = stage_num + 1
        else:
            found_incomplete = True

    # Cap at max pipeline stage (5) unless all stages are complete.
    # When all are complete, current_stage == 6 signals "pipeline done"
    # and falls through to the default "Pipeline complete." action.
    max_stage = _STAGES[-1]["stage"]
    current_stage = min(current_stage, max_stage + 1)

    current_stage_name = next(
        (s["name"] for s in _STAGES if s["stage"] == current_stage),
        _STAGES[-1]["name"],
    )

    # Stage 4 uses dynamic next-action based on three-phase detection
    algorithm: str = "hill_climb"
    if current_stage == 4:
        action, tools, prompts, subagent_instruction, algorithm = _next_action_for_stage_4(
            run_dir,
            rerun_config=rerun_config,
            project_dir=project_dir,
        )
    else:
        action, tools, prompts, subagent_instruction = _next_action_for_stage(current_stage)

    # Replace {run_id} placeholders in subagent instruction templates.
    if subagent_instruction:
        subagent_instruction = subagent_instruction.format(run_id=run_id or "new")

    # Populate discovered_runs only on the entry-point call (caller_run_id is None).
    # When a run_id is already bound, the orchestrator never reads this array, so
    # skip the disk scan to avoid ~30 redundant discover_runs + _run_summary_for
    # calls per pipeline run.
    if caller_run_id is None:
        all_run_ids = discover_runs(outputs_dir)
        discovered_runs: list[dict[str, Any]] = [_run_summary_for(rid, outputs_dir, project_dir) for rid in all_run_ids]
    else:
        discovered_runs = []

    return {
        "run_id": run_id,
        "stages": stage_results,
        "current_stage": current_stage,
        "current_stage_name": current_stage_name,
        "next_action": action,
        "available_tools": tools,
        "activate_prompt": prompts[0] if prompts else None,
        "algorithm": algorithm,
        "subagent_instruction": subagent_instruction,
        "discovered_runs": discovered_runs,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _next_action_for_stage(stage: int) -> tuple[str, list[str], list[str], str | None]:
    """Return (next_action_text, tool_list, prompt_list, subagent_instruction) for the given stage."""
    return _NEXT_ACTION.get(
        stage,
        ("Pipeline complete.", [], [], None),
    )
