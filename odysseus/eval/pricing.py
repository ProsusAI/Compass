"""Model pricing for cost computation."""

from __future__ import annotations

from odysseus.eval.models import TokenUsage
from pydantic import BaseModel


class ModelPricing(BaseModel):
    """Per-token pricing for a model."""

    input_cost_per_token: float
    cached_cost_per_token: float
    output_cost_per_token: float

    def compute_cost(self, usage: TokenUsage) -> float:
        """Compute total cost from token usage."""
        return (
            self.input_cost_per_token * usage.input_tokens
            + self.cached_cost_per_token * usage.cached_tokens
            + self.output_cost_per_token * usage.output_tokens
        )


MODEL_PRICING: dict[str, ModelPricing] = {
    "claude-sonnet-4-20250514": ModelPricing(
        input_cost_per_token=3.0 / 1_000_000,
        cached_cost_per_token=0.3 / 1_000_000,
        output_cost_per_token=15.0 / 1_000_000,
    ),
    "claude-haiku-4-5-20251001": ModelPricing(
        input_cost_per_token=0.80 / 1_000_000,
        cached_cost_per_token=0.08 / 1_000_000,
        output_cost_per_token=4.0 / 1_000_000,
    ),
    "gpt-4o": ModelPricing(
        input_cost_per_token=2.50 / 1_000_000,
        cached_cost_per_token=1.25 / 1_000_000,
        output_cost_per_token=10.0 / 1_000_000,
    ),
    "gpt-4o-mini": ModelPricing(
        input_cost_per_token=0.15 / 1_000_000,
        cached_cost_per_token=0.075 / 1_000_000,
        output_cost_per_token=0.60 / 1_000_000,
    ),
}


def compute_cost(model: str, usage: TokenUsage) -> float | None:
    """Returns cost if model is in MODEL_PRICING, None otherwise."""
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return None
    return pricing.compute_cost(usage)
