"""Tests for the Review Agent three-tier prompt assembly — beam leaf.

These tests validate the beam-specific overlay map.  Unknown algorithms raise
ValueError (not NotImplementedError — that's the pipeline trunk's sentinel behaviour).
"""

from __future__ import annotations

import pytest

from odysseus.mcp.prompts import _overlay_filename, assemble_review_prompt

# ---------------------------------------------------------------------------
# _overlay_filename — beam leaf behaviour
# ---------------------------------------------------------------------------


class TestOverlayFilename:
    def test_beam_iterative(self):
        assert _overlay_filename("beam", "iterative") == "review_agent_iterative_overlay_beam"

    def test_beam_cold_start(self):
        assert _overlay_filename("beam", "cold_start") == "review_agent_cold_start_overlay_beam"

    def test_unknown_algorithm_raises(self):
        with pytest.raises(ValueError, match="Unknown.*algorithm.*phase"):
            _overlay_filename("unknown_algo", "iterative")

    def test_unknown_phase_raises(self):
        with pytest.raises(ValueError, match="Unknown.*algorithm.*phase"):
            _overlay_filename("beam", "unknown_phase")  # type: ignore[arg-type]

    def test_unknown_combination_raises(self):
        with pytest.raises(ValueError, match="Unknown.*algorithm.*phase"):
            _overlay_filename("unknown_strategy", "iterative")  # type: ignore[arg-type]

    def test_non_beam_algorithm_raises(self):
        """Non-beam algorithms are not in the beam overlay map; raises ValueError."""
        with pytest.raises(ValueError):
            _overlay_filename("hill_climb", "iterative")


# ---------------------------------------------------------------------------
# assemble_review_prompt — beam leaf raises ValueError for unknown algo
# ---------------------------------------------------------------------------


def test_unknown_algorithm_raises_value_error():
    """assemble_review_prompt raises ValueError on beam leaf for unknown algo."""
    with pytest.raises(ValueError):
        assemble_review_prompt("unknown_algo", "iterative")


def test_unknown_phase_raises_value_error():
    """assemble_review_prompt raises ValueError on beam leaf for unknown phase."""
    with pytest.raises(ValueError):
        assemble_review_prompt("beam", "unknown_phase")  # type: ignore[arg-type]


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


# ---------------------------------------------------------------------------
# post_coldstart phase tests (beam leaf feature)
# ---------------------------------------------------------------------------


class TestOverlayFilenamePostColdstart:
    def test_beam_post_coldstart_resolves(self):
        """Beam leaf has post_coldstart overlay (uses iterative overlay)."""
        result = _overlay_filename("beam", "post_coldstart")
        assert result == "review_agent_iterative_overlay_beam"

    def test_unknown_algorithm_post_coldstart_raises(self):
        with pytest.raises(ValueError):
            _overlay_filename("unknown_algo", "post_coldstart")  # type: ignore[arg-type]


def test_post_coldstart_unknown_algorithm_raises():
    """assemble_review_prompt raises ValueError on beam leaf for unknown post_coldstart algo."""
    with pytest.raises(ValueError):
        assemble_review_prompt("unknown_algo", "post_coldstart")


@pytest.mark.parametrize("algorithm", ["beam"])
def test_iterative_prompt_contains_base_heading(algorithm: str):
    from odysseus.mcp.prompts import _load_prompt

    content = assemble_review_prompt(algorithm, "iterative")
    base = _load_prompt("review_agent_base_system")
    assert base[:50] in content


@pytest.mark.parametrize("algorithm", ["beam"])
def test_iterative_prompt_nonempty(algorithm: str):
    content = assemble_review_prompt(algorithm, "iterative")
    assert len(content) > 100


@pytest.mark.parametrize("algorithm", ["beam"])
def test_cold_start_prompt_nonempty(algorithm: str):
    content = assemble_review_prompt(algorithm, "cold_start")
    assert len(content) > 100
