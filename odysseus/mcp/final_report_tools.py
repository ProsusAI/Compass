"""Final Report tools — holdout evaluation and report generation."""

import json
import logging
from pathlib import Path

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

import odysseus.project_dir as _project_dir_mod
from odysseus.agents.eval_runner import run_eval
from odysseus.agents.final_report.preprocessor import (
    build_final_report_briefing as _build_final_report_briefing_impl,
)
from odysseus.agents.pipeline.guards import check_artifacts
from odysseus.agents.prompt_builder.holdout_filter import (
    filter_holdout_dataset as _filter_holdout_dataset_impl,
)
from odysseus.agents.prompt_builder.search_ops import get_candidate_example_ids, get_search_state
from odysseus.eval.backends.registry import BackendRegistry
from odysseus.eval.models import ScoreReport
from odysseus.mcp.prompt_building_tools import build_pipeline_config
from odysseus.mcp.server import mcp


def _compute_baselines(
    holdout_examples: list[dict],
    eval_results: list[dict],
) -> dict | None:
    """Compute baseline strategy performance on holdout set.

    Invariant: every example has every route in its expected.routes dict.
    This is guaranteed by the data validation stage (stratified_split).
    """
    route_cost_sums: dict[str, float] = {}
    route_quality_sums: dict[str, float] = {}

    for ex in holdout_examples:
        routes = ex.get("expected", {}).get("routes", {})
        for route_name, route_data in routes.items():
            cost = route_data.get("cost", 0.0) or 0.0
            quality = route_data.get("quality_score", 0.0) or 0.0
            route_cost_sums[route_name] = route_cost_sums.get(route_name, 0.0) + cost
            route_quality_sums[route_name] = route_quality_sums.get(route_name, 0.0) + quality

    n = len(holdout_examples)
    if n == 0:
        return None

    cheapest_route = min(route_cost_sums, key=lambda r: route_cost_sums[r] / n)
    cheapest_quality = route_quality_sums[cheapest_route] / n
    cheapest_cost = route_cost_sums[cheapest_route] / n

    capable_route = min(route_quality_sums, key=lambda r: (-route_quality_sums[r] / n, r))
    capable_quality = route_quality_sums[capable_route] / n
    capable_cost = route_cost_sums[capable_route] / n

    optimized_cost = 0.0
    optimized_quality = 0.0
    counted = 0
    example_by_id = {ex.get("id"): ex for ex in holdout_examples}
    for r in eval_results:
        if r.get("error"):
            continue
        eid = r.get("example_id")
        ex = example_by_id.get(eid)
        if not ex:
            continue
        pred_route = r.get("output", {}).get("route")
        routes = ex.get("expected", {}).get("routes", {})
        if pred_route and pred_route in routes:
            optimized_cost += routes[pred_route].get("cost", 0.0) or 0.0
            optimized_quality += routes[pred_route].get("quality_score", 0.0) or 0.0
            counted += 1

    if counted > 0:
        optimized_cost /= counted
        optimized_quality /= counted

    return {
        "baselines": [
            {
                "strategy": "always_cheapest",
                "route": cheapest_route,
                "quality_score": round(cheapest_quality, 4),
                "cost": round(cheapest_cost, 4),
            },
            {
                "strategy": "always_capable",
                "route": capable_route,
                "quality_score": round(capable_quality, 4),
                "cost": round(capable_cost, 4),
            },
        ],
        "optimized": {
            "strategy": "optimized_prompt",
            "route": "mixed",
            "quality_score": round(optimized_quality, 4),
            "cost": round(optimized_cost, 4),
        },
    }


@mcp.tool()
async def filter_holdout_dataset(
    ctx: Context,
    holdout_jsonl_path: str,
    exclude_ids: list[str],
    run_id: str,
) -> str:
    """[Stage 5: Final Report] [Deprecated] Filter a holdout JSONL dataset by removing rows with specified IDs.

    .. deprecated::
        Holdout filtering now happens automatically inside ``run_holdout_eval``.
        This tool is retained for manual or debugging use only.

    Removes few-shot examples from the holdout set to prevent data
    contamination before final evaluation.

    Args:
        holdout_jsonl_path: Path to the holdout JSONL dataset file.
        exclude_ids: List of row IDs to exclude from the output.
        run_id: Pipeline run identifier.

    Returns:
        JSON object with filtered_holdout_path pointing to the output file.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    check_artifacts(
        project_dir / "outputs" / run_id / "analysis" / "dev.jsonl",
        stage=5,
        stage_name="Final Report",
        hint="Complete data validation and dataset split first.",
    )

    try:
        filtered_path = _filter_holdout_dataset_impl(
            holdout_jsonl_path=holdout_jsonl_path,
            exclude_ids=exclude_ids,
        )
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    return json.dumps({"filtered_holdout_path": filtered_path})


@mcp.tool()
async def list_pareto_candidates(ctx: Context, run_id: str) -> str:
    """[Stage 5: Final Report] List all Pareto front candidates with dev-set metrics.

    Returns the full Pareto front so the user can choose which prompt
    version to evaluate on the holdout set.

    Args:
        run_id: Pipeline run identifier.

    Returns:
        JSON with candidates list and total count.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    check_artifacts(
        project_dir / "outputs" / run_id / "search" / "search_state.json",
        stage=5,
        stage_name="Final Report",
        hint="The eval loop must converge first.",
    )

    state = get_search_state(run_id=run_id)
    if not state.elite_set:
        raise ToolError("No elite set candidates found in search state.")

    candidates = sorted(
        [
            {
                "prompt_version": c.prompt_version,
                "quality_score": c.quality_score,
                "cost": c.cost,
                "round_introduced": c.round_introduced,
            }
            for c in state.elite_set
        ],
        key=lambda c: (-float(c["quality_score"]), float(c["cost"])),
    )

    marker_path = project_dir / "outputs" / run_id / "pareto_candidates_listed.json"
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(
        json.dumps(
            {
                "candidates": [c["prompt_version"] for c in candidates],
            }
        )
    )

    return json.dumps(
        {
            "candidates": candidates,
            "total_candidates": len(candidates),
        }
    )


@mcp.tool()
async def run_holdout_eval(ctx: Context, run_id: str, prompt_versions: list[str]) -> str:
    """[Stage 5: Final Report] Run holdout evaluation for one or more prompt versions.

    Runs evaluation against the hardcoded holdout dataset at
    ``outputs/<run_id>/analysis/holdout.jsonl``.

    Args:
        run_id: Pipeline run identifier.
        prompt_versions: Prompt versions to evaluate. Required — all must be on the
            Pareto front.

    Returns:
        JSON artifact manifest. On success, returns per-version artifact paths;
        call ``build_final_report_briefing(run_id)`` next for rendered
        LLM-facing report inputs. If backend setup is still required, returns
        the existing ``action_required`` payload unchanged.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    check_artifacts(
        project_dir / "outputs" / run_id / "search" / "search_state.json",
        stage=5,
        stage_name="Final Report",
        hint="The eval loop must converge first.",
    )
    check_artifacts(
        project_dir / "outputs" / run_id / "pareto_candidates_listed.json",
        stage=5,
        stage_name="Final Report",
        hint="Call list_pareto_candidates first to present candidates to the user.",
    )

    state = get_search_state(run_id=run_id)

    if not state.elite_set:
        raise ToolError("No candidates on the elite set — cannot determine best prompt.")

    # Bulk-validate all requested versions up front
    valid_versions = {c.prompt_version for c in state.elite_set}
    invalid = [v for v in prompt_versions if v not in valid_versions]
    if invalid:
        raise ToolError(f"Versions not on the elite set: {invalid}. Valid versions: {sorted(valid_versions)}")

    if not state.backend:
        registry = BackendRegistry.from_directory(project_dir / "backends")
        return json.dumps(
            {
                "action_required": "backend_setup",
                "run_id": run_id,
                "available_backends": registry.list_profiles(),
            }
        )

    holdout_path = str(project_dir / "outputs" / run_id / "analysis" / "holdout.jsonl")

    evaluations: list[dict[str, str]] = []

    for version in prompt_versions:
        # Auto-filter holdout dataset to exclude few-shot examples for this version
        example_ids = get_candidate_example_ids(run_id, version)
        if example_ids:
            data_source = _filter_holdout_dataset_impl(
                holdout_jsonl_path=holdout_path,
                exclude_ids=example_ids,
            )
        else:
            data_source = holdout_path

        run_config = build_pipeline_config(
            state=state,
            prompt_version=version,
            data_source=data_source,
            run_id=run_id,
            project_dir=project_dir,
            eval_subdir="holdout_eval",
        )

        eval_context = {
            "prompt_version": version,
            "data_source": data_source,
            "backend": run_config.backend,
            "run_id": run_id,
            "run_config": run_config,
        }

        result = await run_eval(eval_context)

        if "error" in result:
            err = result["error"]
            raise ToolError(f"run_holdout_eval failed for version {version}: [{err['category']}] {err['detail']}")

        score_report: ScoreReport = result[ScoreReport.CONTEXT_KEY]

        baseline_path: Path | None = None

        # Compute and write baseline comparison
        try:
            holdout_jsonl_path = project_dir / "outputs" / run_id / "analysis" / "holdout.jsonl"
            holdout_text = holdout_jsonl_path.read_text(encoding="utf-8")
            holdout_examples = [json.loads(line) for line in holdout_text.splitlines() if line.strip()]

            results_path = Path(run_config.output.results_path)
            results_text = results_path.read_text(encoding="utf-8")
            eval_result_rows = [
                json.loads(line) for line in results_text.splitlines() if line.strip() and '"__meta__"' not in line
            ]

            baseline_data = _compute_baselines(holdout_examples, eval_result_rows)
            if baseline_data:
                baseline_path = Path(run_config.output.results_path).parent / "baseline_comparison.json"
                baseline_path.write_text(json.dumps(baseline_data, indent=2), encoding="utf-8")
        except Exception:
            logging.getLogger(__name__).warning("Failed to compute baselines", exc_info=True)

        evaluation = {
            "prompt_version": version,
            "report_path": score_report.report_path,
            "results_path": score_report.results_path,
        }
        if baseline_path is not None and baseline_path.is_file():
            evaluation["baseline_comparison_path"] = str(baseline_path)
        evaluations.append(evaluation)

    return json.dumps(
        {
            "evaluations": evaluations,
            "next_step": "build_final_report_briefing",
        }
    )


@mcp.tool()
async def build_final_report_briefing(ctx: Context, run_id: str) -> str:
    """[Stage 5: Final Report] Build a structured briefing from all pipeline artifacts.

    Pre-processes numerical data, metric comparisons, error analysis,
    and generates optimization journey charts. Returns JSON for the
    Final Report Agent to synthesize into a narrative markdown report.

    Args:
        run_id: Pipeline run identifier.

    Returns:
        JSON-serialized FinalReportBriefing.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    run_dir = project_dir / "outputs" / run_id

    holdout_eval_dir = run_dir / "holdout_eval"
    if not any(holdout_eval_dir.glob("v*/report.json")):
        raise ToolError(
            f"No versioned holdout reports found under {holdout_eval_dir}/v*/report.json. "
            "Run holdout evaluation first (run_holdout_eval)."
        )

    briefing = _build_final_report_briefing_impl(
        run_id=run_id,
        run_dir=run_dir,
        project_dir=project_dir,
    )
    return briefing.model_dump_json(indent=2)


_REQUIRED_REPORT_SECTIONS = [
    "## Executive Summary",
    "## Compared Candidates",
    "## Candidate Details",
    "## Problem Definition",
    "## Dataset Overview",
    "## Optimization Process",
    "## Pareto Front",
]


def _validate_report_sections(markdown: str) -> list[str]:
    """Check for missing required sections. Returns list of warnings."""
    warnings: list[str] = []
    for section in _REQUIRED_REPORT_SECTIONS:
        if section not in markdown:
            warnings.append(f"Missing required section: {section}")
    return warnings


@mcp.tool()
async def save_final_report(ctx: Context, run_id: str, report_markdown: str) -> str:
    """[Stage 5: Final Report] Save the final report markdown to disk.

    Writes the report to ``outputs/<run_id>/reports/final_report.md``.
    Validates that required template sections are present and returns
    warnings for any missing sections.

    Args:
        run_id: Pipeline run identifier.
        report_markdown: The complete report in markdown format.

    Returns:
        Confirmation with the file path and any section warnings.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    reports_dir = project_dir / "outputs" / run_id / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report_path = reports_dir / "final_report.md"
    report_path.write_text(report_markdown, encoding="utf-8")

    warnings = _validate_report_sections(report_markdown)

    return json.dumps({"report_path": str(report_path), "status": "saved", "warnings": warnings})
