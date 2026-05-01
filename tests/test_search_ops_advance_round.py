"""Integration tests for advance_round_beam cold-start elite-floor behaviour.

Verifies that:
- After round 1 (new_round == 1), all scored candidates survive regardless of
  Pareto dominance (cold-start elite floor).
- After round 2, standard Pareto competition applies across protected parents
  and their children.
"""

from __future__ import annotations

from odysseus.agents.prompt_builder.search_ops import (
    advance_round_beam,
    get_search_state,
    init_search_state,
    record_eval_result,
    register_candidate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_and_score(
    run_id: str,
    prompt_version: str,
    quality_score: float,
    cost: float,
    tmp_path,
    parent_version: str | None = None,
) -> None:
    register_candidate(
        run_id,
        prompt_version,
        parent_version=parent_version,
        output_dir=tmp_path,
    )
    record_eval_result(
        run_id,
        prompt_version,
        quality_score=quality_score,
        cost=cost,
        output_dir=tmp_path,
    )


# ---------------------------------------------------------------------------
# Cold-start floor: post-round-1 elite retains all candidates
# ---------------------------------------------------------------------------


class TestAdvanceRoundColdStartFloor:
    def test_all_round1_candidates_survive_pareto_domination(self, tmp_path) -> None:
        """Post-round-1 elite must contain all 3 candidates even when one dominates."""
        run_id = "coldstart_test"
        init_search_state(
            backend="anthropic",
            run_id=run_id,
            output_dir=tmp_path,
        )

        # v1 strictly dominates v2 and v3 on both quality and cost.
        _register_and_score(run_id, "v1", quality_score=0.95, cost=0.05, tmp_path=tmp_path)
        _register_and_score(run_id, "v2", quality_score=0.70, cost=0.20, tmp_path=tmp_path)
        _register_and_score(run_id, "v3", quality_score=0.60, cost=0.30, tmp_path=tmp_path)

        summary = advance_round_beam(run_id, output_dir=tmp_path)
        state = get_search_state(run_id, output_dir=tmp_path)

        assert summary.round == 1
        elite_versions = {c.prompt_version for c in state.elite_set}
        assert elite_versions == {"v1", "v2", "v3"}, (
            f"All round-1 strategies must survive; got {elite_versions}"
        )

    def test_round1_elite_size_equals_beam_width(self, tmp_path) -> None:
        """Cold-start elite must retain all beam_width candidates."""
        run_id = "coldstart_size"
        init_search_state(
            backend="anthropic",
            run_id=run_id,
            output_dir=tmp_path,
        )

        _register_and_score(run_id, "v1", quality_score=0.90, cost=0.10, tmp_path=tmp_path)
        _register_and_score(run_id, "v2", quality_score=0.75, cost=0.25, tmp_path=tmp_path)
        _register_and_score(run_id, "v3", quality_score=0.60, cost=0.40, tmp_path=tmp_path)

        advance_round_beam(run_id, output_dir=tmp_path)
        state = get_search_state(run_id, output_dir=tmp_path)

        assert len(state.elite_set) == 3


# ---------------------------------------------------------------------------
# Round 2: normal Pareto resumes over protected parents + children
# ---------------------------------------------------------------------------


class TestAdvanceRoundNormalParetoResumesInRound2:
    def test_dominated_parent_evicted_in_round2_when_child_dominates(self, tmp_path) -> None:
        """By round 2, Pareto applies: a dominated round-1 strategy is evicted if its
        child also dominates it and no child is strictly non-dominated by v1."""
        run_id = "pareto_round2"
        init_search_state(
            backend="anthropic",
            run_id=run_id,
            output_dir=tmp_path,
        )

        # Round 1: three cold-start candidates — v1 dominates v2 and v3.
        _register_and_score(run_id, "v1", quality_score=0.95, cost=0.05, tmp_path=tmp_path)
        _register_and_score(run_id, "v2", quality_score=0.70, cost=0.20, tmp_path=tmp_path)
        _register_and_score(run_id, "v3", quality_score=0.60, cost=0.30, tmp_path=tmp_path)

        advance_round_beam(run_id, output_dir=tmp_path)  # round -> 1, cold-start elite = {v1, v2, v3}

        # Round 2: one child per protected parent.
        # v1c: improves on v1 (completely dominates v2, v3, and v2c, v3c).
        # v2c: slightly better than v2 but still dominated by v1c.
        # v3c: slightly better than v3 but still dominated by v1c.
        _register_and_score(run_id, "v1c", quality_score=0.96, cost=0.04, tmp_path=tmp_path, parent_version="v1")
        _register_and_score(run_id, "v2c", quality_score=0.71, cost=0.19, tmp_path=tmp_path, parent_version="v2")
        _register_and_score(run_id, "v3c", quality_score=0.61, cost=0.29, tmp_path=tmp_path, parent_version="v3")

        advance_round_beam(run_id, output_dir=tmp_path)  # round -> 2, normal Pareto
        state = get_search_state(run_id, output_dir=tmp_path)

        assert state.round == 2
        elite_versions = {c.prompt_version for c in state.elite_set}
        # v1c dominates everything else — only v1c should survive.
        assert "v1c" in elite_versions, "v1c must be on the front as the dominant candidate"
        assert "v2" not in elite_versions, "v2 is dominated by v1c and must be evicted"
        assert "v3" not in elite_versions, "v3 is dominated by v1c and must be evicted"
        assert "v2c" not in elite_versions, "v2c is dominated by v1c"
        assert "v3c" not in elite_versions, "v3c is dominated by v1c"

    def test_non_dominated_children_survive_in_round2(self, tmp_path) -> None:
        """Children that occupy genuinely distinct Pareto positions survive round 2."""
        run_id = "pareto_round2_diverse"
        init_search_state(
            backend="anthropic",
            run_id=run_id,
            output_dir=tmp_path,
        )

        # Round 1: v1 dominates v2 and v3 — all survive due to cold-start floor.
        _register_and_score(run_id, "v1", quality_score=0.95, cost=0.20, tmp_path=tmp_path)
        _register_and_score(run_id, "v2", quality_score=0.70, cost=0.20, tmp_path=tmp_path)
        _register_and_score(run_id, "v3", quality_score=0.60, cost=0.30, tmp_path=tmp_path)

        advance_round_beam(run_id, output_dir=tmp_path)

        # Round 2: each parent gets a child.
        # v1c: highest quality, moderate cost.
        # v2c: moderate quality, very low cost (genuinely non-dominated).
        # v3c: better than v3 but still dominated by v1c.
        _register_and_score(run_id, "v1c", quality_score=0.96, cost=0.20, tmp_path=tmp_path, parent_version="v1")
        _register_and_score(run_id, "v2c", quality_score=0.72, cost=0.05, tmp_path=tmp_path, parent_version="v2")
        _register_and_score(run_id, "v3c", quality_score=0.61, cost=0.29, tmp_path=tmp_path, parent_version="v3")

        advance_round_beam(run_id, output_dir=tmp_path)
        state = get_search_state(run_id, output_dir=tmp_path)

        elite_versions = {c.prompt_version for c in state.elite_set}
        # v1c (high quality) and v2c (low cost) are both non-dominated.
        assert "v1c" in elite_versions, "v1c is Pareto non-dominated"
        assert "v2c" in elite_versions, "v2c is Pareto non-dominated (cheapest)"
        # v3c is dominated by both — must be gone.
        assert "v3c" not in elite_versions, "v3c is dominated and must be pruned"

    def test_stagnation_count_zero_on_round1(self, tmp_path) -> None:
        """Stagnation count must be 0 after round 1 regardless of hypervolume change."""
        run_id = "stagnation_round1"
        init_search_state(
            backend="anthropic",
            run_id=run_id,
            output_dir=tmp_path,
        )

        _register_and_score(run_id, "v1", quality_score=0.90, cost=0.10, tmp_path=tmp_path)
        _register_and_score(run_id, "v2", quality_score=0.75, cost=0.25, tmp_path=tmp_path)
        _register_and_score(run_id, "v3", quality_score=0.60, cost=0.40, tmp_path=tmp_path)

        summary = advance_round_beam(run_id, output_dir=tmp_path)

        assert summary.stagnation_count == 0, (
            f"Stagnation must be 0 after round 1; got {summary.stagnation_count}"
        )
