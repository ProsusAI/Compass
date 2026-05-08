"""Tests for the model-routing advisory hint shipped in MCP responses."""

from odysseus.mcp.orchestrator_tools import recommended_model_for
from odysseus.mcp.server import _REVIEW_AGENT_PROMPT_NAMES, _STAGE_PROMPT_MAP

# ---------------------------------------------------------------------------
# Helpers that replicate the dispatch-prefix logic from get_pipeline_status()
# without requiring a live MCP server or async context.
# ---------------------------------------------------------------------------


def _build_dispatch_prefix(activate_prompt: str | None) -> str:
    """Return the dispatch prefix string exactly as get_pipeline_status() builds it."""
    recommended_model = recommended_model_for(activate_prompt)
    tier = "strong" if recommended_model == "sonnet" else "fast"
    model_alias = '"sonnet"' if recommended_model == "sonnet" else '"haiku"'
    return (
        "⚠️ DISPATCH REQUIRED — Spawn a sub-agent. "
        "Do NOT call stage tools yourself.\n\n"
        f"  Recommended model tier for this dispatch: {tier}\n"
        f"  (Claude Code: pass `model: {model_alias}` as a literal\n"
        f"   parameter on your Agent call — REQUIRED, do not omit; omission\n"
        f"   inherits the orchestrator's model.\n"
        f"   Other runtimes: select the equivalent tier on your backend.)\n\n"
    )


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


# ---------------------------------------------------------------------------
# Dispatch-prefix wording tests (two-layer fast/strong framing)
# ---------------------------------------------------------------------------


def test_dispatch_prefix_non_review_contains_fast_haiku_and_required():
    """Non-review activate_prompt → prefix contains 'fast', model: \"haiku\", and 'REQUIRED'."""
    prefix = _build_dispatch_prefix("odysseus_prompt_builder")
    assert "fast" in prefix, "Expected tier word 'fast' for non-review prompt"
    assert 'model: "haiku"' in prefix, 'Expected literal model: "haiku" in prefix'
    assert "REQUIRED" in prefix, "Expected 'REQUIRED' directive in prefix"


def test_dispatch_prefix_review_contains_strong_and_sonnet():
    """Review activate_prompt → prefix contains 'strong' and model: \"sonnet\"."""
    # Use any name from _REVIEW_AGENT_PROMPT_NAMES
    review_prompt = next(iter(_REVIEW_AGENT_PROMPT_NAMES))
    prefix = _build_dispatch_prefix(review_prompt)
    assert "strong" in prefix, "Expected tier word 'strong' for review prompt"
    assert 'model: "sonnet"' in prefix, 'Expected literal model: "sonnet" in prefix'


def test_dispatch_prefix_both_contain_other_runtimes_fallback():
    """Both non-review and review prefixes must contain the other-runtimes fallback clause."""
    non_review_prefix = _build_dispatch_prefix("odysseus_prompt_builder")
    review_prompt = next(iter(_REVIEW_AGENT_PROMPT_NAMES))
    review_prefix = _build_dispatch_prefix(review_prompt)

    fallback_clause = "Other runtimes: select the equivalent tier"
    assert fallback_clause in non_review_prefix, "Non-review prefix missing other-runtimes fallback clause"
    assert fallback_clause in review_prefix, "Review prefix missing other-runtimes fallback clause"
