"""MCP prompt definitions for Odysseus."""

from typing import Literal

from mcp.server.fastmcp.prompts.base import Message, UserMessage

from odysseus.mcp.server import _load_text, mcp


def _load_prompt(name: str) -> str:
    """Load a prompt file from odysseus/agents/prompts/<name>.md."""
    return _load_text(f"odysseus/agents/prompts/{name}.md")


def _overlay_filename(algorithm: str, phase: Literal["iterative", "cold_start"]) -> str:
    """Return the overlay prompt filename stem for the given (algorithm, phase) pair.

    Raises:
        ValueError: When the (algorithm, phase) combination is not recognised.
    """
    _overlay_map: dict[tuple[str, str], str] = {
        ("hill_climb", "iterative"): "review_agent_iterative_overlay_hillclimb",
        ("hill_climb", "cold_start"): "review_agent_cold_start_overlay_hillclimb",
    }
    key = (algorithm, phase)
    if key not in _overlay_map:
        raise ValueError(
            f"Unknown (algorithm, phase) combination: ({algorithm!r}, {phase!r}). "
            f"Valid algorithms: hill_climb. "
            f"Valid phases: iterative, cold_start."
        )
    return _overlay_map[key]


def assemble_review_prompt(algorithm: str, phase: Literal["iterative", "cold_start"]) -> str:
    """Compose the full Review Agent system prompt for the given strategy and phase.

    The assembled prompt is: base + phase-base + strategy overlay, separated by
    horizontal rules so the agent can read them as three layered sections.

    Args:
        algorithm: Strategy discriminator — ``"hill_climb"`` on this branch.
        phase: ``"iterative"`` for rounds ≥ 2; ``"cold_start"`` for the seeding round.

    Returns:
        Assembled Markdown string ready to use as a system prompt.

    Raises:
        ValueError: When ``(algorithm, phase)`` is not a recognised combination.
        FileNotFoundError: When any of the three component prompt files is missing.
    """
    # Validate the combination first — raises ValueError for unknown pairs.
    overlay_name = _overlay_filename(algorithm, phase)
    base = _load_prompt("review_agent_base_system")
    phase_base = _load_prompt(f"review_agent_{phase}_base_system")
    overlay = _load_prompt(overlay_name)
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
async def odysseus_review_agent_iterative(algorithm: str = "hill_climb") -> list[Message]:
    """System prompt for the Review Agent — iterative phase (rounds ≥ 2).

    Assembles a three-tier prompt: shared base + iterative phase base +
    strategy overlay for the given algorithm.

    Args:
        algorithm: Search strategy in use — ``"hill_climb"`` on this branch.
            Defaults to ``hill_climb``.
    """
    content = assemble_review_prompt(algorithm, "iterative")
    return [UserMessage(content=content)]


@mcp.prompt()
async def odysseus_review_agent_cold_start(algorithm: str = "hill_climb") -> list[Message]:
    """System prompt for the Review Agent — cold-start / seeding phase.

    Assembles a three-tier prompt: shared base + cold-start phase base +
    strategy overlay for the given algorithm.

    Args:
        algorithm: Search strategy in use — ``"hill_climb"`` on this branch.
            Defaults to ``hill_climb``.
    """
    content = assemble_review_prompt(algorithm, "cold_start")
    return [UserMessage(content=content)]


@mcp.prompt()
async def odysseus_final_report() -> list[Message]:
    """Activate the Odysseus final report agent.

    Runs holdout evaluation and generates the final optimization report.
    """
    return [UserMessage(content=_load_text("odysseus/agents/prompts/final_report_system.md"))]
