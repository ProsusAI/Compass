"""Tests for EMOSA per-trajectory fanout helpers in odysseus.agents.review.ops."""

from __future__ import annotations

import json
from pathlib import Path

from odysseus.agents.review.models import ChildVariant, EditDirective
from odysseus.agents.review.ops import (
    FanoutStatus,
    clear_dispatched_trajectories,
    clear_trajectory_child_variants,
    load_all_trajectory_child_variants,
    load_dispatched_trajectories,
    record_trajectory_dispatched,
    save_trajectory_child_variants,
    trajectory_fanout_missing,
)

_RUN_ID = "fanout_test_run"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_edit_directive(directive_id: str) -> EditDirective:
    return EditDirective(
        directive_id=directive_id,
        target_version="v1",
        block_type="rule",
        block_identifier="Rule 1",
        granularity="micro",
        directive="Tighten wording",
        priority="medium",
    )


def _make_child_variant(variant_id: str) -> ChildVariant:
    return ChildVariant(
        variant_id=variant_id,
        hypothesis="Test hypothesis",
        directives=[_make_edit_directive("d1")],
    )


def _write_search_state(tmp_path: Path, run_id: str, algorithm_state: dict | None = None, round: int = 1) -> None:
    """Write a minimal search_state.json for testing."""
    search_dir = tmp_path / run_id / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id,
        "round": round,
        "algorithm": "emosa",
        "algorithm_state": algorithm_state or {},
    }
    (search_dir / "search_state.json").write_text(json.dumps(state), encoding="utf-8")


# ---------------------------------------------------------------------------
# trajectory_fanout_missing
# ---------------------------------------------------------------------------


class TestTrajectoryFanoutMissing:
    def test_returns_none_when_no_search_state(self, tmp_path: Path) -> None:
        result = trajectory_fanout_missing(_RUN_ID, output_dir=tmp_path)
        assert result is None

    def test_returns_none_when_no_num_trajectories(self, tmp_path: Path) -> None:
        # search_state.json exists but algorithm_state has no num_trajectories
        _write_search_state(tmp_path, _RUN_ID, algorithm_state={"phase": "search"})
        result = trajectory_fanout_missing(_RUN_ID, output_dir=tmp_path)
        assert result is None

    def test_all_not_dispatched_when_no_slots_written(self, tmp_path: Path) -> None:
        _write_search_state(tmp_path, _RUN_ID, algorithm_state={"num_trajectories": 3})
        result = trajectory_fanout_missing(_RUN_ID, output_dir=tmp_path)
        assert result is not None
        assert result.num_trajectories == 3
        assert result.completed == []
        assert result.dispatched == []
        assert result.in_flight == []
        assert result.not_dispatched == [0, 1, 2]
        assert result.missing == [0, 1, 2]

    def test_partial_completion(self, tmp_path: Path) -> None:
        _write_search_state(tmp_path, _RUN_ID, algorithm_state={"num_trajectories": 3})
        # Write child_variants_t0.json and child_variants_t2.json
        search_dir = tmp_path / _RUN_ID / "search"
        (search_dir / "child_variants_t0.json").write_text("[]", encoding="utf-8")
        (search_dir / "child_variants_t2.json").write_text("[]", encoding="utf-8")

        result = trajectory_fanout_missing(_RUN_ID, output_dir=tmp_path)
        assert result is not None
        assert result.completed == [0, 2]
        assert 1 in result.missing
        assert result.not_dispatched == [1]

    def test_in_flight_when_dispatched_but_not_completed(self, tmp_path: Path) -> None:
        _write_search_state(tmp_path, _RUN_ID, algorithm_state={"num_trajectories": 3})
        # Mark trajectory 1 as dispatched (no child_variants_t1.json yet)
        record_trajectory_dispatched(_RUN_ID, 1, output_dir=tmp_path)

        result = trajectory_fanout_missing(_RUN_ID, output_dir=tmp_path)
        assert result is not None
        assert 1 in result.in_flight
        assert 1 not in result.not_dispatched
        assert 0 in result.not_dispatched
        assert 2 in result.not_dispatched

    def test_all_complete(self, tmp_path: Path) -> None:
        _write_search_state(tmp_path, _RUN_ID, algorithm_state={"num_trajectories": 2})
        search_dir = tmp_path / _RUN_ID / "search"
        (search_dir / "child_variants_t0.json").write_text("[]", encoding="utf-8")
        (search_dir / "child_variants_t1.json").write_text("[]", encoding="utf-8")

        result = trajectory_fanout_missing(_RUN_ID, output_dir=tmp_path)
        assert result is not None
        assert result.completed == [0, 1]
        assert result.missing == []
        assert result.in_flight == []
        assert result.not_dispatched == []

    def test_missing_is_union_of_not_dispatched_and_in_flight(self, tmp_path: Path) -> None:
        _write_search_state(tmp_path, _RUN_ID, algorithm_state={"num_trajectories": 4})
        search_dir = tmp_path / _RUN_ID / "search"
        # trajectory 0: completed
        (search_dir / "child_variants_t0.json").write_text("[]", encoding="utf-8")
        # trajectory 1: in-flight (dispatched, not completed)
        record_trajectory_dispatched(_RUN_ID, 1, output_dir=tmp_path)
        # trajectories 2, 3: not dispatched

        result = trajectory_fanout_missing(_RUN_ID, output_dir=tmp_path)
        assert result is not None
        assert result.completed == [0]
        assert result.in_flight == [1]
        assert sorted(result.not_dispatched) == [2, 3]
        assert sorted(result.missing) == [1, 2, 3]

    def test_fanout_status_is_dataclass(self) -> None:
        fs = FanoutStatus(
            num_trajectories=3,
            missing=[1, 2],
            completed=[0],
            dispatched=[0, 1],
            in_flight=[1],
            not_dispatched=[2],
        )
        assert fs.num_trajectories == 3
        assert fs.completed == [0]


# ---------------------------------------------------------------------------
# save_trajectory_child_variants
# ---------------------------------------------------------------------------


class TestSaveTrajectoryChildVariants:
    def test_writes_correct_filename(self, tmp_path: Path) -> None:
        variants = [_make_child_variant("cv-0")]
        save_trajectory_child_variants(_RUN_ID, 0, variants, output_dir=tmp_path)

        marker = tmp_path / _RUN_ID / "search" / "child_variants_t0.json"
        assert marker.is_file()

    def test_roundtrip(self, tmp_path: Path) -> None:
        variants = [
            _make_child_variant("cv-2-a"),
            _make_child_variant("cv-2-b"),
        ]
        save_trajectory_child_variants(_RUN_ID, 2, variants, output_dir=tmp_path)

        marker = tmp_path / _RUN_ID / "search" / "child_variants_t2.json"
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["variant_id"] == "cv-2-a"
        assert data[1]["variant_id"] == "cv-2-b"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        variants = [_make_child_variant("cv-0")]
        save_trajectory_child_variants(_RUN_ID, 0, variants, output_dir=tmp_path)
        search_dir = tmp_path / _RUN_ID / "search"
        assert search_dir.is_dir()

    def test_overwrites_on_second_call(self, tmp_path: Path) -> None:
        v1 = [_make_child_variant("first")]
        save_trajectory_child_variants(_RUN_ID, 0, v1, output_dir=tmp_path)
        v2 = [_make_child_variant("second"), _make_child_variant("third")]
        save_trajectory_child_variants(_RUN_ID, 0, v2, output_dir=tmp_path)

        marker = tmp_path / _RUN_ID / "search" / "child_variants_t0.json"
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["variant_id"] == "second"

    def test_different_trajectory_ids_create_separate_files(self, tmp_path: Path) -> None:
        for tid in range(3):
            variants = [_make_child_variant(f"cv-{tid}")]
            save_trajectory_child_variants(_RUN_ID, tid, variants, output_dir=tmp_path)

        search_dir = tmp_path / _RUN_ID / "search"
        for tid in range(3):
            assert (search_dir / f"child_variants_t{tid}.json").is_file()


# ---------------------------------------------------------------------------
# load_all_trajectory_child_variants
# ---------------------------------------------------------------------------


class TestLoadAllTrajectoryChildVariants:
    def test_returns_empty_when_no_dir(self, tmp_path: Path) -> None:
        result = load_all_trajectory_child_variants(_RUN_ID, output_dir=tmp_path)
        assert result == []

    def test_merges_and_sorts_by_trajectory_id(self, tmp_path: Path) -> None:
        # Write in non-sequential order to verify sort by file TID
        for tid in [2, 0, 1]:
            variants = [_make_child_variant(f"cv-{tid}")]
            save_trajectory_child_variants(_RUN_ID, tid, variants, output_dir=tmp_path)

        result = load_all_trajectory_child_variants(_RUN_ID, output_dir=tmp_path)
        assert len(result) == 3
        # Verify ordering: variant_id matches tid order (cv-0, cv-1, cv-2)
        assert result[0].variant_id == "cv-0"
        assert result[1].variant_id == "cv-1"
        assert result[2].variant_id == "cv-2"


# ---------------------------------------------------------------------------
# record_trajectory_dispatched / load_dispatched_trajectories
# ---------------------------------------------------------------------------


class TestTrajectoryDispatchedRecord:
    def test_record_and_load(self, tmp_path: Path) -> None:
        _write_search_state(tmp_path, _RUN_ID, round=5)
        record_trajectory_dispatched(_RUN_ID, 0, output_dir=tmp_path)
        loaded = load_dispatched_trajectories(_RUN_ID, output_dir=tmp_path)
        assert loaded == [0]

    def test_idempotent_duplicate_record(self, tmp_path: Path) -> None:
        _write_search_state(tmp_path, _RUN_ID, round=1)
        record_trajectory_dispatched(_RUN_ID, 2, output_dir=tmp_path)
        record_trajectory_dispatched(_RUN_ID, 2, output_dir=tmp_path)
        loaded = load_dispatched_trajectories(_RUN_ID, output_dir=tmp_path)
        assert loaded == [2]

    def test_accumulates_multiple_trajectories(self, tmp_path: Path) -> None:
        _write_search_state(tmp_path, _RUN_ID, round=1)
        for tid in [3, 1, 0, 2]:
            record_trajectory_dispatched(_RUN_ID, tid, output_dir=tmp_path)
        loaded = load_dispatched_trajectories(_RUN_ID, output_dir=tmp_path)
        assert loaded == [0, 1, 2, 3]

    def test_stale_round_returns_empty(self, tmp_path: Path) -> None:
        # Write dispatched file for round 1
        _write_search_state(tmp_path, _RUN_ID, round=1)
        record_trajectory_dispatched(_RUN_ID, 0, output_dir=tmp_path)
        # Bump round to 2 in state
        _write_search_state(tmp_path, _RUN_ID, round=2)
        loaded = load_dispatched_trajectories(_RUN_ID, output_dir=tmp_path)
        assert loaded == []

    def test_stale_round_resets_on_next_record(self, tmp_path: Path) -> None:
        _write_search_state(tmp_path, _RUN_ID, round=1)
        record_trajectory_dispatched(_RUN_ID, 0, output_dir=tmp_path)
        # Bump to round 2 — new dispatch should reset
        _write_search_state(tmp_path, _RUN_ID, round=2)
        record_trajectory_dispatched(_RUN_ID, 1, output_dir=tmp_path)
        loaded = load_dispatched_trajectories(_RUN_ID, output_dir=tmp_path)
        assert loaded == [1]

    def test_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        assert load_dispatched_trajectories(_RUN_ID, output_dir=tmp_path) == []


# ---------------------------------------------------------------------------
# clear_dispatched_trajectories
# ---------------------------------------------------------------------------


class TestClearDispatchedTrajectories:
    def test_deletes_file(self, tmp_path: Path) -> None:
        _write_search_state(tmp_path, _RUN_ID, round=1)
        record_trajectory_dispatched(_RUN_ID, 0, output_dir=tmp_path)
        clear_dispatched_trajectories(_RUN_ID, output_dir=tmp_path)
        assert load_dispatched_trajectories(_RUN_ID, output_dir=tmp_path) == []

    def test_no_op_when_absent(self, tmp_path: Path) -> None:
        clear_dispatched_trajectories(_RUN_ID, output_dir=tmp_path)  # should not raise


# ---------------------------------------------------------------------------
# clear_trajectory_child_variants
# ---------------------------------------------------------------------------


class TestClearTrajectoryChildVariants:
    def test_deletes_all_slot_files(self, tmp_path: Path) -> None:
        for tid in range(3):
            variants = [_make_child_variant(f"cv-{tid}")]
            save_trajectory_child_variants(_RUN_ID, tid, variants, output_dir=tmp_path)
        clear_trajectory_child_variants(_RUN_ID, output_dir=tmp_path)
        search_dir = tmp_path / _RUN_ID / "search"
        assert not list(search_dir.glob("child_variants_t*.json"))

    def test_no_op_when_dir_absent(self, tmp_path: Path) -> None:
        clear_trajectory_child_variants(_RUN_ID, output_dir=tmp_path)  # should not raise
