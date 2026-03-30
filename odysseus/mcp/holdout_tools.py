"""Holdout tools — holdout evaluation."""

from mcp.server.fastmcp import Context

import odysseus.project_dir as _project_dir_mod
from odysseus.agents.pipeline.guards import check_artifacts
from odysseus.mcp.server import mcp


@mcp.tool()
async def run_holdout_eval(ctx: Context, prompt_version: str, data_source: str, run_id: str) -> str:
    """[Stage 7: Holdout Validation] Run evaluation on the holdout split.

    This tool must only be available to the Final Evaluation agent.
    It must NOT be in the Eval Runner agent's tool list.

    Args:
        prompt_version: Prompt version to evaluate.
        data_source: Path to the dataset file.
        run_id: Pipeline run identifier.

    Returns:
        Serialized score report.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    check_artifacts(
        project_dir / "outputs" / run_id / "search" / "search_state.json",
        stage=7,
        stage_name="Holdout Validation",
        hint="The eval loop must converge first.",
    )
    # TODO: implement holdout eval wiring (same pattern as run_eval with data_split="holdout")
    return f"run_holdout_eval stub: prompt_version={prompt_version}, data_source={data_source}, run_id={run_id}"
