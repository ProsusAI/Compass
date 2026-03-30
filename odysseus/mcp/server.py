"""MCP server core — app instance, shared helpers, and main entrypoint.

Thin adapter layer — each tool delegates to an agent class that owns
all business logic.  The MCP layer only translates between tool
parameters/return values and agent context dicts.
"""

from __future__ import annotations

import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import Tool as MCPTool

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_STAGE_PROMPT_MAP: dict[int | str, str] = {
    1: "odysseus/agents/prompts/user_input_system.md",
    2: "odysseus/agents/prompts/data_validation_system.md",
    3: "odysseus/agents/prompts/backend_setup_system.md",
    4: "odysseus/agents/prompts/prompt_builder_system.md",
    # Stage 5 is dynamic — looked up by activate_prompt name:
    "odysseus_prompt_builder": "odysseus/agents/prompts/prompt_builder_system.md",
    "odysseus_review_agent": "odysseus/agents/prompts/review_agent_system.md",
}

# ---------------------------------------------------------------------------
# Stage registry — maps each pipeline stage to the tool names visible to the
# sub-agent operating in that stage.  ``get_pipeline_status`` is available in
# every stage so sub-agents can always check pipeline progress.
# ---------------------------------------------------------------------------

STAGE_REGISTRY: dict[str, list[str]] = {
    "orchestrator": [
        "optimize_routing_prompt",
        "get_pipeline_status",
        "start_stage",
        "complete_stage",
    ],
    "input_report": [
        "submit_input_report",
        "get_pipeline_status",
    ],
    "data_validation": [
        "detect_and_parse_dataset",
        "transform_dataset",
        "validate_dataset",
        "save_routing_context",
        "stratified_split_tool",
        "get_pipeline_status",
    ],
    "backend_setup": [
        "get_default_pricing",
        "get_pipeline_status",
    ],
    "prompt_building": [
        "init_search_state_tool",
        "register_candidate_tool",
        "run_eval",
        "record_eval_result_tool",
        "advance_round_tool",
        "get_search_state_tool",
        "filter_holdout_dataset_tool",
        "get_pipeline_status",
    ],
    "review": [
        "build_review_briefing_tool",
        "record_directive_outcomes_tool",
        "get_search_state_tool",
        "run_eval",
        "get_pipeline_status",
    ],
    "holdout": [
        "filter_holdout_dataset_tool",
        "run_holdout_eval",
        "get_pipeline_status",
    ],
}

# Module-level active stage — safe because stdio transport means one client
# per process.  Tools mutate this via ``start_stage`` / ``complete_stage``.
# ``None`` disables filtering (all tools visible); the MCP entrypoint sets
# this to ``"orchestrator"`` at startup.
_active_stage: str | None = "orchestrator"


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


def _normalize_model_family(model: str) -> str:
    """Strip date suffixes and replace dots with dashes for filename lookup."""
    normalized = re.sub(r"-\d{4}-?\d{2}-?\d{2}$", "", model)
    return normalized.replace(".", "-")


mcp = FastMCP("odysseus")


def get_active_stage() -> str | None:
    """Return the current active stage name, or ``None`` if filtering is disabled."""
    return _active_stage


def set_active_stage(stage: str | None) -> None:
    """Set the active stage.  Only ``start_stage`` / ``complete_stage`` should call this.

    Pass ``None`` to disable stage filtering (all tools visible).
    """
    global _active_stage  # noqa: PLW0603
    _active_stage = stage


# ---------------------------------------------------------------------------
# Override ``list_tools`` so that ``tools/list`` only returns tools visible
# in the current stage.
# ---------------------------------------------------------------------------

_original_list_tools = mcp.list_tools


async def _filtered_list_tools() -> list[MCPTool]:
    """Return only the tools allowed in the current active stage."""
    all_tools = await _original_list_tools()
    allowed = STAGE_REGISTRY.get(_active_stage)
    if allowed is None:
        return all_tools
    allowed_set = set(allowed)
    return [t for t in all_tools if t.name in allowed_set]


mcp.list_tools = _filtered_list_tools  # type: ignore[assignment]


def create_app() -> FastMCP:
    """Return the configured FastMCP application instance."""
    return mcp


# Import all tool/resource/prompt modules to trigger @mcp decorator registration.
import odysseus.mcp.backend_setup_tools as _backend_setup_tools  # noqa: E402, F401
import odysseus.mcp.data_validation_tools as _data_validation_tools  # noqa: E402, F401
import odysseus.mcp.holdout_tools as _holdout_tools  # noqa: E402, F401
import odysseus.mcp.input_report_tools as _input_report_tools  # noqa: E402, F401
import odysseus.mcp.orchestrator_tools as _orchestrator_tools  # noqa: E402, F401
import odysseus.mcp.prompt_building_tools as _prompt_building_tools  # noqa: E402, F401
import odysseus.mcp.prompts as _prompts  # noqa: E402, F401
import odysseus.mcp.resources as _resources  # noqa: E402, F401
import odysseus.mcp.review_tools as _review_tools  # noqa: E402, F401


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
