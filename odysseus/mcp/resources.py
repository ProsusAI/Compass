"""MCP resource definitions for Odysseus."""

from mcp.server.fastmcp.exceptions import ToolError

import odysseus.mcp.server as _server
from odysseus.mcp.server import _load_text, _normalize_model_family, mcp
from odysseus.project_dir import get_project_dir


@mcp.resource("odysseus://agents/input/clarification-skill")
async def input_clarification_skill() -> str:
    """Structured clarification skill -- conversational strategy for the input agent."""
    return _load_text("odysseus/skills/structured-clarification/SKILL.md")


@mcp.resource("odysseus://agents/input/defaults")
async def input_defaults() -> str:
    """Default values and override mechanism for optional fields."""
    return _load_text("odysseus/agents/user_input/defaults.md")


@mcp.resource("odysseus://agents/backend-setup/clarification-skill")
async def backend_setup_clarification_skill() -> str:
    """Structured clarification skill -- conversational strategy for the backend setup agent."""
    return _load_text("odysseus/skills/structured-clarification/SKILL.md")


@mcp.resource("odysseus://agents/backend-setup/taxonomy")
async def backend_setup_taxonomy() -> str:
    """Field taxonomy for backend configuration -- blocking vs non-blocking fields."""
    return _load_text("odysseus/agents/backend_setup_taxonomy.md")


@mcp.resource("odysseus://agents/backend-setup/defaults")
async def backend_setup_defaults() -> str:
    """Default values and pricing resolution for backend configuration."""
    return _load_text("odysseus/agents/backend_setup_defaults.md")


@mcp.resource("odysseus://agents/data-validation/format-spec")
async def data_validation_format_spec() -> str:
    """Data format specification (THP-80) for the data validation agent."""
    return _load_text("odysseus/agents/data_validation/format.md")


@mcp.resource("odysseus://agents/data-validation/output-spec")
async def data_validation_output_spec() -> str:
    """Output format specification (THP-81) for the data validation agent."""
    return _load_text("odysseus/agents/data_validation/output.md")


@mcp.resource("odysseus://backends/{backend_label}")
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


@mcp.resource("odysseus://agents/prompt-builder/best-practices")
async def prompt_builder_best_practices() -> str:
    """General prompt engineering principles for routing prompts."""
    return _load_text("odysseus/agents/prompt_builder/best_practices.md")


@mcp.resource("odysseus://agents/prompt-builder/conventions-claude")
async def prompt_builder_conventions_claude() -> str:
    """Claude conventions and Anthropic cookbook patterns for routing prompts."""
    return _load_text("odysseus/agents/prompt_builder/conventions_claude.md")


@mcp.resource("odysseus://agents/prompt-builder/conventions-openai")
async def prompt_builder_conventions_openai() -> str:
    """OpenAI GPT-5 conventions and cookbook patterns for routing prompts."""
    return _load_text("odysseus/agents/prompt_builder/conventions_openai.md")


@mcp.resource("odysseus://agents/prompt-builder/conventions-{provider}/{model_family}")
async def model_specific_conventions(provider: str, model_family: str) -> str:
    """Model-specific conventions addendum for routing prompts.

    Returns the model-specific cookbook content if a file exists for this
    provider/model combination. Returns an empty string if no model-specific
    guidance is available -- this is the expected case for most models.

    The model string is normalized: date suffixes are stripped
    (gpt-5.2-2025-03-11 -> gpt-5.2) and dots become dashes for filename
    lookup (gpt-5.2 -> gpt-5-2).
    """
    sanitized = _normalize_model_family(model_family)
    relative_path = f"odysseus/agents/prompt_builder/conventions_{provider}_{sanitized}.md"
    path = _server._PROJECT_ROOT / relative_path
    if not path.is_file():
        return ""
    return path.read_text()


@mcp.resource("odysseus://agents/routing-analysis/classify-example-skill")
async def classify_example_skill() -> str:
    """Classify-example skill for the Routing Analysis Agent."""
    return _load_text("odysseus/skills/classify-example/SKILL.md")


@mcp.resource("odysseus://agents/routing-analysis/generate-rationale-skill")
async def generate_rationale_skill() -> str:
    """Generate-routing-rationale skill for the Routing Analysis Agent."""
    return _load_text("odysseus/skills/generate-routing-rationale/SKILL.md")


@mcp.resource("odysseus://agents/routing-analysis/check-overlap-skill")
async def check_overlap_skill() -> str:
    """Check-semantic-overlap skill for the Routing Analysis Agent."""
    return _load_text("odysseus/skills/check-semantic-overlap/SKILL.md")


@mcp.resource("odysseus://agents/review-agent/guidelines")
async def review_agent_guidelines() -> str:
    """Review criteria and evaluation priority reference for the Review Agent."""
    return _load_text("odysseus/agents/prompts/review_agent_system.md")
