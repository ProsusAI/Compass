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


