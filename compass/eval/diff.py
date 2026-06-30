# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Shared diff computation for run-over-run comparison."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class MetricDiff(BaseModel):
    """A single metric change between two runs."""

    key: str
    old: float | None
    new: float | None
    status: Literal["changed", "added", "removed"]


class OverheadDiff(BaseModel):
    """Cost and duration change between two runs."""

    old_cost: float
    new_cost: float
    old_duration: float
    new_duration: float


def compute_metric_diffs(old: dict[str, float], new: dict[str, float]) -> list[MetricDiff]:
    """Compare two metric dicts. Returns only changed/added/removed entries, sorted by key."""
    all_keys = sorted(set(old) | set(new))
    diffs: list[MetricDiff] = []
    for key in all_keys:
        if key in old and key in new:
            if old[key] != new[key]:
                diffs.append(MetricDiff(key=key, old=old[key], new=new[key], status="changed"))
        elif key in new:
            diffs.append(MetricDiff(key=key, old=None, new=new[key], status="added"))
        else:
            diffs.append(MetricDiff(key=key, old=old[key], new=None, status="removed"))
    return diffs


def compute_overhead_diff(
    *,
    old_cost: float,
    old_duration: float,
    new_cost: float,
    new_duration: float,
) -> OverheadDiff | None:
    """Compare cost and duration. Returns None if nothing changed."""
    if old_cost == new_cost and old_duration == new_duration:
        return None
    return OverheadDiff(
        old_cost=old_cost,
        new_cost=new_cost,
        old_duration=old_duration,
        new_duration=new_duration,
    )
