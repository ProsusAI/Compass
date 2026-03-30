# odysseus/agents/data_validation/split.py
"""Route-only stratified split for dev/holdout partitioning.

Relocated and simplified from odysseus.agents.routing_analysis.split.
Uses only assigned_route as the stratum key (no rationale card annotations).
"""

from __future__ import annotations

import hashlib
import math
import random
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field


class SplitReport(BaseModel):
    """Report produced alongside the dev/holdout split."""

    dev_size: int
    holdout_size: int
    dev_ratio: float
    dataset_hash: str
    per_route_dev: dict[str, int] = Field(default_factory=dict)
    per_route_holdout: dict[str, int] = Field(default_factory=dict)


def compute_dataset_hash(examples: list[dict[str, Any]]) -> str:
    """Deterministic SHA-256 hash over (id, input, expected.route) tuples.

    Order-independent. Returns 16 hex chars.
    Algorithm matches the original in routing_analysis/registry.py.
    """
    tuples = sorted(
        (str(e["id"]), str(e["input"]), str(e["expected"]["route"]))
        for e in examples
    )
    payload = "\n".join(f"{id_}\t{inp}\t{route}" for id_, inp, route in tuples)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def stratified_split(
    examples: list[dict[str, Any]],
    *,
    dev_ratio: float = 0.8,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], SplitReport]:
    """Split examples into dev and holdout sets, stratified by route.

    Args:
        examples: List of example dicts with expected.route field.
        dev_ratio: Fraction allocated to dev set (default 0.8).

    Returns:
        (dev_examples, holdout_examples, split_report)
    """
    dataset_hash = compute_dataset_hash(examples)
    rng = random.Random(int(dataset_hash, 16))

    # Group by route
    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ex in examples:
        route = ex["expected"]["route"]
        strata[route].append(ex)

    dev: list[dict[str, Any]] = []
    holdout: list[dict[str, Any]] = []
    per_route_dev: dict[str, int] = {}
    per_route_holdout: dict[str, int] = {}

    for route, group in sorted(strata.items()):
        shuffled = list(group)
        rng.shuffle(shuffled)

        if len(shuffled) < 2:
            # Singletons go to dev
            dev.extend(shuffled)
            per_route_dev[route] = len(shuffled)
            per_route_holdout[route] = 0
        else:
            n_dev = max(1, math.floor(len(shuffled) * dev_ratio))
            dev.extend(shuffled[:n_dev])
            holdout.extend(shuffled[n_dev:])
            per_route_dev[route] = n_dev
            per_route_holdout[route] = len(shuffled) - n_dev

    report = SplitReport(
        dev_size=len(dev),
        holdout_size=len(holdout),
        dev_ratio=dev_ratio,
        dataset_hash=dataset_hash,
        per_route_dev=per_route_dev,
        per_route_holdout=per_route_holdout,
    )

    return dev, holdout, report
