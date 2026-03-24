"""Tests for stratified split (THP-110)."""

from __future__ import annotations

import pytest

from odysseus.agents.stratified_split import SplitMismatchError, SplitReport


def test_split_report_round_trip():
    """SplitReport can be constructed and serialized."""
    report = SplitReport(
        dataset_hash="abc123",
        split_ratio={"dev": 0.8, "holdout": 0.2},
        total_examples=10,
        dev_count=8,
        holdout_count=2,
        singleton_strata_count=0,
        strata=[],
        distributions={
            "assigned_route": {"dev": {}, "holdout": {}},
            "intent_pattern": {"dev": {}, "holdout": {}},
            "complexity_structure": {"dev": {}, "holdout": {}},
            "ambiguity_tags": {"dev": {}, "holdout": {}},
        },
    )
    data = report.model_dump()
    assert data["dataset_hash"] == "abc123"
    assert data["total_examples"] == 10


def test_split_mismatch_error_is_exception():
    """SplitMismatchError can be raised and caught."""
    with pytest.raises(SplitMismatchError, match="missing"):
        raise SplitMismatchError("missing cards for examples: ex-1")
