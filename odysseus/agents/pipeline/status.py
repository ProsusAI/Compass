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
        "subfolder": None,  # custom checker spans validation/ and analysis/
        "files": [],
    },
    {
        "stage": 3,
        "name": "Backend Configured",
        "subfolder": None,
        "files": [],  # special: checked via project_dir/backends/*.yaml
    },
    {
        "stage": 4,
        "name": "Prompt v1 Compiled",
        "subfolder": "prompts",
        "files": [],  # special: globs v1.*
    },
    {
        "stage": 5,
        "name": "Refinement Loop",
        "subfolder": "search",
        "files": [],  # special: parses search_state.json for converged == true
    },
    {
        "stage": 6,
        "name": "Holdout Validation",
        "subfolder": "reports",
        "files": [],  # special: holdout_report.json
    },
    {
        "stage": 7,
        "name": "Final Report",
        "subfolder": None,
        "files": [],  # future stub
    },
]

# ---------------------------------------------------------------------------
# Stage 5 dynamic HARD_STOP templates
# ---------------------------------------------------------------------------

_STAGE_5_BUILD_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 5 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, "
    "init_search_state_tool, register_candidate_tool, record_eval_result_tool, "
    "advance_round_tool, run_eval, filter_holdout_dataset_tool\n"
    "Your tools: get_pipeline_status only\n\n"
    "NOTE: optimize_routing_prompt is the pipeline entry-point tool (orchestrator-level only). "
    "Do not call it from within the sub-agent.\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 5 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

_STAGE_5_REVIEW_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 5 review-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='review') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, "
    "build_review_briefing_tool, record_directive_outcomes_tool\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 5 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

# ---------------------------------------------------------------------------
# Next-action mapping
# ---------------------------------------------------------------------------

_NEXT_ACTION: dict[int, tuple[str, list[str], list[str], str | None]] = {
    1: (
        "Submit an input report to start the pipeline. "
        "REQUIRED: activate prompt 'odysseus_routing_input' before calling any stage 1 tools.",
        ["submit_input_report"],
        ["odysseus_routing_input"],
        (
            "<HARD_STOP>\n"
            "You MUST NOT call any Stage 1 tools from the current context.\n\n"
            "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
            "PRE-DISPATCH: Call start_stage(stage='input_report') BEFORE spawning the sub-agent.\n"
            "(No run_id yet — Stage 1 creates it via submit_input_report.)\n\n"
            "Sub-agent tools: get_pipeline_status, submit_input_report\n"
            "Your tools: get_pipeline_status only\n\n"
            "POST-EXIT: After the sub-agent returns, extract the run_id from its output, "
            "then call complete_stage(run_id='<run_id_from_submit>'), "
            "then call get_pipeline_status.\n"
            "If Stage 1 is not complete, re-dispatch the sub-agent. Do not call stage tools yourself.\n"
            "</HARD_STOP>\n\n"
            "<stage_system_prompt></stage_system_prompt>"
        ),
    ),
    2: (
        "Validate and transform the dataset, then produce the dev/holdout split. "
        "REQUIRED: activate prompt 'odysseus_data_validation' before calling any stage 2 tools.",
        [
            "validate_dataset",
            "detect_and_parse_dataset",
            "transform_dataset",
            "save_routing_context",
            "stratified_split_tool",
        ],
        ["odysseus_data_validation"],
        (
            "<HARD_STOP>\n"
            "You MUST NOT call any Stage 2 tools from the current context.\n\n"
            "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
            "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='data_validation') BEFORE spawning the sub-agent.\n\n"
            "Sub-agent tools: get_pipeline_status, validate_dataset, "
            "detect_and_parse_dataset, transform_dataset, save_routing_context, "
            "stratified_split_tool\n"
            "Your tools: get_pipeline_status only\n\n"
            "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
            "then call get_pipeline_status.\n"
            "If Stage 2 is not complete, re-dispatch the sub-agent. Do not call stage tools yourself.\n"
            "</HARD_STOP>\n\n"
            "<stage_system_prompt></stage_system_prompt>"
        ),
    ),
    3: (
        "Configure at least one routing backend (create a backends/*.yaml file). "
        "REQUIRED: activate prompt 'odysseus_backend_setup' for guided configuration.",
        [],
        ["odysseus_backend_setup"],
        (
            "<HARD_STOP>\n"
            "You MUST NOT perform backend setup from the current context.\n\n"
            "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
            "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='backend_setup') BEFORE spawning the sub-agent.\n\n"
            "Sub-agent tools: get_pipeline_status, get_default_pricing\n"
            "Your tools: get_pipeline_status only\n\n"
            "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
            "then call get_pipeline_status.\n"
            "If Stage 3 is not complete, re-dispatch the sub-agent. Do not perform backend setup yourself.\n"
            "</HARD_STOP>\n\n"
            "<stage_system_prompt></stage_system_prompt>"
        ),
    ),
    4: (
        "Compile the initial routing prompt (v1). "
        "REQUIRED: activate prompt 'odysseus_prompt_builder' before calling any stage 4 tools.",
        [
            "init_search_state_tool",
            "register_candidate_tool",
            "record_eval_result_tool",
            "advance_round_tool",
            "get_search_state_tool",
            "run_eval",
            "filter_holdout_dataset_tool",
        ],
        ["odysseus_prompt_builder"],
        (
            "<HARD_STOP>\n"
            "You MUST NOT call any Stage 4 tools from the current context.\n\n"
            "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
            "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') BEFORE spawning the sub-agent.\n\n"
            "Sub-agent tools: get_pipeline_status, init_search_state_tool, "
            "register_candidate_tool, record_eval_result_tool, advance_round_tool, "
            "get_search_state_tool, run_eval, filter_holdout_dataset_tool\n"
            "Your tools: get_pipeline_status only\n\n"
            "NOTE: optimize_routing_prompt is the pipeline entry-point tool (orchestrator-level only).\n"
            "It is NOT a stage 4 sub-agent tool and must not be called from within the sub-agent.\n\n"
            "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
            "then call get_pipeline_status.\n"
            "If Stage 4 is not complete, re-dispatch the sub-agent. Do not call stage tools yourself.\n"
            "</HARD_STOP>\n\n"
            "<stage_system_prompt></stage_system_prompt>"
        ),
    ),
    # Stage 5 is handled dynamically by _next_action_for_stage_5
    6: (
        "The refinement loop has converged. Run holdout validation.",
        ["run_holdout_eval", "filter_holdout_dataset_tool"],
        [],
        (
            "<HARD_STOP>\n"
            "You MUST NOT call any Stage 6 tools from the current context.\n\n"
            "REQUIRED: Spawn a sub-agent to run holdout validation.\n\n"
            "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='holdout') BEFORE spawning the sub-agent.\n\n"
            "Sub-agent tools: get_pipeline_status, filter_holdout_dataset_tool, run_holdout_eval\n"
            "Your tools: get_pipeline_status only\n\n"
            "Sub-agent instructions:\n"
            "1. Call get_pipeline_status to verify current_stage is 6\n"
            "2. Call filter_holdout_dataset_tool to remove few-shot examples from the holdout set\n"
            "3. Call run_holdout_eval to evaluate the best prompt against the filtered holdout set\n"
            "4. Call get_pipeline_status to verify stage completion\n\n"
            "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
            "then call get_pipeline_status.\n"
            "If Stage 6 is not complete, re-dispatch the sub-agent. Do not call stage tools yourself.\n"
            "</HARD_STOP>"
        ),
    ),
    7: (
        "Generate the final report.",
        [],
        [],
        None,
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

    # Cap current_stage at 7 (max pipeline stage)
    current_stage = min(current_stage, 7)

    current_stage_name = next(
        (s["name"] for s in _STAGES if s["stage"] == current_stage),
        _STAGES[-1]["name"],
    )

    # Stage 5 uses dynamic next-action based on loop_phase
    if current_stage == 5:
        action, tools, prompts, subagent_instruction = _next_action_for_stage_5(run_dir)
    else:
        action, tools, prompts, subagent_instruction = _next_action_for_stage(current_stage)

    # Replace {run_id} placeholders in subagent instruction templates.
    if subagent_instruction:
        subagent_instruction = subagent_instruction.format(run_id=run_id or "new")

    return {
        "run_id": run_id,
        "stages": stage_results,
        "current_stage": current_stage,
        "current_stage_name": current_stage_name,
        "next_action": action,
        "available_tools": tools,
        "activate_prompt": prompts[0] if prompts else None,
        "subagent_instruction": subagent_instruction,
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

    if stage_num == 2:
        return _check_stage_2(run_dir)
    if stage_num == 3:
        return _check_stage_3(project_dir)
    if stage_num == 4:
        return _check_stage_4(run_dir)
    if stage_num == 5:
        return _check_stage_5(run_dir)
    if stage_num == 6:
        return _check_stage_6(run_dir)
    if stage_num in (7,):
        # Future stubs — always incomplete
        return "incomplete", [], ""

    # Generic file-existence check (stage 1)
    subfolder: str | None = stage_def["subfolder"]
    files: list[str] = stage_def["files"]

    folder = run_dir / subfolder if subfolder else run_dir

    artifacts = [str(folder / f) for f in files]
    missing = [p for p in artifacts if not Path(p).is_file()]
    if missing:
        return "incomplete", artifacts, ""
    return "complete", artifacts, ""


def _check_stage_2(run_dir: Path) -> tuple[str, list[str], str]:
    """Stage 2: Data Validated — validation files + dev/holdout split outputs."""
    validation_files = [
        run_dir / "validation" / "transformed.jsonl",
        run_dir / "validation" / "data_quality_report.json",
        run_dir / "validation" / "routing_context.json",
    ]
    split_files = [
        run_dir / "analysis" / "dev.jsonl",
        run_dir / "analysis" / "holdout.jsonl",
    ]
    all_files = validation_files + split_files
    artifacts = [str(f) for f in all_files]
    missing = [p for p in artifacts if not Path(p).is_file()]
    if missing:
        return "incomplete", artifacts, ""
    return "complete", artifacts, ""


def _check_stage_3(project_dir: Path) -> tuple[str, list[str], str]:
    """Stage 3: Backend Configured — checks project_dir/backends/*.yaml."""
    backends_dir = project_dir / "backends"
    if not backends_dir.is_dir():
        return "incomplete", [], ""
    yaml_files = list(backends_dir.glob("*.yaml"))
    if not yaml_files:
        return "incomplete", [], ""
    artifacts = [str(f) for f in sorted(yaml_files)]
    return "complete", artifacts, ""


def _check_stage_4(run_dir: Path) -> tuple[str, list[str], str]:
    """Stage 4: Prompt v1 Compiled — globs v1.* in run_dir/prompts/."""
    prompts_dir = run_dir / "prompts"
    if not prompts_dir.is_dir():
        return "incomplete", [], ""
    matches = list(prompts_dir.glob("v1.*"))
    if not matches:
        return "incomplete", [], ""
    artifacts = [str(f) for f in sorted(matches)]
    return "complete", artifacts, ""


def _check_stage_5(run_dir: Path) -> tuple[str, list[str], str]:
    """Stage 5: Refinement Loop — search_state.json with converged == true."""
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


def _check_stage_6(run_dir: Path) -> tuple[str, list[str], str]:
    """Stage 6: Holdout Validation — reports/holdout/holdout_report.json exists."""
    report = run_dir / "reports" / "holdout" / "holdout_report.json"
    if report.is_file():
        return "complete", [str(report)], ""
    return "incomplete", [], ""


def _next_action_for_stage_5(
    run_dir: Path,
) -> tuple[str, list[str], list[str], str]:
    """Return (action, tools, prompts, subagent_instruction) for Stage 5.

    Reads search_state.json to determine loop_phase (defaults to 'build' if
    state file is absent or malformed).
    """
    search_state_path = run_dir / "search" / "search_state.json"
    loop_phase = "review"
    if search_state_path.is_file():
        try:
            data = json.loads(search_state_path.read_text())
            loop_phase = data.get("loop_phase", "review")
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    if loop_phase == "review":
        return (
            "Stage 5 — review phase: spawn the Review Agent sub-agent to analyse "
            "eval results and emit edit directives. "
            "REQUIRED: activate prompt 'odysseus_review_agent' before calling any review tools.",
            [
                "get_search_state_tool",
                "build_review_briefing_tool",
                "record_directive_outcomes_tool",
            ],
            ["odysseus_review_agent"],
            _STAGE_5_REVIEW_INSTRUCTION,
        )
    else:
        return (
            "Stage 5 — build phase: spawn the Prompt Builder sub-agent to generate "
            "prompt variants and evaluate them. "
            "REQUIRED: activate prompt 'odysseus_prompt_builder' before calling any build tools.",
            [
                "get_search_state_tool",
                "init_search_state_tool",
                "register_candidate_tool",
                "record_eval_result_tool",
                "advance_round_tool",
                "run_eval",
                "filter_holdout_dataset_tool",
            ],
            ["odysseus_prompt_builder"],
            _STAGE_5_BUILD_INSTRUCTION,
        )


def _next_action_for_stage(stage: int) -> tuple[str, list[str], list[str], str | None]:
    """Return (next_action_text, tool_list, prompt_list, subagent_instruction) for the given stage."""
    return _NEXT_ACTION.get(
        stage,
        ("Pipeline complete.", [], [], None),
    )
