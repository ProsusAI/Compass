"""Tests for odysseus.agents.pipeline.dispatch — marker and fanout primitives."""

from __future__ import annotations

import json
from pathlib import Path

from odysseus.agents.pipeline.dispatch import (
    DispatchFanout,
    clear_build_dispatched,
    clear_review_dispatched,
    is_build_dispatched,
    is_review_dispatched,
    record_build_dispatched,
    record_review_dispatched,
    review_fanout_status,
)

_RUN_ID = "test_run"


# ---------------------------------------------------------------------------
# Build-dispatch marker
# ---------------------------------------------------------------------------


class TestBuildDispatchMarker:
    def test_record_creates_marker(self, tmp_path: Path) -> None:
        assert not is_build_dispatched(_RUN_ID, tmp_path)
        record_build_dispatched(_RUN_ID, round=1, output_dir=tmp_path)
        assert is_build_dispatched(_RUN_ID, tmp_path)

    def test_marker_path(self, tmp_path: Path) -> None:
        record_build_dispatched(_RUN_ID, round=2, output_dir=tmp_path)
        marker = tmp_path / _RUN_ID / "search" / "build_dispatched.json"
        assert marker.is_file()
        import json

        data = json.loads(marker.read_text())
        assert data["round"] == 2

    def test_clear_removes_marker(self, tmp_path: Path) -> None:
        record_build_dispatched(_RUN_ID, round=1, output_dir=tmp_path)
        assert is_build_dispatched(_RUN_ID, tmp_path)
        clear_build_dispatched(_RUN_ID, tmp_path)
        assert not is_build_dispatched(_RUN_ID, tmp_path)

    def test_clear_is_idempotent_when_absent(self, tmp_path: Path) -> None:
        # Should not raise even if marker doesn't exist
        clear_build_dispatched(_RUN_ID, tmp_path)

    def test_record_creates_parent_dirs(self, tmp_path: Path) -> None:
        # search/ dir does not exist yet
        record_build_dispatched(_RUN_ID, round=1, output_dir=tmp_path)
        marker = tmp_path / _RUN_ID / "search" / "build_dispatched.json"
        assert marker.is_file()


# ---------------------------------------------------------------------------
# Review-dispatch marker
# ---------------------------------------------------------------------------


class TestReviewDispatchMarker:
    def test_record_creates_marker(self, tmp_path: Path) -> None:
        assert not is_review_dispatched(_RUN_ID, tmp_path)
        record_review_dispatched(_RUN_ID, round=3, output_dir=tmp_path)
        assert is_review_dispatched(_RUN_ID, tmp_path)

    def test_marker_path(self, tmp_path: Path) -> None:
        record_review_dispatched(_RUN_ID, round=5, output_dir=tmp_path)
        marker = tmp_path / _RUN_ID / "search" / "review_dispatched.json"
        assert marker.is_file()
        import json

        data = json.loads(marker.read_text())
        assert data["round"] == 5

    def test_clear_removes_marker(self, tmp_path: Path) -> None:
        record_review_dispatched(_RUN_ID, round=1, output_dir=tmp_path)
        assert is_review_dispatched(_RUN_ID, tmp_path)
        clear_review_dispatched(_RUN_ID, tmp_path)
        assert not is_review_dispatched(_RUN_ID, tmp_path)

    def test_clear_is_idempotent_when_absent(self, tmp_path: Path) -> None:
        clear_review_dispatched(_RUN_ID, tmp_path)


# ---------------------------------------------------------------------------
# DispatchFanout dataclass
# ---------------------------------------------------------------------------


class TestDispatchFanout:
    def test_is_complete_when_all_completed(self) -> None:
        f = DispatchFanout(expected=1, completed=[0])
        assert f.is_complete

    def test_is_not_complete_when_in_flight(self) -> None:
        f = DispatchFanout(expected=1, in_flight=[0])
        assert not f.is_complete

    def test_is_not_complete_when_not_dispatched(self) -> None:
        f = DispatchFanout(expected=1, not_dispatched=[0])
        assert not f.is_complete

    def test_missing_combines_in_flight_and_not_dispatched(self) -> None:
        f = DispatchFanout(expected=3, in_flight=[1], not_dispatched=[2])
        assert set(f.missing) == {1, 2}

    def test_missing_empty_when_complete(self) -> None:
        f = DispatchFanout(expected=1, completed=[0])
        assert f.missing == []


# ---------------------------------------------------------------------------
# review_fanout_status
# ---------------------------------------------------------------------------


class TestReviewFanoutStatus:
    def test_completed_when_child_variants_exists(self, tmp_path: Path) -> None:
        # Write child_variants.json sentinel
        search_dir = tmp_path / _RUN_ID / "search"
        search_dir.mkdir(parents=True)
        (search_dir / "child_variants.json").write_text("[]")

        status = review_fanout_status(_RUN_ID, expected=1, output_dir=tmp_path)
        assert status.expected == 1
        assert status.completed == [0]
        assert status.is_complete

    def test_in_flight_when_marker_exists_but_no_variants(self, tmp_path: Path) -> None:
        record_review_dispatched(_RUN_ID, round=1, output_dir=tmp_path)
        # No child_variants.json

        status = review_fanout_status(_RUN_ID, expected=1, output_dir=tmp_path)
        assert status.expected == 1
        assert status.in_flight == [0]
        assert not status.is_complete

    def test_not_dispatched_when_neither_exists(self, tmp_path: Path) -> None:
        status = review_fanout_status(_RUN_ID, expected=1, output_dir=tmp_path)
        assert status.expected == 1
        assert status.not_dispatched == [0]
        assert not status.is_complete

    def test_non_emosa_expected_1_not_dispatched(self, tmp_path: Path) -> None:
        # Non-EMOSA algorithms default to single-slot not_dispatched when nothing exists
        status = review_fanout_status(_RUN_ID, algorithm="hill_climb", expected=1, output_dir=tmp_path)
        assert status.not_dispatched == [0]
        assert not status.is_complete


# ---------------------------------------------------------------------------
# review_fanout_status — EMOSA K-way arm
# ---------------------------------------------------------------------------


class TestReviewFanoutStatusEmosa:
    def _write_search_state(self, tmp_path: Path, run_id: str, num_trajectories: int, round: int = 1) -> None:
        search_dir = tmp_path / run_id / "search"
        search_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "run_id": run_id,
            "round": round,
            "algorithm": "emosa",
            "algorithm_state": {"num_trajectories": num_trajectories},
        }
        (search_dir / "search_state.json").write_text(json.dumps(state), encoding="utf-8")

    def test_all_not_dispatched_at_start(self, tmp_path: Path) -> None:
        self._write_search_state(tmp_path, _RUN_ID, num_trajectories=3)
        status = review_fanout_status(_RUN_ID, algorithm="emosa", output_dir=tmp_path)
        assert status.expected == 3
        assert status.not_dispatched == [0, 1, 2]
        assert status.completed == []
        assert not status.is_complete

    def test_partial_completion(self, tmp_path: Path) -> None:
        self._write_search_state(tmp_path, _RUN_ID, num_trajectories=3)
        search_dir = tmp_path / _RUN_ID / "search"
        (search_dir / "child_variants_t0.json").write_text("[]", encoding="utf-8")
        (search_dir / "child_variants_t2.json").write_text("[]", encoding="utf-8")

        status = review_fanout_status(_RUN_ID, algorithm="emosa", output_dir=tmp_path)
        assert status.expected == 3
        assert status.completed == [0, 2]
        assert 1 in status.not_dispatched
        assert not status.is_complete

    def test_complete_when_all_slots_written(self, tmp_path: Path) -> None:
        self._write_search_state(tmp_path, _RUN_ID, num_trajectories=2)
        search_dir = tmp_path / _RUN_ID / "search"
        (search_dir / "child_variants_t0.json").write_text("[]", encoding="utf-8")
        (search_dir / "child_variants_t1.json").write_text("[]", encoding="utf-8")

        status = review_fanout_status(_RUN_ID, algorithm="emosa", output_dir=tmp_path)
        assert status.expected == 2
        assert status.is_complete
        assert status.missing == []

    def test_in_flight_when_dispatched_not_completed(self, tmp_path: Path) -> None:
        self._write_search_state(tmp_path, _RUN_ID, num_trajectories=3)
        from odysseus.agents.review.ops import record_trajectory_dispatched

        record_trajectory_dispatched(_RUN_ID, 1, output_dir=tmp_path)

        status = review_fanout_status(_RUN_ID, algorithm="emosa", output_dir=tmp_path)
        assert 1 in status.in_flight
        assert 1 not in status.not_dispatched
        assert not status.is_complete

    def test_falls_back_to_single_slot_when_no_algorithm_state(self, tmp_path: Path) -> None:
        # No search_state.json at all — trajectory_fanout_missing returns None
        # so review_fanout_status falls back to single-slot path
        status = review_fanout_status(_RUN_ID, algorithm="emosa", output_dir=tmp_path)
        assert status.expected == 1
        assert status.not_dispatched == [0]

    def test_missing_property_is_not_dispatched_union_in_flight(self, tmp_path: Path) -> None:
        self._write_search_state(tmp_path, _RUN_ID, num_trajectories=4)
        search_dir = tmp_path / _RUN_ID / "search"
        (search_dir / "child_variants_t0.json").write_text("[]", encoding="utf-8")
        from odysseus.agents.review.ops import record_trajectory_dispatched

        record_trajectory_dispatched(_RUN_ID, 1, output_dir=tmp_path)

        status = review_fanout_status(_RUN_ID, algorithm="emosa", output_dir=tmp_path)
        # slot 0 complete, slot 1 in-flight, slots 2,3 not dispatched
        assert set(status.missing) == {1, 2, 3}
