"""Mock echo backend — returns expected route without API calls."""

from __future__ import annotations

from typing import Any

from odysseus.eval.backends.profile import BackendProfile
from odysseus.eval.models import Example, TokenUsage
from odysseus.eval.pricing import ModelPricing


class MockEchoBackend:
    """Backend that echoes the expected route from the example.

    Used for integration testing without real API keys. Returns
    output in the same format the accuracy metric expects.
    """

    def __init__(self, profile: BackendProfile) -> None:
        self._profile = profile

    @property
    def model_name(self) -> str:
        return self._profile.model

    @property
    def pricing(self) -> ModelPricing | None:
        return self._profile.pricing

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        route = example.expected.get("route", "unknown")
        output = {"route": route}
        usage = TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5)
        return output, usage
