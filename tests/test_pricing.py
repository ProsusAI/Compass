"""Tests for model pricing."""

from odysseus.eval.models import TokenUsage
from odysseus.eval.pricing import ModelPricing, compute_cost, get_default_pricing


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


class TestDefaultPricing:
    def test_known_anthropic_model_resolves(self) -> None:
        pricing = get_default_pricing("anthropic", "claude-haiku-4-5")
        assert pricing is not None
        assert isinstance(pricing, ModelPricing)
        assert pricing.input_cost_per_million_tokens == 0.80

    def test_known_openai_model_resolves(self) -> None:
        pricing = get_default_pricing("openai", "gpt-4.1")
        assert pricing is not None
        assert pricing.input_cost_per_million_tokens == 2.00

    def test_unknown_model_returns_none(self) -> None:
        pricing = get_default_pricing("anthropic", "nonexistent-model")
        assert pricing is None

    def test_unknown_provider_returns_none(self) -> None:
        pricing = get_default_pricing("unknown_provider", "some-model")
        assert pricing is None

    def test_all_entries_are_model_pricing(self) -> None:
        from odysseus.eval.pricing import DEFAULT_PRICING

        for key, value in DEFAULT_PRICING.items():
            assert isinstance(key, tuple) and len(key) == 2, f"Key {key} should be (provider, model)"
            assert isinstance(value, ModelPricing), f"Value for {key} should be ModelPricing"
