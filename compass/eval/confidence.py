# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Bootstrap confidence intervals for evaluation metrics."""

from __future__ import annotations

import random

from compass.eval.metrics import MetricFn
from compass.eval.models import ConfidenceInterval, EvalResult, Example, MetricConfig


def _default_n_bootstrap(n: int) -> int:
    """Adaptive bootstrap sample count based on dataset size."""
    return 10_000 if n >= 200 else 2_000


def bootstrap_cis(
    filtered_results: list[EvalResult],
    filtered_examples: list[Example],
    metric_configs: list[MetricConfig],
    registry: dict[str, MetricFn],
    n_bootstrap: int,
    ci_level: float = 0.95,
    seed: int | None = None,
) -> dict[str, ConfidenceInterval]:
    """Compute bootstrap percentile CIs for all registered metrics.

    Resamples the already-filtered (result, example) pairs with replacement.
    No model calls are made — only metric computation functions are re-run.
    Metric functions that raise on a resample are silently skipped for that iteration.
    Returns an empty dict if there are no pairs to resample.
    """
    n = len(filtered_results)
    if n == 0:
        return {}

    rng = random.Random(seed)
    pairs = list(zip(filtered_results, filtered_examples, strict=True))

    # Collect per-metric value lists across all bootstrap iterations
    bootstrap_values: dict[str, list[float]] = {}

    for _ in range(n_bootstrap):
        sample = rng.choices(pairs, k=n)
        sample_results = [p[0] for p in sample]
        sample_examples = [p[1] for p in sample]

        for config in metric_configs:
            fn = registry.get(config.name)
            if fn is None:
                continue
            try:
                result_dict = fn(sample_results, sample_examples, **config.params)
                for key, value in result_dict.items():
                    bootstrap_values.setdefault(key, []).append(value)
            except Exception:
                pass

    # Compute percentile intervals. Index bounds are derived per key from the
    # number of values actually collected for that key — not from n_bootstrap —
    # because metric keys that are only defined on some resamples (e.g. per-class
    # confusion/precision/f1 keys when a bootstrap sample omits a class, or
    # metrics that raise on a resample) accumulate fewer than n_bootstrap values.
    # Using n_bootstrap-based indices would index out of range for those keys.
    alpha = (1.0 - ci_level) / 2.0

    cis: dict[str, ConfidenceInterval] = {}
    for key, values in bootstrap_values.items():
        m = len(values)
        if m < 2:
            continue
        sorted_values = sorted(values)
        lo_idx = int(alpha * m)
        hi_idx = min(int((1.0 - alpha) * m), m - 1)
        cis[key] = ConfidenceInterval(
            lower=sorted_values[lo_idx],
            upper=sorted_values[hi_idx],
            level=ci_level,
        )

    return cis
