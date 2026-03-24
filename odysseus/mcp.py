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

from odysseus.agents.data_validation_checks import run_all_checks
from odysseus.agents.eval_runner import EvalRunnerAgent
from odysseus.agents.prompt_builder_holdout_filter import filter_holdout_dataset
from odysseus.agents.prompt_builder_search_ops import (
    advance_round,
    get_search_state,
    init_search_state,
    record_eval_result,
    register_candidate,
)
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


@mcp.prompt()
async def odysseus_data_validation() -> list[Message]:
    """Activate the Odysseus data validation agent.

    Use after the input agent has produced a validated input report.
    Validates the routing dataset and produces a data quality report.
    """
    system_prompt = _load_text("prompts/data_validation_system.md")
    return [UserMessage(content=system_prompt)]


@mcp.prompt()
async def odysseus_prompt_builder() -> list[Message]:
    """Activate the Odysseus prompt builder agent.

    Use after the routing analysis agent has produced annotated and split datasets.
    """
    system_prompt = _load_text("odysseus/agents/prompts/prompt_builder_system.md")
    return [UserMessage(content=system_prompt)]


@mcp.resource("odysseus://agents/input/clarification-guide")
async def input_clarification_guide() -> str:
    """Per-field clarification guidance for the input agent."""
    return _load_text("odysseus/agents/user_input_clarification_guide.md")


@mcp.resource("odysseus://agents/input/defaults")
async def input_defaults() -> str:
    """Default values and override mechanism for optional fields."""
    return _load_text("odysseus/agents/user_input_defaults.md")


@mcp.resource("odysseus://agents/data-validation/format-spec")
async def data_validation_format_spec() -> str:
    """Data format specification (THP-80) for the data validation agent."""
    return _load_text("odysseus/agents/data_validation_format.md")


@mcp.resource("odysseus://agents/data-validation/output-spec")
async def data_validation_output_spec() -> str:
    """Output format specification (THP-81) for the data validation agent."""
    return _load_text("odysseus/agents/data_validation_output.md")


@mcp.resource("odysseus://agents/prompt-builder/best-practices")
async def prompt_builder_best_practices() -> str:
    """General prompt engineering principles for routing prompts."""
    return _load_text("odysseus/agents/prompt_builder_best_practices.md")


@mcp.resource("odysseus://agents/prompt-builder/conventions-claude")
async def prompt_builder_conventions_claude() -> str:
    """Claude conventions and Anthropic cookbook patterns for routing prompts."""
    return _load_text("odysseus/agents/prompt_builder_conventions_claude.md")


@mcp.resource("odysseus://agents/prompt-builder/conventions-openai")
async def prompt_builder_conventions_openai() -> str:
    """OpenAI conventions and cookbook patterns for routing prompts."""
    return _load_text("odysseus/agents/prompt_builder_conventions_openai.md")


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


@mcp.tool()
async def validate_dataset(dataset_path: str) -> str:
    """Run all validation checks against a JSONL routing dataset.

    Args:
        dataset_path: Absolute path to the JSONL dataset file.

    Returns:
        JSON-serialized DataQualityReport with schema findings,
        label distribution, volume adequacy, and query length stats.
    """
    path = Path(dataset_path)
    if not path.is_file():
        raise ToolError(f"Dataset file not found: {dataset_path}")

    rows: list[dict] = []
    line_num = 0
    try:
        text = path.read_text(encoding="utf-8")
        for line_num, line in enumerate(text.splitlines(), start=1):  # noqa: B007
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
    except json.JSONDecodeError as exc:
        raise ToolError(f"Malformed JSONL at line {line_num}: {exc}") from exc

    report = run_all_checks(rows)
    return report.model_dump_json(indent=2)


@mcp.tool()
async def init_search_state_tool(
    backend: str,
    max_rounds: int = 50,
    stagnation_limit: int = 3,
    convergence_limit: int = 5,
    primary_metric_name: str | None = None,
) -> str:
    """Initialise a new prompt-builder search state.

    Args:
        backend: Backend identifier (e.g. "anthropic", "openai").
        max_rounds: Maximum number of search rounds before forced convergence.
        stagnation_limit: Stagnation rounds before switching to exploratory mode.
        convergence_limit: Stagnation rounds that trigger convergence.
        primary_metric_name: Optional name of the primary quality metric.

    Returns:
        JSON-serialized SearchState for the new search run.
    """
    state = init_search_state(
        backend=backend,
        max_rounds=max_rounds,
        stagnation_limit=stagnation_limit,
        convergence_limit=convergence_limit,
        primary_metric_name=primary_metric_name,
    )
    return state.model_dump_json(indent=2)


@mcp.tool()
async def register_candidate_tool(
    search_state_id: str,
    prompt_version: str,
    parent_version: str | None = None,
) -> str:
    """Register a new candidate prompt version for the current search round.

    Args:
        search_state_id: ID of the search state to update.
        prompt_version: Unique version identifier for the new prompt candidate.
        parent_version: Parent prompt version, if any.

    Returns:
        JSON object confirming the registered prompt version.
    """
    try:
        register_candidate(
            search_state_id=search_state_id,
            prompt_version=prompt_version,
            parent_version=parent_version,
        )
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return json.dumps({"registered": prompt_version})


@mcp.tool()
async def record_eval_result_tool(
    search_state_id: str,
    prompt_version: str,
    quality_score: float,
    cost: float,
) -> str:
    """Record evaluation results for a pending candidate.

    Args:
        search_state_id: ID of the search state to update.
        prompt_version: Version identifier of the candidate being evaluated.
        quality_score: Evaluation quality score.
        cost: Evaluation cost.

    Returns:
        JSON object with prompt_version, quality_score, and cost.
    """
    try:
        result = record_eval_result(
            search_state_id=search_state_id,
            prompt_version=prompt_version,
            quality_score=quality_score,
            cost=cost,
        )
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return json.dumps(result)


@mcp.tool()
async def advance_round_tool(search_state_id: str) -> str:
    """Advance the search loop by one round.

    Processes all pending candidates, updates the Pareto front, adjusts
    stagnation tracking, and checks for convergence.

    Args:
        search_state_id: ID of the search state to advance.

    Returns:
        JSON-serialized RoundSummary for the completed round.
    """
    try:
        summary = advance_round(search_state_id=search_state_id)
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return summary.model_dump_json(indent=2)


@mcp.tool()
async def get_search_state_tool(search_state_id: str) -> str:
    """Load and return the current search state.

    Args:
        search_state_id: ID of the search state to retrieve.

    Returns:
        JSON-serialized SearchState.
    """
    try:
        state = get_search_state(search_state_id=search_state_id)
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    return state.model_dump_json(indent=2)


@mcp.tool()
async def filter_holdout_dataset_tool(
    holdout_jsonl_path: str,
    exclude_ids: list[str],
) -> str:
    """Filter a holdout JSONL dataset by removing rows with specified IDs.

    Removes few-shot examples from the holdout set to prevent data
    contamination before final evaluation.

    Args:
        holdout_jsonl_path: Path to the holdout JSONL dataset file.
        exclude_ids: List of row IDs to exclude from the output.

    Returns:
        JSON object with filtered_holdout_path pointing to the output file.
    """
    try:
        filtered_path = filter_holdout_dataset(
            holdout_jsonl_path=holdout_jsonl_path,
            exclude_ids=exclude_ids,
        )
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    return json.dumps({"filtered_holdout_path": filtered_path})


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
