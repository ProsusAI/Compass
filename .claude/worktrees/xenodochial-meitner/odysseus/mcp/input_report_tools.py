"""Input report tools — submit validated input report."""

import json
import uuid

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

import odysseus.project_dir as _project_dir_mod
from odysseus.mcp.server import mcp


@mcp.tool()
async def submit_input_report(
    ctx: Context,
    report: str,
    dataset_path: str,
    problem_description: str,
    bootstrap_from_run_id: str | None = None,
) -> str:
    """[Stage 1: Input] Submit a validated input report to the pipeline.

    No prerequisites. Returns a run_id for scoping all subsequent tools.

    Args:
        report: The full validated input report (Markdown).
        dataset_path: Absolute filesystem path to the JSONL routing dataset.
        problem_description: The validated problem description.
        bootstrap_from_run_id: Optional run_id to copy the latest prompt version from.

    Returns:
        JSON with run_id, report_path, and dataset_path.
    """
    if not report.strip():
        raise ToolError("submit_input_report failed: report is empty")
    if not dataset_path.strip():
        raise ToolError("submit_input_report failed: dataset_path is empty")
    if not problem_description.strip():
        raise ToolError("submit_input_report failed: problem_description is empty")

    run_id = uuid.uuid4().hex[:8]
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)

    input_dir = project_dir / "outputs" / run_id / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    report_path = input_dir / "input_report.md"
    report_path.write_text(report)

    if bootstrap_from_run_id is not None:
        src_prompts = project_dir / "outputs" / bootstrap_from_run_id / "prompts"
        if src_prompts.is_dir():
            prompt_files = sorted(src_prompts.glob("v*.txt"))
            if prompt_files:
                latest = prompt_files[-1]
                dest_prompts = project_dir / "outputs" / run_id / "prompts"
                dest_prompts.mkdir(parents=True, exist_ok=True)
                (dest_prompts / "bootstrap.txt").write_text(latest.read_text())

    return json.dumps(
        {
            "run_id": run_id,
            "report_path": str(report_path),
            "dataset_path": dataset_path,
        }
    )
