# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Tests for compass.agents.prompt_builder_search_ops.

Most tests in this file require a concrete _BRANCH_ALGORITHM set on the
running branch (i.e., a leaf branch like feat/generalize-hill_climb).
Only the algorithm-agnostic infrastructure tests are kept here on the
pipeline trunk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from compass.agents.prompt_builder.search_ops import (
    get_search_state,
    set_loop_phase,
)


class TestGetSearchState:
    def test_raises_for_missing_state(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            get_search_state("nonexistent", output_dir=tmp_path)


class TestSetLoopPhase:
    def test_raises_if_no_state(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            set_loop_phase("no_such_run", "build", output_dir=tmp_path)
