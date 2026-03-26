"""Stateless pipeline progress detection module.

Derives stage completion from artifact existence on disk.
Never writes files — pure queries only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from odysseus.project_dir import get_project_dir

# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

_STAGES: list[dict[str, Any]] = [
    {
        "stage": 1,
        "name": "Input Report",
        "subfolder": "input",
        "files": ["input_report.md"],
    },
    {
        "stage": 2,
        "name": "Data Validated",
        "subfolder": "validation",
        "files": ["transformed.jsonl", "data_quality_report.json", "routing_context.json"],
    },
    {
        "stage": 3,
        "name": "Routing Analysis & Split",
        "subfolder": "analysis",
        "files": [
            "validation_report.json",
            "dev.jsonl",
            "holdout.jsonl",
            "dev_rationale_card_set.json",
            "holdout_rationale_card_set.json",
            "vocabulary_registry.json",
        ],
    },
    {
        "stage": 4,
        "name": "Backend Configured",
        "subfolder": None,
        "files": [],  # special: checked via project_dir/backends/*.yaml
    },
    {
        "stage": 5,
        "name": "Prompt v1 Compiled",
        "subfolder": "prompts",
        "files": [],  # special: globs v1.*
    },
    {
        "stage": 6,
        "name": "Eval Loop Active",
        "subfolder": "search",
        "files": [],  # special: parses search_state.json for round >= 1
    },
    {
        "stage": 7,
        "name": "Converged",
        "subfolder": "search",
        "files": [],  # special: parses search_state.json for converged == true
    },
    {
        "stage": 8,
        "name": "Holdout Validation",
        "subfolder": None,
        "files": [],  # future stub
    },
    {
        "stage": 9,
        "name": "Final Report",
        "subfolder": None,
        "files": [],  # future stub
    },
]

# ---------------------------------------------------------------------------
# Next-action mapping
# ---------------------------------------------------------------------------

_NEXT_ACTION: dict[int, tuple[str, list[str], list[str]]] = {
    1: (
        "Submit an input report to start the pipeline.",
        ["submit_input_report"],
        ["odysseus://user_input"],
    ),
    2: (
        "Validate and transform the dataset.",
        ["validate_dataset", "transform_dataset"],
        ["odysseus://data_validation"],
    ),
    3: (
        "Run routing analysis and split the dataset into dev/holdout sets.",
        ["stratified_split_tool", "create_seed_registry_tool"],
        ["odysseus://routing_analysis"],
    ),
    4: (
        "Configure at least one routing backend (create a backends/*.yaml file).",
        [],
        [],
    ),
    5: (
        "Compile the initial routing prompt (v1).",
        ["optimize_routing_prompt"],
        ["odysseus://prompt_builder"],
    ),
    6: (
        "Start the eval loop to iteratively refine the routing prompt.",
        ["init_search_state_tool", "advance_round_tool"],
        ["odysseus://eval_loop"],
    ),
    7: (
        "The eval loop has converged. Run holdout validation.",
        ["run_holdout_eval", "filter_holdout_dataset_tool"],
        [],
    ),
    8: (
        "Generate the final report.",
        [],
        [],
    ),
    9: (
        "Pipeline complete.",
        [],
        [],
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def discover_runs(outputs_dir: Path) -> list[str]:
    """Scan outputs_dir for pipeline runs, sorted most-recent-first by mtime.

    A valid run directory contains ``<run_id>/input/input_report.md``.
    """
    runs: list[tuple[float, str]] = []
    if not outputs_dir.is_dir():
        return []
    for candidate in outputs_dir.iterdir():
        if not candidate.is_dir():
            continue
        report = candidate / "input" / "input_report.md"
        if report.is_file():
            runs.append((report.stat().st_mtime, candidate.name))
    runs.sort(key=lambda x: x[0], reverse=True)
    return [run_id for _, run_id in runs]


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

    # Resolve run_id
    if run_id is None:
        runs = discover_runs(outputs_dir)
        if not runs:
            action, tools, prompts = _next_action_for_stage(1)
            return {
                "run_id": None,
                "stages": [],
                "current_stage": 1,
                "current_stage_name": _STAGES[0]["name"],
                "next_action": "No pipeline runs found. Call submit_input_report to start.",
                "available_tools": tools,
                "available_prompts": prompts,
            }
        run_id = runs[0]

    run_dir = outputs_dir / run_id
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

        status, artifacts, detail = _check_stage(stage_def, run_dir, project_dir)

        entry: dict[str, Any] = {
            "stage": stage_num,
            "name": stage_name,
            "status": status,
            "artifacts": artifacts,
        }
        if detail:
            entry["detail"] = detail

        stage_results.append(entry)

        if status == "complete":
            current_stage = stage_num + 1
        else:
            found_incomplete = True

    # Cap current_stage at 9
    current_stage = min(current_stage, 9)

    current_stage_name = next(
        (s["name"] for s in _STAGES if s["stage"] == current_stage),
        _STAGES[-1]["name"],
    )
    next_action, tools, prompts = _next_action_for_stage(current_stage)

    return {
        "run_id": run_id,
        "stages": stage_results,
        "current_stage": current_stage,
        "current_stage_name": current_stage_name,
        "next_action": next_action,
        "available_tools": tools,
        "available_prompts": prompts,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_stage(
    stage_def: dict[str, Any],
    run_dir: Path,
    project_dir: Path,
) -> tuple[str, list[str], str]:
    """Check a single stage.

    Returns (status, artifact_paths, detail).
    """
    stage_num: int = stage_def["stage"]

    if stage_num == 4:
        return _check_stage_4(project_dir)
    if stage_num == 5:
        return _check_stage_5(run_dir)
    if stage_num == 6:
        return _check_stage_6(run_dir)
    if stage_num == 7:
        return _check_stage_7(run_dir)
    if stage_num in (8, 9):
        # Future stubs — always incomplete
        return "incomplete", [], ""
    if stage_num == 3:
        return _check_stage_3(stage_def, run_dir, project_dir)

    # Generic file-existence check (stages 1 & 2)
    subfolder: str | None = stage_def["subfolder"]
    files: list[str] = stage_def["files"]

    folder = run_dir / subfolder if subfolder else run_dir

    artifacts = [str(folder / f) for f in files]
    missing = [p for p in artifacts if not Path(p).is_file()]
    if missing:
        return "incomplete", artifacts, ""
    return "complete", artifacts, ""


def _check_stage_3(
    stage_def: dict[str, Any],
    run_dir: Path,
    project_dir: Path,
) -> tuple[str, list[str], str]:
    """Stage 3: Routing Analysis & Split, with in-progress detection."""
    folder = run_dir / "analysis"
    files: list[str] = stage_def["files"]
    artifacts = [str(folder / f) for f in files]
    missing = [p for p in artifacts if not Path(p).is_file()]

    if not missing:
        return "complete", artifacts, ""

    # Check for in-progress scratch files
    scratch_dir = project_dir / "scratch"
    in_progress_markers = [
        "phase1_classification.json",
        "phase2_rationale.json",
        "phase3_validated.json",
    ]
    found_scratch: list[str] = []
    if scratch_dir.is_dir():
        for sub in scratch_dir.iterdir():
            if not sub.is_dir():
                continue
            for marker in in_progress_markers:
                candidate = sub / marker
                if candidate.is_file():
                    found_scratch.append(str(candidate))

    if found_scratch:
        detail = f"Scratch files detected: {', '.join(found_scratch)}"
        return "in_progress", artifacts, detail

    return "incomplete", artifacts, ""


def _check_stage_4(project_dir: Path) -> tuple[str, list[str], str]:
    """Stage 4: Backend Configured — checks project_dir/backends/*.yaml."""
    backends_dir = project_dir / "backends"
    if not backends_dir.is_dir():
        return "incomplete", [], ""
    yaml_files = list(backends_dir.glob("*.yaml"))
    if not yaml_files:
        return "incomplete", [], ""
    artifacts = [str(f) for f in sorted(yaml_files)]
    return "complete", artifacts, ""


def _check_stage_5(run_dir: Path) -> tuple[str, list[str], str]:
    """Stage 5: Prompt v1 Compiled — globs v1.* in run_dir/prompts/."""
    prompts_dir = run_dir / "prompts"
    if not prompts_dir.is_dir():
        return "incomplete", [], ""
    matches = list(prompts_dir.glob("v1.*"))
    if not matches:
        return "incomplete", [], ""
    artifacts = [str(f) for f in sorted(matches)]
    return "complete", artifacts, ""


def _check_stage_6(run_dir: Path) -> tuple[str, list[str], str]:
    """Stage 6: Eval Loop Active — search_state.json with round >= 1."""
    search_state = run_dir / "search" / "search_state.json"
    if not search_state.is_file():
        return "incomplete", [], ""
    try:
        data = json.loads(search_state.read_text())
        if int(data.get("round", 0)) >= 1:
            return "complete", [str(search_state)], ""
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return "incomplete", [str(search_state)], ""


def _check_stage_7(run_dir: Path) -> tuple[str, list[str], str]:
    """Stage 7: Converged — search_state.json with converged == true."""
    search_state = run_dir / "search" / "search_state.json"
    if not search_state.is_file():
        return "incomplete", [], ""
    try:
        data = json.loads(search_state.read_text())
        if data.get("converged") is True:
            return "complete", [str(search_state)], ""
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return "incomplete", [str(search_state)], ""


def _next_action_for_stage(stage: int) -> tuple[str, list[str], list[str]]:
    """Return (next_action_text, tool_list, prompt_list) for the given stage."""
    return _NEXT_ACTION.get(
        stage,
        ("Pipeline complete.", [], []),
    )
