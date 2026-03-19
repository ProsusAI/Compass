"""MCP server entrypoint for Odysseus."""

import json
from pathlib import Path
from typing import Literal

import yaml
from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from odysseus.eval.models import MetricConfig, RunConfig

mcp = FastMCP("odysseus")

_DEFAULT_METRICS = [
    MetricConfig(name="accuracy"),
    MetricConfig(name="confusion"),
    MetricConfig(name="f1"),
    MetricConfig(name="cost_quality_reduction"),
]


def _load_config(
    prompt_version: str,
    data_source: str,
    backend: str,
    data_split: Literal["dev", "holdout"],
    config_path: str,
) -> RunConfig:
    """Load a YAML config and overlay tool parameters.

    Tool parameters always override YAML keys. If the YAML omits
    'metrics', all 4 built-in metrics are used as defaults.
    """
    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    raw.update({
        "backend": backend,
        "prompt_version": prompt_version,
        "data_source": data_source,
        "data_split": data_split,
    })

    if "metrics" not in raw:
        raw["metrics"] = [m.model_dump() for m in _DEFAULT_METRICS]

    return RunConfig.model_validate(raw)


def _build_run_config(
    prompt_version: str,
    data_source: str,
    data_split: Literal["dev", "holdout"],
) -> RunConfig:
    """Build a RunConfig with the given split hardcoded.

    This is the single place where RunConfig is assembled for MCP tools.
    The split is always provided by the calling tool, never by the agent.
    """
    # TODO(THP-129): read backend/metrics from environment or config file
    return RunConfig(
        backend="default",
        prompt_version=prompt_version,
        data_source=data_source,
        data_split=data_split,
        metrics=[MetricConfig(name="accuracy")],
    )


@mcp.tool()
async def run_eval(prompt_version: str, data_source: str) -> str:
    """Run evaluation on the dev split.

    Args:
        prompt_version: Prompt version to evaluate.
        data_source: Path to the dataset file.

    Returns:
        Serialized score report.
    """
    config = _build_run_config(
        prompt_version=prompt_version,
        data_source=data_source,
        data_split="dev",
    )
    # TODO(THP-129): wire RunDependencies and call controller.run()
    return f"run_eval stub: config.data_split={config.data_split}"


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
    config = _build_run_config(
        prompt_version=prompt_version,
        data_source=data_source,
        data_split="holdout",
    )
    # TODO: wire RunDependencies and call controller.run()
    return f"run_holdout_eval stub: config.data_split={config.data_split}"


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


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
