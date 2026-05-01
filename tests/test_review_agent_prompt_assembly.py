"""Tests for the Review Agent three-tier prompt assembly."""

from __future__ import annotations

import pytest

from odysseus.mcp.prompts import _overlay_filename, assemble_review_prompt

# ---------------------------------------------------------------------------
# _overlay_filename
# ---------------------------------------------------------------------------


class TestOverlayFilename:
    def test_hill_climb_iterative(self):
        assert _overlay_filename("hill_climb", "iterative") == "review_agent_iterative_overlay_hillclimb"

    def test_hill_climb_cold_start(self):
        assert _overlay_filename("hill_climb", "cold_start") == "review_agent_cold_start_overlay_hillclimb"

    def test_unknown_algorithm_raises(self):
        with pytest.raises(ValueError, match="Unknown.*algorithm.*phase"):
            _overlay_filename("unknown_algo", "iterative")

    def test_unknown_phase_raises(self):
        with pytest.raises(ValueError, match="Unknown.*algorithm.*phase"):
            _overlay_filename("hill_climb", "unknown_phase")  # type: ignore[arg-type]

    def test_unknown_combination_raises(self):
        with pytest.raises(ValueError, match="Unknown.*algorithm.*phase"):
            _overlay_filename("unknown_strategy", "iterative")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# assemble_review_prompt — content checks
# ---------------------------------------------------------------------------

# Markers that must appear in the assembled prompt for each (algorithm, phase)
_ITERATIVE_FLOW_HEADING = "Flow: identify failure mode"
_COLD_START_FLOW_HEADING = "Flow: formulate diverse strategies"
_BASE_HEADING = "Entry verification"


@pytest.mark.parametrize("algorithm", ["hill_climb"])
def test_iterative_prompt_contains_base_heading(algorithm: str):
    """Assembled iterative prompt contains the base 'Entry verification' heading."""
    prompt = assemble_review_prompt(algorithm, "iterative")
    assert _BASE_HEADING in prompt, f"Base heading missing for {algorithm}/iterative"


@pytest.mark.parametrize("algorithm", ["hill_climb"])
def test_iterative_prompt_contains_flow_heading(algorithm: str):
    """Assembled iterative prompt contains the iterative flow heading."""
    prompt = assemble_review_prompt(algorithm, "iterative")
    assert _ITERATIVE_FLOW_HEADING in prompt, f"Iterative flow heading missing for {algorithm}"


@pytest.mark.parametrize("algorithm", ["hill_climb"])
def test_iterative_prompt_contains_loop_phase(algorithm: str):
    """Assembled iterative prompt contains 'Loop phase' from the overlay."""
    prompt = assemble_review_prompt(algorithm, "iterative")
    assert "Loop phase" in prompt, f"'Loop phase' missing from {algorithm}/iterative overlay"


@pytest.mark.parametrize("algorithm", ["hill_climb"])
def test_iterative_prompt_nonempty(algorithm: str):
    """assemble_review_prompt returns a non-empty string for the iterative combo."""
    prompt = assemble_review_prompt(algorithm, "iterative")
    assert len(prompt) > 100


@pytest.mark.parametrize("algorithm", ["hill_climb"])
def test_cold_start_prompt_contains_base_heading(algorithm: str):
    """Assembled cold-start prompt contains the base 'Entry verification' heading."""
    prompt = assemble_review_prompt(algorithm, "cold_start")
    assert _BASE_HEADING in prompt, f"Base heading missing for {algorithm}/cold_start"


@pytest.mark.parametrize("algorithm", ["hill_climb"])
def test_cold_start_prompt_contains_flow_heading(algorithm: str):
    """Assembled cold-start prompt contains the cold-start flow heading."""
    prompt = assemble_review_prompt(algorithm, "cold_start")
    assert _COLD_START_FLOW_HEADING in prompt, f"Cold-start flow heading missing for {algorithm}"


@pytest.mark.parametrize("algorithm", ["hill_climb"])
def test_cold_start_prompt_contains_loop_phase(algorithm: str):
    """Assembled cold-start prompt contains 'Loop phase' from the overlay."""
    prompt = assemble_review_prompt(algorithm, "cold_start")
    assert "Loop phase" in prompt, f"'Loop phase' missing from {algorithm}/cold_start overlay"


@pytest.mark.parametrize("algorithm", ["hill_climb"])
def test_cold_start_prompt_nonempty(algorithm: str):
    """assemble_review_prompt returns a non-empty string for the cold-start combo."""
    prompt = assemble_review_prompt(algorithm, "cold_start")
    assert len(prompt) > 100


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_unknown_algorithm_raises_value_error():
    """assemble_review_prompt raises ValueError for an unknown algorithm."""
    with pytest.raises(ValueError, match="Unknown"):
        assemble_review_prompt("unknown_algo", "iterative")


def test_unknown_phase_raises_value_error():
    """assemble_review_prompt raises ValueError for an unknown phase."""
    with pytest.raises(ValueError, match="Unknown"):
        assemble_review_prompt("hill_climb", "unknown_phase")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Snapshot: shared bases must NOT contain strategy-specific terms
# ---------------------------------------------------------------------------

_STRATEGY_NAMES = [
    "hill-climb",
    "hill_climb",
    "trajectory",
    "weight_vector",
    "lambda",
    "Tchebycheff",
    "binding_axis",
    "mutation_mode",
    "parent_a",
    "parent_b",
    "crowding_distance",
]

_BASE_FILES = [
    "review_agent_base_system",
    "review_agent_iterative_base_system",
    "review_agent_cold_start_base_system",
]


@pytest.mark.parametrize("base_file", _BASE_FILES)
@pytest.mark.parametrize("term", _STRATEGY_NAMES)
def test_shared_base_does_not_contain_strategy_term(base_file: str, term: str):
    """Shared base prompt files must not contain strategy-specific terms."""
    from odysseus.mcp.prompts import _load_prompt

    content = _load_prompt(base_file)
    assert term not in content, (
        f"Strategy-specific term {term!r} found in shared base {base_file!r}. "
        "Shared bases must be strategy-agnostic; move strategy-specific content to overlays."
    )
