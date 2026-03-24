"""Bedrock backend — Anthropic models via AWS Bedrock using the Anthropic SDK."""

from __future__ import annotations

from typing import Any

import anthropic
import boto3

from odysseus.eval.backends.profile import BackendProfile
from odysseus.eval.models import Example, TokenUsage
from odysseus.eval.pricing import ModelPricing


class BedrockBackend:
    def __init__(self, profile: BackendProfile) -> None:
        self._profile = profile
        session_kwargs = {k: v for k, v in profile.provider_params.items() if k != "region_name"}
        region = profile.provider_params.get("region_name")

        session = boto3.Session(**session_kwargs)
        client_kwargs: dict[str, Any] = {"aws_session": session}
        if region:
            client_kwargs["aws_region"] = region

        self._client = anthropic.AsyncAnthropicBedrock(**client_kwargs)

    @property
    def model_name(self) -> str:
        return self._profile.model

    @property
    def pricing(self) -> ModelPricing | None:
        return self._profile.pricing

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        kwargs: dict[str, Any] = {}
        if self._profile.max_tokens is not None:
            kwargs["max_tokens"] = self._profile.max_tokens
        else:
            kwargs["max_tokens"] = 1024
        if self._profile.temperature is not None:
            kwargs["temperature"] = self._profile.temperature
        kwargs.update(self._profile.extra_params)

        response = await self._client.messages.create(
            model=self._profile.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )

        usage = response.usage
        token_usage = TokenUsage(
            input_tokens=usage.input_tokens,
            cached_tokens=getattr(usage, "cache_read_input_tokens", 0),
            output_tokens=usage.output_tokens,
        )
        output = {"content": response.content[0].text}
        return output, token_usage
