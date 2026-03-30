"""Routing analysis tools — registry, validation, split."""

import json
from pathlib import Path

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

import odysseus.project_dir as _project_dir_mod
from odysseus.agents.pipeline.guards import check_artifacts
from odysseus.agents.routing_analysis.checks_deterministic import validate_deterministic
from odysseus.agents.routing_analysis.models import RationaleCardSet, RoutingContext, VocabularyRegistry
from odysseus.agents.routing_analysis.registry import create_seed_registry, prune_registry, resolve_registry
from odysseus.agents.routing_analysis.split import stratified_split
from odysseus.mcp.server import _load_examples, _write_jsonl, mcp


@mcp.tool()
async def create_seed_registry_tool(ctx: Context, run_id: str) -> str:
    """[Stage 3: Routing Analysis] Initialize a vocabulary registry with 4 canonical ambiguity tags.

    Args:
        run_id: Pipeline run identifier.

    Returns:
        JSON-serialized VocabularyRegistry with seed ambiguity tags.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    check_artifacts(
        project_dir / "outputs" / run_id / "validation" / "data_quality_report.json",
        project_dir / "outputs" / run_id / "validation" / "routing_context.json",
        stage=3,
        stage_name="Routing Analysis",
        hint="Complete data validation first.",
    )

    registry = create_seed_registry()
    return registry.model_dump_json(indent=2)


@mcp.tool()
async def resolve_registry_tool(
    ctx: Context,
    run_id: str,
    dataset_hash: str,
    registry_dir: str = "outputs",
) -> str:
    """[Stage 3: Routing Analysis] Look up an existing registry by dataset hash.

    Args:
        run_id: Pipeline run identifier.
        dataset_hash: SHA-256 hash (16 hex chars) of the dataset.
        registry_dir: Directory to search for saved registries. Defaults to "outputs".

    Returns:
        JSON-serialized VocabularyRegistry if found, or {"found": false, ...}.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    check_artifacts(
        project_dir / "outputs" / run_id / "validation" / "data_quality_report.json",
        project_dir / "outputs" / run_id / "validation" / "routing_context.json",
        stage=3,
        stage_name="Routing Analysis",
        hint="Complete data validation first.",
    )

    registry_path = Path(registry_dir) if Path(registry_dir).is_absolute() else project_dir / registry_dir
    result = resolve_registry(dataset_hash, registry_path)
    if result is None:
        return json.dumps({"found": False, "dataset_hash": dataset_hash, "registry_dir": registry_dir})
    return result.model_dump_json(indent=2)


@mcp.tool()
async def validate_rationale_card_set_tool(
    ctx: Context,
    run_id: str,
    card_set_path: str,
    dataset_size: int,
) -> str:
    """[Stage 3: Routing Analysis] Run deterministic validation checks on a rationale card set.

    Does not call an LLM judge; semantic overlap is handled by the
    check-semantic-overlap skill.

    Args:
        run_id: Pipeline run identifier.
        card_set_path: Absolute path to a JSON file containing a serialized RationaleCardSet.
        dataset_size: Total number of examples in the dataset.

    Returns:
        JSON array of RationaleCheckResult objects.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    routing_context_path = project_dir / "outputs" / run_id / "validation" / "routing_context.json"
    check_artifacts(
        project_dir / "outputs" / run_id / "validation" / "data_quality_report.json",
        routing_context_path,
        stage=3,
        stage_name="Routing Analysis",
        hint="Complete data validation first.",
    )

    card_set_file = Path(card_set_path)
    if not card_set_file.is_file():
        raise ToolError(f"Card set file not found: {card_set_path}")
    card_set = RationaleCardSet.model_validate_json(card_set_file.read_text(encoding="utf-8"))
    routing_context = RoutingContext.model_validate_json(routing_context_path.read_text(encoding="utf-8"))
    results = validate_deterministic(card_set, routing_context, dataset_size)
    return json.dumps([r.model_dump() for r in results], indent=2)


@mcp.tool()
async def prune_registry_tool(
    ctx: Context,
    run_id: str,
    registry_path: str,
    dataset_size: int,
) -> str:
    """[Stage 3: Routing Analysis] Remove vocabulary entries below the cluster threshold.

    Threshold: max(3, ceil(0.05 * dataset_size)).

    Args:
        run_id: Pipeline run identifier.
        registry_path: Absolute path to a JSON file containing a serialized VocabularyRegistry.
        dataset_size: Total number of examples in the dataset.

    Returns:
        JSON with pruned_registry and removed_entries.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    check_artifacts(
        project_dir / "outputs" / run_id / "validation" / "data_quality_report.json",
        project_dir / "outputs" / run_id / "validation" / "routing_context.json",
        stage=3,
        stage_name="Routing Analysis",
        hint="Complete data validation first.",
    )

    registry_file = Path(registry_path)
    if not registry_file.is_file():
        raise ToolError(f"Registry file not found: {registry_path}")
    registry = VocabularyRegistry.model_validate_json(registry_file.read_text(encoding="utf-8"))
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
    ctx: Context,
    run_id: str,
    dataset_path: str,
    card_set_path: str,
    dev_ratio: float = 0.8,
) -> str:
    """[Stage 3: Routing Analysis -- Phase 4] Split a dataset and card set into dev and holdout partitions.

    Writes dev.jsonl, holdout.jsonl, dev_rationale_card_set.json,
    holdout_rationale_card_set.json, and split_report.json to
    outputs/<run_id>/analysis/.

    Args:
        run_id: Pipeline run identifier.
        dataset_path: Absolute path to the JSONL dataset file.
        card_set_path: Absolute path to the JSON file containing a serialized RationaleCardSet.
        dev_ratio: Proportion allocated to dev set. Defaults to 0.8.

    Returns:
        JSON with paths to all output files.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    check_artifacts(
        project_dir / "outputs" / run_id / "analysis" / "validation_report.json",
        stage=3,
        stage_name="Routing Analysis — Phase 4",
        hint="Complete routing analysis validation first.",
    )

    path = Path(dataset_path)
    if not path.is_file():
        raise ToolError(f"Dataset file not found: {dataset_path}")

    card_set_file = Path(card_set_path)
    if not card_set_file.is_file():
        raise ToolError(f"Card set file not found: {card_set_path}")

    examples = _load_examples(path)
    card_set = RationaleCardSet.model_validate_json(card_set_file.read_text(encoding="utf-8"))

    dev_examples, holdout_examples, dev_card_set, holdout_card_set, split_report = stratified_split(
        examples, card_set, dev_ratio
    )

    output_dir = project_dir / "outputs" / run_id / "analysis"
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
