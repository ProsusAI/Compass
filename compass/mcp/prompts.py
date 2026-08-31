# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""MCP prompt definitions for Compass."""

from typing import Literal

from mcp.server.fastmcp.prompts.base import Message, UserMessage

from compass.mcp.server import _load_text, mcp


def _load_prompt(name: str) -> str:
    """Load a prompt file from compass/agents/prompts/<name>.md."""
    return _load_text(f"compass/agents/prompts/{name}.md")


def _overlay_filename(algorithm: str, phase: Literal["iterative", "cold_start", "post_coldstart"]) -> str:
    """Return the overlay prompt filename stem for the given (algorithm, phase) pair.

    | phase            | overlay used                                |
    |------------------|---------------------------------------------|
    | iterative        | review_agent_iterative_overlay_beam         |
    | cold_start       | review_agent_cold_start_overlay_beam        |
    | post_coldstart   | review_agent_post_coldstart_overlay_beam    |

    Raises:
        ValueError: When the (algorithm, phase) combination is not recognised.
    """
    _overlay_map: dict[tuple[str, str], str] = {
        ("beam", "iterative"): "review_agent_iterative_overlay_beam",
        ("beam", "cold_start"): "review_agent_cold_start_overlay_beam",
        ("beam", "post_coldstart"): "review_agent_post_coldstart_overlay_beam",
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

    For ``"post_coldstart"`` (beam only), the assembled prompt is three layers
    in this order: base + post-coldstart override + iterative-phase base. The
    round-2 override is placed BEFORE the iterative base so the agent reads
    the round-2 mandate (one child per protected parent, no merges) before
    the generic iterative diagnostic workflow it modifies.

    Args:
        algorithm: Search strategy — ``"beam"`` is the only supported value.
        phase: ``"iterative"`` for rounds ≥ 3; ``"cold_start"`` for the seeding
            round; ``"post_coldstart"`` for round 2 of beam search after cold-start.

    Returns:
        Assembled Markdown string ready to use as a system prompt.

    Raises:
        ValueError: When ``(algorithm, phase)`` is not a recognised combination.
        FileNotFoundError: When any of the component prompt files is missing.
    """
    if phase == "post_coldstart":
        if algorithm != "beam":
            raise ValueError(
                f"Unknown (algorithm, phase) combination: ({algorithm!r}, {phase!r}). Valid algorithms: beam."
            )
        base = _load_prompt("review_agent_base_system")
        post_override = _load_prompt(_overlay_filename(algorithm, phase))
        iterative_base = _load_prompt("review_agent_iterative_base_system")
        return f"{base}\n\n---\n\n{post_override}\n\n---\n\n{iterative_base}"

    overlay_name = _overlay_filename(algorithm, phase)
    base = _load_prompt("review_agent_base_system")
    overlay = _load_prompt(overlay_name)
    phase_base = _load_prompt(f"review_agent_{phase}_base_system")
    return f"{base}\n\n---\n\n{phase_base}\n\n---\n\n{overlay}"


# Stage prompt bodies pre-loaded at import time — keyed by the identifier used
# in _STAGE_PROMPT_MAP (int stage number or activate_prompt name string).
# The Review Agent prompts are NOT here — they use assemble_review_prompt().
_STAGE_PROMPT_BODIES: dict[int | str, str] = {
    1: _load_text("compass/agents/prompts/user_input_system.md"),
    2: _load_text("compass/agents/prompts/data_validation_system.md"),
    3: _load_text("compass/agents/prompts/backend_setup_system.md"),
    "compass_prompt_builder": _load_text("compass/agents/prompts/prompt_builder_system.md"),
    "compass_prompt_builder_rerun": _load_text("compass/agents/prompts/prompt_builder_rerun_system.md"),
    5: _load_text("compass/agents/prompts/final_report_system.md"),
}


@mcp.prompt()
async def compass_review_agent_iterative(algorithm: str = "beam") -> list[Message]:
    """System prompt for the Review Agent — iterative phase (rounds ≥ 2).

    Assembles a three-tier prompt: shared base + iterative phase base +
    strategy overlay for the given algorithm.

    Args:
        algorithm: Search strategy — ``"beam"`` is the only supported value
            (also the default).
    """
    content = assemble_review_prompt(algorithm, "iterative")
    return [UserMessage(content=content)]


@mcp.prompt()
async def compass_review_agent_cold_start(algorithm: str = "beam") -> list[Message]:
    """System prompt for the Review Agent — cold-start / seeding phase.

    Assembles a three-tier prompt: shared base + cold-start phase base +
    strategy overlay for the given algorithm.

    Args:
        algorithm: Search strategy — ``"beam"`` is the only supported value
            (also the default).
    """
    content = assemble_review_prompt(algorithm, "cold_start")
    return [UserMessage(content=content)]


@mcp.prompt()
async def compass_review_agent_post_coldstart(algorithm: str = "beam") -> list[Message]:
    """System prompt for the Review Agent — round-2 post-cold-start phase.

    Assembles a three-tier prompt: shared base + post-coldstart override + iterative phase base for the given algorithm.

    Args:
        algorithm: Search strategy — ``"beam"`` is the only supported value
            (also the default).
    """
    content = assemble_review_prompt(algorithm, "post_coldstart")
    return [UserMessage(content=content)]
