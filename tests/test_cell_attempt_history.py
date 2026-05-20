"""Tests for confusion cell exhaustion tracking.

Covers:
- enrich_confusion_with_history (compass.agents.review.preprocessor)
- load_cell_attempt_history / save_cell_attempt_history (compass.agents.review.ops)
- update_cell_attempt_history (compass.agents.review.ops)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from compass.agents.review.models import BatchOutcome, ChildVariant, ConfusionImpact
from compass.agents.review.ops import (
    load_cell_attempt_history,
    save_cell_attempt_history,
    update_cell_attempt_history,
)
from compass.agents.review.preprocessor import (
    _filter_cell_attempt_history_for_impacts,
    enrich_confusion_with_history,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_confusion_impact(
    true_route: str = "route_a",
    predicted_route: str = "route_b",
    cost_impact: float = 0.5,
    quality_impact: float = -0.3,
) -> ConfusionImpact:
    return ConfusionImpact(
        true_route=true_route,
        predicted_route=predicted_route,
        count=10,
        support=50,
        misroute_rate=0.2,
        cost_impact=cost_impact,
        quality_impact=quality_impact,
        avg_cost_impact=0.05,
        avg_quality_impact=-0.03,
        persistence_rate=0.8,
        persistent_count=8,
        volatile_count=2,
    )


def _make_child_variant(
    variant_id: str = "cv-1-0",
    target_confusion_cell: str | None = "route_a/route_b",
) -> ChildVariant:
    return ChildVariant(
        variant_id=variant_id,
        hypothesis="test hypothesis",
        directives=[],
        target_confusion_cell=target_confusion_cell,
    )


def _make_batch_outcome(
    variant_id: str = "cv-1-0",
    quality_delta: float | None = 0.02,
    metric_deltas: dict[str, float] | None = None,
) -> BatchOutcome:
    if metric_deltas is None:
        metric_deltas = {"accuracy": 0.02, "cost_change_with_overhead": -0.01}
    return BatchOutcome(
        variant_id=variant_id,
        parent_version="v1",
        mutation_strategy="targeted",
        directive_ids=["d1"],
        candidate_version="v2",
        eval_status="scored",
        quality_delta_vs_parent=quality_delta,
        is_new_best=False,
        metric_deltas_vs_parent=metric_deltas,
    )


# ---------------------------------------------------------------------------
# enrich_confusion_with_history
# ---------------------------------------------------------------------------


def test_enrich_no_history_uses_raw_impact() -> None:
    """Cells with no history get effective_impact = abs(cost_impact) + abs(quality_impact)."""
    ci = _make_confusion_impact(cost_impact=0.5, quality_impact=-0.3)
    result = enrich_confusion_with_history([ci], {})

    assert len(result) == 1
    assert result[0].effective_impact == pytest.approx(0.8)
    assert result[0].attempt_count == 0
    assert result[0].failed_attempt_count == 0
    assert result[0].best_outcome is None


def test_enrich_one_failed_attempt_halves_impact() -> None:
    """One failed attempt applies a 0.5x decay to effective_impact."""
    ci = _make_confusion_impact(cost_impact=0.5, quality_impact=-0.3)
    history = {"route_a/route_b": [{"outcome": "no_effect"}]}
    result = enrich_confusion_with_history([ci], history)

    assert result[0].effective_impact == pytest.approx(0.8 * 0.5)
    assert result[0].failed_attempt_count == 1
    assert result[0].attempt_count == 1


def test_enrich_two_failed_attempts_quarter_impact() -> None:
    """Two failed attempts apply a 0.25x decay."""
    ci = _make_confusion_impact(cost_impact=0.5, quality_impact=-0.3)
    history = {"route_a/route_b": [{"outcome": "no_effect"}, {"outcome": "regressed"}]}
    result = enrich_confusion_with_history([ci], history)

    assert result[0].effective_impact == pytest.approx(0.8 * 0.25)
    assert result[0].failed_attempt_count == 2
    assert result[0].attempt_count == 2


def test_enrich_three_failed_attempts_eighth_impact() -> None:
    """Three failed attempts apply a 0.125x decay."""
    ci = _make_confusion_impact(cost_impact=0.5, quality_impact=-0.3)
    history = {
        "route_a/route_b": [
            {"outcome": "no_effect"},
            {"outcome": "no_effect"},
            {"outcome": "regressed"},
        ]
    }
    result = enrich_confusion_with_history([ci], history)

    assert result[0].effective_impact == pytest.approx(0.8 * 0.125)
    assert result[0].failed_attempt_count == 3
    assert result[0].attempt_count == 3


def test_enrich_reset_on_success_counts_only_trailing_failures() -> None:
    """History [no_effect, no_effect, improved, no_effect] → failed_attempt_count = 1."""
    ci = _make_confusion_impact(cost_impact=0.5, quality_impact=-0.3)
    history = {
        "route_a/route_b": [
            {"outcome": "no_effect"},
            {"outcome": "no_effect"},
            {"outcome": "improved"},
            {"outcome": "no_effect"},
        ]
    }
    result = enrich_confusion_with_history([ci], history)

    assert result[0].failed_attempt_count == 1
    assert result[0].attempt_count == 4
    assert result[0].effective_impact == pytest.approx(0.8 * 0.5)


def test_enrich_resorting_by_effective_impact() -> None:
    """A cell with raw_impact=1.0 and 2 failures ranks below a cell with raw_impact=0.5 and 0 failures."""
    high_raw = _make_confusion_impact(
        true_route="route_a",
        predicted_route="route_b",
        cost_impact=0.6,
        quality_impact=-0.4,  # raw = 1.0
    )
    low_raw = _make_confusion_impact(
        true_route="route_c",
        predicted_route="route_d",
        cost_impact=0.3,
        quality_impact=-0.2,  # raw = 0.5
    )
    history = {
        "route_a/route_b": [{"outcome": "no_effect"}, {"outcome": "no_effect"}],
    }
    result = enrich_confusion_with_history([high_raw, low_raw], history)

    # high_raw effective = 1.0 * 0.25 = 0.25, low_raw effective = 0.5 * 1.0 = 0.5
    assert result[0].true_route == "route_c"  # low_raw sorts first (higher effective impact)
    assert result[1].true_route == "route_a"  # high_raw sorts second
    assert result[0].effective_impact == pytest.approx(0.5)
    assert result[1].effective_impact == pytest.approx(0.25)


def test_enrich_best_outcome_improved_beats_no_effect() -> None:
    """best_outcome reflects the best outcome seen across all history entries."""
    ci = _make_confusion_impact()
    history = {
        "route_a/route_b": [
            {"outcome": "no_effect"},
            {"outcome": "improved"},
            {"outcome": "no_effect"},
        ]
    }
    result = enrich_confusion_with_history([ci], history)
    assert result[0].best_outcome == "improved"


def test_enrich_best_outcome_no_effect_beats_regressed() -> None:
    """best_outcome = 'no_effect' when no improvement has ever occurred but not all regressions."""
    ci = _make_confusion_impact()
    history = {
        "route_a/route_b": [
            {"outcome": "regressed"},
            {"outcome": "no_effect"},
        ]
    }
    result = enrich_confusion_with_history([ci], history)
    assert result[0].best_outcome == "no_effect"


def test_enrich_best_outcome_all_regressed() -> None:
    """best_outcome = 'regressed' when every attempt regressed."""
    ci = _make_confusion_impact()
    history = {"route_a/route_b": [{"outcome": "regressed"}, {"outcome": "regressed"}]}
    result = enrich_confusion_with_history([ci], history)
    assert result[0].best_outcome == "regressed"


def test_enrich_last_attempted_round_populated() -> None:
    """last_attempted_round is set to the max round across all entries (regression test for bug fix)."""
    ci = _make_confusion_impact()
    history = {
        "route_a/route_b": [
            {"round": 2, "outcome": "no_effect"},
            {"round": 5, "outcome": "regressed"},
            {"round": 3, "outcome": "no_effect"},
        ]
    }
    result = enrich_confusion_with_history([ci], history)
    assert result[0].last_attempted_round == 5


def test_enrich_last_attempted_round_none_when_no_round_field() -> None:
    """last_attempted_round is None when entries have no 'round' key (legacy data)."""
    ci = _make_confusion_impact()
    history = {
        "route_a/route_b": [
            {"outcome": "no_effect"},
        ]
    }
    result = enrich_confusion_with_history([ci], history)
    assert result[0].last_attempted_round is None


def test_filter_cell_attempt_history_for_impacts_keeps_only_active_cells() -> None:
    impacts = [
        _make_confusion_impact(true_route="route_a", predicted_route="route_b"),
    ]
    history = {
        "route_a/route_b": [{"outcome": "no_effect"}],
        "route_x/route_y": [{"outcome": "regressed"}],
    }

    filtered = _filter_cell_attempt_history_for_impacts(impacts, history)

    assert filtered == {"route_a/route_b": [{"outcome": "no_effect"}]}


# ---------------------------------------------------------------------------
# load_cell_attempt_history / save_cell_attempt_history
# ---------------------------------------------------------------------------


def test_cell_attempt_history_roundtrip(tmp_path: Path) -> None:
    """Save and load returns the same data."""
    (tmp_path / "test_run" / "search").mkdir(parents=True)
    history: dict[str, list[dict]] = {
        "route_a/route_b": [
            {"round": 1, "variant_id": "cv-1-0", "outcome": "no_effect"},
            {"round": 2, "variant_id": "cv-2-0", "outcome": "improved"},
        ],
        "route_c/route_d": [
            {"round": 1, "variant_id": "cv-1-1", "outcome": "regressed"},
        ],
    }

    save_cell_attempt_history("test_run", history, output_dir=tmp_path)
    loaded = load_cell_attempt_history("test_run", output_dir=tmp_path)

    assert loaded == history
    assert loaded["route_a/route_b"][0]["outcome"] == "no_effect"
    assert loaded["route_a/route_b"][1]["outcome"] == "improved"
    assert loaded["route_c/route_d"][0]["variant_id"] == "cv-1-1"


def test_load_cell_attempt_history_missing_file_returns_empty(tmp_path: Path) -> None:
    """Load returns an empty dict when the file doesn't exist."""
    result = load_cell_attempt_history("nonexistent_run", output_dir=tmp_path)
    assert result == {}


def test_save_cell_attempt_history_creates_directory_structure(tmp_path: Path) -> None:
    """Save creates the expected directory and file structure."""
    save_cell_attempt_history("new_run", {}, output_dir=tmp_path)
    expected = tmp_path / "new_run" / "search" / "cell_attempt_history.json"
    assert expected.exists()


# ---------------------------------------------------------------------------
# update_cell_attempt_history
# ---------------------------------------------------------------------------


def test_update_cell_attempt_history_round_field_present(tmp_path: Path) -> None:
    """Every persisted entry must contain a 'round' key (regression test for the bug fix)."""
    (tmp_path / "test_run" / "search").mkdir(parents=True)

    cv = _make_child_variant(variant_id="cv-1-0", target_confusion_cell="route_a/route_b")
    bo = _make_batch_outcome(variant_id="cv-1-0", quality_delta=0.02)
    ci = _make_confusion_impact(cost_impact=0.1, quality_impact=-0.5)

    update_cell_attempt_history(
        "test_run",
        batch_outcomes=[bo],
        child_variants=[cv],
        confusion_analysis=[ci],
        current_round=3,
        output_dir=tmp_path,
    )

    history = load_cell_attempt_history("test_run", output_dir=tmp_path)
    entry = history["route_a/route_b"][0]
    assert "round" in entry
    assert entry["round"] == 3


def test_update_cell_attempt_history_basic_update(tmp_path: Path) -> None:
    """A batch outcome with a matching cell-targeted variant appends to that cell's history."""
    (tmp_path / "test_run" / "search").mkdir(parents=True)

    cv = _make_child_variant(variant_id="cv-1-0", target_confusion_cell="route_a/route_b")
    bo = _make_batch_outcome(variant_id="cv-1-0", quality_delta=0.02)
    ci = _make_confusion_impact(cost_impact=0.1, quality_impact=-0.5)  # quality-dominated

    update_cell_attempt_history(
        "test_run",
        batch_outcomes=[bo],
        child_variants=[cv],
        confusion_analysis=[ci],
        current_round=1,
        output_dir=tmp_path,
    )

    history = load_cell_attempt_history("test_run", output_dir=tmp_path)
    assert "route_a/route_b" in history
    assert len(history["route_a/route_b"]) == 1
    assert history["route_a/route_b"][0]["variant_id"] == "cv-1-0"
    assert history["route_a/route_b"][0]["outcome"] == "improved"


def test_update_cell_attempt_history_no_matching_variants(tmp_path: Path) -> None:
    """When no child variants have target_confusion_cell, history is unchanged."""
    (tmp_path / "test_run" / "search").mkdir(parents=True)

    cv = _make_child_variant(variant_id="cv-1-0", target_confusion_cell=None)
    bo = _make_batch_outcome(variant_id="cv-1-0")
    ci = _make_confusion_impact()

    update_cell_attempt_history(
        "test_run",
        batch_outcomes=[bo],
        child_variants=[cv],
        confusion_analysis=[ci],
        current_round=1,
        output_dir=tmp_path,
    )

    history = load_cell_attempt_history("test_run", output_dir=tmp_path)
    assert history == {}


def test_update_cell_attempt_history_cost_dominated_improved(tmp_path: Path) -> None:
    """Cost-dominated cell with negative cost_change_with_overhead delta → 'improved'."""
    (tmp_path / "test_run" / "search").mkdir(parents=True)

    cv = _make_child_variant(variant_id="cv-1-0", target_confusion_cell="route_a/route_b")
    bo = _make_batch_outcome(
        variant_id="cv-1-0",
        quality_delta=None,
        metric_deltas={"cost_change_with_overhead": -0.05},  # clearly improved (cheaper)
    )
    # cost_impact dominates: abs(1.0) > abs(0.1)
    ci = _make_confusion_impact(cost_impact=1.0, quality_impact=0.1)

    update_cell_attempt_history(
        "test_run",
        batch_outcomes=[bo],
        child_variants=[cv],
        confusion_analysis=[ci],
        current_round=2,
        output_dir=tmp_path,
    )

    history = load_cell_attempt_history("test_run", output_dir=tmp_path)
    assert history["route_a/route_b"][0]["outcome"] == "improved"
    assert history["route_a/route_b"][0]["round"] == 2


def test_update_cell_attempt_history_quality_dominated_no_effect(tmp_path: Path) -> None:
    """Quality-dominated cell with near-zero quality_delta → 'no_effect'."""
    (tmp_path / "test_run" / "search").mkdir(parents=True)

    cv = _make_child_variant(variant_id="cv-1-0", target_confusion_cell="route_a/route_b")
    bo = _make_batch_outcome(
        variant_id="cv-1-0",
        quality_delta=0.001,  # below 0.005 threshold → no_effect
        metric_deltas={"cost_change_with_overhead": 0.0},
    )
    # quality_impact dominates: abs(-0.8) > abs(0.1)
    ci = _make_confusion_impact(cost_impact=0.1, quality_impact=-0.8)

    update_cell_attempt_history(
        "test_run",
        batch_outcomes=[bo],
        child_variants=[cv],
        confusion_analysis=[ci],
        current_round=1,
        output_dir=tmp_path,
    )

    history = load_cell_attempt_history("test_run", output_dir=tmp_path)
    assert history["route_a/route_b"][0]["outcome"] == "no_effect"


def test_update_cell_attempt_history_cost_dominated_regressed(tmp_path: Path) -> None:
    """Cost-dominated cell with positive cost_change_with_overhead delta → 'regressed'."""
    (tmp_path / "test_run" / "search").mkdir(parents=True)

    cv = _make_child_variant(variant_id="cv-1-0", target_confusion_cell="route_a/route_b")
    bo = _make_batch_outcome(
        variant_id="cv-1-0",
        quality_delta=None,
        metric_deltas={"cost_change_with_overhead": 0.1},  # more expensive = regressed
    )
    ci = _make_confusion_impact(cost_impact=1.0, quality_impact=0.1)

    update_cell_attempt_history(
        "test_run",
        batch_outcomes=[bo],
        child_variants=[cv],
        confusion_analysis=[ci],
        current_round=1,
        output_dir=tmp_path,
    )

    history = load_cell_attempt_history("test_run", output_dir=tmp_path)
    assert history["route_a/route_b"][0]["outcome"] == "regressed"


def test_update_cell_attempt_history_quality_dominated_regressed(tmp_path: Path) -> None:
    """Quality-dominated cell with sufficiently negative quality_delta → 'regressed'."""
    (tmp_path / "test_run" / "search").mkdir(parents=True)

    cv = _make_child_variant(variant_id="cv-1-0", target_confusion_cell="route_a/route_b")
    bo = _make_batch_outcome(
        variant_id="cv-1-0",
        quality_delta=-0.02,  # below -0.005 threshold → regressed
        metric_deltas={"cost_change_with_overhead": 0.0},
    )
    ci = _make_confusion_impact(cost_impact=0.1, quality_impact=-0.8)

    update_cell_attempt_history(
        "test_run",
        batch_outcomes=[bo],
        child_variants=[cv],
        confusion_analysis=[ci],
        current_round=4,
        output_dir=tmp_path,
    )

    history = load_cell_attempt_history("test_run", output_dir=tmp_path)
    assert history["route_a/route_b"][0]["outcome"] == "regressed"
    assert history["route_a/route_b"][0]["round"] == 4


def test_update_cell_attempt_history_accumulates_across_calls(tmp_path: Path) -> None:
    """Multiple calls to update_cell_attempt_history accumulate entries."""
    (tmp_path / "test_run" / "search").mkdir(parents=True)

    cv = _make_child_variant(variant_id="cv-1-0", target_confusion_cell="route_a/route_b")
    ci = _make_confusion_impact(cost_impact=0.1, quality_impact=-0.8)

    bo1 = _make_batch_outcome(variant_id="cv-1-0", quality_delta=0.001)  # no_effect
    update_cell_attempt_history(
        "test_run",
        batch_outcomes=[bo1],
        child_variants=[cv],
        confusion_analysis=[ci],
        current_round=1,
        output_dir=tmp_path,
    )

    bo2 = _make_batch_outcome(variant_id="cv-1-0", quality_delta=0.02)  # improved
    update_cell_attempt_history(
        "test_run",
        batch_outcomes=[bo2],
        child_variants=[cv],
        confusion_analysis=[ci],
        current_round=2,
        output_dir=tmp_path,
    )

    history = load_cell_attempt_history("test_run", output_dir=tmp_path)
    assert len(history["route_a/route_b"]) == 2
    assert history["route_a/route_b"][0]["outcome"] == "no_effect"
    assert history["route_a/route_b"][0]["round"] == 1
    assert history["route_a/route_b"][1]["outcome"] == "improved"
    assert history["route_a/route_b"][1]["round"] == 2


def test_update_cell_attempt_history_cost_dominated_at_threshold_boundary(tmp_path: Path) -> None:
    """Cost-dominated: exactly at 0.005 boundary is 'no_effect' (not improved, not regressed)."""
    (tmp_path / "test_run" / "search").mkdir(parents=True)

    cv = _make_child_variant(variant_id="cv-1-0", target_confusion_cell="route_a/route_b")
    bo = _make_batch_outcome(
        variant_id="cv-1-0",
        quality_delta=None,
        metric_deltas={"cost_change_with_overhead": -0.005},  # at boundary, not < -0.005
    )
    ci = _make_confusion_impact(cost_impact=1.0, quality_impact=0.1)

    update_cell_attempt_history(
        "test_run",
        batch_outcomes=[bo],
        child_variants=[cv],
        confusion_analysis=[ci],
        current_round=1,
        output_dir=tmp_path,
    )

    history = load_cell_attempt_history("test_run", output_dir=tmp_path)
    assert history["route_a/route_b"][0]["outcome"] == "no_effect"


def test_update_cell_attempt_history_quality_dominated_at_threshold_boundary(tmp_path: Path) -> None:
    """Quality-dominated: exactly at 0.005 boundary is 'no_effect' (not improved)."""
    (tmp_path / "test_run" / "search").mkdir(parents=True)

    cv = _make_child_variant(variant_id="cv-1-0", target_confusion_cell="route_a/route_b")
    bo = _make_batch_outcome(
        variant_id="cv-1-0",
        quality_delta=0.005,  # at boundary, not > 0.005
        metric_deltas={"cost_change_with_overhead": 0.0},
    )
    ci = _make_confusion_impact(cost_impact=0.1, quality_impact=-0.8)

    update_cell_attempt_history(
        "test_run",
        batch_outcomes=[bo],
        child_variants=[cv],
        confusion_analysis=[ci],
        current_round=1,
        output_dir=tmp_path,
    )

    history = load_cell_attempt_history("test_run", output_dir=tmp_path)
    assert history["route_a/route_b"][0]["outcome"] == "no_effect"
