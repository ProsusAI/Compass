"""MCP server core — app instance, shared helpers, and main entrypoint.

Thin adapter layer — each tool delegates to an agent class that owns
all business logic.  The MCP layer only translates between tool
parameters/return values and agent context dicts.
"""

import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_STAGE_PROMPT_MAP: dict[int | str, str] = {
    1: "odysseus/agents/prompts/user_input_system.md",
    2: "odysseus/agents/prompts/data_validation_system.md",
    3: "odysseus/agents/prompts/routing_analysis_system.md",
    4: "odysseus/agents/prompts/backend_setup_system.md",
    5: "odysseus/agents/prompts/prompt_builder_system.md",
    # Stage 6 is dynamic — looked up by activate_prompt name:
    "odysseus_prompt_builder": "odysseus/agents/prompts/prompt_builder_system.md",
    "odysseus_review_agent": "odysseus/agents/prompts/review_agent_system.md",
}


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
import odysseus.mcp.routing_analysis_tools as _routing_analysis_tools  # noqa: E402, F401


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
