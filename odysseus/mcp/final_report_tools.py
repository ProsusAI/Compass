"""Final Report tools — holdout evaluation and report generation."""

import json

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

import odysseus.project_dir as _project_dir_mod
from odysseus.agents.eval_runner import EvalRunnerAgent
from odysseus.agents.final_report.preprocessor import build_final_report_briefing
from odysseus.agents.pipeline.guards import check_artifacts
from odysseus.agents.prompt_builder.holdout_filter import filter_holdout_dataset
from odysseus.agents.prompt_builder.search_ops import get_search_state
from odysseus.eval.backends.registry import BackendRegistry
from odysseus.eval.models import ScoreReport
from odysseus.mcp.prompt_building_tools import build_pipeline_config
from odysseus.mcp.server import mcp


@mcp.tool()
async def filter_holdout_dataset_tool(
    ctx: Context,
    holdout_jsonl_path: str,
    exclude_ids: list[str],
    run_id: str,
) -> str:
    """[Stage 5: Final Report] Filter a holdout JSONL dataset by removing rows with specified IDs.

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
        filtered_path = filter_holdout_dataset(
            holdout_jsonl_path=holdout_jsonl_path,
            exclude_ids=exclude_ids,
        )
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    return json.dumps({"filtered_holdout_path": filtered_path})


@mcp.tool()
async def run_holdout_eval(ctx: Context, run_id: str) -> str:
    """[Stage 5: Final Report] Run evaluation on the holdout split.

    Automatically selects the best prompt from the Pareto front (highest
    quality score; ties broken by lowest cost) and runs evaluation against
    the hardcoded holdout dataset at
    ``outputs/<run_id>/analysis/holdout.jsonl``.

    Args:
        run_id: Pipeline run identifier.

    Returns:
        Serialized score report including the auto-selected prompt_version.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    check_artifacts(
        project_dir / "outputs" / run_id / "search" / "search_state.json",
        stage=5,
        stage_name="Final Report",
        hint="The eval loop must converge first.",
    )

    data_source = str(project_dir / "outputs" / run_id / "analysis" / "holdout.jsonl")

    state = get_search_state(run_id=run_id)

    if not state.pareto_front:
        raise ToolError("No candidates on the Pareto front — cannot determine best prompt.")

    best = max(state.pareto_front, key=lambda c: (c.quality_score, -c.cost))
    prompt_version = best.prompt_version

    if not state.backend:
        registry = BackendRegistry.from_directory(project_dir / "backends")
        return json.dumps(
            {
                "action_required": "backend_setup",
                "run_id": run_id,
                "available_backends": registry.list_profiles(),
            }
        )

    run_config = build_pipeline_config(
        state=state,
        prompt_version=prompt_version,
        data_source=data_source,
        run_id=run_id,
        project_dir=project_dir,
        eval_subdir="holdout_eval",
    )

    agent = EvalRunnerAgent()
    context = {
        "prompt_version": prompt_version,
        "data_source": data_source,
        "backend": run_config.backend,
        "run_id": run_id,
        "run_config": run_config,
    }

    result = await agent.run(context)

    if "error" in result:
        err = result["error"]
        raise ToolError(f"run_holdout_eval failed: [{err['category']}] {err['detail']}")

    score_report: ScoreReport = result[ScoreReport.CONTEXT_KEY]
    return json.dumps(
        {
            "prompt_version": prompt_version,
            "report_path": score_report.report_path,
            "results_path": score_report.results_path,
            "metrics": score_report.metrics,
            "summary": score_report.summary.model_dump(mode="json"),
        }
    )


@mcp.tool()
async def build_final_report_briefing_tool(ctx: Context, run_id: str) -> str:
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

    check_artifacts(
        run_dir / "holdout_eval" / "report.json",
        stage=5,
        stage_name="Final Report",
        hint="Run holdout evaluation first (run_holdout_eval).",
    )

    briefing = build_final_report_briefing(
        run_id=run_id,
        run_dir=run_dir,
        project_dir=project_dir,
    )
    return briefing.model_dump_json(indent=2)


@mcp.tool()
async def save_final_report(ctx: Context, run_id: str, report_markdown: str) -> str:
    """[Stage 5: Final Report] Save the final report markdown to disk.

    Writes the report to ``outputs/<run_id>/reports/final_report.md``.

    Args:
        run_id: Pipeline run identifier.
        report_markdown: The complete report in markdown format.

    Returns:
        Confirmation with the file path.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    reports_dir = project_dir / "outputs" / run_id / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report_path = reports_dir / "final_report.md"
    report_path.write_text(report_markdown, encoding="utf-8")

    return json.dumps({"report_path": str(report_path), "status": "saved"})
