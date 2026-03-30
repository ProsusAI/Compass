"""MCP prompt definitions for Odysseus."""

from mcp.server.fastmcp.prompts.base import Message, UserMessage

from odysseus.mcp.server import _load_text, mcp


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
async def odysseus_review_agent() -> list[Message]:
    """System prompt for the Review Agent -- supervises the prompt optimization search loop."""
    return [UserMessage(content=_load_text("odysseus/agents/prompts/review_agent_system.md"))]
