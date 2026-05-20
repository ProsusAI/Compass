"""Tests for the metrics engine."""

from __future__ import annotations

import pytest

from compass.eval.metrics import (
    DefaultMetricsEngine,
    compute_accuracy,
    compute_confusion,
    compute_cost_quality_change,
    compute_f1,
    create_default_engine,
)
from compass.eval.models import EvalResult, Example, Expected, MetricConfig

# --- Helpers ---


def _example(id: str, route: str = "gpt-4o") -> Example:
    """Create a minimal Example with expected route."""
    return Example(
        id=id,
        input=f"q-{id}",
        expected=Expected.model_validate(
            {
                "route": route,
                "routes": {
                    "gpt-4o": {"cost": 0.03, "quality_score": 0.95},
                    "claude-sonnet": {"cost": 0.01, "quality_score": 0.88},
                    "haiku": {"cost": 0.002, "quality_score": 0.72},
                },
            }
        ),
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


# --- compute_f1 tests ---


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
    assert out["precision/haiku"] == 0.0
    assert out["recall/haiku"] == 0.0
    assert out["f1/haiku"] == 0.0
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
    assert out["f1/macro"] == pytest.approx(2.0 / 3.0)


def test_f1_empty_results():
    out = compute_f1([], [])
    assert out == {"f1/macro": 0.0}


# --- compute_cost_quality_change tests ---


def _cost_quality_example(id: str, route: str, routes: dict[str, dict[str, float]]) -> Example:
    """Create an Example with explicit per-class cost/quality."""
    return Example(
        id=id,
        input=f"q-{id}",
        expected=Expected.model_validate({"route": route, "routes": routes}),
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

    out = compute_cost_quality_change(results, examples)

    # Baseline (gpt-4o): cost = 0.03*2 = 0.06, quality = 0.95*2 = 1.90
    # Predicted (claude-sonnet): cost = 0.01*2 = 0.02, quality = 0.88*2 = 1.76
    # Oracle: ex-0=claude-sonnet(0.01, 0.88), ex-1=haiku(0.002, 0.72)
    #   cost = 0.012, quality = 1.60
    # Routing overhead = 0 (cost=None on both results)
    assert out["cost_change"] == pytest.approx((0.02 - 0.06) / 0.06)
    assert out["cost_change_with_overhead"] == pytest.approx((0.02 - 0.06) / 0.06)
    assert out["quality_change"] == pytest.approx((1.76 - 1.90) / 1.90)
    assert out["oracle_cost_change"] == pytest.approx((0.012 - 0.06) / 0.06)
    assert out["oracle_quality_change"] == pytest.approx((1.60 - 1.90) / 1.90)
    _qc = (1.76 - 1.90) / 1.90
    _oqc = (1.60 - 1.90) / 1.90
    assert out["oracle_quality_captured"] == pytest.approx((1 + _qc) / (1 + _oqc))
    # Absolute oracle values: ex-0=claude-sonnet(0.88), ex-1=haiku(0.72)
    assert out["oracle_quality"] == pytest.approx(1.60)
    assert out["oracle_cost"] == pytest.approx(0.012)


def test_cost_quality_explicit_baseline():
    """User specifies haiku as baseline instead of auto-select."""
    examples = [_cost_quality_example("ex-0", route="gpt-4o", routes=_ROUTES)]
    results = [_result("ex-0", route="claude-sonnet")]

    out = compute_cost_quality_change(results, examples, baseline_class="haiku")

    # Baseline (haiku): cost = 0.002, quality = 0.72
    # Predicted (claude-sonnet): cost = 0.01, quality = 0.88
    # Oracle (gpt-4o): cost = 0.03, quality = 0.95
    assert out["cost_change"] == pytest.approx((0.01 - 0.002) / 0.002)
    assert out["quality_change"] == pytest.approx((0.88 - 0.72) / 0.72)
    assert out["oracle_cost_change"] == pytest.approx((0.03 - 0.002) / 0.002)
    assert out["oracle_quality_change"] == pytest.approx((0.95 - 0.72) / 0.72)
    _qc = (0.88 - 0.72) / 0.72
    _oqc = (0.95 - 0.72) / 0.72
    assert out["oracle_quality_captured"] == pytest.approx((1 + _qc) / (1 + _oqc))


def test_cost_quality_all_match_baseline():
    """All predictions match baseline — changes are 0."""
    examples = [_cost_quality_example("ex-0", route="gpt-4o", routes=_ROUTES)]
    results = [_result("ex-0", route="gpt-4o")]

    out = compute_cost_quality_change(results, examples, baseline_class="gpt-4o")

    assert out["cost_change"] == 0.0
    assert out["cost_change_with_overhead"] == 0.0
    assert out["quality_change"] == 0.0
    # oracle_quality_change == 0, so oracle_quality_captured defaults to 1.0
    assert out["oracle_quality_captured"] == 1.0


def test_cost_quality_hallucinated_route_skipped(caplog):
    """Predicted route not in expected['routes'] — sample skipped with warning."""
    examples = [
        _cost_quality_example("ex-0", route="gpt-4o", routes=_ROUTES),
        _cost_quality_example("ex-1", route="gpt-4o", routes=_ROUTES),
    ]
    results = [
        _result("ex-0", route="nonexistent-model"),  # hallucinated
        _result("ex-1", route="claude-sonnet"),  # valid
    ]

    out = compute_cost_quality_change(results, examples, baseline_class="gpt-4o")

    # Only ex-1 counted: baseline cost=0.03, pred cost=0.01
    assert out["cost_change"] == pytest.approx((0.01 - 0.03) / 0.03)
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

    out = compute_cost_quality_change(results, examples)

    # Should use alpha-model as baseline (alphabetically first among tied)
    # Baseline: cost=0.05, quality=0.90
    # Predicted: cost=0.01, quality=0.90
    assert out["cost_change"] == pytest.approx((0.01 - 0.05) / 0.05)
    assert out["quality_change"] == 0.0


def test_cost_quality_empty_results():
    out = compute_cost_quality_change([], [])
    assert out["cost_change"] == 0.0
    assert out["cost_change_with_overhead"] == 0.0
    assert out["quality_change"] == 0.0
    assert out["oracle_cost_change"] == 0.0
    assert out["oracle_quality_change"] == 0.0
    assert out["oracle_quality_captured"] == 1.0
    assert out["oracle_quality"] == 0.0
    assert out["oracle_cost"] == 0.0


def test_cost_quality_all_predictions_hallucinated_logs_error(caplog: pytest.LogCaptureFixture):
    """When every prediction is outside expected.routes keys (label namespace mismatch),
    emit a single aggregate logger.error with sample values from each side."""
    examples = [
        _cost_quality_example("ex-0", route="gpt-4o", routes=_ROUTES),
        _cost_quality_example("ex-1", route="haiku", routes=_ROUTES),
    ]
    # Predictions use a different label namespace — none match _ROUTES keys.
    results = [_result("ex-0", route="0_simple"), _result("ex-1", route="1_complex")]

    with caplog.at_level("ERROR", logger="compass.eval.metrics"):
        out = compute_cost_quality_change(results, examples)

    assert out["cost_change"] == 0.0
    assert out["quality_change"] == 0.0

    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) == 1
    msg = error_records[0].getMessage()
    assert "every prediction skipped as hallucination" in msg
    assert "0_simple" in msg
    assert "gpt-4o" in msg or "claude-sonnet" in msg or "haiku" in msg


def test_cost_quality_with_routing_overhead():
    """Routing overhead is included in cost_change_with_overhead but not cost_change."""
    examples = [
        _cost_quality_example("ex-0", route="claude-sonnet", routes=_ROUTES),
        _cost_quality_example("ex-1", route="haiku", routes=_ROUTES),
    ]
    # Each routing call costs 0.005
    results = [
        EvalResult(
            example_id="ex-0",
            model="test-model",
            output={"route": "claude-sonnet"},
            error=None,
            latency_ms=100.0,
            retries=0,
            token_usage=None,
            cost=0.005,
        ),
        EvalResult(
            example_id="ex-1",
            model="test-model",
            output={"route": "claude-sonnet"},
            error=None,
            latency_ms=100.0,
            retries=0,
            token_usage=None,
            cost=0.005,
        ),
    ]

    out = compute_cost_quality_change(results, examples)

    # Baseline (gpt-4o): cost = 0.03*2 = 0.06
    # Predicted (claude-sonnet): cost = 0.01*2 = 0.02
    # Routing overhead: 0.005*2 = 0.01
    assert out["cost_change"] == pytest.approx((0.02 - 0.06) / 0.06)
    assert out["cost_change_with_overhead"] == pytest.approx((0.02 + 0.01 - 0.06) / 0.06)


# --- oracle_quality_captured focused tests ---


class TestOracleQualityCaptured:
    """Focused regression tests for oracle_quality_captured key."""

    def test_normal_positive_case(self):
        """Candidate improves on baseline and tracks oracle — ratio in (0, 1]."""
        # Baseline=haiku(0.72), predicted=claude-sonnet(0.88), oracle=gpt-4o(0.95)
        examples = [_cost_quality_example("ex-0", route="gpt-4o", routes=_ROUTES)]
        results = [_result("ex-0", route="claude-sonnet")]
        out = compute_cost_quality_change(results, examples, baseline_class="haiku")
        qc = (0.88 - 0.72) / 0.72
        oqc = (0.95 - 0.72) / 0.72
        assert out["oracle_quality_captured"] == pytest.approx((1 + qc) / (1 + oqc))
        assert 0.0 <= out["oracle_quality_captured"] <= 1.0

    def test_mixed_sign_stays_in_range(self):
        """Candidate under-routes (quality_change < 0) while oracle improves — result in [0, 1]."""
        routes = {
            "gpt-4o": {"cost": 0.03, "quality_score": 0.95},
            "haiku": {"cost": 0.002, "quality_score": 0.72},
            "claude-sonnet": {"cost": 0.01, "quality_score": 0.88},
        }
        # Baseline=claude-sonnet, candidate always picks haiku (worse), oracle=gpt-4o (better)
        examples = [_cost_quality_example("ex-0", route="gpt-4o", routes=routes)]
        results = [_result("ex-0", route="haiku")]
        out = compute_cost_quality_change(results, examples, baseline_class="claude-sonnet")
        qc = (0.72 - 0.88) / 0.88
        oqc = (0.95 - 0.88) / 0.88
        assert out["quality_change"] < 0
        assert out["oracle_quality_change"] > 0
        assert out["oracle_quality_captured"] == pytest.approx((1 + qc) / (1 + oqc))
        assert 0.0 <= out["oracle_quality_captured"] <= 1.0

    def test_zero_oracle_change_returns_one(self):
        """When oracle_quality_change == 0.0, oracle_quality_captured is 1.0."""
        # Baseline == oracle class (gpt-4o), so oracle_quality_change = 0
        examples = [_cost_quality_example("ex-0", route="gpt-4o", routes=_ROUTES)]
        results = [_result("ex-0", route="claude-sonnet")]
        out = compute_cost_quality_change(results, examples, baseline_class="gpt-4o")
        assert out["oracle_quality_change"] == 0.0
        assert out["oracle_quality_captured"] == 1.0

    def test_empty_results_returns_one(self):
        """zero_result path sets oracle_quality_captured = 1.0."""
        out = compute_cost_quality_change([], [])
        assert out["oracle_quality_captured"] == 1.0


# --- create_default_engine tests ---


def test_create_default_engine_has_all_builtins():
    engine = create_default_engine()
    assert "accuracy" in engine._registry
    assert "confusion" in engine._registry
    assert "f1" in engine._registry
    assert "cost_quality_change" in engine._registry


def test_create_default_engine_satisfies_protocol():
    from compass.eval.protocols import MetricsEngine

    engine = create_default_engine()
    assert isinstance(engine, MetricsEngine)


def test_create_default_engine_computes_accuracy():
    """Integration: factory engine computes accuracy end-to-end."""
    engine = create_default_engine()
    results = [_result("ex-0", route="gpt-4o"), _result("ex-1", route="haiku")]
    examples = [_example("ex-0", route="gpt-4o"), _example("ex-1", route="claude-sonnet")]
    out = engine.compute(results, examples, [MetricConfig(name="accuracy")])
    assert out == {"accuracy": 0.5}
