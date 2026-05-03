"""MCP prompt definitions for Odysseus."""

from typing import Literal

from mcp.server.fastmcp.prompts.base import Message, UserMessage

from odysseus.mcp.server import _load_text, mcp


def _load_prompt(name: str) -> str:
    """Load a prompt file from odysseus/agents/prompts/<name>.md."""
    return _load_text(f"odysseus/agents/prompts/{name}.md")


def _overlay_filename(algorithm: str, phase: Literal["iterative", "cold_start", "post_coldstart"]) -> str:
    """Return the overlay prompt filename stem for the given (algorithm, phase) pair.

    | phase            | overlay used                              |
    |------------------|-------------------------------------------|
    | iterative        | algorithm-specific iterative overlay      |
    | cold_start       | algorithm-specific cold-start overlay     |
    | post_coldstart   | algorithm-specific iterative overlay      |

    Raises:
        ValueError: When the (algorithm, phase) combination is not recognised.
    """
    _overlay_map: dict[tuple[str, str], str] = {
        ("beam", "iterative"): "review_agent_iterative_overlay_beam",
        ("beam", "cold_start"): "review_agent_cold_start_overlay_beam",
        ("beam", "post_coldstart"): "review_agent_iterative_overlay_beam",
    }
    key = (algorithm, phase)
    if key not in _overlay_map:
        raise ValueError(
            f"Unknown (algorithm, phase) combination: ({algorithm!r}, {phase!r}). "
            f"Valid algorithms: beam. "
            f"Valid phases: iterative, cold_start, post_coldstart."
        )
    return _overlay_map[key]


def assemble_review_prompt(
    algorithm: str,
    phase: Literal["iterative", "cold_start", "post_coldstart"],
) -> str:
    """Compose the full Review Agent system prompt for the given strategy and phase.

    For ``"iterative"`` and ``"cold_start"``, the assembled prompt is three layers:
    base + phase-base + strategy overlay, separated by horizontal rules.

    For ``"post_coldstart"``, the assembled prompt is four layers:
    base + iterative-phase-base + post-coldstart override + strategy overlay.
    The iterative base applies the standard diagnostic workflow; the post-coldstart
    override mandates exactly one child per protected parent for round 2.

    Args:
        algorithm: Strategy discriminator — ``"beam"`` on this leaf.
        phase: ``"iterative"`` for rounds ≥ 2; ``"cold_start"`` for the seeding
            round; ``"post_coldstart"`` for round 2 of beam search after cold-start.

    Returns:
        Assembled Markdown string ready to use as a system prompt.

    Raises:
        ValueError: When ``(algorithm, phase)`` is not a recognised combination.
        FileNotFoundError: When any of the component prompt files is missing.
    """
    overlay_name = _overlay_filename(algorithm, phase)
    base = _load_prompt("review_agent_base_system")
    overlay = _load_prompt(overlay_name)
    if phase == "post_coldstart":
        iterative_base = _load_prompt("review_agent_iterative_base_system")
        post_override = _load_prompt("review_agent_post_coldstart_base_system")
        return f"{base}\n\n---\n\n{iterative_base}\n\n---\n\n{post_override}\n\n---\n\n{overlay}"
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
async def odysseus_review_agent_iterative(algorithm: str = "beam") -> list[Message]:
    """System prompt for the Review Agent — iterative phase (rounds ≥ 2).

    Assembles a three-tier prompt: shared base + iterative phase base +
    strategy overlay for the given algorithm.

    Args:
        algorithm: Search strategy in use — ``"beam"`` on this leaf.
            Defaults to ``beam``.
    """
    content = assemble_review_prompt(algorithm, "iterative")
    return [UserMessage(content=content)]


@mcp.prompt()
async def odysseus_review_agent_cold_start(algorithm: str = "beam") -> list[Message]:
    """System prompt for the Review Agent — cold-start / seeding phase.

    Assembles a three-tier prompt: shared base + cold-start phase base +
    strategy overlay for the given algorithm.

    Args:
        algorithm: Search strategy in use — ``"beam"`` on this leaf.
            Defaults to ``beam``.
    """
    content = assemble_review_prompt(algorithm, "cold_start")
    return [UserMessage(content=content)]


@mcp.prompt()
async def odysseus_review_agent_post_coldstart(algorithm: str = "beam") -> list[Message]:
    """System prompt for the Review Agent — round-2 post-cold-start phase.

    Assembles a four-tier prompt: shared base + iterative phase base +
    post-coldstart override + iterative strategy overlay for the given algorithm.

    Args:
        algorithm: Search strategy in use — ``"beam"`` on this leaf.
            Defaults to ``beam``.
    """
    content = assemble_review_prompt(algorithm, "post_coldstart")
    return [UserMessage(content=content)]


@mcp.prompt()
async def odysseus_final_report() -> list[Message]:
    """Activate the Odysseus final report agent.

    Runs holdout evaluation and generates the final optimization report.
    """
    return [UserMessage(content=_load_text("odysseus/agents/prompts/final_report_system.md"))]
