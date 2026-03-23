"""MCP server entrypoint for Odysseus.

Thin adapter layer — each tool delegates to an agent class that owns
all business logic.  The MCP layer only translates between tool
parameters/return values and agent context dicts.
"""

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.prompts.base import Message, UserMessage

from odysseus.agents.eval_runner import EvalRunnerAgent
from odysseus.eval.models import ScoreReport

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_text(relative_path: str) -> str:
    """Load a text file relative to the project root.

    Raises FileNotFoundError with a clear message if the file is missing.
    """
    path = _PROJECT_ROOT / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"Required prompt file not found: {path} (resolved from project root {_PROJECT_ROOT})")
    return path.read_text()


mcp = FastMCP("odysseus")


@mcp.prompt()
async def odysseus_routing_input() -> list[Message]:
    """Activate the Odysseus routing input agent.

    Use when a user wants help with a routing optimization problem.
    Guides the user through providing a complete problem specification.
    """
    system_prompt = _load_text("prompts/user_input_system.md")
    return [UserMessage(content=system_prompt)]


@mcp.resource("odysseus://agents/input/clarification-guide")
async def input_clarification_guide() -> str:
    """Per-field clarification guidance for the input agent."""
    return _load_text("odysseus/agents/user_input_clarification_guide.md")


@mcp.resource("odysseus://agents/input/defaults")
async def input_defaults() -> str:
    """Default values and override mechanism for optional fields."""
    return _load_text("odysseus/agents/user_input_defaults.md")


@mcp.tool()
async def run_holdout_eval(prompt_version: str, data_source: str) -> str:
    """Run evaluation on the holdout split.

    This tool must only be available to the Final Evaluation agent.
    It must NOT be in the Eval Runner agent's tool list.

    Args:
        prompt_version: Prompt version to evaluate.
        data_source: Path to the dataset file.

    Returns:
        Serialized score report.
    """
    # TODO: implement holdout eval wiring (same pattern as run_eval with data_split="holdout")
    return f"run_holdout_eval stub: prompt_version={prompt_version}, data_source={data_source}"


@mcp.tool()
async def optimize_routing_prompt(
    data_path: str,
    problem_description: str,
    target_metrics: list[str],
) -> str:
    """Run the full routing prompt optimization pipeline.

    Args:
        data_path: Path to JSONL routing dataset.
        problem_description: Natural language description of the routing task.
        target_metrics: List of metric names and thresholds (e.g. "accuracy>=0.90").

    Returns:
        Structured evaluation report with the final optimized prompt.
    """
    # TODO: Wire up the full pipeline
    return f"Pipeline not yet implemented. Received: {data_path}, {problem_description}, {target_metrics}"


@mcp.tool()
async def run_eval(
    prompt_version: str,
    data_source: str,
    backend: str,
    config_path: str = "outputs/run_config.yaml",
) -> str:
    """Run an evaluation of a prompt version against a dataset.

    Args:
        prompt_version: Prompt version identifier (e.g. "v3", "latest").
        data_source: Path to the JSONL dataset file.
        backend: Backend label matching a profile in backends/ directory.
        config_path: Path to YAML config with metrics, concurrency, retry,
                     and output settings. Defaults to "outputs/run_config.yaml".

    Returns:
        JSON object with report_path and results_path pointing to
        the full evaluation output on disk.
    """
    agent = EvalRunnerAgent()
    result = await agent.run(
        {
            "prompt_version": prompt_version,
            "data_source": data_source,
            "backend": backend,
            "config_path": config_path,
        }
    )

    if "error" in result:
        err = result["error"]
        raise ToolError(f"run_eval failed: [{err['category']}] {err['detail']}")

    score_report: ScoreReport = result[ScoreReport.CONTEXT_KEY]
    return json.dumps(
        {
            "report_path": score_report.report_path,
            "results_path": score_report.results_path,
        }
    )


@mcp.tool()
async def submit_input_report(
    report: str,
    dataset_path: str,
    problem_description: str,
) -> str:
    """Submit a validated input report to the pipeline.

    Called after the input agent conversation completes and
    the validated input report has been produced. Triggers
    the next pipeline stage.

    Args:
        report: The full validated input report (Markdown).
        dataset_path: Absolute filesystem path to the JSONL routing dataset.
        problem_description: The validated problem description.

    Returns:
        Confirmation or next-stage result.
    """
    # TODO: Wire to next pipeline agent.
    # Expected: save report to disk, build pipeline context,
    # and dispatch the next agent (e.g. Data Validation or Analysis).
    if not report.strip():
        raise ToolError("submit_input_report failed: report is empty")
    if not dataset_path.strip():
        raise ToolError("submit_input_report failed: dataset_path is empty")
    if not problem_description.strip():
        raise ToolError("submit_input_report failed: problem_description is empty")
    return "Input report received. Next pipeline stage not yet implemented."


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
