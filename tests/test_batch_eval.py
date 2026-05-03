"""Tests for odysseus.eval.batch_eval — models and utility functions.

Integration tests that require a running search state (init_search_state)
live on the algorithm leaf branches where _BRANCH_ALGORITHM is set.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from odysseus.eval.batch_eval import (
    BatchEvalCandidate,
    BatchEvalResult,
    CandidateEvalOutcome,
    _extract_quality_score,
    _extract_quality_score_from_dict,
)


# ---------------------------------------------------------------------------
# BatchEvalCandidate / BatchEvalResult model tests
# ---------------------------------------------------------------------------


class TestBatchEvalModels:
    def test_batch_eval_candidate_defaults(self) -> None:
        c = BatchEvalCandidate(prompt_version="v1")
        assert c.parent_version is None
        assert c.example_ids == []

    def test_batch_eval_candidate_with_fields(self) -> None:
        c = BatchEvalCandidate(
            prompt_version="v2",
            parent_version="v1",
            example_ids=["e1", "e2"],
        )
        assert c.prompt_version == "v2"
        assert c.parent_version == "v1"
        assert c.example_ids == ["e1", "e2"]

    def test_candidate_eval_outcome_complete(self) -> None:
        o = CandidateEvalOutcome(
            prompt_version="v2",
            eval_status="complete",
            quality_score=0.9,
            cost=-0.1,
        )
        assert o.eval_status == "complete"
        assert o.error is None

    def test_candidate_eval_outcome_failed(self) -> None:
        o = CandidateEvalOutcome(
            prompt_version="v2",
            eval_status="failed",
            error="Connection error",
        )
        assert o.eval_status == "failed"
        assert o.quality_score is None

    def test_batch_eval_result_empty(self) -> None:
        r = BatchEvalResult(succeeded=[], failed=[])
        assert r.succeeded == []
        assert r.failed == []


# ---------------------------------------------------------------------------
# trajectory_id plumbing through BatchEvalCandidate
# ---------------------------------------------------------------------------


def test_batch_eval_candidate_has_trajectory_id_field() -> None:
    """BatchEvalCandidate has a trajectory_id field defaulting to None."""
    c = BatchEvalCandidate(prompt_version="v1")
    assert c.trajectory_id is None


def test_batch_eval_candidate_trajectory_id_roundtrips() -> None:
    """BatchEvalCandidate.model_validate with trajectory_id=1 round-trips correctly."""
    data = {"prompt_version": "v1", "parent_version": None, "example_ids": [], "trajectory_id": 1}
    c = BatchEvalCandidate.model_validate(data)
    assert c.trajectory_id == 1
    dumped = c.model_dump()
    assert dumped["trajectory_id"] == 1


# ---------------------------------------------------------------------------
# _extract_quality_score preference tests
# ---------------------------------------------------------------------------


class TestExtractQualityScorePreference:
    """oracle_quality_captured should be preferred over accuracy."""

    def _fake_report(self, metrics: dict) -> object:
        """Build a minimal report-like object with a .metrics attribute."""
        report = MagicMock()
        report.metrics = metrics
        return report

    def test_prefers_oracle_quality_captured_over_accuracy(self):
        """When both keys present, returns oracle_quality_captured."""
        report = self._fake_report({"oracle_quality_captured": 0.92, "accuracy": 0.85})
        assert _extract_quality_score(report, primary_metric_name=None) == pytest.approx(0.92)

    def test_falls_back_to_accuracy_when_no_oracle_key(self):
        """Without oracle_quality_captured, falls back to accuracy."""
        report = self._fake_report({"accuracy": 0.85})
        assert _extract_quality_score(report, primary_metric_name=None) == pytest.approx(0.85)

    def test_primary_metric_name_takes_precedence(self):
        """Explicit primary_metric_name overrides oracle_quality_captured."""
        report = self._fake_report({"accuracy": 0.75, "oracle_quality_captured": 0.92})
        assert _extract_quality_score(report, primary_metric_name="accuracy") == pytest.approx(0.75)

    def test_extract_quality_score_from_dict_prefers_oracle(self):
        """_extract_quality_score_from_dict mirrors the same preference."""
        metrics = {"oracle_quality_captured": 0.92, "accuracy": 0.85}
        assert _extract_quality_score_from_dict(metrics, primary_metric_name=None) == pytest.approx(0.92)

    def test_extract_quality_score_from_dict_no_oracle(self):
        """_extract_quality_score_from_dict falls back to accuracy when oracle key absent."""
        metrics = {"accuracy": 0.85}
        assert _extract_quality_score_from_dict(metrics, primary_metric_name=None) == pytest.approx(0.85)
