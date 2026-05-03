"""Tests for _append_archive / _load_archive helpers and archive wiring in advance_round."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odysseus.agents.prompt_builder.search import Candidate
from odysseus.agents.prompt_builder.search_ops import (
    _append_archive,
    _archive_path,
    _load_archive,
    record_eval_result,
    register_candidate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate(
    prompt_version: str,
    parent_version: str | None = None,
    quality_score: float = 0.9,
    cost: float = 0.01,
    round_introduced: int = 1,
    eval_status: str = "complete",
) -> Candidate:
    return Candidate(
        prompt_version=prompt_version,
        parent_version=parent_version,
        quality_score=quality_score,
        cost=cost,
        round_introduced=round_introduced,
        eval_status=eval_status,
    )


def _register_and_score(
    run_id: str,
    prompt_version: str,
    quality_score: float,
    cost: float,
    tmp_path: Path,
    parent_version: str | None = None,
) -> None:
    register_candidate(run_id, prompt_version, parent_version=parent_version, output_dir=tmp_path)
    record_eval_result(run_id, prompt_version, quality_score=quality_score, cost=cost, output_dir=tmp_path)


# ---------------------------------------------------------------------------
# Unit: _append_archive
# ---------------------------------------------------------------------------


class TestAppendArchive:
    def test_creates_file_when_absent(self, tmp_path: Path) -> None:
        """_append_archive creates candidate_archive.json when it does not exist."""
        run_id = "arc-create"
        candidates = [_make_candidate("v1", parent_version="v0")]
        _append_archive(run_id, candidates, tmp_path)
        archive_file = _archive_path(run_id, tmp_path)
        assert archive_file.exists()

    def test_writes_model_dump_form(self, tmp_path: Path) -> None:
        """Written entries match Candidate.model_dump() output."""
        run_id = "arc-dump"
        c = _make_candidate("v1", parent_version="v0", quality_score=0.85, cost=0.02)
        _append_archive(run_id, [c], tmp_path)
        raw = json.loads(_archive_path(run_id, tmp_path).read_text())
        assert len(raw) == 1
        entry = raw[0]
        assert entry["prompt_version"] == "v1"
        assert entry["parent_version"] == "v0"
        assert entry["quality_score"] == pytest.approx(0.85)
        assert entry["cost"] == pytest.approx(0.02)

    def test_no_duplicate_on_re_append(self, tmp_path: Path) -> None:
        """Re-calling _append_archive with the same prompt_version does not duplicate."""
        run_id = "arc-dedup"
        c = _make_candidate("v1")
        _append_archive(run_id, [c], tmp_path)
        _append_archive(run_id, [c], tmp_path)
        archive = _load_archive(run_id, tmp_path)
        assert len(archive) == 1

    def test_dedupes_by_prompt_version_across_calls(self, tmp_path: Path) -> None:
        """Candidates already in the archive are skipped; new ones are appended."""
        run_id = "arc-dedup2"
        c1 = _make_candidate("v1")
        c2 = _make_candidate("v2")
        _append_archive(run_id, [c1], tmp_path)
        _append_archive(run_id, [c1, c2], tmp_path)
        archive = _load_archive(run_id, tmp_path)
        versions = [e["prompt_version"] for e in archive]
        assert versions.count("v1") == 1
        assert versions.count("v2") == 1

    def test_no_op_for_empty_candidates(self, tmp_path: Path) -> None:
        """_append_archive with an empty list does not create the file."""
        run_id = "arc-noop"
        _append_archive(run_id, [], tmp_path)
        assert not _archive_path(run_id, tmp_path).exists()


# ---------------------------------------------------------------------------
# Unit: _load_archive
# ---------------------------------------------------------------------------


class TestLoadArchive:
    def test_returns_empty_list_when_no_file(self, tmp_path: Path) -> None:
        assert _load_archive("no-run", tmp_path) == []

    def test_round_trip_preserves_fields(self, tmp_path: Path) -> None:
        """Write via _append_archive, read via _load_archive, key fields preserved."""
        run_id = "arc-rt"
        c = _make_candidate(
            "v3",
            parent_version="v2",
            quality_score=0.77,
            cost=0.05,
            round_introduced=3,
        )
        _append_archive(run_id, [c], tmp_path)
        archive = _load_archive(run_id, tmp_path)
        assert len(archive) == 1
        entry = archive[0]
        assert entry["prompt_version"] == "v3"
        assert entry["parent_version"] == "v2"
        assert entry["quality_score"] == pytest.approx(0.77)
        assert entry["cost"] == pytest.approx(0.05)
        assert entry["round_introduced"] == 3
