"""Metrics engine with dynamic metric registration."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable

from odysseus.eval.models import ConfidenceInterval, EvalResult, Example, MetricConfig

logger = logging.getLogger(__name__)

MetricFn = Callable[..., dict[str, float]]


def _filter_pairs(
    results: list[EvalResult],
    examples: list[Example],
    example_by_id: dict[str, Example] | None = None,
) -> tuple[list[EvalResult], list[Example]]:
    """Pair results with examples by ID, filtering out errored results.

    Returns (filtered_results, filtered_examples) with matching indices.
    """
    if example_by_id is None:
        example_by_id = {ex.id: ex for ex in examples}

    filtered_results: list[EvalResult] = []
    filtered_examples: list[Example] = []
    for result in results:
        if result.error is not None:
            continue
        if result.example_id not in example_by_id:
            continue
        filtered_results.append(result)
        filtered_examples.append(example_by_id[result.example_id])

    return filtered_results, filtered_examples


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
        # Build example lookup and pair/filter
        example_by_id: dict[str, Example] = {ex.id: ex for ex in examples}
        filtered_results, filtered_examples = _filter_pairs(results, examples, example_by_id)

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

    def compute_cis(
        self,
        results: list[EvalResult],
        examples: list[Example],
        metric_configs: list[MetricConfig],
        n_bootstrap: int | None = None,
        ci_level: float = 0.95,
    ) -> dict[str, ConfidenceInterval]:
        """Bootstrap CIs using the same filtered pairs as compute()."""
        from odysseus.eval.confidence import _default_n_bootstrap, bootstrap_cis

        example_by_id: dict[str, Example] = {ex.id: ex for ex in examples}
        filtered_results, filtered_examples = _filter_pairs(results, examples, example_by_id)
        n = len(filtered_results)
        effective_n = n_bootstrap if n_bootstrap is not None else _default_n_bootstrap(n)
        return bootstrap_cis(
            filtered_results,
            filtered_examples,
            metric_configs,
            self._registry,
            effective_n,
            ci_level,
        )


def compute_accuracy(results: list[EvalResult], examples: list[Example]) -> dict[str, float]:
    """Fraction of predictions matching the expected route."""
    if not results:
        return {"accuracy": 0.0}
    correct = sum(
        1
        for r, ex in zip(results, examples, strict=True)
        if r.output is not None and r.output["route"] == ex.expected.route
    )
    return {"accuracy": correct / len(results)}


def compute_confusion(results: list[EvalResult], examples: list[Example]) -> dict[str, float]:
    """Confusion matrix as flat dict keyed by confusion/{true}/{predicted}."""
    if not results:
        return {}

    classes: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for r, ex in zip(results, examples, strict=True):
        true_class = ex.expected.route
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


def compute_cost_quality_change(
    results: list[EvalResult],
    examples: list[Example],
    *,
    baseline_class: str | None = None,
) -> dict[str, float]:
    """Cost and quality percentage change vs baseline, plus oracle changes.

    Args:
        results: Filtered successful results.
        examples: Matched examples (same order as results).
        baseline_class: Route class to use as baseline. If None, auto-selects
            the class with highest mean quality_score (tie-break alphabetical).
    """
    zero_result = {
        "cost_change": 0.0,
        "cost_change_with_overhead": 0.0,
        "quality_change": 0.0,
        "oracle_cost_change": 0.0,
        "oracle_quality_change": 0.0,
        "oracle_quality_captured": 1.0,
        "oracle_quality": 0.0,
        "oracle_cost": 0.0,
        "predicted_quality": 0.0,
        "predicted_cost": 0.0,
        "routing_overhead": 0.0,
        "baseline_quality": 0.0,
        "baseline_cost": 0.0,
    }

    if not results:
        return zero_result

    # Auto-select baseline if needed
    if baseline_class is None:
        baseline_class = _select_baseline_class(examples)

    # Compute totals, skipping hallucinated routes
    baseline_cost = 0.0
    baseline_quality = 0.0
    predicted_cost = 0.0
    predicted_quality = 0.0
    oracle_cost = 0.0
    oracle_quality = 0.0
    routing_overhead = 0.0
    counted = 0
    skipped_pred_samples: list[str] = []
    expected_keys_sample: list[str] = []

    for r, ex in zip(results, examples, strict=True):
        routes = ex.expected.routes
        pred_route = r.output["route"] if r.output else None

        # Skip hallucinated routes
        if pred_route is not None and pred_route not in routes:
            logger.warning(
                "Predicted route %r not in expected routes for example %s — skipping",
                pred_route,
                ex.id,
            )
            if len(skipped_pred_samples) < 5 and pred_route not in skipped_pred_samples:
                skipped_pred_samples.append(pred_route)
            if not expected_keys_sample:
                expected_keys_sample = sorted(routes.keys())
            continue

        oracle_route = ex.expected.route

        baseline_cost += routes[baseline_class].cost or 0.0
        baseline_quality += routes[baseline_class].quality_score or 0.0
        predicted_cost += (routes[pred_route].cost or 0.0) if pred_route else 0.0
        predicted_quality += (routes[pred_route].quality_score or 0.0) if pred_route else 0.0
        oracle_cost += routes[oracle_route].cost or 0.0
        oracle_quality += routes[oracle_route].quality_score or 0.0
        routing_overhead += r.cost or 0.0
        counted += 1

    if counted == 0:
        logger.error(
            "compute_cost_quality_change: every prediction skipped as hallucination "
            "(%d results, 0 counted). Likely a route-label namespace mismatch: "
            "predicted routes are not keys of expected.routes. "
            "Sample predicted routes: %s; expected.routes keys: %s. "
            "Fix the routing prompt / dataset so both use the same label set "
            "(canonical = expected.routes keys).",
            len(results),
            skipped_pred_samples,
            expected_keys_sample,
        )
        return zero_result

    cost_change = (predicted_cost - baseline_cost) / baseline_cost if baseline_cost != 0 else 0.0
    cost_change_with_overhead = (
        (predicted_cost + routing_overhead - baseline_cost) / baseline_cost if baseline_cost != 0 else 0.0
    )

    quality_change = (predicted_quality - baseline_quality) / baseline_quality if baseline_quality != 0 else 0.0
    oracle_quality_change = (oracle_quality - baseline_quality) / baseline_quality if baseline_quality != 0 else 0.0

    return {
        "cost_change": cost_change,
        "cost_change_with_overhead": cost_change_with_overhead,
        "quality_change": quality_change,
        "oracle_cost_change": ((oracle_cost - baseline_cost) / baseline_cost if baseline_cost != 0 else 0.0),
        "oracle_quality_change": oracle_quality_change,
        "oracle_quality_captured": (
            (1 + quality_change) / (1 + oracle_quality_change) if oracle_quality_change != 0.0 else 1.0
        ),
        "oracle_quality": oracle_quality,
        "oracle_cost": oracle_cost,
        "predicted_quality": predicted_quality,
        "predicted_cost": predicted_cost,
        "routing_overhead": routing_overhead,
        "baseline_quality": baseline_quality,
        "baseline_cost": baseline_cost,
    }


def _select_baseline_class(examples: list[Example]) -> str:
    """Select the class with the highest mean quality_score. Tie-break alphabetically."""
    quality_sums: dict[str, float] = {}
    quality_counts: dict[str, int] = {}

    for ex in examples:
        for cls, data in ex.expected.routes.items():
            quality_sums[cls] = quality_sums.get(cls, 0.0) + (data.quality_score or 0.0)
            quality_counts[cls] = quality_counts.get(cls, 0) + 1

    # Highest mean quality; tie-break by alphabetically first class name
    return min(
        quality_sums,
        key=lambda cls: (-quality_sums[cls] / quality_counts[cls], cls),
    )


def create_default_engine() -> DefaultMetricsEngine:
    """Create a DefaultMetricsEngine with all built-in metrics registered."""
    engine = DefaultMetricsEngine()
    engine.register("accuracy", compute_accuracy)
    engine.register("confusion", compute_confusion)
    engine.register("f1", compute_f1)
    engine.register("cost_quality_change", compute_cost_quality_change)
    return engine


def compute_f1(results: list[EvalResult], examples: list[Example]) -> dict[str, float]:
    """Per-class precision, recall, F1, and macro F1."""
    if not results:
        return {"f1/macro": 0.0}

    classes: set[str] = set()
    true_labels: list[str] = []
    pred_labels: list[str] = []
    for r, ex in zip(results, examples, strict=True):
        true_cls = ex.expected.route
        pred_cls = r.output["route"] if r.output else ""
        classes.add(true_cls)
        classes.add(pred_cls)
        true_labels.append(true_cls)
        pred_labels.append(pred_cls)

    out: dict[str, float] = {}
    f1_scores: list[float] = []

    for cls in sorted(classes):
        tp = sum(1 for t, p in zip(true_labels, pred_labels, strict=True) if t == cls and p == cls)
        fp = sum(1 for t, p in zip(true_labels, pred_labels, strict=True) if t != cls and p == cls)
        fn = sum(1 for t, p in zip(true_labels, pred_labels, strict=True) if t == cls and p != cls)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        out[f"precision/{cls}"] = precision
        out[f"recall/{cls}"] = recall
        out[f"f1/{cls}"] = f1
        f1_scores.append(f1)

    out["f1/macro"] = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0

    return out
