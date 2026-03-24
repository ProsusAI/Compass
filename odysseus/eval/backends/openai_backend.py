"""OpenAI backend — direct SDK client for OpenAI API."""

from __future__ import annotations

import os
from typing import Any

import openai

from odysseus.eval.backends.profile import BackendProfile
from odysseus.eval.models import Example, TokenUsage
from odysseus.eval.pricing import ModelPricing


class OpenAIBackend:
    def __init__(self, profile: BackendProfile) -> None:
        self._profile = profile
        api_key: str | None = None
        if profile.api_key_env:
            api_key = os.environ[profile.api_key_env]

        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if profile.api_base:
            client_kwargs["base_url"] = profile.api_base
        client_kwargs.update(profile.provider_params)

        self._client = openai.AsyncOpenAI(**client_kwargs)

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
        if self._profile.temperature is not None:
            kwargs["temperature"] = self._profile.temperature
        kwargs.update(self._profile.extra_params)

        response = await self._client.chat.completions.create(
            model=self._profile.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )

        usage = response.usage
        assert usage is not None, "OpenAI response missing usage data"
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) or 0

        token_usage = TokenUsage(
            input_tokens=usage.prompt_tokens or 0,
            cached_tokens=cached,
            output_tokens=usage.completion_tokens or 0,
        )
        output = {"content": response.choices[0].message.content}
        return output, token_usage
