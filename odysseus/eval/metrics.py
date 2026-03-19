"""Metrics engine with dynamic metric registration."""

from __future__ import annotations

import logging
from collections import Counter
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


def compute_accuracy(
    results: list[EvalResult], examples: list[Example]
) -> dict[str, float]:
    """Fraction of predictions matching the expected route."""
    if not results:
        return {"accuracy": 0.0}
    correct = sum(
        1
        for r, ex in zip(results, examples)
        if r.output is not None and r.output["route"] == ex.expected["route"]
    )
    return {"accuracy": correct / len(results)}


def compute_confusion(
    results: list[EvalResult], examples: list[Example]
) -> dict[str, float]:
    """Confusion matrix as flat dict keyed by confusion/{true}/{predicted}."""
    if not results:
        return {}

    classes: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for r, ex in zip(results, examples):
        true_class = ex.expected["route"]
        pred_class = r.output["route"] if r.output else ""
        classes.add(true_class)
        classes.add(pred_class)
        pairs.append((true_class, pred_class))

    counts = Counter(pairs)

    sorted_classes = sorted(classes)
    out: dict[str, float] = {}
    for true_cls in sorted_classes:
        for pred_cls in sorted_classes:
            out[f"confusion/{true_cls}/{pred_cls}"] = float(counts.get((true_cls, pred_cls), 0))

    return out


def compute_f1(
    results: list[EvalResult], examples: list[Example]
) -> dict[str, float]:
    """Per-class precision, recall, F1, and macro F1."""
    if not results:
        return {"f1/macro": 0.0}

    classes: set[str] = set()
    true_labels: list[str] = []
    pred_labels: list[str] = []
    for r, ex in zip(results, examples):
        true_cls = ex.expected["route"]
        pred_cls = r.output["route"] if r.output else ""
        classes.add(true_cls)
        classes.add(pred_cls)
        true_labels.append(true_cls)
        pred_labels.append(pred_cls)

    out: dict[str, float] = {}
    f1_scores: list[float] = []

    for cls in sorted(classes):
        tp = sum(1 for t, p in zip(true_labels, pred_labels) if t == cls and p == cls)
        fp = sum(1 for t, p in zip(true_labels, pred_labels) if t != cls and p == cls)
        fn = sum(1 for t, p in zip(true_labels, pred_labels) if t == cls and p != cls)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        out[f"precision/{cls}"] = precision
        out[f"recall/{cls}"] = recall
        out[f"f1/{cls}"] = f1
        f1_scores.append(f1)

    out["f1/macro"] = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0

    return out
