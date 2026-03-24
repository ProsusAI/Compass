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
from odysseus.agents.routing_rationale_checks_deterministic import validate_deterministic
from odysseus.agents.routing_rationale_models import RationaleCardSet, RoutingContext, VocabularyRegistry
from odysseus.agents.routing_rationale_registry import create_seed_registry, prune_registry, resolve_registry
from odysseus.agents.stratified_split import stratified_split
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


def _load_examples(path: Path) -> list:
    """Load Example objects from a JSONL file."""
    from odysseus.eval.models import Example

    examples = []
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        examples.append(Example.model_validate_json(stripped))
    return examples


def _write_jsonl(path: Path, examples: list) -> None:
    """Write Example objects to a JSONL file."""
    with path.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(ex.model_dump_json() + "\n")


mcp = FastMCP("odysseus")


@mcp.prompt()
async def odysseus_routing_input() -> list[Message]:
    """Activate the Odysseus routing input agent.

    Use when a user wants help with a routing optimization problem.
    Guides the user through providing a complete problem specification.
    """
    system_prompt = _load_text("odysseus/agents/prompts/user_input_system.md")
    return [UserMessage(content=system_prompt)]


@mcp.prompt()
async def odysseus_data_validation() -> list[Message]:
    """Activate the Odysseus data validation agent.

    Use after the input agent has produced a validated input report.
    Validates the routing dataset and produces a data quality report.
    """
    system_prompt = _load_text("odysseus/agents/prompts/data_validation_system.md")
    return [UserMessage(content=system_prompt)]


@mcp.resource("odysseus://agents/input/clarification-skill")
async def input_clarification_skill() -> str:
    """Structured clarification skill — conversational strategy for the input agent."""
    return _load_text("odysseus/agents/skills/structured-clarification.md")


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


@mcp.prompt()
async def odysseus_routing_analysis() -> list[Message]:
    """Activate the Odysseus routing analysis agent.

    Use after the data validation agent has produced a data quality report
    and routing context. Annotates, validates, and splits the dataset.
    """
    system_prompt = _load_text("odysseus/agents/prompts/routing_analysis_system.md")
    return [UserMessage(content=system_prompt)]


@mcp.resource("odysseus://agents/routing-analysis/classify-example-skill")
async def classify_example_skill() -> str:
    """Classify-example skill for the Routing Analysis Agent."""
    return _load_text("odysseus/skills/classify-example/SKILL.md")


@mcp.resource("odysseus://agents/routing-analysis/generate-rationale-skill")
async def generate_rationale_skill() -> str:
    """Generate-routing-rationale skill for the Routing Analysis Agent."""
    return _load_text("odysseus/skills/generate-routing-rationale/SKILL.md")


@mcp.resource("odysseus://agents/routing-analysis/check-overlap-skill")
async def check_overlap_skill() -> str:
    """Check-semantic-overlap skill for the Routing Analysis Agent."""
    return _load_text("odysseus/skills/check-semantic-overlap/SKILL.md")


@mcp.tool()
async def create_seed_registry_tool() -> str:
    """Initialize a vocabulary registry with 4 canonical ambiguity tags.

    Returns:
        JSON-serialized VocabularyRegistry with seed ambiguity tags.
    """
    registry = create_seed_registry()
    return registry.model_dump_json(indent=2)


@mcp.tool()
async def resolve_registry_tool(
    dataset_hash: str,
    registry_dir: str = "outputs",
) -> str:
    """Look up an existing registry by dataset hash.

    Args:
        dataset_hash: SHA-256 hash (16 hex chars) of the dataset.
        registry_dir: Directory to search for saved registries. Defaults to "outputs".

    Returns:
        JSON-serialized VocabularyRegistry if found, or {"found": false, ...}.
    """
    registry_path = Path(registry_dir)
    result = resolve_registry(dataset_hash, registry_path)
    if result is None:
        return json.dumps({"found": False, "dataset_hash": dataset_hash, "registry_dir": registry_dir})
    return result.model_dump_json(indent=2)


@mcp.tool()
async def validate_rationale_card_set_tool(
    card_set_json: str,
    routing_context_json: str,
    dataset_size: int,
) -> str:
    """Run deterministic validation checks on a rationale card set.

    Does not call an LLM judge; semantic overlap is handled by the
    check-semantic-overlap skill.

    Args:
        card_set_json: JSON-serialized RationaleCardSet.
        routing_context_json: JSON-serialized RoutingContext.
        dataset_size: Total number of examples in the dataset.

    Returns:
        JSON array of RationaleCheckResult objects.
    """
    card_set = RationaleCardSet.model_validate_json(card_set_json)
    routing_context = RoutingContext.model_validate_json(routing_context_json)
    results = validate_deterministic(card_set, routing_context, dataset_size)
    return json.dumps([r.model_dump() for r in results], indent=2)


@mcp.tool()
async def prune_registry_tool(
    registry_json: str,
    dataset_size: int,
) -> str:
    """Remove vocabulary entries below the cluster threshold.

    Threshold: max(3, ceil(0.05 * dataset_size)).

    Args:
        registry_json: JSON-serialized VocabularyRegistry.
        dataset_size: Total number of examples in the dataset.

    Returns:
        JSON with pruned_registry and removed_entries.
    """
    registry = VocabularyRegistry.model_validate_json(registry_json)
    pruned_registry, removed_entries = prune_registry(registry, dataset_size)
    return json.dumps(
        {
            "pruned_registry": json.loads(pruned_registry.model_dump_json()),
            "removed_entries": removed_entries,
        },
        indent=2,
    )


@mcp.tool()
async def stratified_split_tool(
    dataset_path: str,
    card_set_json: str,
    dev_ratio: float = 0.8,
) -> str:
    """Split a dataset and card set into dev and holdout partitions.

    Writes dev.jsonl, holdout.jsonl, dev_rationale_card_set.json,
    holdout_rationale_card_set.json, and split_report.json to an
    isolated subdirectory under outputs/ keyed by dataset hash.

    Args:
        dataset_path: Absolute path to the JSONL dataset file.
        card_set_json: JSON-serialized RationaleCardSet.
        dev_ratio: Proportion allocated to dev set. Defaults to 0.8.

    Returns:
        JSON with paths to all output files.
    """
    path = Path(dataset_path)
    if not path.is_file():
        raise ToolError(f"Dataset file not found: {dataset_path}")

    examples = _load_examples(path)
    card_set = RationaleCardSet.model_validate_json(card_set_json)

    dev_examples, holdout_examples, dev_card_set, holdout_card_set, split_report = stratified_split(
        examples, card_set, dev_ratio
    )

    output_dir = Path("outputs") / split_report.dataset_hash
    output_dir.mkdir(parents=True, exist_ok=True)
    dev_path = output_dir / "dev.jsonl"
    holdout_path = output_dir / "holdout.jsonl"
    dev_card_set_path = output_dir / "dev_rationale_card_set.json"
    holdout_card_set_path = output_dir / "holdout_rationale_card_set.json"
    split_report_path = output_dir / "split_report.json"

    _write_jsonl(dev_path, dev_examples)
    _write_jsonl(holdout_path, holdout_examples)
    dev_card_set_path.write_text(dev_card_set.model_dump_json(indent=2), encoding="utf-8")
    holdout_card_set_path.write_text(holdout_card_set.model_dump_json(indent=2), encoding="utf-8")
    split_report_path.write_text(split_report.model_dump_json(indent=2), encoding="utf-8")

    return json.dumps(
        {
            "dev_path": str(dev_path),
            "holdout_path": str(holdout_path),
            "dev_card_set_path": str(dev_card_set_path),
            "holdout_card_set_path": str(holdout_card_set_path),
            "split_report_path": str(split_report_path),
        },
        indent=2,
    )


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
