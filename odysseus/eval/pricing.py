"""Model pricing for cost computation."""

from __future__ import annotations

from pydantic import BaseModel

from odysseus.eval.models import TokenUsage

_SCALE = 1_000_000


class ModelPricing(BaseModel):
    """Per-token pricing for a model.

    Costs are expressed per million tokens (matching provider pricing pages)
    and converted internally.
    """

    input_cost_per_million_tokens: float
    cached_cost_per_million_tokens: float
    output_cost_per_million_tokens: float

    def compute_cost(self, usage: TokenUsage) -> float:
        """Compute total cost from token usage."""
        return (
            self.input_cost_per_million_tokens * usage.input_tokens
            + self.cached_cost_per_million_tokens * usage.cached_tokens
            + self.output_cost_per_million_tokens * usage.output_tokens
        ) / _SCALE


def compute_cost(pricing: ModelPricing | None, usage: TokenUsage) -> float | None:
    """Returns cost if pricing is provided, None otherwise."""
    if pricing is None:
        return None
    return pricing.compute_cost(usage)
