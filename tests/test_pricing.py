"""Tests for model pricing."""

from odysseus.eval.models import TokenUsage
from odysseus.eval.pricing import ModelPricing, compute_cost


def test_model_pricing_compute_cost():
    pricing = ModelPricing(
        input_cost_per_million_tokens=3.0,
        cached_cost_per_million_tokens=0.3,
        output_cost_per_million_tokens=15.0,
    )
    usage = TokenUsage(input_tokens=1000, cached_tokens=500, output_tokens=200)
    cost = pricing.compute_cost(usage)
    expected = (3.0 * 1000 + 0.3 * 500 + 15.0 * 200) / 1_000_000
    assert abs(cost - expected) < 1e-12


def test_compute_cost_with_pricing():
    pricing = ModelPricing(
        input_cost_per_million_tokens=3.0,
        cached_cost_per_million_tokens=0.3,
        output_cost_per_million_tokens=15.0,
    )
    usage = TokenUsage(input_tokens=100, cached_tokens=0, output_tokens=50)
    cost = compute_cost(pricing, usage)
    assert cost is not None
    assert cost > 0


def test_compute_cost_none_pricing():
    usage = TokenUsage(input_tokens=100, cached_tokens=0, output_tokens=50)
    cost = compute_cost(None, usage)
    assert cost is None
