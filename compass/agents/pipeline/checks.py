# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Stage-completion check helpers for the pipeline status module.

Each ``_check_stage_*`` function returns ``(status, artifact_paths, detail)``
where *status* is one of ``"complete"`` or ``"incomplete"``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from compass.agents.pipeline.status_types import StageDetail
from compass.eval.backends.profile import BackendProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public check functions (called by status.py)
# ---------------------------------------------------------------------------


def _check_stage(
    stage_def: dict[str, Any],
    run_dir: Path,
    project_dir: Path,
    rerun_config: dict[str, Any] | None = None,
) -> tuple[str, list[str], StageDetail | None]:
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
        return "incomplete", artifacts, None
    return "complete", artifacts, None


def _check_stage_2(run_dir: Path) -> tuple[str, list[str], StageDetail | None]:
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
        return (
            "incomplete",
            artifacts,
            StageDetail(
                kind="halt",
                code="data_quality_critical_fail",
                artifact_path="validation/data_quality_report.json",
                prompt_to_user=(
                    "The data quality report has critical schema failures. "
                    "Read the failing schema_findings (severity='critical', status='fail') "
                    "and present the violations to the user. Ask for a corrected field mapping."
                ),
                expected_response="Corrected field mapping or instruction to proceed despite failures.",
                halt_on_failure_after=2,
            ),
        )

    missing = [p for p in artifacts if not Path(p).is_file()]
    if not missing:
        return "complete", artifacts, None

    # Check for intermediate "proposed mapping" state
    proposed_mapping = run_dir / "validation" / "proposed_mapping.json"
    transformed = run_dir / "validation" / "transformed.jsonl"
    if proposed_mapping.is_file() and not transformed.is_file():
        return (
            "incomplete",
            artifacts + [str(proposed_mapping)],
            StageDetail(
                kind="user_input_needed",
                code="mapping_confirmation_needed",
                artifact_path="validation/proposed_mapping.json",
                prompt_to_user=(
                    "A proposed field mapping is ready for review. "
                    "Present it as a table (source field → target field) with sample rows "
                    "and list any unmapped fields. Ask the user to confirm or provide corrections."
                ),
                expected_response="Confirmed mapping or corrected mapping from the user.",
                halt_on_failure_after=2,
            ),
        )

    return "incomplete", artifacts, None


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
) -> tuple[str, list[str], StageDetail | None]:
    """Stage 3: Backend Configured.

    In normal mode: at least one backends/*.yaml must have valid pricing.
    In rerun mode (rerun_config.json present): the specific new_backend named in
    the config must have a YAML with valid pricing, and new_backend must be non-null.
    """
    if rerun_config is not None:
        # Rerun mode: new_backend must be explicitly set
        new_backend = rerun_config.get("new_backend")
        if not new_backend:
            return (
                "incomplete",
                [],
                StageDetail(
                    kind="user_input_needed",
                    code="rerun_backend_not_configured",
                    artifact_path="rerun_config.json",
                    prompt_to_user=(
                        "The rerun configuration does not specify a new backend. "
                        "Ask the user which backend they want to use for the rerun."
                    ),
                    expected_response="Backend name to use for the rerun.",
                    halt_on_failure_after=3,
                ),
            )

        backends_dir = project_dir / "backends"
        yaml_path = backends_dir / f"{new_backend}.yaml"
        if not yaml_path.is_file():
            return "incomplete", [str(yaml_path)], None

        try:
            profile = BackendProfile.from_yaml(yaml_path)
            if profile.pricing is not None:
                return "complete", [str(yaml_path)], None
        except Exception:
            pass
        return (
            "incomplete",
            [str(yaml_path)],
            StageDetail(
                kind="user_input_needed",
                code="pricing_missing",
                artifact_path=f"backends/{new_backend}.yaml",
                prompt_to_user=(
                    "The backend YAML is missing pricing information. "
                    "Ask the user for: input_cost_per_million_tokens, "
                    "cached_cost_per_million_tokens, and output_cost_per_million_tokens."
                ),
                expected_response="Pricing values: input, cached, and output costs per million tokens.",
                halt_on_failure_after=3,
            ),
        )

    # Normal mode: any backend with pricing
    backends_dir = project_dir / "backends"
    if not backends_dir.is_dir():
        return "incomplete", [], None
    yaml_files = list(backends_dir.glob("*.yaml"))
    if not yaml_files:
        backend_options = run_dir / "backend_options.json"
        if backend_options.is_file():
            return (
                "incomplete",
                [str(backend_options)],
                StageDetail(
                    kind="user_input_needed",
                    code="backend_selection_needed",
                    artifact_path="backend_options.json",
                    prompt_to_user=(
                        "No backend is configured yet. "
                        "Read backend_options.json and present the available backends to the user. "
                        "If backends exist: ask which to use or if they want to create a new one. "
                        "If none: ask for label, provider, model, requests_per_minute, tokens_per_minute."
                    ),
                    expected_response="Backend selection or new backend configuration from the user.",
                    halt_on_failure_after=3,
                ),
            )
        return "incomplete", [], None

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
        return (
            "incomplete",
            artifacts,
            StageDetail(
                kind="user_input_needed",
                code="pricing_missing",
                artifact_path="backends/",
                prompt_to_user=(
                    "No backend with pricing is configured. "
                    "Ask the user for: input_cost_per_million_tokens, "
                    "cached_cost_per_million_tokens, and output_cost_per_million_tokens."
                ),
                expected_response="Pricing values: input, cached, and output costs per million tokens.",
                halt_on_failure_after=3,
            ),
        )
    return "complete", artifacts, None


def _check_stage_4(run_dir: Path) -> tuple[str, list[str], StageDetail | None]:
    """Stage 4: Refinement Loop — search_state.json with converged == true."""
    search_state = run_dir / "search" / "search_state.json"
    if not search_state.is_file():
        return "incomplete", [], None
    try:
        data = json.loads(search_state.read_text())
        if data.get("converged") is True:
            return "complete", [str(search_state)], None
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return "incomplete", [str(search_state)], None


def _check_stage_5(run_dir: Path) -> tuple[str, list[str], StageDetail | None]:
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
        return "complete", [str(report)], None

    artifacts: list[str] = []
    if pareto_candidates.is_file():
        artifacts.append(str(pareto_candidates))
    if holdout_report_path is not None:
        artifacts.append(str(holdout_report_path))

    if pareto_candidates.is_file() and not holdout_report_exists:
        return (
            "incomplete",
            artifacts,
            StageDetail(
                kind="user_input_needed",
                code="version_selection_needed",
                artifact_path="pareto_candidates_listed.json",
                prompt_to_user=(
                    "Pareto candidates are listed but no holdout evaluation has been run. "
                    "Read pareto_candidates_listed.json and present the candidates as a table "
                    "(version, quality score, cost, round). Ask which prompt_versions "
                    "(one or more) the user wants to evaluate on the holdout set."
                ),
                expected_response="One or more prompt_versions chosen by the user.",
                halt_on_failure_after=2,
            ),
        )

    return "incomplete", artifacts, None
