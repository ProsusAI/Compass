"""Model pricing for cost computation."""

from __future__ import annotations

from pydantic import BaseModel

from odysseus.eval.models import TokenUsage

_SCALE = 1_000_000


class ModelPricing(BaseModel):
    """Per-token pricing for a model.

    Costs are expressed per million tokens (matching provider pricing pages)
    and converted internally.

    Cache write fields default to 0 — only Anthropic 1P uses separate 5m/1h
    cache write billing; OpenAI and Bedrock leave them unset.
    """

    input_cost_per_million_tokens: float
    cached_cost_per_million_tokens: float
    cache_write_5m_cost_per_million_tokens: float = 0.0
    cache_write_1h_cost_per_million_tokens: float = 0.0
    output_cost_per_million_tokens: float

    def compute_cost(self, usage: TokenUsage) -> float:
        """Compute total cost from token usage."""
        return (
            self.input_cost_per_million_tokens * usage.input_tokens
            + self.cached_cost_per_million_tokens * usage.cached_tokens
            + self.cache_write_5m_cost_per_million_tokens * usage.cache_write_5m_tokens
            + self.cache_write_1h_cost_per_million_tokens * usage.cache_write_1h_tokens
            + self.output_cost_per_million_tokens * usage.output_tokens
        ) / _SCALE


def compute_cost(pricing: ModelPricing | None, usage: TokenUsage) -> float | None:
    """Returns cost if pricing is provided, None otherwise."""
    if pricing is None:
        return None
    return pricing.compute_cost(usage)


DEFAULT_PRICING: dict[tuple[str, str], ModelPricing] = {
    # Anthropic
    ("anthropic", "claude-haiku-4-5"): ModelPricing(
        input_cost_per_million_tokens=0.80,
        cached_cost_per_million_tokens=0.08,
        cache_write_5m_cost_per_million_tokens=1.25,
        cache_write_1h_cost_per_million_tokens=2.00,
        output_cost_per_million_tokens=4.00,
    ),
    ("anthropic", "claude-sonnet-4-5"): ModelPricing(
        input_cost_per_million_tokens=3.00,
        cached_cost_per_million_tokens=0.30,
        cache_write_5m_cost_per_million_tokens=3.75,
        cache_write_1h_cost_per_million_tokens=6.00,
        output_cost_per_million_tokens=15.00,
    ),
    ("anthropic", "claude-opus-4"): ModelPricing(
        input_cost_per_million_tokens=15.00,
        cached_cost_per_million_tokens=1.50,
        cache_write_5m_cost_per_million_tokens=18.75,
        cache_write_1h_cost_per_million_tokens=30.00,
        output_cost_per_million_tokens=75.00,
    ),
    # OpenAI
    ("openai", "gpt-5.4"): ModelPricing(
        input_cost_per_million_tokens=2.50,
        cached_cost_per_million_tokens=0.25,
        output_cost_per_million_tokens=15.00,
    ),
    ("openai", "gpt-5.4-mini"): ModelPricing(
        input_cost_per_million_tokens=0.75,
        cached_cost_per_million_tokens=0.075,
        output_cost_per_million_tokens=4.50,
    ),
    ("openai", "gpt-5.4-nano"): ModelPricing(
        input_cost_per_million_tokens=0.20,
        cached_cost_per_million_tokens=0.02,
        output_cost_per_million_tokens=1.25,
    ),
    ("openai", "gpt-5.2"): ModelPricing(
        input_cost_per_million_tokens=1.75,
        cached_cost_per_million_tokens=0.175,
        output_cost_per_million_tokens=14.00,
    ),
    ("openai", "gpt-5.1"): ModelPricing(
        input_cost_per_million_tokens=1.25,
        cached_cost_per_million_tokens=0.125,
        output_cost_per_million_tokens=10.00,
    ),
    ("openai", "gpt-5"): ModelPricing(
        input_cost_per_million_tokens=1.25,
        cached_cost_per_million_tokens=0.125,
        output_cost_per_million_tokens=10.00,
    ),
    ("openai", "gpt-5-mini"): ModelPricing(
        input_cost_per_million_tokens=0.25,
        cached_cost_per_million_tokens=0.025,
        output_cost_per_million_tokens=2.00,
    ),
    ("openai", "gpt-5-nano"): ModelPricing(
        input_cost_per_million_tokens=0.05,
        cached_cost_per_million_tokens=0.005,
        output_cost_per_million_tokens=0.40,
    ),
    ("openai", "gpt-4.1"): ModelPricing(
        input_cost_per_million_tokens=2.00,
        cached_cost_per_million_tokens=0.50,
        output_cost_per_million_tokens=8.00,
    ),
    ("openai", "gpt-4.1-mini"): ModelPricing(
        input_cost_per_million_tokens=0.40,
        cached_cost_per_million_tokens=0.10,
        output_cost_per_million_tokens=1.60,
    ),
    ("openai", "gpt-4.1-nano"): ModelPricing(
        input_cost_per_million_tokens=0.10,
        cached_cost_per_million_tokens=0.025,
        output_cost_per_million_tokens=0.40,
    ),
    ("openai", "o4-mini"): ModelPricing(
        input_cost_per_million_tokens=1.10,
        cached_cost_per_million_tokens=0.275,
        output_cost_per_million_tokens=4.40,
    ),
}


def get_default_pricing(provider: str, model: str) -> ModelPricing | None:
    """Look up default pricing for a (provider, model) pair.

    Returns None if the combination is not in the table.
    """
    return DEFAULT_PRICING.get((provider, model))
