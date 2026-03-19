"""Metrics engine with dynamic metric registration."""

from __future__ import annotations

import logging
from collections.abc import Callable

from odysseus.eval.models import EvalResult, Example, MetricConfig

logger = logging.getLogger(__name__)

MetricFn = Callable[..., dict[str, float]]


class DefaultMetricsEngine:
    """Registry-based metrics engine.

    Maintains a dict mapping metric names to callable implementations.
    Satisfies the MetricsEngine protocol.
    """

    def __init__(self) -> None:
        self._registry: dict[str, MetricFn] = {}

    def register(self, name: str, fn: MetricFn) -> None:
        """Register a metric function. Overwrites if name exists."""
        self._registry[name] = fn

    def compute(
        self,
        results: list[EvalResult],
        examples: list[Example],
        metric_configs: list[MetricConfig],
    ) -> dict[str, float]:
        """Compute all requested metrics over results and examples.

        1. Pairs results with examples by ID, filters errored results.
        2. For each MetricConfig, dispatches to the registered function.
        3. Merges all returned dicts. Raises ValueError on duplicate keys.
        """
        # Build example lookup
        example_by_id: dict[str, Example] = {ex.id: ex for ex in examples}

        # Pair and filter
        filtered_results: list[EvalResult] = []
        filtered_examples: list[Example] = []
        for result in results:
            if result.error is not None:
                continue
            if result.example_id not in example_by_id:
                continue
            filtered_results.append(result)
            filtered_examples.append(example_by_id[result.example_id])

        # Dispatch and merge
        merged: dict[str, float] = {}
        for config in metric_configs:
            if config.name not in self._registry:
                raise ValueError(f"Unknown metric: {config.name!r}")
            fn = self._registry[config.name]
            result_dict = fn(filtered_results, filtered_examples, **config.params)
            for key, value in result_dict.items():
                if key in merged:
                    raise ValueError(f"Duplicate metric key {key!r} — two metrics produced the same key")
                merged[key] = value

        return merged
