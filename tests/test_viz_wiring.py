"""Smoke test: _try_write_viz is called and produces viz.html at state-mutation call sites.

This test requires init_search_state to work (i.e., _BRANCH_ALGORITHM must be set).
It lives on leaf branches (feat/generalize-{hill_climb,beam,emosa,sms_emoa}).
"""

from __future__ import annotations

# Tests removed — require a leaf branch with _BRANCH_ALGORITHM set to run.
# See feat/generalize-hill_climb for the canonical implementation.
