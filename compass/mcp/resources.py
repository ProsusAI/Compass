# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""MCP resource definitions for Compass."""

from mcp.server.fastmcp.exceptions import ToolError

import compass.mcp.server as _server
from compass.mcp.server import _load_text, mcp, normalize_model_family
from compass.project_dir import get_project_dir


@mcp.resource("compass://agents/input/clarification-skill")
async def input_clarification_skill() -> str:
    """Structured clarification skill -- conversational strategy for the input agent."""
    return _load_text("compass/skills/structured-clarification/SKILL.md")


@mcp.resource("compass://agents/input/defaults")
async def input_defaults() -> str:
    """Default values and override mechanism for optional fields."""
    return _load_text("compass/agents/user_input/defaults.md")


@mcp.resource("compass://agents/backend-setup/clarification-skill")
async def backend_setup_clarification_skill() -> str:
    """Structured clarification skill -- conversational strategy for the backend setup agent."""
    return _load_text("compass/skills/structured-clarification/SKILL.md")


@mcp.resource("compass://agents/backend-setup/taxonomy")
async def backend_setup_taxonomy() -> str:
    """Field taxonomy for backend configuration -- blocking vs non-blocking fields."""
    return _load_text("compass/agents/backend_setup_taxonomy.md")


@mcp.resource("compass://agents/backend-setup/defaults")
async def backend_setup_defaults() -> str:
    """Default values and pricing resolution for backend configuration."""
    return _load_text("compass/agents/backend_setup_defaults.md")


@mcp.resource("compass://agents/data-validation/format-spec")
async def data_validation_format_spec() -> str:
    """Data format specification (THP-80) for the data validation agent."""
    return _load_text("compass/agents/data_validation/format.md")


@mcp.resource("compass://agents/data-validation/output-spec")
async def data_validation_output_spec() -> str:
    """Output format specification (THP-81) for the data validation agent."""
    return _load_text("compass/agents/data_validation/output.md")


@mcp.resource("compass://backends/{backend_label}")
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


@mcp.resource("compass://agents/prompt-builder/best-practices")
async def prompt_builder_best_practices() -> str:
    """General prompt engineering principles for routing prompts."""
    return _load_text("compass/agents/prompt_builder/best_practices.md")


@mcp.resource("compass://agents/prompt-builder/conventions-claude")
async def prompt_builder_conventions_claude() -> str:
    """Claude conventions and Anthropic cookbook patterns for routing prompts."""
    return _load_text("compass/agents/prompt_builder/conventions_claude.md")


@mcp.resource("compass://agents/prompt-builder/conventions-openai")
async def prompt_builder_conventions_openai() -> str:
    """OpenAI GPT-5 conventions and cookbook patterns for routing prompts."""
    return _load_text("compass/agents/prompt_builder/conventions_openai.md")


@mcp.resource("compass://agents/prompt-builder/conventions-{provider}/{model_family}")
async def model_specific_conventions(provider: str, model_family: str) -> str:
    """Model-specific conventions addendum for routing prompts.

    Returns the model-specific cookbook content if a file exists for this
    provider/model combination. Returns an empty string if no model-specific
    guidance is available -- this is the expected case for most models.

    The model string is normalized: date suffixes are stripped
    (gpt-5.2-2025-03-11 -> gpt-5.2) and dots become dashes for filename
    lookup (gpt-5.2 -> gpt-5-2).
    """
    sanitized = normalize_model_family(model_family)
    relative_path = f"compass/agents/prompt_builder/conventions_{provider}_{sanitized}.md"
    path = _server._PROJECT_ROOT / relative_path
    if not path.is_file():
        return ""
    return path.read_text()


@mcp.resource("compass://agents/review-agent/guidelines")
async def review_agent_guidelines() -> str:
    """Review Agent base system prompt plus iterative-phase shared guidelines."""
    return (
        _load_text("compass/agents/prompts/review_agent_base_system.md")
        + "\n\n---\n\n"
        + _load_text("compass/agents/prompts/review_agent_iterative_base_system.md")
    )


@mcp.resource("compass://agents/final-report/template")
async def final_report_template() -> str:
    """Markdown skeleton for the final report — section order and placeholders."""
    return _load_text("compass/agents/prompts/final_report_template.md")
