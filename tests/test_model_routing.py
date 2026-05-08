"""Tests for the model-routing advisory hint shipped in MCP responses."""

from odysseus.mcp.orchestrator_tools import recommended_model_for
from odysseus.mcp.server import _REVIEW_AGENT_PROMPT_NAMES, _STAGE_PROMPT_MAP


def test_review_prompt_names_returns_sonnet():
    """Every name in _REVIEW_AGENT_PROMPT_NAMES must map to 'sonnet'."""
    for name in _REVIEW_AGENT_PROMPT_NAMES:
        assert recommended_model_for(name) == "sonnet", (
            f"Expected 'sonnet' for review prompt '{name}', got '{recommended_model_for(name)}'"
        )


def test_non_review_prompt_returns_haiku():
    """A representative non-review activate_prompt must map to 'haiku'."""
    # Verify the key is actually in the stage map (guards against rename)
    assert "odysseus_prompt_builder" in _STAGE_PROMPT_MAP, (
        "'odysseus_prompt_builder' not found in _STAGE_PROMPT_MAP — update this test"
    )
    assert recommended_model_for("odysseus_prompt_builder") == "haiku"


def test_none_activate_prompt_returns_haiku():
    """None (no activate_prompt) must fall back to 'haiku'."""
    assert recommended_model_for(None) == "haiku"


def test_all_stage_prompt_map_keys_return_haiku():
    """Every key in _STAGE_PROMPT_MAP (non-review stages) must map to 'haiku'."""
    for key in _STAGE_PROMPT_MAP:
        # String keys are activate_prompt names; int keys are stage numbers (not passed as activate_prompt)
        if isinstance(key, str):
            assert recommended_model_for(key) == "haiku", (
                f"Expected 'haiku' for stage prompt '{key}', got '{recommended_model_for(key)}'"
            )


def test_review_prompt_names_not_empty():
    """_REVIEW_AGENT_PROMPT_NAMES must be non-empty so the routing rule has effect."""
    assert len(_REVIEW_AGENT_PROMPT_NAMES) > 0
