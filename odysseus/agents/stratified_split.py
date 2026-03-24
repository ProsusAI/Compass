"""Deterministic stratified split for annotated routing datasets (THP-110).

Spec: docs/superpowers/specs/2026-03-24-thp-110-stratified-split-methodology.md
"""

from __future__ import annotations

from pydantic import BaseModel


class SplitMismatchError(Exception):
    """Raised when examples and rationale cards don't match by example_id."""


class StratumReport(BaseModel):
    """Distribution report for a single stratum."""

    key: list[str]
    total: int
    dev: int
    holdout: int


class SplitReport(BaseModel):
    """Report produced alongside the dev/holdout split."""

    dataset_hash: str
    split_ratio: dict[str, float]
    total_examples: int
    dev_count: int
    holdout_count: int
    singleton_strata_count: int
    strata: list[StratumReport]
    distributions: dict[str, dict[str, dict[str, float | int]]]
