# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Mock echo backend — returns expected route without API calls."""

from __future__ import annotations

from typing import Any

from compass.eval.backends.profile import BackendProfile
from compass.eval.models import Example, TokenUsage
from compass.eval.pricing import ModelPricing


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
        route = example.expected.route
        output = {"route": route}
        usage = TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5)
        return output, usage
