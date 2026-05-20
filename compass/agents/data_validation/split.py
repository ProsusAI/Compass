"""Deterministic stratified split for routing datasets (Stage 2: Data Validation).

Splits examples by route without requiring a rationale card set.
"""

from __future__ import annotations

import hashlib
import random
from collections import defaultdict

from pydantic import BaseModel

from compass.eval.models import Example


class StratumReport(BaseModel):
    """Distribution report for a single stratum."""

    key: str
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
    route_distribution: dict[str, dict[str, int]]


def compute_dataset_hash(examples: list[Example]) -> str:
    """Compute a deterministic SHA-256 hash over (id, input, expected.route) tuples."""
    tuples = sorted((ex.id, ex.input, ex.expected.route) for ex in examples)
    payload = "\n".join(f"{id_}\t{inp}\t{route}" for id_, inp, route in tuples)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def stratified_split(
    examples: list[Example],
    dev_ratio: float = 0.2,
) -> tuple[list[Example], list[Example], SplitReport]:
    """Split examples into dev and holdout sets, stratified by route.

    Args:
        examples: Full dataset examples.
        dev_ratio: Proportion allocated to dev set. Default 0.2.

    Returns:
        (dev_examples, holdout_examples, report)
    """
    if len(examples) < 2:
        return _build_result(examples, [], examples, dev_ratio)

    # Build strata by route
    strata: dict[str, list[Example]] = defaultdict(list)
    for ex in examples:
        strata[ex.expected.route].append(ex)

    dataset_hash = compute_dataset_hash(examples)
    rng = random.Random(dataset_hash)

    dev: list[Example] = []
    holdout: list[Example] = []
    singleton_count = 0

    for _key, members in sorted(strata.items()):
        if len(members) < 2:
            dev.extend(members)
            singleton_count += 1
            continue

        # Sort by ID before shuffling for input-order independence
        shuffled = sorted(members, key=lambda ex: ex.id)
        rng.shuffle(shuffled)

        holdout_count = round(len(shuffled) * (1.0 - dev_ratio))
        dev.extend(shuffled[holdout_count:])
        holdout.extend(shuffled[:holdout_count])

    # Fallback: if holdout is empty and there are enough examples,
    # move some singleton-assigned examples to holdout.
    target_holdout = round(len(examples) * (1.0 - dev_ratio))
    if not holdout and target_holdout > 0 and len(dev) > 1:
        shuffled_dev = sorted(dev, key=lambda ex: ex.id)
        rng.shuffle(shuffled_dev)
        holdout = shuffled_dev[:target_holdout]
        dev = shuffled_dev[target_holdout:]

    return _build_result(dev, holdout, examples, dev_ratio, singleton_count)


def _build_result(
    dev: list[Example],
    holdout: list[Example],
    all_examples: list[Example],
    dev_ratio: float,
    singleton_strata_count: int = 0,
) -> tuple[list[Example], list[Example], SplitReport]:
    """Construct the split result with report."""
    dataset_hash = compute_dataset_hash(all_examples)

    dev_ids = {ex.id for ex in dev}

    # Build strata report by route
    strata_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "dev": 0, "holdout": 0})
    for ex in all_examples:
        route = ex.expected.route
        strata_counts[route]["total"] += 1
        if ex.id in dev_ids:
            strata_counts[route]["dev"] += 1
        else:
            strata_counts[route]["holdout"] += 1

    strata_report = [
        StratumReport(key=k, total=v["total"], dev=v["dev"], holdout=v["holdout"])
        for k, v in sorted(strata_counts.items())
    ]

    # Route distribution
    route_distribution = {
        route: {"dev": v["dev"], "holdout": v["holdout"]} for route, v in sorted(strata_counts.items())
    }

    report = SplitReport(
        dataset_hash=dataset_hash,
        split_ratio={"dev": dev_ratio, "holdout": round(1.0 - dev_ratio, 4)},
        total_examples=len(all_examples),
        dev_count=len(dev),
        holdout_count=len(holdout),
        singleton_strata_count=singleton_strata_count,
        strata=strata_report,
        route_distribution=route_distribution,
    )

    return dev, holdout, report
