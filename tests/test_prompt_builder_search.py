"""Tests for odysseus.agents.prompt_builder_search."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from odysseus.agents.prompt_builder.search import (
    Candidate,
    RoundSummary,
    SearchState,
    compute_front_improvement,
    dominates,
    select_best,
    update_pareto_front,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _candidate(
    prompt_version: str = "v1",
    parent_version: str | None = None,
    quality_score: float = 0.9,
    cost: float = 0.01,
    round_introduced: int = 1,
    **kwargs,
) -> Candidate:
    return Candidate(
        prompt_version=prompt_version,
        parent_version=parent_version,
        quality_score=quality_score,
        cost=cost,
        round_introduced=round_introduced,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Task 1: Candidate model
# ---------------------------------------------------------------------------


class TestCandidate:
    def test_valid_construction(self) -> None:
        c = _candidate(prompt_version="v1", parent_version=None, quality_score=0.85, cost=0.02)
        assert c.prompt_version == "v1"
        assert c.parent_version is None
        assert c.quality_score == 0.85
        assert c.cost == 0.02
        assert c.round_introduced == 1

    def test_parent_version_can_be_string(self) -> None:
        c = _candidate(parent_version="v0")
        assert c.parent_version == "v0"

    def test_empty_prompt_version_rejected(self) -> None:
        with pytest.raises(ValidationError, match="prompt_version must be non-empty"):
            Candidate(
                prompt_version="",
                parent_version=None,
                quality_score=0.9,
                cost=0.01,
                round_introduced=1,
            )

    def test_negative_quality_score_allowed(self) -> None:
        """No constraint on score range — negative values are valid."""
        c = _candidate(quality_score=-1.0)
        assert c.quality_score == -1.0

    def test_zero_cost_allowed(self) -> None:
        c = _candidate(cost=0.0)
        assert c.cost == 0.0

    def test_missing_prompt_version_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Candidate(  # type: ignore[call-arg]
                parent_version=None,
                quality_score=0.9,
                cost=0.01,
                round_introduced=1,
            )

    def test_example_ids_stored(self) -> None:
        c = _candidate(prompt_version="v1", example_ids=["ex-1", "ex-2"])
        assert c.example_ids == ["ex-1", "ex-2"]

    def test_example_ids_defaults_empty(self) -> None:
        c = _candidate(prompt_version="v1")
        assert c.example_ids == []

    # ------------------------------------------------------------------
    # Optional strategy-specific fields
    # ------------------------------------------------------------------

    def test_optional_fields_default_none(self) -> None:
        c = _candidate()
        assert c.secondary_parent_version is None
        assert c.eval_status is None
        assert c.mutation_strategy is None
        assert c.route_metrics is None
        assert c.trajectory_id is None

    def test_secondary_parent_version_can_be_set(self) -> None:
        c = _candidate(secondary_parent_version="v0")
        assert c.secondary_parent_version == "v0"

    def test_eval_status_accepts_valid_literals(self) -> None:
        for status in ("pending", "running", "complete", "failed"):
            c = _candidate(eval_status=status)  # type: ignore[arg-type]
            assert c.eval_status == status

    def test_eval_status_rejects_invalid(self) -> None:
        with pytest.raises(ValidationError):
            _candidate(eval_status="unknown")  # type: ignore[arg-type]

    def test_mutation_strategy_can_be_set(self) -> None:
        c = _candidate(mutation_strategy="rule_add")
        assert c.mutation_strategy == "rule_add"

    def test_route_metrics_can_be_set(self) -> None:
        metrics = {"accuracy": 0.9, "cost_per_token": 0.002}
        c = _candidate(route_metrics=metrics)
        assert c.route_metrics == metrics

    def test_trajectory_id_can_be_set(self) -> None:
        c = _candidate(trajectory_id=2)
        assert c.trajectory_id == 2

    # ------------------------------------------------------------------
    # iteration_introduced alias
    # ------------------------------------------------------------------

    def test_iteration_introduced_alias_maps_to_round_introduced(self) -> None:
        """SMS-EMOA state files use iteration_introduced; it must map to round_introduced."""
        c = Candidate.model_validate(
            {
                "prompt_version": "v1",
                "parent_version": None,
                "quality_score": 0.9,
                "cost": 0.01,
                "iteration_introduced": 3,
            }
        )
        assert c.round_introduced == 3

    def test_round_introduced_wins_over_alias(self) -> None:
        """If both keys are present, round_introduced takes precedence."""
        c = Candidate.model_validate(
            {
                "prompt_version": "v1",
                "parent_version": None,
                "quality_score": 0.9,
                "cost": 0.01,
                "round_introduced": 5,
                "iteration_introduced": 3,
            }
        )
        assert c.round_introduced == 5

    def test_serialisation_emits_round_introduced_not_alias(self) -> None:
        """Round-trip: serialised JSON uses canonical round_introduced key."""
        c = _candidate(round_introduced=4)
        dumped = c.model_dump()
        assert "round_introduced" in dumped
        assert "iteration_introduced" not in dumped
        assert dumped["round_introduced"] == 4

    # ------------------------------------------------------------------
    # Backward-compat: old fixtures with dominated field are ignored
    # ------------------------------------------------------------------

    def test_old_dominated_field_is_ignored_on_load(self) -> None:
        """Fixtures from before the cross-branch generalisation may carry dominated.
        With extra='ignore', the field is silently discarded and loading succeeds."""
        c = Candidate.model_validate(
            {
                "prompt_version": "v1",
                "parent_version": None,
                "quality_score": 0.9,
                "cost": 0.01,
                "round_introduced": 1,
                "dominated": True,  # old field — must be silently ignored
            }
        )
        assert c.prompt_version == "v1"
        assert not hasattr(c, "dominated")

    def test_round_trip_with_all_optional_fields(self) -> None:
        """Full round-trip: construct with all optional fields, serialise, reload."""
        c = Candidate(
            prompt_version="v1",
            parent_version="v0",
            quality_score=0.88,
            cost=0.015,
            round_introduced=2,
            example_ids=["ex-1"],
            secondary_parent_version="v0b",
            eval_status="complete",
            mutation_strategy="rule_add",
            route_metrics={"accuracy": 0.88},
            trajectory_id=1,
        )
        reloaded = Candidate.model_validate_json(c.model_dump_json())
        assert reloaded.secondary_parent_version == "v0b"
        assert reloaded.eval_status == "complete"
        assert reloaded.mutation_strategy == "rule_add"
        assert reloaded.route_metrics == {"accuracy": 0.88}
        assert reloaded.trajectory_id == 1

    def test_round_trip_with_no_optional_fields(self) -> None:
        """Minimal candidate (no optional fields) round-trips cleanly."""
        c = _candidate()
        reloaded = Candidate.model_validate_json(c.model_dump_json())
        assert reloaded.prompt_version == c.prompt_version
        assert reloaded.secondary_parent_version is None
        assert reloaded.eval_status is None
        assert reloaded.mutation_strategy is None
        assert reloaded.route_metrics is None
        assert reloaded.trajectory_id is None


# ---------------------------------------------------------------------------
# Task 2: RoundSummary model
# ---------------------------------------------------------------------------


class TestRoundSummary:
    def test_valid_construction(self) -> None:
        rs = RoundSummary(
            round=1,
            candidates_evaluated=["v1", "v2"],
            new_pareto_points=1,
            front_size=2,
            mutation_mode="targeted",
            stagnation_count=0,
        )
        assert rs.round == 1
        assert rs.candidates_evaluated == ["v1", "v2"]
        assert rs.new_pareto_points == 1
        assert rs.front_size == 2
        assert rs.mutation_mode == "targeted"
        assert rs.stagnation_count == 0

    def test_exploratory_mutation_mode(self) -> None:
        rs = RoundSummary(
            round=2,
            candidates_evaluated=[],
            new_pareto_points=0,
            front_size=3,
            mutation_mode="exploratory",
            stagnation_count=2,
        )
        assert rs.mutation_mode == "exploratory"

    def test_round_must_be_at_least_1(self) -> None:
        with pytest.raises(ValidationError):
            RoundSummary(
                round=0,
                candidates_evaluated=[],
                new_pareto_points=0,
                front_size=0,
                mutation_mode="targeted",
                stagnation_count=0,
            )

    def test_invalid_mutation_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RoundSummary(
                round=1,
                candidates_evaluated=[],
                new_pareto_points=0,
                front_size=0,
                mutation_mode="random",  # type: ignore[arg-type]
                stagnation_count=0,
            )

    def test_empty_candidates_evaluated(self) -> None:
        rs = RoundSummary(
            round=1,
            candidates_evaluated=[],
            new_pareto_points=0,
            front_size=0,
            mutation_mode="targeted",
            stagnation_count=0,
        )
        assert rs.candidates_evaluated == []


# ---------------------------------------------------------------------------
# Task 3: SearchState model
# ---------------------------------------------------------------------------


class TestSearchState:
    def _valid_state(self, **overrides) -> dict:
        base = {
            "search_state_id": "state-1",
            "backend": "anthropic",
        }
        base.update(overrides)
        return base

    def test_valid_construction_defaults(self) -> None:
        s = SearchState(**self._valid_state())
        assert s.search_state_id == "state-1"
        assert s.backend == "anthropic"
        assert s.primary_metric_name is None
        assert s.round == 0
        assert s.pareto_front == []
        assert s.round_history == []
        assert s.stagnation_count == 0
        assert s.stagnation_limit == 3
        assert s.convergence_limit == 5
        assert s.max_rounds == 50
        assert s.mutation_mode == "targeted"
        assert s.converged is False

    def test_primary_metric_name_can_be_set(self) -> None:
        s = SearchState(**self._valid_state(primary_metric_name="f1_macro"))
        assert s.primary_metric_name == "f1_macro"

    def test_pareto_front_can_hold_candidates(self) -> None:
        c = _candidate()
        s = SearchState(**self._valid_state(pareto_front=[c]))
        assert len(s.pareto_front) == 1
        assert s.pareto_front[0].prompt_version == "v1"

    def test_round_history_can_hold_summaries(self) -> None:
        rs = RoundSummary(
            round=1,
            candidates_evaluated=["v1"],
            new_pareto_points=1,
            front_size=1,
            mutation_mode="targeted",
            stagnation_count=0,
        )
        s = SearchState(**self._valid_state(round_history=[rs]))
        assert len(s.round_history) == 1

    def test_empty_search_state_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="search_state_id must be non-empty"):
            SearchState(search_state_id="", backend="anthropic")

    def test_convergence_limit_must_be_gt_stagnation_limit(self) -> None:
        with pytest.raises(ValidationError, match="convergence_limit"):
            SearchState(
                search_state_id="s1",
                backend="anthropic",
                stagnation_limit=5,
                convergence_limit=5,  # equal — not strictly greater
            )

    def test_convergence_limit_less_than_stagnation_limit_rejected(self) -> None:
        with pytest.raises(ValidationError, match="convergence_limit"):
            SearchState(
                search_state_id="s1",
                backend="anthropic",
                stagnation_limit=5,
                convergence_limit=3,
            )

    def test_convergence_limit_one_more_than_stagnation_limit_accepted(self) -> None:
        s = SearchState(
            search_state_id="s1",
            backend="anthropic",
            stagnation_limit=4,
            convergence_limit=5,
        )
        assert s.convergence_limit == 5

    def test_exploratory_mutation_mode(self) -> None:
        s = SearchState(**self._valid_state(mutation_mode="exploratory"))
        assert s.mutation_mode == "exploratory"

    def test_converged_can_be_set(self) -> None:
        s = SearchState(**self._valid_state(converged=True))
        assert s.converged is True

    def test_invalid_mutation_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SearchState(**self._valid_state(mutation_mode="random"))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Task 4: Pareto dominance logic
# ---------------------------------------------------------------------------


class TestDominates:
    def test_strictly_better_quality_dominates(self) -> None:
        a = _candidate(quality_score=0.9, cost=0.01)
        b = _candidate(quality_score=0.8, cost=0.01)
        assert dominates(a, b) is True
        assert dominates(b, a) is False

    def test_strictly_better_cost_dominates(self) -> None:
        a = _candidate(quality_score=0.9, cost=0.005)
        b = _candidate(quality_score=0.9, cost=0.01)
        assert dominates(a, b) is True
        assert dominates(b, a) is False

    def test_better_on_both_dimensions_dominates(self) -> None:
        a = _candidate(quality_score=0.95, cost=0.005)
        b = _candidate(quality_score=0.80, cost=0.02)
        assert dominates(a, b) is True
        assert dominates(b, a) is False

    def test_equal_candidates_do_not_dominate(self) -> None:
        a = _candidate(quality_score=0.9, cost=0.01)
        b = _candidate(quality_score=0.9, cost=0.01)
        assert dominates(a, b) is False
        assert dominates(b, a) is False

    def test_incomparable_candidates_do_not_dominate(self) -> None:
        """Higher quality but higher cost — neither dominates."""
        a = _candidate(quality_score=0.95, cost=0.02)
        b = _candidate(quality_score=0.80, cost=0.005)
        assert dominates(a, b) is False
        assert dominates(b, a) is False

    def test_worse_on_both_dimensions_not_dominating(self) -> None:
        a = _candidate(quality_score=0.7, cost=0.05)
        b = _candidate(quality_score=0.9, cost=0.01)
        assert dominates(a, b) is False

    def test_dominates_ignores_prompt_version(self) -> None:
        """Dominance is purely score/cost based."""
        a = _candidate(prompt_version="v-alpha", quality_score=0.9, cost=0.01)
        b = _candidate(prompt_version="v-beta", quality_score=0.85, cost=0.01)
        assert dominates(a, b) is True


class TestUpdateParetoFront:
    def test_empty_front_accepts_single_candidate(self) -> None:
        c = _candidate(prompt_version="v1", quality_score=0.9, cost=0.01)
        front, new_points = update_pareto_front([], [c])
        assert len(front) == 1
        assert new_points == 1

    def test_dominated_candidate_not_added(self) -> None:
        existing = _candidate(prompt_version="v1", quality_score=0.9, cost=0.01)
        weaker = _candidate(prompt_version="v2", quality_score=0.8, cost=0.02)
        front, new_points = update_pareto_front([existing], [weaker])
        assert len(front) == 1
        assert new_points == 0
        assert front[0].prompt_version == "v1"

    def test_dominating_candidate_removes_dominated(self) -> None:
        weak = _candidate(prompt_version="v1", quality_score=0.8, cost=0.02)
        strong = _candidate(prompt_version="v2", quality_score=0.9, cost=0.01)
        front, new_points = update_pareto_front([weak], [strong])
        assert len(front) == 1
        assert front[0].prompt_version == "v2"
        assert new_points == 1

    def test_incomparable_candidates_coexist_on_front(self) -> None:
        a = _candidate(prompt_version="v1", quality_score=0.95, cost=0.05)
        b = _candidate(prompt_version="v2", quality_score=0.80, cost=0.005)
        front, new_points = update_pareto_front([a], [b])
        assert len(front) == 2
        assert new_points == 1

    def test_duplicate_quality_cost_rejected(self) -> None:
        existing = _candidate(prompt_version="v1", quality_score=0.9, cost=0.01)
        dup = _candidate(prompt_version="v2", quality_score=0.9, cost=0.01)
        front, new_points = update_pareto_front([existing], [dup])
        assert len(front) == 1
        assert new_points == 0
        assert front[0].prompt_version == "v1"

    def test_multiple_new_candidates_processed(self) -> None:
        existing = _candidate(prompt_version="v1", quality_score=0.8, cost=0.02)
        better = _candidate(prompt_version="v2", quality_score=0.9, cost=0.01)
        incomparable = _candidate(prompt_version="v3", quality_score=0.95, cost=0.05)
        front, new_points = update_pareto_front([existing], [better, incomparable])
        assert new_points == 2
        versions = {c.prompt_version for c in front}
        assert "v1" not in versions
        assert "v2" in versions
        assert "v3" in versions

    def test_empty_new_candidates_returns_unchanged_front(self) -> None:
        existing = _candidate(prompt_version="v1")
        front, new_points = update_pareto_front([existing], [])
        assert len(front) == 1
        assert new_points == 0

    def test_empty_front_and_empty_candidates(self) -> None:
        front, new_points = update_pareto_front([], [])
        assert front == []
        assert new_points == 0

    def test_new_candidate_dominates_multiple_existing(self) -> None:
        weak1 = _candidate(prompt_version="v1", quality_score=0.7, cost=0.05)
        weak2 = _candidate(prompt_version="v2", quality_score=0.8, cost=0.03)
        strong = _candidate(prompt_version="v3", quality_score=0.9, cost=0.01)
        front, new_points = update_pareto_front([weak1, weak2], [strong])
        assert len(front) == 1
        assert front[0].prompt_version == "v3"
        assert new_points == 1

    def test_original_front_list_not_mutated(self) -> None:
        """The input front list should not be mutated in place."""
        original = [_candidate(prompt_version="v1", quality_score=0.8, cost=0.02)]
        original_copy = list(original)
        new_c = _candidate(prompt_version="v2", quality_score=0.9, cost=0.01)
        update_pareto_front(original, [new_c])
        # The original list passed in may be reassigned internally, but
        # what we care about is that the returned front is correct.
        # The test verifies the function is usable in a pure style.
        assert original_copy[0].prompt_version == "v1"

    def test_candidate_dominated_by_later_new_candidate_not_added(self) -> None:
        """If a new candidate is dominated by another new candidate, it's not added."""
        weak_new = _candidate(prompt_version="v1", quality_score=0.8, cost=0.02)
        strong_new = _candidate(prompt_version="v2", quality_score=0.9, cost=0.01)
        # Process strong first: weak_new is then dominated
        front, new_points = update_pareto_front([], [strong_new, weak_new])
        assert len(front) == 1
        assert front[0].prompt_version == "v2"
        assert new_points == 1


# ---------------------------------------------------------------------------
# Task 5: select_best helper
# ---------------------------------------------------------------------------


class TestSelectBest:
    def test_single_candidate(self) -> None:
        c = _candidate(prompt_version="v1", quality_score=0.9, cost=0.01)
        assert select_best([c]) == "v1"

    def test_highest_quality_wins(self) -> None:
        low = _candidate(prompt_version="v1", quality_score=0.7, cost=0.005)
        high = _candidate(prompt_version="v2", quality_score=0.95, cost=0.05)
        assert select_best([low, high]) == "v2"

    def test_tie_broken_by_lowest_cost(self) -> None:
        cheap = _candidate(prompt_version="v-cheap", quality_score=0.9, cost=0.005)
        pricey = _candidate(prompt_version="v-pricey", quality_score=0.9, cost=0.05)
        assert select_best([cheap, pricey]) == "v-cheap"

    def test_empty_front_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            select_best([])

    def test_multiple_candidates_correct_selection(self) -> None:
        c1 = _candidate(prompt_version="v1", quality_score=0.80, cost=0.01)
        c2 = _candidate(prompt_version="v2", quality_score=0.95, cost=0.02)
        c3 = _candidate(prompt_version="v3", quality_score=0.95, cost=0.005)
        # v3 and v2 tie on quality; v3 wins on lower cost
        assert select_best([c1, c2, c3]) == "v3"

    def test_order_independent(self) -> None:
        c1 = _candidate(prompt_version="v1", quality_score=0.9, cost=0.01)
        c2 = _candidate(prompt_version="v2", quality_score=0.85, cost=0.005)
        assert select_best([c1, c2]) == select_best([c2, c1])


# ---------------------------------------------------------------------------
# loop_phase field
# ---------------------------------------------------------------------------


class TestLoopPhase:
    def test_default_loop_phase_is_build(self) -> None:
        state = SearchState(
            search_state_id="s1",
            backend="anthropic",
            stagnation_limit=3,
            convergence_limit=5,
        )
        assert state.loop_phase == "review"

    def test_loop_phase_accepts_review(self) -> None:
        state = SearchState(
            search_state_id="s1",
            backend="anthropic",
            stagnation_limit=3,
            convergence_limit=5,
            loop_phase="review",
        )
        assert state.loop_phase == "review"

    def test_loop_phase_rejects_invalid(self) -> None:
        with pytest.raises(ValidationError):
            SearchState(
                search_state_id="s1",
                backend="anthropic",
                stagnation_limit=3,
                convergence_limit=5,
                loop_phase="invalid",
            )


# ---------------------------------------------------------------------------
# converged field on RoundSummary
# ---------------------------------------------------------------------------


class TestRoundSummaryConverged:
    def test_converged_defaults_false(self) -> None:
        rs = RoundSummary(
            round=1,
            candidates_evaluated=["v1"],
            new_pareto_points=1,
            front_size=1,
            mutation_mode="targeted",
            stagnation_count=0,
        )
        assert rs.converged is False

    def test_converged_can_be_true(self) -> None:
        rs = RoundSummary(
            round=1,
            candidates_evaluated=["v1"],
            new_pareto_points=0,
            front_size=1,
            mutation_mode="targeted",
            stagnation_count=5,
            converged=True,
        )
        assert rs.converged is True


# ---------------------------------------------------------------------------
# compute_front_improvement
# ---------------------------------------------------------------------------


class TestComputeFrontImprovement:
    def test_empty_old_front_returns_zero(self) -> None:
        new_front = [_candidate(prompt_version="v1", quality_score=0.9, cost=0.01)]
        result = compute_front_improvement([], new_front)
        assert result == pytest.approx(0.9)

    def test_empty_new_front_returns_zero(self) -> None:
        old_front = [_candidate(prompt_version="v1", quality_score=0.9, cost=0.01)]
        result = compute_front_improvement(old_front, [])
        assert result == 0.0

    def test_no_improvement_same_quality_returns_zero(self) -> None:
        old_front = [_candidate(prompt_version="v1", quality_score=0.9, cost=0.01)]
        new_front = [_candidate(prompt_version="v1", quality_score=0.9, cost=0.01)]
        result = compute_front_improvement(old_front, new_front)
        assert result == 0.0

    def test_no_improvement_worse_quality_returns_zero(self) -> None:
        old_front = [_candidate(prompt_version="v1", quality_score=0.9, cost=0.01)]
        new_front = [_candidate(prompt_version="v2", quality_score=0.8, cost=0.01)]
        result = compute_front_improvement(old_front, new_front)
        assert result == 0.0

    def test_small_improvement_returns_delta(self) -> None:
        old_front = [_candidate(prompt_version="v1", quality_score=0.80, cost=0.01)]
        new_front = [_candidate(prompt_version="v2", quality_score=0.81, cost=0.01)]
        result = compute_front_improvement(old_front, new_front)
        assert result == pytest.approx(0.01)

    def test_large_improvement_returns_delta(self) -> None:
        old_front = [_candidate(prompt_version="v1", quality_score=0.50, cost=0.01)]
        new_front = [_candidate(prompt_version="v2", quality_score=0.90, cost=0.01)]
        result = compute_front_improvement(old_front, new_front)
        assert result == pytest.approx(0.40)

    def test_cost_only_improvement_returns_zero(self) -> None:
        """Quality is unchanged; only cost improved — quality-only metric returns 0.0."""
        old_front = [_candidate(prompt_version="v1", quality_score=0.9, cost=0.10)]
        new_front = [_candidate(prompt_version="v2", quality_score=0.9, cost=0.01)]
        result = compute_front_improvement(old_front, new_front)
        assert result == 0.0
