"""Stateless pipeline progress detection module.

Derives stage completion from artifact existence on disk.
Never writes files — pure queries only.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from odysseus.agents.pipeline.instructions import (
    STAGE_1_INSTRUCTION,
    STAGE_2_INSTRUCTION,
    STAGE_3_INSTRUCTION,
    STAGE_4_BUILD_INSTRUCTION,
    STAGE_4_BUILD_RECOVERING_INSTRUCTION,
    STAGE_4_CALIBRATION_INSTRUCTION,
    STAGE_4_COLD_START_INSTRUCTION,
    STAGE_4_RERUN_INSTRUCTION,
    STAGE_4_REVIEW_INSTRUCTION,
    STAGE_4_REVIEW_POST_COLDSTART_INSTRUCTION,
    STAGE_5_INSTRUCTION,
)
from odysseus.project_dir import get_project_dir


def _is_build_dispatched(run_id: str, search_dir: Path) -> bool:  # noqa: ARG001
    """Return True iff the build-dispatch marker exists in search_dir.

    Inline helper rather than importing from dispatch to avoid a circular
    dependency (dispatch → project_dir; status → pipeline → dispatch).
    The ``run_id`` parameter is accepted for API symmetry but the
    search_dir path already encodes the run identity.
    """
    build_marker = search_dir / "build_dispatched.json"
    return build_marker.exists()


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
# Deduplicated tool lists for Stage 4 phases
# ---------------------------------------------------------------------------

_COLD_REVIEW_TOOLS: list[str] = [
    "get_search_state_tool",
    "build_review_briefing_tool",
    "record_directive_outcomes_tool",
]

_REVIEW_TOOLS: list[str] = [
    "get_search_state_tool",
    "build_review_briefing_tool",
    "record_directive_outcomes_tool",
    "get_prompt_text_tool",
    "query_holdout_examples_tool",
]

_BUILD_TOOLS: list[str] = [
    "get_search_state_tool",
    "get_edit_directives_tool",
    "init_search_state_tool",
    "register_candidate_tool",
    "record_eval_result_tool",
    "advance_step_tool",
    "run_eval",
    "run_batch_eval",
]

_RERUN_TOOLS: list[str] = [
    "get_search_state_tool",
    "init_search_state_tool",
    "register_candidate_tool",
    "record_eval_result_tool",
    "advance_step_tool",
    "run_eval",
]

# ---------------------------------------------------------------------------
# Next-action mapping
# ---------------------------------------------------------------------------

_NEXT_ACTION: dict[int, tuple[str, list[str], list[str], str | None]] = {
    1: (
        "Submit an input report to start the pipeline. "
        "REQUIRED: activate prompt 'odysseus_routing_input' before calling any stage 1 tools.",
        ["submit_input_report"],
        ["odysseus_routing_input"],
        STAGE_1_INSTRUCTION,
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
        STAGE_2_INSTRUCTION,
    ),
    3: (
        "Configure at least one routing backend (create a backends/*.yaml file). "
        "REQUIRED: activate prompt 'odysseus_backend_setup' for guided configuration.",
        [],
        ["odysseus_backend_setup"],
        STAGE_3_INSTRUCTION,
    ),
    # Stage 4 is handled dynamically by _next_action_for_stage_4
    5: (
        "The refinement loop has converged. Run holdout evaluation and generate the final report. "
        "REQUIRED: activate prompt 'odysseus_final_report' before calling any stage 5 tools.",
        [
            "filter_holdout_dataset_tool",
            "list_pareto_candidates",
            "run_holdout_eval",
            "build_final_report_briefing_tool",
            "save_final_report",
        ],
        ["odysseus_final_report"],
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
        "algorithm": algorithm,
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
    rerun_config: dict[str, Any] | None = None,
) -> tuple[str, list[str], str]:
    """Check a single stage.

    Returns (status, artifact_paths, detail).
    """
    stage_num: int = stage_def["stage"]

    if stage_num == 2:
        return _check_stage_2(run_dir)
    if stage_num == 3:
        return _check_stage_3(project_dir, run_dir, rerun_config=rerun_config)
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
    """Stage 2: Data Validated — validation files + dev/holdout split outputs.

    Critical-severity failures in the data quality report block stage
    completion regardless of file presence: downstream stages (eval,
    prompt builder) read the dataset verbatim and would silently
    produce broken results (e.g. zero cost/quality metrics) on
    misaligned route labels.
    """
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

    quality_report_path = run_dir / "validation" / "data_quality_report.json"
    if quality_report_path.is_file() and _has_critical_schema_failure(quality_report_path):
        return "incomplete", artifacts, "data_quality_critical_fail"

    missing = [p for p in artifacts if not Path(p).is_file()]
    if not missing:
        return "complete", artifacts, ""

    # Check for intermediate "proposed mapping" state
    proposed_mapping = run_dir / "validation" / "proposed_mapping.json"
    transformed = run_dir / "validation" / "transformed.jsonl"
    if proposed_mapping.is_file() and not transformed.is_file():
        return "incomplete", artifacts + [str(proposed_mapping)], "mapping_confirmation_needed"

    return "incomplete", artifacts, ""


def _has_critical_schema_failure(quality_report_path: Path) -> bool:
    """Return True if the data quality report has any critical schema failure.

    Read defensively — a missing or malformed report is treated as no
    critical failure (the file-existence checks elsewhere handle absence).
    """
    try:
        report = json.loads(quality_report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    findings = report.get("schema_findings") if isinstance(report, dict) else None
    if not isinstance(findings, list):
        return False
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if finding.get("severity") == "critical" and finding.get("status") == "fail":
            return True
    return False


def _check_stage_3(
    project_dir: Path,
    run_dir: Path,
    rerun_config: dict[str, Any] | None = None,
) -> tuple[str, list[str], str]:
    """Stage 3: Backend Configured.

    In normal mode: at least one backends/*.yaml must have valid pricing.
    In rerun mode (rerun_config.json present): the specific new_backend named in
    the config must have a YAML with valid pricing, and new_backend must be non-null.
    """
    from odysseus.eval.backends.profile import BackendProfile

    # When called from _run_summary_for (no rerun_config passed), read from disk
    if rerun_config is None:
        rerun_config = _read_rerun_config(run_dir)

    if rerun_config is not None:
        # Rerun mode: new_backend must be explicitly set
        new_backend = rerun_config.get("new_backend")
        if not new_backend:
            return "incomplete", [], "rerun_backend_not_configured"

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
        backend_options = run_dir / "backend_options.json"
        if backend_options.is_file():
            return "incomplete", [str(backend_options)], "backend_selection_needed"
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
    holdout_eval_dir = run_dir / "holdout_eval"

    # Check both flat path and versioned subdirectories (e.g. holdout_eval/v7/report.json)
    versioned_reports = list(holdout_eval_dir.glob("v*/report.json"))
    flat_report = holdout_eval_dir / "report.json"
    holdout_report_path: Path | None = (
        versioned_reports[0] if versioned_reports else (flat_report if flat_report.is_file() else None)
    )
    holdout_report_exists = holdout_report_path is not None

    if report.is_file():
        return "complete", [str(report)], ""

    artifacts: list[str] = []
    if pareto_candidates.is_file():
        artifacts.append(str(pareto_candidates))
    if holdout_report_path is not None:
        artifacts.append(str(holdout_report_path))

    if pareto_candidates.is_file() and not holdout_report_exists:
        return "incomplete", artifacts, "version_selection_needed"

    return "incomplete", artifacts, ""


# ---------------------------------------------------------------------------
# Stage 4 — three-phase detection
# ---------------------------------------------------------------------------

_VALID_LOOP_PHASES = {
    "build",
    "review",
    "warmup_seed",
    "warmup_build",
    "warmup_reduce",
    "calibration",
    "build_recovering",
}


def _detect_stage_4_phase(
    run_dir: Path,
    rerun_config: dict[str, Any] | None,
) -> str:
    """Detect which phase Stage 4 is in.

    Returns one of: ``"rerun"``, ``"cold_start"``, ``"build_v1"``,
    ``"review"``, ``"review_post_coldstart"``, ``"build"``, or one of the
    extended phases (``"warmup_seed"``, ``"warmup_build"``,
    ``"warmup_reduce"``, ``"calibration"``, ``"build_recovering"``) for
    feature branches.

    ``"review_post_coldstart"`` is a derived phase (not a raw on-disk value):
    it is returned when ``loop_phase == "review"``, ``round == 1``, and
    ``algorithm == "beam"``.

    For ``algorithm == "emosa"`` the function uses the calibration-aware
    detection path (no cold_start/build_v1 phases).

    Defense-in-depth: if the persisted ``loop_phase`` is ``"build"`` but
    neither ``child_variants.json`` nor ``build_dispatched.json`` exist on
    disk, the phase is re-interpreted as ``"review"`` to prevent deadlock.
    """
    if rerun_config is not None:
        return "rerun"

    search_dir = run_dir / "search"
    search_state_path = search_dir / "search_state.json"

    # -----------------------------------------------------------------------
    # EMOSA calibration-aware path
    # -----------------------------------------------------------------------
    algorithm = _read_algorithm_from_state(run_dir)
    if algorithm == "emosa":
        return _detect_stage_4_phase_emosa(run_dir, search_dir, search_state_path)

    # -----------------------------------------------------------------------
    # Hill-climb / default path (cold_start → build_v1 → normal loop)
    # -----------------------------------------------------------------------
    directive_history = search_dir / "directive_history.json"
    prompts_dir = run_dir / "prompts"
    has_v1 = prompts_dir.is_dir() and (
        any(prompts_dir.glob("v1.yaml")) or any(prompts_dir.glob("v1.json")) or any(prompts_dir.glob("v1.txt"))
    )

    # Phase 1: Cold-start — no directives yet (search_state.json may exist due to
    # pre-initialisation by _ensure_stage4_search_state).
    if not directive_history.is_file():
        return "cold_start"

    # Phase 2: Build v1 — directives exist but no compiled prompt yet
    if not has_v1:
        return "build_v1"

    # Phase 3: Normal loop — read loop_phase from search state
    loop_phase = "review"
    search_round = 0
    algorithm_value = "hill_climb"
    state_data: dict[str, Any] = {}
    if search_state_path.is_file():
        try:
            state_data = json.loads(search_state_path.read_text())
            raw_phase = state_data.get("loop_phase", "review")
            if raw_phase not in _VALID_LOOP_PHASES:
                logger.warning(
                    "Unexpected loop_phase '%s' in %s/search/search_state.json, defaulting to 'review'",
                    raw_phase,
                    run_dir,
                )
            else:
                loop_phase = raw_phase
            search_round = int(state_data.get("round", 0))
            algorithm_value = str(state_data.get("algorithm", "hill_climb"))
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("Failed to parse search_state.json in %s: %s", run_dir, exc)

    # Recovery detection: if loop_phase is "build" and active_evals is non-empty,
    # a previous build attempt was interrupted mid-eval — enter recovery mode.
    if loop_phase == "build":
        active_evals = state_data.get("active_evals", [])
        if active_evals:
            return "build_recovering"

    # Defense-in-depth: if loop_phase is "build" but there are no child_variants
    # on disk AND the build marker is also absent, the builder was never actually
    # dispatched — flip back to "review" to prevent deadlock.
    if loop_phase == "build":
        child_variants = search_dir / "child_variants.json"
        if not child_variants.exists() and not _is_build_dispatched(run_dir.name, search_dir):
            logger.warning(
                "loop_phase='build' but child_variants.json and build_dispatched.json absent "
                "in %s/search/ — defense-in-depth re-flip to 'review'",
                run_dir,
            )
            loop_phase = "review"

    if loop_phase == "review" and search_round == 1 and algorithm_value == "beam":
        return "review_post_coldstart"

    return loop_phase


def _detect_stage_4_phase_emosa(
    run_dir: Path,
    search_dir: Path,
    search_state_path: Path,
) -> str:
    """EMOSA calibration-aware phase detection sub-routine.

    Returns one of: ``"calibration"``, ``"review"``, ``"build"``,
    ``"build_recovering"``.
    """
    # No search state at all — calibration not yet started.
    if not search_state_path.is_file():
        return "calibration"

    # Parse search state.
    loop_phase = "calibration"
    state_data: dict[str, Any] = {}
    try:
        state_data = json.loads(search_state_path.read_text())
        raw_phase = state_data.get("loop_phase", "calibration")
        if raw_phase not in _VALID_LOOP_PHASES:
            logger.warning(
                "Unexpected loop_phase '%s' in %s/search/search_state.json, defaulting to 'calibration'",
                raw_phase,
                run_dir,
            )
        else:
            loop_phase = raw_phase
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Failed to parse search_state.json in %s: %s", run_dir, exc)

    # Recovery detection: active_evals non-empty signals mid-build crash.
    active_evals = state_data.get("active_evals", [])
    if active_evals:
        return "build_recovering"

    # Calibration phase: trajectories not yet seeded.
    if loop_phase == "calibration":
        return "calibration"

    # Defense-in-depth: if loop_phase is "build" but no per-trajectory
    # child_variants_t*.json files exist AND build_dispatched.json is absent,
    # the builder was never actually dispatched — flip back to "review" to
    # prevent deadlock.  Mirrors the hill-climb guard at lines 599-610.
    if (
        loop_phase == "build"
        and not any(search_dir.glob("child_variants_t*.json"))
        and not _is_build_dispatched(run_dir.name, search_dir)
    ):
        logger.warning(
            "loop_phase='build' but no child_variants_t*.json on disk and "
            "build_dispatched.json absent in %s/search/ — defense-in-depth "
            "re-flip to 'review'",
            run_dir,
        )
        loop_phase = "review"

    # Steady-state: trust loop_phase directly for review/build.
    if loop_phase in {"review", "build"}:
        return loop_phase

    # Fallback: default to "build".
    return "build"


def _read_algorithm_from_state(run_dir: Path) -> str:
    """Read the algorithm discriminator from search_state.json.

    Returns ``"hill_climb"`` (the default) when the file is absent, unreadable,
    or does not contain an ``algorithm`` field.
    """
    search_state_path = run_dir / "search" / "search_state.json"
    if not search_state_path.is_file():
        return "hill_climb"
    try:
        data = json.loads(search_state_path.read_text())
        return str(data.get("algorithm", "hill_climb"))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Failed to read algorithm from %s: %s", search_state_path, exc)
        return "hill_climb"


def _read_trajectory_count(run_dir: Path) -> int:
    """Read the number of EMOSA trajectories from search_state.json algorithm_state pocket.

    Returns 3 (a safe default) when the state is absent or contains no trajectory data.
    """
    search_state_path = run_dir / "search" / "search_state.json"
    if not search_state_path.is_file():
        return 3
    try:
        data = json.loads(search_state_path.read_text())
        pocket = data.get("algorithm_state") or {}
        num = pocket.get("num_trajectories")
        if num is not None:
            return int(num)
        # Fallback: count trajectories list length if present
        trajectories = pocket.get("trajectories", [])
        if trajectories:
            return len(trajectories)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Failed to read trajectory count from %s: %s", search_state_path, exc)
    return 3


def _ensure_stage4_search_state(run_dir: Path, project_dir: Path | None = None) -> None:
    """Auto-create ``search_state.json`` at Stage 4 entry if it does not exist.

    This runs once on first Stage-4 dispatch so that ``_detect_stage_4_phase``
    and the cold-start Review Agent see a real ``SearchState`` with the branch
    algorithm already persisted — ``get_search_state_tool`` no longer raises
    ``FileNotFoundError`` during the cold-start sub-agent.

    When the file already exists this function is a no-op.

    Args:
        run_dir: Run-level output directory (``outputs/<run_id>``).
        project_dir: Project root used to locate ``backends/``. Defaults to
            :func:`get_project_dir` when ``None``.
    """
    search_state_path = run_dir / "search" / "search_state.json"
    if search_state_path.is_file():
        return

    if project_dir is None:
        project_dir = get_project_dir()

    from odysseus.agents.prompt_builder.search_ops import init_search_state

    # Resolve backend from Stage 3 outputs (backends/*.yaml stem), falling back
    # to the first priced backend found, then empty string.
    backend: str = ""
    backends_dir = project_dir / "backends"
    if backends_dir.is_dir():
        from odysseus.eval.backends.profile import BackendProfile

        for yf in sorted(backends_dir.glob("*.yaml")):
            try:
                profile = BackendProfile.from_yaml(yf)
                if profile.pricing is not None:
                    backend = yf.stem
                    break
            except Exception:
                continue

    # Read primary_metric_name from routing_context.json if available.
    primary_metric_name: str | None = None
    routing_context_path = run_dir / "validation" / "routing_context.json"
    if routing_context_path.is_file():
        try:
            rc_data = json.loads(routing_context_path.read_text())
            raw = rc_data.get("primary_metric_name")
            if isinstance(raw, str) and raw:
                primary_metric_name = raw
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("Failed to read primary_metric_name from %s: %s", routing_context_path, exc)

    # output_dir is run_dir's parent (e.g. <project>/outputs)
    output_dir = run_dir.parent
    run_id = run_dir.name
    try:
        init_search_state(
            run_id=run_id,
            backend=backend,
            primary_metric_name=primary_metric_name,
            output_dir=output_dir,
        )
        logger.info("Pre-initialised search_state.json for run %s (backend=%r)", run_id, backend)
    except Exception as exc:
        logger.warning("Failed to pre-initialise search_state.json for run %s: %s", run_id, exc)


def _next_action_for_stage_4(
    run_dir: Path,
    rerun_config: dict[str, Any] | None = None,
    project_dir: Path | None = None,
) -> tuple[str, list[str], list[str], str, str]:
    """Return (action, tools, prompts, subagent_instruction, algorithm) for Stage 4.

    The ``algorithm`` element is the search strategy discriminator read from
    ``search_state.json`` (defaults to ``"hill_climb"`` when absent).  It is
    used by the orchestrator to compose the strategy-aware Review Agent prompt.
    """
    # Pre-init search_state.json on first Stage-4 dispatch so cold-start
    # sub-agents can call get_search_state_tool without FileNotFoundError.
    _ensure_stage4_search_state(run_dir, project_dir=project_dir)

    phase = _detect_stage_4_phase(run_dir, rerun_config)
    algorithm = _read_algorithm_from_state(run_dir)

    # Rerun is special — needs template formatting with config values
    if phase == "rerun":
        assert rerun_config is not None  # noqa: S101
        source_version = rerun_config.get("source_prompt_version", "unknown")
        new_backend = rerun_config.get("new_backend", "unknown")
        rerun_instr = STAGE_4_RERUN_INSTRUCTION.format(
            run_id=run_dir.name,
            source_prompt_version=source_version,
            new_backend=new_backend,
        )
        return (
            "Stage 4 — rerun mode: spawn the Prompt Builder Rerun agent to restructure "
            f"the source prompt (version {source_version}) for the new backend ({new_backend}). "
            "REQUIRED: activate prompt 'odysseus_prompt_builder_rerun' before calling any build tools.",
            _RERUN_TOOLS,
            ["odysseus_prompt_builder_rerun"],
            rerun_instr,
            algorithm,
        )

    # EMOSA review phase: K-way parallel fanout — one sub-agent per trajectory.
    # Format the instruction with trajectory count so the orchestrator knows how
    # many sub-agents to spawn and can wait for all K completions.
    if phase == "review" and algorithm == "emosa":
        from odysseus.agents.review.ops import trajectory_fanout_missing

        num_trajectories = _read_trajectory_count(run_dir)
        review_instr = STAGE_4_REVIEW_INSTRUCTION_EMOSA.format(
            run_id=run_dir.name,
            num_trajectories=num_trajectories,
            max_trajectory_id=num_trajectories - 1,
        )

        fanout = trajectory_fanout_missing(run_dir.name, output_dir=run_dir.parent)

        if fanout is not None:
            num_completed = len(fanout.completed)
            num_in_flight = len(fanout.in_flight)
            num_not_dispatched = len(fanout.not_dispatched)
            num_trajectories_total = fanout.num_trajectories

            if num_not_dispatched == num_trajectories_total and num_completed == 0 and num_in_flight == 0:
                status_text = (
                    f"Stage 4 — review phase: spawn {num_trajectories_total} Review Agent sub-agents "
                    "in parallel (one per trajectory) to analyse eval results and emit child variants. "
                    "REQUIRED: activate prompt 'odysseus_review_agent_iterative' before calling any review tools."
                )
            elif num_not_dispatched > 0 and num_in_flight == 0:
                status_text = (
                    f"Stage 4 — review phase (partial, {num_completed}/{num_trajectories_total} completed): "
                    f"dispatch Review Agent sub-agents for trajectory_id(s) {sorted(fanout.not_dispatched)}."
                )
                review_instr = review_instr + f"\nMISSING_TRAJECTORIES: {sorted(fanout.not_dispatched)}"
            elif num_not_dispatched > 0 and num_in_flight > 0:
                status_text = (
                    f"Stage 4 — review phase (partial, {num_completed}/{num_trajectories_total} completed, "
                    f"{num_in_flight} in flight): "
                    f"dispatch missing trajectory_id(s) {sorted(fanout.not_dispatched)} in parallel; "
                    f"do NOT respawn trajectory_id(s) {sorted(fanout.in_flight)} which are already dispatched."
                )
                review_instr = review_instr + f"\nMISSING_TRAJECTORIES: {sorted(fanout.not_dispatched)}"
            else:
                # All dispatched, some still in flight
                status_text = (
                    f"Stage 4 — review phase: all {num_trajectories_total} trajectories dispatched "
                    f"({num_completed} completed, {num_in_flight} still running). "
                    f"WAIT for in-flight agents to finish; "
                    f"do NOT respawn trajectory_id(s) {sorted(fanout.in_flight)}. "
                    f"Re-poll get_pipeline_status in 30-60s."
                )
        else:
            # No algorithm_state yet (pre-calibration fallback)
            status_text = (
                f"Stage 4 — review phase: spawn {num_trajectories} Review Agent sub-agents "
                "in parallel (one per trajectory) to analyse eval results and emit child variants. "
                "REQUIRED: activate prompt 'odysseus_review_agent_iterative' before calling any review tools."
            )

        return (
            status_text,
            _REVIEW_TOOLS,
            ["odysseus_review_agent_iterative"],
            review_instr,
            algorithm,
        )

    # All other phases use a static dispatch table.
    # Extended phases (warmup_*, calibration, build_recovering) are used by
    # feature branches; on main (hill-climb) they are never entered.  They are
    # mapped to the nearest equivalent action so the orchestrator always has a
    # valid next action even when reading state from a feature-branch run.
    #
    # Review phases use strategy-aware prompt names so the orchestrator can
    # compose base + phase-base + strategy overlay at dispatch time.
    _review_entry = (
        "Stage 4 — review phase: spawn the Review Agent to analyse "
        "eval results and emit edit directives. "
        "REQUIRED: activate prompt 'odysseus_review_agent_iterative' before calling any review tools.",
        _REVIEW_TOOLS,
        ["odysseus_review_agent_iterative"],
        STAGE_4_REVIEW_INSTRUCTION,
        algorithm,
    )
    _build_entry = (
        "Stage 4 — build phase: spawn the Prompt Builder to generate "
        "prompt variants and evaluate them. "
        "REQUIRED: activate prompt 'odysseus_prompt_builder' before calling any build tools.",
        _BUILD_TOOLS,
        ["odysseus_prompt_builder"],
        STAGE_4_BUILD_INSTRUCTION,
        algorithm,
    )
    _build_recovering_entry = (
        "Stage 4 — build-recovering phase: active_evals is non-empty from a prior interrupted run. "
        "Spawn the Prompt Builder to resume in-flight evaluations via run_batch_eval(candidates=[]). "
        "REQUIRED: activate prompt 'odysseus_prompt_builder' before calling any build tools.",
        _BUILD_TOOLS,
        ["odysseus_prompt_builder"],
        STAGE_4_BUILD_RECOVERING_INSTRUCTION,
        algorithm,
    )
    phase_config: dict[str, tuple[str, list[str], list[str], str, str]] = {
        "cold_start": (
            "Stage 4 — cold-start: spawn the Review Agent to seed the search "
            "with diverse initial hypotheses. "
            "REQUIRED: activate prompt 'odysseus_review_agent_cold_start' before calling any review tools.",
            _COLD_REVIEW_TOOLS,
            ["odysseus_review_agent_cold_start"],
            STAGE_4_COLD_START_INSTRUCTION,
            algorithm,
        ),
        "build_v1": (
            "Stage 4 — build phase: spawn the Prompt Builder to compile the "
            "initial routing prompt (v1) using seed examples from the Review Agent. "
            "REQUIRED: activate prompt 'odysseus_prompt_builder' before calling any build tools.",
            _BUILD_TOOLS,
            ["odysseus_prompt_builder"],
            STAGE_4_BUILD_INSTRUCTION,
            algorithm,
        ),
        "review": _review_entry,
        "review_post_coldstart": (
            "Stage 4 — post-cold-start review: spawn the Review Agent to analyse round-1 results "
            "and emit exactly one child variant per protected parent. "
            "REQUIRED: activate prompt 'odysseus_review_agent_post_coldstart' before calling any review tools.",
            _REVIEW_TOOLS,
            ["odysseus_review_agent_post_coldstart"],
            STAGE_4_REVIEW_POST_COLDSTART_INSTRUCTION,
            algorithm,
        ),
        "build": _build_entry,
        # Extended phases — feature branches only; mapped to nearest equivalent
        "warmup_seed": (
            "Stage 4 — warmup-seed phase: spawn the Review Agent to seed the population. "
            "REQUIRED: activate prompt 'odysseus_review_agent_cold_start' before calling any review tools.",
            _COLD_REVIEW_TOOLS,
            ["odysseus_review_agent_cold_start"],
            STAGE_4_COLD_START_INSTRUCTION,
            algorithm,
        ),
        "warmup_build": _build_entry,
        "warmup_reduce": _build_entry,
        # EMOSA calibration phase
        "calibration": (
            "Stage 4 — calibration phase: spawn the Prompt Builder to emit K diverse seed prompts, "
            "score them, and seed K EMOSA trajectories. "
            "REQUIRED: activate prompt 'odysseus_prompt_builder' before calling any build tools.",
            _BUILD_TOOLS,
            ["odysseus_prompt_builder"],
            STAGE_4_CALIBRATION_INSTRUCTION,
            algorithm,
        ),
        "build_recovering": _build_recovering_entry,
    }
    return phase_config[phase]


def _next_action_for_stage(stage: int) -> tuple[str, list[str], list[str], str | None]:
    """Return (next_action_text, tool_list, prompt_list, subagent_instruction) for the given stage."""
    return _NEXT_ACTION.get(
        stage,
        ("Pipeline complete.", [], [], None),
    )


# ---------------------------------------------------------------------------
# Rerun config helpers
# ---------------------------------------------------------------------------


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
