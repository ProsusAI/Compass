"""Tests for the Review Agent three-tier prompt assembly.

Algorithm-specific overlay tests (e.g. hill_climb, emosa, beam) require the
respective leaf branch where _overlay_map is populated.  Only algorithm-agnostic
tests are kept here on the pipeline trunk.
"""

from __future__ import annotations

import pytest

from odysseus.mcp.prompts import _overlay_filename, assemble_review_prompt

# ---------------------------------------------------------------------------
# _overlay_filename — trunk behaviour
# ---------------------------------------------------------------------------


class TestOverlayFilename:
    def test_any_algorithm_raises_on_trunk(self):
        """Trunk _overlay_map is empty; any (algorithm, phase) pair raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            _overlay_filename("hill_climb", "iterative")

    def test_unknown_algorithm_raises(self):
        """Unknown algorithm also raises NotImplementedError on trunk."""
        with pytest.raises(NotImplementedError):
            _overlay_filename("unknown_algo", "iterative")

    def test_unknown_phase_raises(self):
        """Unknown phase raises NotImplementedError on trunk."""
        with pytest.raises(NotImplementedError):
            _overlay_filename("hill_climb", "unknown_phase")  # type: ignore[arg-type]

    def test_unknown_combination_raises(self):
        """Unknown strategy/phase combo raises NotImplementedError on trunk."""
        with pytest.raises(NotImplementedError):
            _overlay_filename("unknown_strategy", "iterative")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# assemble_review_prompt — trunk raises NotImplementedError
# ---------------------------------------------------------------------------


def test_unknown_algorithm_raises_value_error():
    """assemble_review_prompt raises NotImplementedError on trunk (no overlays)."""
    with pytest.raises(NotImplementedError):
        assemble_review_prompt("unknown_algo", "iterative")


def test_unknown_phase_raises_value_error():
    """assemble_review_prompt raises NotImplementedError on trunk (no overlays)."""
    with pytest.raises(NotImplementedError):
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


# ---------------------------------------------------------------------------
# post_coldstart phase tests (leaf-branch feature)
# ---------------------------------------------------------------------------


class TestOverlayFilenamePostColdstart:
    def test_any_algorithm_raises_on_trunk(self):
        """post_coldstart overlays are leaf-branch-specific; trunk raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            _overlay_filename("hill_climb", "post_coldstart")

    def test_unknown_algorithm_post_coldstart_raises(self):
        with pytest.raises(NotImplementedError):
            _overlay_filename("unknown_algo", "post_coldstart")  # type: ignore[arg-type]


def test_post_coldstart_unknown_algorithm_raises():
    """assemble_review_prompt raises NotImplementedError on trunk for post_coldstart."""
    with pytest.raises(NotImplementedError):
        assemble_review_prompt("unknown_algo", "post_coldstart")
