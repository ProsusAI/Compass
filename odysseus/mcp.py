"""MCP server entrypoint for Odysseus.

Thin adapter layer — each tool delegates to an agent class that owns
all business logic.  The MCP layer only translates between tool
parameters/return values and agent context dicts.
"""

import json
import re
from pathlib import Path
from typing import Any

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
from odysseus.agents.routing_rationale_checks_deterministic import validate_deterministic
from odysseus.agents.routing_rationale_models import RationaleCardSet, RoutingContext, VocabularyRegistry
from odysseus.agents.routing_rationale_registry import create_seed_registry, prune_registry, resolve_registry
from odysseus.agents.stratified_split import stratified_split
from odysseus.eval.backends.registry import BackendRegistry
from odysseus.eval.models import ScoreReport
from odysseus.project_dir import get_project_dir

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


@mcp.prompt()
async def odysseus_prompt_builder() -> list[Message]:
    """Activate the Odysseus prompt builder agent.

    Use after the routing analysis agent has produced annotated and split datasets.
    """
    system_prompt = _load_text("odysseus/agents/prompts/prompt_builder_system.md")
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


@mcp.resource("odysseus://backends/{backend_label}")
async def backend_profile(backend_label: str) -> str:
    """Backend profile YAML for a given backend label.

    Returns the raw YAML content of the backend profile file so agents
    can read the provider field and other configuration.

    Args:
        backend_label: Backend label matching a YAML file in backends/
                       (e.g. "openai", "anthropic", "mock-echo").
    """
    project_dir = get_project_dir()
    profile_path = project_dir / "backends" / f"{backend_label}.yaml"
    if not profile_path.is_file():
        raise ToolError(
            f"Backend profile not found: {profile_path}. "
            f"Available profiles: {[p.stem for p in (project_dir / 'backends').glob('*.yaml')]}"
        )
    return profile_path.read_text()


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
    """OpenAI GPT-5 conventions and cookbook patterns for routing prompts."""
    return _load_text("odysseus/agents/prompt_builder_conventions_openai.md")


def _normalize_model_family(model: str) -> str:
    """Strip date suffixes and replace dots with dashes for filename lookup."""
    normalized = re.sub(r"-\d{4}-?\d{2}-?\d{2}$", "", model)
    return normalized.replace(".", "-")


@mcp.resource("odysseus://agents/prompt-builder/conventions-{provider}/{model_family}")
async def model_specific_conventions(provider: str, model_family: str) -> str:
    """Model-specific conventions addendum for routing prompts.

    Returns the model-specific cookbook content if a file exists for this
    provider/model combination. Returns an empty string if no model-specific
    guidance is available — this is the expected case for most models.

    The model string is normalized: date suffixes are stripped
    (gpt-5.2-2025-03-11 → gpt-5.2) and dots become dashes for filename
    lookup (gpt-5.2 → gpt-5-2).
    """
    sanitized = _normalize_model_family(model_family)
    relative_path = f"odysseus/agents/prompt_builder_conventions_{provider}_{sanitized}.md"
    path = _PROJECT_ROOT / relative_path
    if not path.is_file():
        return ""
    return path.read_text()


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
    search_state_id: str | None = None,
) -> str:
    """Run an evaluation of a prompt version against a dataset.

    Args:
        prompt_version: Prompt version identifier (e.g. "v3", "latest").
        data_source: Path to the JSONL dataset file.
        backend: Backend label matching a profile in backends/ directory.
        config_path: Path to YAML config with metrics, concurrency, retry,
                     and output settings. Defaults to "outputs/run_config.yaml".
        search_state_id: Search state ID for the optimization loop. When
                         provided and the loop is at round 0 with no history,
                         returns an action_required response instead of running
                         the eval, signalling the orchestrator to collect
                         backend configuration first.

    Returns:
        JSON object with report_path and results_path pointing to
        the full evaluation output on disk, OR an action_required
        object on first run.
    """
    # Pre-flight: on first run in loop, signal backend setup needed
    if search_state_id is not None:
        state = get_search_state(search_state_id=search_state_id)
        if state.round == 0 and len(state.round_history) == 0:
            project_dir = get_project_dir()
            registry = BackendRegistry.from_directory(project_dir / "backends")
            return json.dumps(
                {
                    "action_required": "backend_setup",
                    "search_state_id": search_state_id,
                    "available_backends": registry.list_profiles(),
                }
            )

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
    registry_path = Path(registry_dir) if Path(registry_dir).is_absolute() else get_project_dir() / registry_dir
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

    output_dir = get_project_dir() / "outputs" / split_report.dataset_hash
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


@mcp.prompt()
async def odysseus_review_agent() -> list[Message]:
    """System prompt for the Review Agent — supervises the prompt optimization search loop."""
    return [UserMessage(content=_load_text("odysseus/agents/prompts/review_agent_system.md"))]


@mcp.resource("odysseus://agents/review-agent/guidelines")
async def review_agent_guidelines() -> str:
    """Review criteria and evaluation priority reference for the Review Agent."""
    return _load_text("odysseus/agents/prompts/review_agent_system.md")


@mcp.tool()
async def build_review_briefing_tool(
    search_state_id: str,
    candidate_versions: list[str],
    parent_versions: dict[str, str | None],
    report_paths: dict[str, str],
    holdout_card_set_path: str = "",
    output_dir: str = "outputs",
) -> str:
    """Build a ReviewBriefing for the Review Agent by pre-processing all numerical data.

    Loads search state, score reports, prompt texts, mutation log, and directive
    history, then computes candidate comparisons, per-class recall, diversity
    metrics, diminishing returns, mutation correlation, and oracle metrics.

    Args:
        search_state_id: The search state to review.
        candidate_versions: Versions evaluated in the current round.
        parent_versions: Mapping of candidate → parent version.
        report_paths: Mapping of version → path to its ScoreReport JSON.
        holdout_card_set_path: Path to holdout rationale card set JSON (optional).
        output_dir: Output directory (default "outputs").

    Returns:
        JSON-serialized ReviewBriefing.
    """
    from odysseus.agents.prompt_builder_search_ops import get_search_state
    from odysseus.agents.review_models import ExampleSummary
    from odysseus.agents.review_ops import (
        load_directive_history,
        load_mutation_log,
        load_round_reports,
        save_round_report,
    )
    from odysseus.agents.review_preprocessor import build_review_briefing
    from odysseus.prompts.manager import FilePromptManager

    out = Path(output_dir) if Path(output_dir).is_absolute() else get_project_dir() / output_dir

    # Load search state
    state = get_search_state(search_state_id, output_dir=out)

    # Load score reports for current candidates + front + parents
    all_versions: set[str] = set(candidate_versions)
    for c in state.pareto_front:
        all_versions.add(c.prompt_version)
    for parent in parent_versions.values():
        if parent is not None:
            all_versions.add(parent)

    # Load historical round reports
    historical = load_round_reports(search_state_id, output_dir=out)

    # Load current round reports via report_paths param; fall back to historical for front members
    score_reports: dict[str, Any] = {}
    for version in all_versions:
        if version in report_paths:
            rp = Path(report_paths[version])
            if rp.exists():
                score_reports[version] = json.loads(rp.read_text(encoding="utf-8"))
        elif version not in score_reports:
            for round_data in historical.values():
                if version in round_data:
                    score_reports[version] = round_data[version]
                    break

    # Load prompt texts
    import contextlib

    prompt_mgr = FilePromptManager(get_project_dir() / "prompts")
    prompt_texts: dict[str, str] = {}
    for version in all_versions:
        with contextlib.suppress(FileNotFoundError):
            prompt_texts[version] = prompt_mgr.load(version)

    # Load mutation log and directive history
    mutation_log = load_mutation_log(search_state_id, output_dir=out)
    directive_history = load_directive_history(search_state_id, output_dir=out)

    # Load holdout examples from rationale card set if path provided
    holdout_examples: list[ExampleSummary] = []
    if holdout_card_set_path:
        card_set_data = json.loads(Path(holdout_card_set_path).read_text(encoding="utf-8"))
        for card_id, card in card_set_data.get("cards", {}).items():
            holdout_examples.append(
                ExampleSummary(
                    example_id=card_id,
                    route=card.get("assigned_route", ""),
                    ambiguity_tags=card.get("ambiguity_tags", []),
                )
            )

    # Build briefing
    briefing = build_review_briefing(
        search_state=state,
        score_reports=score_reports,
        historical_reports=historical,
        prompt_texts=prompt_texts,
        mutation_log=mutation_log,
        directive_history=directive_history,
        holdout_examples=holdout_examples,
        candidate_versions=candidate_versions,
        parent_versions=parent_versions,
    )

    # Save current round's reports for future historical access
    current_round_reports = {v: score_reports[v] for v in candidate_versions if v in score_reports}
    save_round_report(search_state_id, state.round, current_round_reports, output_dir=out)

    return briefing.model_dump_json(indent=2)


@mcp.tool()
async def record_directive_outcomes_tool(
    search_state_id: str,
    outcomes: list[dict[str, Any]],
    output_dir: str = "outputs",
) -> str:
    """Record the outcomes of prior Review Agent directives.

    Args:
        search_state_id: ID of the search state these outcomes belong to.
        outcomes: List of DirectiveOutcome dicts to record.
        output_dir: Output directory (default "outputs").

    Returns:
        JSON object with recorded count and new total.
    """
    from odysseus.agents.review_models import DirectiveOutcome
    from odysseus.agents.review_ops import load_directive_history, save_directive_history

    out = Path(output_dir) if Path(output_dir).is_absolute() else get_project_dir() / output_dir
    parsed = [DirectiveOutcome.model_validate(o) for o in outcomes]
    existing = load_directive_history(search_state_id, output_dir=out)
    save_directive_history(search_state_id, existing + parsed, output_dir=out)
    return json.dumps({"recorded": len(parsed), "total": len(existing) + len(parsed)})


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
