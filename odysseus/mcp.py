"""MCP server entrypoint for Odysseus.

Thin adapter layer — each tool delegates to an agent class that owns
all business logic.  The MCP layer only translates between tool
parameters/return values and agent context dicts.
"""

import json

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.agents.eval_runner import EvalRunnerAgent
from odysseus.eval.models import ScoreReport

mcp = FastMCP("odysseus")


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


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
