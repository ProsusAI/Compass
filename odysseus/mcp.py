"""MCP server entrypoint for Odysseus."""

import json
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

from odysseus.eval import controller
from odysseus.eval.backends.registry import BackendRegistry
from odysseus.eval.collector import JsonResultsCollector
from odysseus.eval.dataset import JsonlDatasetManager
from odysseus.eval.metrics import create_default_engine
from odysseus.eval.models import RunConfig
from odysseus.eval.protocols import RunDependencies
from odysseus.prompts.manager import FilePromptManager

mcp = FastMCP("odysseus")


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
    try:
        # Load stable config from YAML
        with open(config_path) as f:
            config_data: dict = yaml.safe_load(f)

        # Overlay agent-controlled parameters
        config_data["backend"] = backend
        config_data["prompt_version"] = prompt_version
        config_data["data_source"] = data_source
        config_data["data_split"] = "dev"

        config = RunConfig.model_validate(config_data)

        # Wire dependencies
        registry = BackendRegistry.from_directory(Path("backends"))
        profile = registry.get_profile(backend)
        backend_instance = registry.create_backend(backend)

        deps = RunDependencies(
            backend=backend_instance,
            prompt_manager=FilePromptManager(prompts_dir=Path("prompts")),
            dataset_manager=JsonlDatasetManager(),
            metrics_engine=create_default_engine(),
            results_collector=JsonResultsCollector(),
            requests_per_minute=profile.requests_per_minute,
            tokens_per_minute=profile.tokens_per_minute,
        )

        # Execute
        await controller.run(config, deps)

        return json.dumps({
            "report_path": config.output.report_path,
            "results_path": config.output.results_path,
        })

    except FileNotFoundError as e:
        return json.dumps({"error": "not_found", "detail": str(e)})
    except (ValueError, ValidationError) as e:
        return json.dumps({"error": "validation_error", "detail": str(e)})
    except KeyError as e:
        return json.dumps({"error": "not_found", "detail": str(e)})
    except PermissionError as e:
        return json.dumps({"error": "permission_denied", "detail": str(e)})
    except Exception as e:
        raise ToolError(f"run_eval failed unexpectedly: {e}") from e


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
