"""Coercion of parent_version to "base" during beam cold-start (round 0).

The beam cold-start overlay (review_agent_cold_start_overlay_beam.md) mandates
``parent_version == briefing.initial_parent_version`` for every seed. The
Review LLM does not always comply, so ``register_candidate`` enforces it.
"""

from __future__ import annotations

from compass.agents.prompt_builder.search_ops import (
    _load_pending,
    advance_round_beam,
    init_search_state,
    record_eval_result,
    register_candidate,
)
from compass.agents.review.models import INITIAL_PARENT_VERSION


def _pending_by_version(run_id: str, tmp_path) -> dict[str, str | None]:
    return {c.prompt_version: c.parent_version for c in _load_pending(run_id, tmp_path)}


class TestColdStartParentCoercion:
    def test_coldstart_coerces_arbitrary_parent_to_base(self, tmp_path) -> None:
        run_id = "coldstart_parent"
        init_search_state(backend="anthropic", run_id=run_id, output_dir=tmp_path)

        # Review LLM emits a non-"base" parent on a cold-start seed.
        register_candidate(
            run_id,
            "v1",
            parent_version="some_other_version",
            output_dir=tmp_path,
        )
        # Also covers the missing/None case.
        register_candidate(
            run_id,
            "v2",
            parent_version=None,
            output_dir=tmp_path,
        )

        parents = _pending_by_version(run_id, tmp_path)
        assert parents["v1"] == INITIAL_PARENT_VERSION
        assert parents["v2"] == INITIAL_PARENT_VERSION

    def test_iterative_round_leaves_parent_untouched(self, tmp_path) -> None:
        run_id = "iterative_parent"
        init_search_state(backend="anthropic", run_id=run_id, output_dir=tmp_path)

        # Complete cold-start round so state.round advances to 1.
        for v, q, c in [("v1", 0.9, 0.1), ("v2", 0.7, 0.2), ("v3", 0.6, 0.3)]:
            register_candidate(run_id, v, parent_version=None, output_dir=tmp_path)
            record_eval_result(run_id, v, quality_score=q, cost=c, output_dir=tmp_path)
        advance_round_beam(run_id, output_dir=tmp_path)

        # Iterative-phase registration: parent_version must be preserved as-is.
        register_candidate(
            run_id,
            "v4",
            parent_version="v1",
            output_dir=tmp_path,
        )
        parents = _pending_by_version(run_id, tmp_path)
        assert parents["v4"] == "v1"
