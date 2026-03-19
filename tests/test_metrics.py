"""Tests for the metrics engine."""

from __future__ import annotations

import pytest

from odysseus.eval.metrics import DefaultMetricsEngine, compute_accuracy, compute_confusion
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


# --- compute_accuracy tests ---


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
    out = compute_accuracy(results, examples)
    assert out == {"accuracy": 0.5}


def test_accuracy_empty_results():
    out = compute_accuracy([], [])
    assert out == {"accuracy": 0.0}


# --- compute_confusion tests ---


def test_confusion_basic():
    """3 samples: 2 correct, 1 misrouted."""
    results = [
        _result("ex-0", route="gpt-4o"),
        _result("ex-1", route="claude-sonnet"),
        _result("ex-2", route="haiku"),
    ]
    examples = [
        _example("ex-0", route="gpt-4o"),
        _example("ex-1", route="claude-sonnet"),
        _example("ex-2", route="claude-sonnet"),
    ]
    out = compute_confusion(results, examples)
    assert out["confusion/gpt-4o/gpt-4o"] == 1.0
    assert out["confusion/claude-sonnet/claude-sonnet"] == 1.0
    assert out["confusion/claude-sonnet/haiku"] == 1.0
    assert out["confusion/gpt-4o/claude-sonnet"] == 0.0
    assert out["confusion/gpt-4o/haiku"] == 0.0
    assert out["confusion/haiku/gpt-4o"] == 0.0
    assert out["confusion/haiku/claude-sonnet"] == 0.0
    assert out["confusion/haiku/haiku"] == 0.0
    assert out["confusion/claude-sonnet/gpt-4o"] == 0.0


def test_confusion_empty_results():
    out = compute_confusion([], [])
    assert out == {}
