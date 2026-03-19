"""Tests for model pricing."""

from odysseus.eval.models import TokenUsage
from odysseus.eval.pricing import MODEL_PRICING, ModelPricing, compute_cost


def test_model_pricing_compute_cost():
    pricing = ModelPricing(
        input_cost_per_token=3.0 / 1_000_000,
        cached_cost_per_token=0.3 / 1_000_000,
        output_cost_per_token=15.0 / 1_000_000,
    )
    usage = TokenUsage(input_tokens=1000, cached_tokens=500, output_tokens=200)
    cost = pricing.compute_cost(usage)
    expected = (3.0 * 1000 + 0.3 * 500 + 15.0 * 200) / 1_000_000
    assert abs(cost - expected) < 1e-12


def test_compute_cost_known_model():
    usage = TokenUsage(input_tokens=100, cached_tokens=0, output_tokens=50)
    cost = compute_cost("claude-sonnet-4-20250514", usage)
    assert cost is not None
    assert cost > 0


def test_compute_cost_unknown_model():
    usage = TokenUsage(input_tokens=100, cached_tokens=0, output_tokens=50)
    cost = compute_cost("unknown-model", usage)
    assert cost is None


def test_model_pricing_dict_not_empty():
    assert len(MODEL_PRICING) > 0
