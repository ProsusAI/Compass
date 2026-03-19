# THP-88 Metrics Engine Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a metrics engine with dynamic metric registration that computes routing-evaluation metrics (accuracy, confusion matrix, per-class F1, cost/quality reduction) over prediction results and ground-truth data.

**Architecture:** Flat function registry in a single `DefaultMetricsEngine` class. Each metric is a stateless function registered by name. The engine pairs results with examples, filters errors, dispatches to registered functions, and merges returned dicts. Protocol updated to pass `examples` alongside `results`.

**Tech Stack:** Pydantic v2 models, pytest, Python `collections.Counter`

**Spec:** `docs/superpowers/specs/2026-03-19-thp88-metrics-engine-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `odysseus/eval/metrics.py` | Create | `DefaultMetricsEngine` class, all built-in metric functions, `create_default_engine()` factory, `MetricFn` type alias |
| `odysseus/eval/protocols.py` | Modify | Add `examples: list[Example]` param to `MetricsEngine.compute()` signature |
| `odysseus/eval/controller.py` | Modify | Pass `examples` to `deps.metrics_engine.compute()` call in `run()` |
| `tests/test_controller.py` | Modify | Update `MockMetricsEngine.compute()` signature to accept `examples` param |
| `tests/test_metrics.py` | Create | Full test coverage for engine and all built-in metrics |

---

## Chunk 1: Protocol update and engine skeleton

### Task 1: Update MetricsEngine protocol to include `examples`

**Files:**
- Modify: `odysseus/eval/protocols.py:43-47`
- Modify: `tests/test_controller.py:95-100`
- Modify: `odysseus/eval/controller.py:66`

- [ ] **Step 1: Update the MetricsEngine protocol signature**

In `odysseus/eval/protocols.py`, replace the `MetricsEngine` protocol's `compute` method:

```python
@runtime_checkable
class MetricsEngine(Protocol):
    """Computes metrics over evaluation results."""

    def compute(
        self,
        results: list[EvalResult],
        examples: list[Example],
        metric_configs: list[MetricConfig],
    ) -> dict[str, float]: ...
```

- [ ] **Step 2: Update MockMetricsEngine in controller tests**

In `tests/test_controller.py`, update the `MockMetricsEngine.compute` method signature to match:

```python
class MockMetricsEngine:
    def __init__(self, metrics: dict[str, float] | None = None):
        self._metrics = metrics or {"accuracy": 1.0}

    def compute(
        self, results: list[EvalResult], examples: list[Example], metric_configs: list[MetricConfig]
    ) -> dict[str, float]:
        return self._metrics
```

Note: `Example` is already imported in `tests/test_controller.py` (line 9).

- [ ] **Step 3: Update controller call site**

In `odysseus/eval/controller.py`, change line 66 from:

```python
    metrics = deps.metrics_engine.compute(list(results), config.metrics)
```

to:

```python
    metrics = deps.metrics_engine.compute(list(results), examples, config.metrics)
```

- [ ] **Step 4: Run existing tests to verify nothing broke**

Run: `uv run pytest tests/test_controller.py tests/test_models.py -v`

Expected: ALL existing tests PASS.

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/protocols.py odysseus/eval/controller.py tests/test_controller.py
git commit -m "feat(eval): add examples param to MetricsEngine protocol"
```

---

### Task 2: Engine skeleton — register, lookup, filter, merge

**Files:**
- Create: `odysseus/eval/metrics.py`
- Create: `tests/test_metrics.py`

- [ ] **Step 1: Write failing tests for engine core behavior**

Create `tests/test_metrics.py`:

```python
"""Tests for the metrics engine."""

from __future__ import annotations

import pytest

from odysseus.eval.metrics import DefaultMetricsEngine
from odysseus.eval.models import EvalResult, Example, MetricConfig


# --- Helpers ---


def _example(id: str, route: str = "gpt-4o") -> Example:
    """Create a minimal Example with expected route."""
    return Example(
        id=id,
        input={"query": f"q-{id}"},
        expected={
            "route": route,
            "routes": {
                "gpt-4o": {"cost": 0.03, "quality_score": 0.95},
                "claude-sonnet": {"cost": 0.01, "quality_score": 0.88},
                "haiku": {"cost": 0.002, "quality_score": 0.72},
            },
        },
    )


def _result(example_id: str, route: str = "gpt-4o", error: str | None = None) -> EvalResult:
    """Create a minimal EvalResult with predicted route."""
    return EvalResult(
        example_id=example_id,
        model="test-model",
        output={"route": route} if error is None else None,
        error=error,
        latency_ms=100.0,
        retries=0,
        token_usage=None,
        cost=None,
    )


# --- Engine tests ---


def test_unknown_metric_raises_value_error():
    engine = DefaultMetricsEngine()
    with pytest.raises(ValueError, match="not_registered"):
        engine.compute(
            [_result("ex-0")],
            [_example("ex-0")],
            [MetricConfig(name="not_registered")],
        )


def test_custom_metric_via_register():
    engine = DefaultMetricsEngine()
    engine.register("custom", lambda results, examples: {"custom_val": 0.42})
    out = engine.compute(
        [_result("ex-0")],
        [_example("ex-0")],
        [MetricConfig(name="custom")],
    )
    assert out == {"custom_val": 0.42}


def test_errored_results_filtered_out():
    engine = DefaultMetricsEngine()
    call_counts: list[int] = []

    def counting_metric(results: list, examples: list) -> dict[str, float]:
        call_counts.append(len(results))
        return {"count": float(len(results))}

    engine.register("counter", counting_metric)
    out = engine.compute(
        [_result("ex-0"), _result("ex-1", error="boom")],
        [_example("ex-0"), _example("ex-1")],
        [MetricConfig(name="counter")],
    )
    assert out == {"count": 1.0}
    assert call_counts == [1]


def test_empty_results_after_filtering():
    engine = DefaultMetricsEngine()
    engine.register("dummy", lambda results, examples: {"val": float(len(results))})
    out = engine.compute(
        [_result("ex-0", error="fail")],
        [_example("ex-0")],
        [MetricConfig(name="dummy")],
    )
    assert out == {"val": 0.0}


def test_duplicate_keys_raise_value_error():
    engine = DefaultMetricsEngine()
    engine.register("m1", lambda r, e: {"shared_key": 1.0})
    engine.register("m2", lambda r, e: {"shared_key": 2.0})
    with pytest.raises(ValueError, match="shared_key"):
        engine.compute(
            [_result("ex-0")],
            [_example("ex-0")],
            [MetricConfig(name="m1"), MetricConfig(name="m2")],
        )


def test_params_passed_to_metric_function():
    engine = DefaultMetricsEngine()

    def param_echo(results: list, examples: list, **params) -> dict[str, float]:
        return {k: float(v) for k, v in params.items()}

    engine.register("echo", param_echo)
    out = engine.compute(
        [_result("ex-0")],
        [_example("ex-0")],
        [MetricConfig(name="echo", params={"alpha": 0.5, "beta": 1.0})],
    )
    assert out == {"alpha": 0.5, "beta": 1.0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_metrics.py -v`

Expected: FAIL — `odysseus.eval.metrics` module does not exist yet.

- [ ] **Step 3: Implement DefaultMetricsEngine**

Create `odysseus/eval/metrics.py`:

```python
"""Metrics engine with dynamic metric registration."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from typing import Any

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
                    raise ValueError(
                        f"Duplicate metric key {key!r} — two metrics produced the same key"
                    )
                merged[key] = value

        return merged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_metrics.py -v`

Expected: ALL `test_*` in `tests/test_metrics.py` PASS.

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/metrics.py tests/test_metrics.py
git commit -m "feat(eval): add DefaultMetricsEngine with register/compute/filter"
```

---

## Chunk 2: Accuracy and confusion metrics

### Task 3: `compute_accuracy` metric

**Files:**
- Modify: `tests/test_metrics.py`
- Modify: `odysseus/eval/metrics.py`

- [ ] **Step 1: Write failing tests for accuracy**

Add to `tests/test_metrics.py`:

```python
from odysseus.eval.metrics import compute_accuracy


def test_accuracy_all_correct():
    results = [_result("ex-0", route="gpt-4o"), _result("ex-1", route="claude-sonnet")]
    examples = [_example("ex-0", route="gpt-4o"), _example("ex-1", route="claude-sonnet")]
    out = compute_accuracy(results, examples)
    assert out == {"accuracy": 1.0}


def test_accuracy_all_wrong():
    results = [_result("ex-0", route="haiku"), _result("ex-1", route="haiku")]
    examples = [_example("ex-0", route="gpt-4o"), _example("ex-1", route="claude-sonnet")]
    out = compute_accuracy(results, examples)
    assert out == {"accuracy": 0.0}


def test_accuracy_mixed():
    results = [
        _result("ex-0", route="gpt-4o"),
        _result("ex-1", route="haiku"),
        _result("ex-2", route="claude-sonnet"),
        _result("ex-3", route="gpt-4o"),
    ]
    examples = [
        _example("ex-0", route="gpt-4o"),
        _example("ex-1", route="claude-sonnet"),
        _example("ex-2", route="claude-sonnet"),
        _example("ex-3", route="haiku"),
    ]
    # 2 correct (ex-0, ex-2) out of 4
    out = compute_accuracy(results, examples)
    assert out == {"accuracy": 0.5}


def test_accuracy_empty_results():
    out = compute_accuracy([], [])
    assert out == {"accuracy": 0.0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_metrics.py -v -k "accuracy"`

Expected: FAIL — `compute_accuracy` not yet defined.

- [ ] **Step 3: Implement compute_accuracy**

Add to `odysseus/eval/metrics.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_metrics.py -v -k "accuracy"`

Expected: ALL `test_accuracy_*` PASS.

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/metrics.py tests/test_metrics.py
git commit -m "feat(eval): add compute_accuracy metric"
```

---

### Task 4: `compute_confusion` metric

**Files:**
- Modify: `tests/test_metrics.py`
- Modify: `odysseus/eval/metrics.py`

- [ ] **Step 1: Write failing tests for confusion matrix**

Add to `tests/test_metrics.py`:

```python
from odysseus.eval.metrics import compute_confusion


def test_confusion_basic():
    """3 samples: 2 correct, 1 misrouted."""
    results = [
        _result("ex-0", route="gpt-4o"),
        _result("ex-1", route="claude-sonnet"),
        _result("ex-2", route="haiku"),  # misrouted
    ]
    examples = [
        _example("ex-0", route="gpt-4o"),
        _example("ex-1", route="claude-sonnet"),
        _example("ex-2", route="claude-sonnet"),  # true=claude-sonnet, pred=haiku
    ]
    out = compute_confusion(results, examples)
    assert out["confusion/gpt-4o/gpt-4o"] == 1.0
    assert out["confusion/claude-sonnet/claude-sonnet"] == 1.0
    assert out["confusion/claude-sonnet/haiku"] == 1.0
    # Zero cells should also be present
    assert out["confusion/gpt-4o/claude-sonnet"] == 0.0
    assert out["confusion/gpt-4o/haiku"] == 0.0
    assert out["confusion/haiku/gpt-4o"] == 0.0
    assert out["confusion/haiku/claude-sonnet"] == 0.0
    assert out["confusion/haiku/haiku"] == 0.0
    assert out["confusion/claude-sonnet/gpt-4o"] == 0.0


def test_confusion_empty_results():
    out = compute_confusion([], [])
    assert out == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_metrics.py -v -k "confusion"`

Expected: FAIL — `compute_confusion` not yet defined.

- [ ] **Step 3: Implement compute_confusion**

Add to `odysseus/eval/metrics.py`:

```python
def compute_confusion(
    results: list[EvalResult], examples: list[Example]
) -> dict[str, float]:
    """Confusion matrix as flat dict keyed by confusion/{true}/{predicted}."""
    if not results:
        return {}

    # Collect all unique classes from both true and predicted
    classes: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for r, ex in zip(results, examples):
        true_class = ex.expected["route"]
        pred_class = r.output["route"] if r.output else ""
        classes.add(true_class)
        classes.add(pred_class)
        pairs.append((true_class, pred_class))

    # Count
    counts = Counter(pairs)

    # Build full matrix (including zero cells)
    sorted_classes = sorted(classes)
    out: dict[str, float] = {}
    for true_cls in sorted_classes:
        for pred_cls in sorted_classes:
            out[f"confusion/{true_cls}/{pred_cls}"] = float(counts.get((true_cls, pred_cls), 0))

    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_metrics.py -v -k "confusion"`

Expected: ALL `test_confusion_*` PASS.

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/metrics.py tests/test_metrics.py
git commit -m "feat(eval): add compute_confusion metric"
```

---

## Chunk 3: F1 metric

### Task 5: `compute_f1` metric (per-class precision, recall, F1, macro)

**Files:**
- Modify: `tests/test_metrics.py`
- Modify: `odysseus/eval/metrics.py`

- [ ] **Step 1: Write failing tests for F1**

Add to `tests/test_metrics.py`:

```python
from odysseus.eval.metrics import compute_f1


def test_f1_perfect_predictions():
    results = [_result("ex-0", route="gpt-4o"), _result("ex-1", route="claude-sonnet")]
    examples = [_example("ex-0", route="gpt-4o"), _example("ex-1", route="claude-sonnet")]
    out = compute_f1(results, examples)
    assert out["f1/gpt-4o"] == 1.0
    assert out["precision/gpt-4o"] == 1.0
    assert out["recall/gpt-4o"] == 1.0
    assert out["f1/claude-sonnet"] == 1.0
    assert out["f1/macro"] == 1.0


def test_f1_class_with_zero_predictions():
    """haiku has true samples but zero predictions — precision=0, recall=0, f1=0."""
    results = [
        _result("ex-0", route="gpt-4o"),
        _result("ex-1", route="gpt-4o"),  # misrouted: true=haiku, pred=gpt-4o
    ]
    examples = [
        _example("ex-0", route="gpt-4o"),
        _example("ex-1", route="haiku"),
    ]
    out = compute_f1(results, examples)
    # haiku: TP=0, FP=0, FN=1 => precision=0, recall=0, f1=0
    assert out["precision/haiku"] == 0.0
    assert out["recall/haiku"] == 0.0
    assert out["f1/haiku"] == 0.0
    # gpt-4o: TP=1, FP=1, FN=0 => precision=0.5, recall=1.0, f1=2/3
    assert out["precision/gpt-4o"] == pytest.approx(0.5)
    assert out["recall/gpt-4o"] == 1.0
    assert out["f1/gpt-4o"] == pytest.approx(2.0 / 3.0)


def test_f1_macro_averages_across_classes():
    """Macro F1 is unweighted average across all classes."""
    results = [
        _result("ex-0", route="gpt-4o"),
        _result("ex-1", route="gpt-4o"),
        _result("ex-2", route="claude-sonnet"),
    ]
    examples = [
        _example("ex-0", route="gpt-4o"),
        _example("ex-1", route="claude-sonnet"),
        _example("ex-2", route="claude-sonnet"),
    ]
    out = compute_f1(results, examples)
    # gpt-4o: TP=1, FP=1, FN=0 => P=0.5, R=1.0, F1=2/3
    # claude-sonnet: TP=1, FP=0, FN=1 => P=1.0, R=0.5, F1=2/3
    # macro F1 = (2/3 + 2/3) / 2 = 2/3
    assert out["f1/macro"] == pytest.approx(2.0 / 3.0)


def test_f1_empty_results():
    out = compute_f1([], [])
    assert out == {"f1/macro": 0.0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_metrics.py -v -k "f1"`

Expected: FAIL — `compute_f1` not yet defined.

- [ ] **Step 3: Implement compute_f1**

Add to `odysseus/eval/metrics.py`:

```python
def compute_f1(
    results: list[EvalResult], examples: list[Example]
) -> dict[str, float]:
    """Per-class precision, recall, F1, and macro F1."""
    if not results:
        return {"f1/macro": 0.0}

    # Collect true/predicted pairs and all classes
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

    # Per-class TP, FP, FN
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_metrics.py -v -k "f1"`

Expected: ALL `test_f1_*` PASS.

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/metrics.py tests/test_metrics.py
git commit -m "feat(eval): add compute_f1 metric with per-class precision/recall"
```

---

## Chunk 4: Cost/quality reduction metric

### Task 6: `compute_cost_quality_reduction` metric

**Files:**
- Modify: `tests/test_metrics.py`
- Modify: `odysseus/eval/metrics.py`

- [ ] **Step 1: Write failing tests for cost/quality reduction**

Add to `tests/test_metrics.py`:

```python
from odysseus.eval.metrics import compute_cost_quality_reduction


def _cost_quality_example(id: str, route: str, routes: dict[str, dict[str, float]]) -> Example:
    """Create an Example with explicit per-class cost/quality."""
    return Example(
        id=id,
        input={"query": f"q-{id}"},
        expected={"route": route, "routes": routes},
    )


# Shared route costs/quality for cost_quality tests
_ROUTES = {
    "gpt-4o": {"cost": 0.03, "quality_score": 0.95},
    "claude-sonnet": {"cost": 0.01, "quality_score": 0.88},
    "haiku": {"cost": 0.002, "quality_score": 0.72},
}


def test_cost_quality_default_baseline():
    """Auto-selects gpt-4o (highest mean quality=0.95) as baseline."""
    examples = [
        _cost_quality_example("ex-0", route="claude-sonnet", routes=_ROUTES),
        _cost_quality_example("ex-1", route="haiku", routes=_ROUTES),
    ]
    # Predict claude-sonnet for both
    results = [_result("ex-0", route="claude-sonnet"), _result("ex-1", route="claude-sonnet")]

    out = compute_cost_quality_reduction(results, examples)

    # Baseline (gpt-4o): cost = 0.03*2 = 0.06, quality = 0.95*2 = 1.90
    # Predicted (claude-sonnet): cost = 0.01*2 = 0.02, quality = 0.88*2 = 1.76
    # Oracle: ex-0=claude-sonnet(0.01, 0.88), ex-1=haiku(0.002, 0.72)
    #   cost = 0.012, quality = 1.60
    assert out["cost_reduction"] == pytest.approx((0.02 - 0.06) / 0.06)
    assert out["quality_reduction"] == pytest.approx((1.76 - 1.90) / 1.90)
    assert out["oracle_cost_reduction"] == pytest.approx((0.012 - 0.06) / 0.06)
    assert out["oracle_quality_reduction"] == pytest.approx((1.60 - 1.90) / 1.90)


def test_cost_quality_explicit_baseline():
    """User specifies haiku as baseline instead of auto-select."""
    examples = [_cost_quality_example("ex-0", route="gpt-4o", routes=_ROUTES)]
    results = [_result("ex-0", route="claude-sonnet")]

    out = compute_cost_quality_reduction(results, examples, baseline_class="haiku")

    # Baseline (haiku): cost = 0.002, quality = 0.72
    # Predicted (claude-sonnet): cost = 0.01, quality = 0.88
    # Oracle (gpt-4o): cost = 0.03, quality = 0.95
    assert out["cost_reduction"] == pytest.approx((0.01 - 0.002) / 0.002)
    assert out["quality_reduction"] == pytest.approx((0.88 - 0.72) / 0.72)
    assert out["oracle_cost_reduction"] == pytest.approx((0.03 - 0.002) / 0.002)
    assert out["oracle_quality_reduction"] == pytest.approx((0.95 - 0.72) / 0.72)


def test_cost_quality_all_match_baseline():
    """All predictions match baseline — reductions are 0."""
    examples = [_cost_quality_example("ex-0", route="gpt-4o", routes=_ROUTES)]
    results = [_result("ex-0", route="gpt-4o")]

    out = compute_cost_quality_reduction(results, examples, baseline_class="gpt-4o")

    assert out["cost_reduction"] == 0.0
    assert out["quality_reduction"] == 0.0


def test_cost_quality_hallucinated_route_skipped(caplog):
    """Predicted route not in expected['routes'] — sample skipped with warning."""
    examples = [
        _cost_quality_example("ex-0", route="gpt-4o", routes=_ROUTES),
        _cost_quality_example("ex-1", route="gpt-4o", routes=_ROUTES),
    ]
    results = [
        _result("ex-0", route="nonexistent-model"),  # hallucinated
        _result("ex-1", route="claude-sonnet"),       # valid
    ]

    out = compute_cost_quality_reduction(results, examples, baseline_class="gpt-4o")

    # Only ex-1 counted: baseline cost=0.03, pred cost=0.01
    assert out["cost_reduction"] == pytest.approx((0.01 - 0.03) / 0.03)
    assert "nonexistent-model" in caplog.text


def test_cost_quality_baseline_tiebreak_alphabetical():
    """When two classes tie on quality, pick alphabetically first."""
    tied_routes = {
        "alpha-model": {"cost": 0.05, "quality_score": 0.90},
        "beta-model": {"cost": 0.01, "quality_score": 0.90},
    }
    examples = [
        _cost_quality_example("ex-0", route="alpha-model", routes=tied_routes),
    ]
    results = [_result("ex-0", route="beta-model")]

    out = compute_cost_quality_reduction(results, examples)

    # Should use alpha-model as baseline (alphabetically first among tied)
    # Baseline: cost=0.05, quality=0.90
    # Predicted: cost=0.01, quality=0.90
    assert out["cost_reduction"] == pytest.approx((0.01 - 0.05) / 0.05)
    assert out["quality_reduction"] == 0.0


def test_cost_quality_empty_results():
    out = compute_cost_quality_reduction([], [])
    assert out["cost_reduction"] == 0.0
    assert out["quality_reduction"] == 0.0
    assert out["oracle_cost_reduction"] == 0.0
    assert out["oracle_quality_reduction"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_metrics.py -v -k "cost_quality"`

Expected: FAIL — `compute_cost_quality_reduction` not yet defined.

- [ ] **Step 3: Implement compute_cost_quality_reduction**

Add to `odysseus/eval/metrics.py`:

```python
def compute_cost_quality_reduction(
    results: list[EvalResult],
    examples: list[Example],
    *,
    baseline_class: str | None = None,
) -> dict[str, float]:
    """Cost and quality percentage change vs baseline, plus oracle reductions.

    Args:
        results: Filtered successful results.
        examples: Matched examples (same order as results).
        baseline_class: Route class to use as baseline. If None, auto-selects
            the class with highest mean quality_score (tie-break alphabetical).
    """
    zero_result = {
        "cost_reduction": 0.0,
        "quality_reduction": 0.0,
        "oracle_cost_reduction": 0.0,
        "oracle_quality_reduction": 0.0,
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
    counted = 0

    for r, ex in zip(results, examples):
        routes = ex.expected["routes"]
        pred_route = r.output["route"] if r.output else None

        # Skip hallucinated routes
        if pred_route is not None and pred_route not in routes:
            logger.warning(
                "Predicted route %r not in expected routes for example %s — skipping",
                pred_route,
                ex.id,
            )
            continue

        oracle_route = ex.expected["route"]

        baseline_cost += routes[baseline_class]["cost"]
        baseline_quality += routes[baseline_class]["quality_score"]
        predicted_cost += routes[pred_route]["cost"] if pred_route else 0.0
        predicted_quality += routes[pred_route]["quality_score"] if pred_route else 0.0
        oracle_cost += routes[oracle_route]["cost"]
        oracle_quality += routes[oracle_route]["quality_score"]
        counted += 1

    if counted == 0:
        return zero_result

    return {
        "cost_reduction": (
            (predicted_cost - baseline_cost) / baseline_cost if baseline_cost != 0 else 0.0
        ),
        "quality_reduction": (
            (predicted_quality - baseline_quality) / baseline_quality
            if baseline_quality != 0
            else 0.0
        ),
        "oracle_cost_reduction": (
            (oracle_cost - baseline_cost) / baseline_cost if baseline_cost != 0 else 0.0
        ),
        "oracle_quality_reduction": (
            (oracle_quality - baseline_quality) / baseline_quality
            if baseline_quality != 0
            else 0.0
        ),
    }


def _select_baseline_class(examples: list[Example]) -> str:
    """Select the class with the highest mean quality_score. Tie-break alphabetically."""
    quality_sums: dict[str, float] = {}
    quality_counts: dict[str, int] = {}

    for ex in examples:
        for cls, data in ex.expected["routes"].items():
            quality_sums[cls] = quality_sums.get(cls, 0.0) + data["quality_score"]
            quality_counts[cls] = quality_counts.get(cls, 0) + 1

    # Highest mean quality; tie-break by alphabetically first class name
    return min(
        quality_sums,
        key=lambda cls: (-quality_sums[cls] / quality_counts[cls], cls),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_metrics.py -v -k "cost_quality"`

Expected: ALL `test_cost_quality_*` PASS.

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/metrics.py tests/test_metrics.py
git commit -m "feat(eval): add compute_cost_quality_reduction metric"
```

---

## Chunk 5: Factory, integration, and final verification

### Task 7: Factory function and registration

**Files:**
- Modify: `tests/test_metrics.py`
- Modify: `odysseus/eval/metrics.py`

- [ ] **Step 1: Write failing test for create_default_engine**

Add to `tests/test_metrics.py`:

```python
from odysseus.eval.metrics import create_default_engine


def test_create_default_engine_has_all_builtins():
    engine = create_default_engine()
    assert "accuracy" in engine._registry
    assert "confusion" in engine._registry
    assert "f1" in engine._registry
    assert "cost_quality_reduction" in engine._registry


def test_create_default_engine_satisfies_protocol():
    from odysseus.eval.protocols import MetricsEngine

    engine = create_default_engine()
    assert isinstance(engine, MetricsEngine)


def test_create_default_engine_computes_accuracy():
    """Integration: factory engine computes accuracy end-to-end."""
    engine = create_default_engine()
    results = [_result("ex-0", route="gpt-4o"), _result("ex-1", route="haiku")]
    examples = [_example("ex-0", route="gpt-4o"), _example("ex-1", route="claude-sonnet")]
    out = engine.compute(results, examples, [MetricConfig(name="accuracy")])
    assert out == {"accuracy": 0.5}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_metrics.py::test_create_default_engine_has_all_builtins -v`

Expected: FAIL — `create_default_engine` not yet defined.

- [ ] **Step 3: Implement create_default_engine**

Add to `odysseus/eval/metrics.py`:

```python
def create_default_engine() -> DefaultMetricsEngine:
    """Create a DefaultMetricsEngine with all built-in metrics registered."""
    engine = DefaultMetricsEngine()
    engine.register("accuracy", compute_accuracy)
    engine.register("confusion", compute_confusion)
    engine.register("f1", compute_f1)
    engine.register("cost_quality_reduction", compute_cost_quality_reduction)
    return engine
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_metrics.py -v -k "create_default_engine"`

Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/metrics.py tests/test_metrics.py
git commit -m "feat(eval): add create_default_engine factory with all builtins"
```

---

### Task 8: Final full test suite and lint

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`

Expected: ALL tests PASS (including existing controller and model tests).

- [ ] **Step 2: Run linter and formatter**

Run: `uv run ruff check odysseus/eval/metrics.py tests/test_metrics.py && uv run ruff format --check odysseus/eval/metrics.py tests/test_metrics.py`

Expected: No errors. If formatting issues, run `uv run ruff format odysseus/eval/metrics.py tests/test_metrics.py` and re-check.

- [ ] **Step 3: Run pyright**

Run: `uv run pyright odysseus/eval/metrics.py`

Expected: No errors.

- [ ] **Step 4: Commit if any formatting fixes were needed**

Only if previous steps required changes:

```bash
git add -u
git commit -m "style: apply ruff formatting to metrics engine"
```
