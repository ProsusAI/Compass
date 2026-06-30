# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Per-leaf invariant — guards against propagation merges overwriting leaf algo state."""

from compass.agents.prompt_builder.search_ops import _BRANCH_ALGORITHM
from compass.mcp.prompts import _overlay_filename


def test_branch_algorithm_is_beam():
    assert _BRANCH_ALGORITHM == "beam"


def test_overlay_map_resolves_beam():
    assert _overlay_filename("beam", "iterative").endswith("_beam")
    assert _overlay_filename("beam", "cold_start").endswith("_beam")
