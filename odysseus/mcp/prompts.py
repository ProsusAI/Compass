"""MCP prompt definitions for Odysseus."""

from typing import Literal

from mcp.server.fastmcp.prompts.base import Message, UserMessage

from odysseus.mcp.server import _load_text, mcp


def _load_prompt(name: str) -> str:
    """Load a prompt file from odysseus/agents/prompts/<name>.md."""
    return _load_text(f"odysseus/agents/prompts/{name}.md")


def _overlay_filename(algorithm: str, phase: Literal["iterative", "cold_start"]) -> str:
    """Return the overlay prompt filename stem for the given (algorithm, phase) pair.

    On the pipeline trunk this map is empty by design; leaves populate it with their
    (algorithm, phase) → overlay-stem entries.

    Raises:
        NotImplementedError: Pipeline trunk has no algorithm overlays; run on a leaf branch.
    """
    _overlay_map: dict[tuple[str, str], str] = {}
    key = (algorithm, phase)
    if key not in _overlay_map:
        raise NotImplementedError(
            "Pipeline trunk has no algorithm overlays; run on a leaf branch "
            "(feat/generalize-{hill-climb,beam,emosa,sms-emoa})."
        )
    return _overlay_map[key]


def assemble_review_prompt(
    algorithm: str,
    phase: Literal["iterative", "cold_start"],
) -> str:
    """Compose the full Review Agent system prompt for the given strategy and phase.

    The assembled prompt is three layers: base + phase-base + strategy overlay,
    separated by horizontal rules.

    On the pipeline trunk the overlay map is empty, so this will always raise
    ``NotImplementedError``. Leaf branches override ``_overlay_filename`` to populate
    the map with their (algorithm, phase) entries.

    Args:
        algorithm: Strategy discriminator (e.g. ``hill_climb``, ``beam``).
        phase: ``"iterative"`` for rounds ≥ 2; ``"cold_start"`` for the seeding round.

    Returns:
        Assembled Markdown string ready to use as a system prompt.

    Raises:
        NotImplementedError: Pipeline trunk has no algorithm overlays.
        FileNotFoundError: When any of the component prompt files is missing.
    """
    overlay_name = _overlay_filename(algorithm, phase)
    base = _load_prompt("review_agent_base_system")
    overlay = _load_prompt(overlay_name)
    phase_base = _load_prompt(f"review_agent_{phase}_base_system")
    return f"{base}\n\n---\n\n{phase_base}\n\n---\n\n{overlay}"


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

    Validates the routing dataset and produces a data quality report.
    """
    system_prompt = _load_text("odysseus/agents/prompts/data_validation_system.md")
    return [UserMessage(content=system_prompt)]


@mcp.prompt()
async def odysseus_prompt_builder() -> list[Message]:
    """Activate the Odysseus prompt builder agent."""
    system_prompt = _load_text("odysseus/agents/prompts/prompt_builder_system.md")
    return [UserMessage(content=system_prompt)]


@mcp.prompt()
async def odysseus_backend_setup() -> list[Message]:
    """Activate the Odysseus backend setup agent.

    Guides the user through selecting or creating a backend profile.
    """
    system_prompt = _load_text("odysseus/agents/prompts/backend_setup_system.md")
    return [UserMessage(content=system_prompt)]


@mcp.prompt()
async def odysseus_review_agent_iterative(algorithm: str) -> list[Message]:
    """System prompt for the Review Agent — iterative phase (rounds ≥ 2).

    Assembles a three-tier prompt: shared base + iterative phase base +
    strategy overlay for the given algorithm.

    On the pipeline trunk this always raises NotImplementedError — run on a leaf branch.

    Args:
        algorithm: Search strategy in use (required; no default on the pipeline trunk).
    """
    content = assemble_review_prompt(algorithm, "iterative")
    return [UserMessage(content=content)]


@mcp.prompt()
async def odysseus_review_agent_cold_start(algorithm: str) -> list[Message]:
    """System prompt for the Review Agent — cold-start / seeding phase.

    Assembles a three-tier prompt: shared base + cold-start phase base +
    strategy overlay for the given algorithm.

    On the pipeline trunk this always raises NotImplementedError — run on a leaf branch.

    Args:
        algorithm: Search strategy in use (required; no default on the pipeline trunk).
    """
    content = assemble_review_prompt(algorithm, "cold_start")
    return [UserMessage(content=content)]


@mcp.prompt()
async def odysseus_final_report() -> list[Message]:
    """Activate the Odysseus final report agent.

    Runs holdout evaluation and generates the final optimization report.
    """
    return [UserMessage(content=_load_text("odysseus/agents/prompts/final_report_system.md"))]
