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
    {"stage": 1, "name": "Input Report", "subfolder": "input", "files": ["input_report.md"]},
    {"stage": 2, "name": "Data Validated", "subfolder": None, "files": []},
    {"stage": 3, "name": "Backend Configured", "subfolder": None, "files": []},
    {"stage": 4, "name": "Refinement Loop", "subfolder": "search", "files": []},
    {"stage": 5, "name": "Final Report", "subfolder": None, "files": []},
]

# ---------------------------------------------------------------------------
# Stage 4 dynamic HARD_STOP templates
# ---------------------------------------------------------------------------

_STAGE_4_COLD_START_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='review') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, "
    "build_review_briefing_tool, record_directive_outcomes_tool\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

_STAGE_4_BUILD_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, "
    "init_search_state_tool, register_candidate_tool, record_eval_result_tool, "
    "advance_round_tool, run_eval\n"
    "Your tools: get_pipeline_status only\n\n"
    "NOTE: optimize_routing_prompt is the pipeline entry-point tool (orchestrator-level only). "
    "Do not call it from within the sub-agent.\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

_STAGE_4_RERUN_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, "
    "init_search_state_tool, register_candidate_tool, record_eval_result_tool, "
    "advance_round_tool, run_eval\n"
    "Your tools: get_pipeline_status only\n\n"
    "NOTE: This is a rerun — the Prompt Builder Rerun agent will restructure the existing prompt "
    "for the new backend. Source prompt version: '{source_prompt_version}'. "
    "New backend: '{new_backend}'.\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

_STAGE_4_REVIEW_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 review-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='review') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, "
    "build_review_briefing_tool, record_directive_outcomes_tool\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
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
            "If Stage 3 is not complete:\n"
            "  - Check the status detail field. If detail is 'pricing_missing', ask the user\n"
            "    for input_cost_per_million_tokens, cached_cost_per_million_tokens, and\n"
            "    output_cost_per_million_tokens. Then re-dispatch the sub-agent with these\n"
            "    pricing values in the conversation context.\n"
            "  - Otherwise, re-dispatch the sub-agent. Do not perform backend setup yourself.\n"
            "  - If Stage 3 remains incomplete after 2 re-dispatches, report the error to the\n"
            "    user and halt.\n"
            "</HARD_STOP>\n\n"
            "<stage_system_prompt></stage_system_prompt>"
        ),
    ),
    # Stage 4 is handled dynamically by _next_action_for_stage_4
    5: (
        "The refinement loop has converged. Run holdout evaluation and generate the final report. "
        "REQUIRED: activate prompt 'odysseus_final_report' before calling any stage 5 tools.",
        [
            "filter_holdout_dataset_tool", "list_pareto_candidates", "run_holdout_eval",
            "build_final_report_briefing_tool", "save_final_report",
        ],
        ["odysseus_final_report"],
        (
            "<HARD_STOP>\n"
            "You MUST NOT call any Stage 5 tools from the current context.\n\n"
            "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
            "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='final_report') BEFORE spawning the sub-agent.\n\n"
            "Sub-agent tools: get_pipeline_status, filter_holdout_dataset_tool, "
            "list_pareto_candidates, run_holdout_eval, "
            "build_final_report_briefing_tool, save_final_report\n"
            "Your tools: get_pipeline_status only\n\n"
            "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
            "then call get_pipeline_status.\n"
            "If Stage 5 is not complete:\n"
            "  - Check the status detail field. If detail is 'version_selection_needed', read the\n"
            "    file at outputs/{run_id}/pareto_candidates_listed.json. Present the candidates\n"
            "    to the user as a table (version, quality score, cost, round) and ask which\n"
            "    prompt_version they want to evaluate on the holdout set. Then re-dispatch the\n"
            "    sub-agent with the chosen prompt_version in the conversation context.\n"
            "  - Otherwise, re-dispatch the sub-agent. Do not call stage tools yourself.\n"
            "  - If Stage 5 remains incomplete after 2 re-dispatches, report the error to the\n"
            "    user and halt.\n"
            "</HARD_STOP>\n\n"
            "<stage_system_prompt></stage_system_prompt>"
        ),
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

    s3_status, _, _ = _check_stage_3(project_dir, run_dir)
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
                "discovered_runs": [],
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
    if current_stage == 4:
        action, tools, prompts, subagent_instruction = _next_action_for_stage_4(run_dir)
    else:
        action, tools, prompts, subagent_instruction = _next_action_for_stage(current_stage)

    # Replace {run_id} placeholders in subagent instruction templates.
    if subagent_instruction:
        subagent_instruction = subagent_instruction.format(run_id=run_id or "new")

    # Populate discovered_runs for all known runs
    all_run_ids = discover_runs(outputs_dir)
    discovered_runs = [_run_summary_for(rid, outputs_dir, project_dir) for rid in all_run_ids]

    return {
        "run_id": run_id,
        "stages": stage_results,
        "current_stage": current_stage,
        "current_stage_name": current_stage_name,
        "next_action": action,
        "available_tools": tools,
        "activate_prompt": prompts[0] if prompts else None,
        "subagent_instruction": subagent_instruction,
        "discovered_runs": discovered_runs,
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
        return _check_stage_3(project_dir, run_dir)
    if stage_num == 4:
        return _check_stage_4(run_dir)
    if stage_num == 5:
        return _check_stage_5(run_dir)

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


def _check_stage_3(project_dir: Path, run_dir: Path) -> tuple[str, list[str], str]:
    """Stage 3: Backend Configured.

    In normal mode: at least one backends/*.yaml must have valid pricing.
    In rerun mode (rerun_config.json present): the specific new_backend named in
    the config must have a YAML with valid pricing, and new_backend must be non-null.
    """
    from odysseus.eval.backends.profile import BackendProfile

    rerun_config = _read_rerun_config(run_dir)

    if rerun_config is not None:
        # Rerun mode: new_backend must be explicitly set
        new_backend = rerun_config.get("new_backend")
        if not new_backend:
            return "incomplete", [], ""

        backends_dir = project_dir / "backends"
        yaml_path = backends_dir / f"{new_backend}.yaml"
        if not yaml_path.is_file():
            return "incomplete", [str(yaml_path)], ""

        try:
            profile = BackendProfile.from_yaml(yaml_path)
            if profile.pricing is not None:
                return "complete", [str(yaml_path)], ""
        except Exception:
            pass
        return "incomplete", [str(yaml_path)], "pricing_missing"

    # Normal mode: any backend with pricing
    backends_dir = project_dir / "backends"
    if not backends_dir.is_dir():
        return "incomplete", [], ""
    yaml_files = list(backends_dir.glob("*.yaml"))
    if not yaml_files:
        return "incomplete", [], ""

    artifacts = [str(f) for f in sorted(yaml_files)]
    has_priced_backend = False

    for yf in yaml_files:
        try:
            profile = BackendProfile.from_yaml(yf)
            if profile.pricing is not None:
                has_priced_backend = True
                break
        except Exception:
            continue

    if not has_priced_backend:
        return "incomplete", artifacts, "pricing_missing"
    return "complete", artifacts, ""


def _check_stage_4(run_dir: Path) -> tuple[str, list[str], str]:
    """Stage 4: Refinement Loop — search_state.json with converged == true."""
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


def _check_stage_5(run_dir: Path) -> tuple[str, list[str], str]:
    """Stage 5: Final Report — reports/final_report.md exists."""
    report = run_dir / "reports" / "final_report.md"
    pareto_candidates = run_dir / "pareto_candidates_listed.json"
    holdout_report = run_dir / "holdout_eval" / "report.json"

    if report.is_file():
        return "complete", [str(report)], ""

    artifacts: list[str] = []
    if pareto_candidates.is_file():
        artifacts.append(str(pareto_candidates))
    if holdout_report.is_file():
        artifacts.append(str(holdout_report))

    if pareto_candidates.is_file() and not holdout_report.is_file():
        return "incomplete", artifacts, "version_selection_needed"

    return "incomplete", artifacts, ""


def _next_action_for_stage_4(
    run_dir: Path,
) -> tuple[str, list[str], list[str], str]:
    """Return (action, tools, prompts, subagent_instruction) for Stage 4.

    Three-phase detection:
    1. No directive_history.json and no search_state.json -> cold-start (Review Agent)
    2. directive_history.json exists but no v1.* -> build-v1 (Prompt Builder)
    3. v1.* exists and search_state.json exists -> normal loop (read loop_phase)
    """
    # Rerun mode: skip three-phase logic
    rerun_config = _read_rerun_config(run_dir)
    if rerun_config is not None:
        source_version = rerun_config.get("source_prompt_version", "unknown")
        new_backend = rerun_config.get("new_backend", "unknown")
        rerun_instr = _STAGE_4_RERUN_INSTRUCTION.format(
            run_id=run_dir.name,
            source_prompt_version=source_version,
            new_backend=new_backend,
        )
        return (
            "Stage 4 — rerun mode: spawn the Prompt Builder Rerun agent to restructure "
            f"the source prompt (version {source_version}) for the new backend ({new_backend}). "
            "REQUIRED: activate prompt 'odysseus_prompt_builder_rerun' before calling any build tools.",
            [
                "get_search_state_tool",
                "init_search_state_tool",
                "register_candidate_tool",
                "record_eval_result_tool",
                "advance_round_tool",
                "run_eval",
            ],
            ["odysseus_prompt_builder_rerun"],
            rerun_instr,
        )

    search_dir = run_dir / "search"
    directive_history = search_dir / "directive_history.json"
    search_state_path = search_dir / "search_state.json"
    prompts_dir = run_dir / "prompts"
    has_v1 = prompts_dir.is_dir() and bool(list(prompts_dir.glob("v1.*")))

    # Phase 1: Cold-start — no directives and no search state
    if not directive_history.is_file() and not search_state_path.is_file():
        return (
            "Stage 4 — cold-start: spawn the Review Agent to select initial "
            "few-shot seed examples from the dataset. "
            "REQUIRED: activate prompt 'odysseus_review_agent' before calling any review tools.",
            [
                "get_search_state_tool",
                "build_review_briefing_tool",
                "record_directive_outcomes_tool",
            ],
            ["odysseus_review_agent"],
            _STAGE_4_COLD_START_INSTRUCTION,
        )

    # Phase 2: Build v1 — directives exist but no compiled prompt yet
    if not has_v1:
        return (
            "Stage 4 — build phase: spawn the Prompt Builder to compile the "
            "initial routing prompt (v1) using seed examples from the Review Agent. "
            "REQUIRED: activate prompt 'odysseus_prompt_builder' before calling any build tools.",
            [
                "get_search_state_tool",
                "init_search_state_tool",
                "register_candidate_tool",
                "record_eval_result_tool",
                "advance_round_tool",
                "run_eval",
            ],
            ["odysseus_prompt_builder"],
            _STAGE_4_BUILD_INSTRUCTION,
        )

    # Phase 3: Normal loop — read loop_phase from search state
    loop_phase = "review"
    if search_state_path.is_file():
        try:
            data = json.loads(search_state_path.read_text())
            loop_phase = data.get("loop_phase", "review")
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    if loop_phase == "review":
        return (
            "Stage 4 — review phase: spawn the Review Agent to analyse "
            "eval results and emit edit directives. "
            "REQUIRED: activate prompt 'odysseus_review_agent' before calling any review tools.",
            [
                "get_search_state_tool",
                "build_review_briefing_tool",
                "record_directive_outcomes_tool",
            ],
            ["odysseus_review_agent"],
            _STAGE_4_REVIEW_INSTRUCTION,
        )
    else:
        return (
            "Stage 4 — build phase: spawn the Prompt Builder to generate "
            "prompt variants and evaluate them. "
            "REQUIRED: activate prompt 'odysseus_prompt_builder' before calling any build tools.",
            [
                "get_search_state_tool",
                "init_search_state_tool",
                "register_candidate_tool",
                "record_eval_result_tool",
                "advance_round_tool",
                "run_eval",
            ],
            ["odysseus_prompt_builder"],
            _STAGE_4_BUILD_INSTRUCTION,
        )


def _next_action_for_stage(stage: int) -> tuple[str, list[str], list[str], str | None]:
    """Return (next_action_text, tool_list, prompt_list, subagent_instruction) for the given stage."""
    return _NEXT_ACTION.get(
        stage,
        ("Pipeline complete.", [], [], None),
    )


def _read_rerun_config(run_dir: Path) -> dict | None:
    """Read rerun_config.json from run_dir, returning None if absent or malformed."""
    config_path = run_dir / "rerun_config.json"
    if not config_path.is_file():
        return None
    try:
        return json.loads(config_path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return None
