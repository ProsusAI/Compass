"""Data validation tools — detect, transform, validate datasets."""

import json
from pathlib import Path

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

import odysseus.project_dir as _project_dir_mod
from odysseus.agents.data_validation.checks import run_all_checks
from odysseus.agents.data_validation.detect import detect_and_parse
from odysseus.agents.data_validation.transform import transform_dataset as _do_transform
from odysseus.agents.pipeline.guards import check_artifacts
from odysseus.agents.routing_analysis.models import RationaleCardSet, RoutingContext
from odysseus.agents.routing_analysis.split import stratified_split
from odysseus.mcp.server import _load_examples, _write_jsonl, mcp


@mcp.tool()
async def detect_and_parse_dataset(ctx: Context, dataset_path: str, run_id: str) -> str:
    """[Stage 2: Data Validation] Detect the format of a dataset file and parse its schema.

    Supports CSV, JSON (array of objects), and JSONL formats.
    Returns column names, sample rows, and nested field paths
    for LLM-driven field mapping inference.

    Args:
        dataset_path: Absolute path to the dataset file.
        run_id: Pipeline run identifier.

    Returns:
        JSON-serialized DetectionResult with source_format, columns,
        sample_rows, nested_paths, and any warnings or skipped lines.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    check_artifacts(
        project_dir / "outputs" / run_id / "input" / "input_report.md",
        stage=2,
        stage_name="Data Validation",
        hint="Submit an input report first.",
    )

    try:
        result = detect_and_parse(dataset_path)
    except (FileNotFoundError, ValueError) as exc:
        raise ToolError(str(exc)) from exc
    return result.model_dump_json(indent=2)


@mcp.tool()
async def transform_dataset(
    ctx: Context,
    dataset_path: str,
    field_mapping: str,
    run_id: str,
) -> str:
    """[Stage 2: Data Validation] Apply a confirmed field mapping and write canonical JSONL.

    Keys in field_mapping are source field names (or dot-paths for nested
    sources). Values are canonical target field names (e.g. "input",
    "expected.route", "expected.routes.opus.cost").

    Args:
        dataset_path: Absolute path to the original dataset file.
        field_mapping: JSON object mapping source fields to target fields.
        run_id: Pipeline run identifier.

    Returns:
        JSON-serialized TransformResult with output_path, rows_written,
        fields_mapped, and fields_dropped.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    check_artifacts(
        project_dir / "outputs" / run_id / "input" / "input_report.md",
        stage=2,
        stage_name="Data Validation",
        hint="Submit an input report first.",
    )

    output_path = str(project_dir / "outputs" / run_id / "validation" / "transformed.jsonl")
    try:
        result = _do_transform(dataset_path, field_mapping, output_path)
    except (FileNotFoundError, ValueError) as exc:
        raise ToolError(str(exc)) from exc
    return result.model_dump_json(indent=2)


@mcp.tool()
async def validate_dataset(ctx: Context, dataset_path: str, run_id: str) -> str:
    """[Stage 2: Data Validation] Run all validation checks against a JSONL routing dataset.

    Args:
        dataset_path: Absolute path to the JSONL dataset file.
        run_id: Pipeline run identifier.

    Returns:
        JSON-serialized DataQualityReport with schema findings,
        label distribution, volume adequacy, and query length stats.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    check_artifacts(
        project_dir / "outputs" / run_id / "input" / "input_report.md",
        stage=2,
        stage_name="Data Validation",
        hint="Submit an input report first.",
    )

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

    # Persist report to run output directory
    report_dir = project_dir / "outputs" / run_id / "validation"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "data_quality_report.json"
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    return report.model_dump_json(indent=2)


@mcp.tool()
async def save_routing_context(ctx: Context, run_id: str, routing_context_json: str) -> str:
    """Persist a RoutingContext to the validation directory for a run.

    Call this after synthesizing the routing context from the data
    quality report and problem description. The JSON is validated
    against the RoutingContext schema before writing.

    Args:
        run_id: The run identifier (e.g. "a1b2c3d4").
        routing_context_json: JSON-serialized RoutingContext object.

    Returns:
        Confirmation message with the persisted file path.
    """
    try:
        routing_context = RoutingContext.model_validate_json(routing_context_json)
    except Exception as exc:
        raise ToolError(f"Invalid RoutingContext JSON: {exc}") from exc

    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    validation_dir = project_dir / "outputs" / run_id / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    out_path = validation_dir / "routing_context.json"
    out_path.write_text(routing_context.model_dump_json(indent=2), encoding="utf-8")
    return f"Routing context saved to {out_path}"


@mcp.tool()
async def stratified_split_tool(
    ctx: Context,
    run_id: str,
    dataset_path: str,
    card_set_path: str,
    dev_ratio: float = 0.8,
) -> str:
    """[Stage 2: Data Validation] Split a dataset and card set into dev and holdout partitions.

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
        project_dir / "outputs" / run_id / "validation" / "data_quality_report.json",
        stage=2,
        stage_name="Data Validation",
        hint="Complete data validation first.",
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
