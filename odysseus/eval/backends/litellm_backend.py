"""LiteLLM backend — unified client for all LLM providers."""

from __future__ import annotations

import os
from typing import Any

import litellm
from pydantic import SecretStr

from odysseus.eval.backends.profile import BackendProfile
from odysseus.eval.models import Example, TokenUsage


class LiteLLMBackend:
    def __init__(self, profile: BackendProfile) -> None:
        self._profile = profile
        self._api_key: SecretStr | None = None
        if profile.api_key_env:
            self._api_key = SecretStr(os.environ[profile.api_key_env])

    @property
    def model_name(self) -> str:
        return self._profile.effective_pricing_model

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        kwargs: dict[str, Any] = {}

        if self._api_key:
            kwargs["api_key"] = self._api_key.get_secret_value()
        if self._profile.api_base:
            kwargs["base_url"] = self._profile.api_base
        if self._profile.max_tokens is not None:
            kwargs["max_tokens"] = self._profile.max_tokens
        if self._profile.temperature is not None:
            kwargs["temperature"] = self._profile.temperature

        kwargs.update(self._profile.provider_params)
        kwargs.update(self._profile.extra_params)

        response = await litellm.acompletion(
            model=self._profile.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )

        usage = response.usage
        token_usage = TokenUsage(
            input_tokens=usage.prompt_tokens,
            cached_tokens=getattr(usage, "cache_read_input_tokens", 0),
            output_tokens=usage.completion_tokens,
        )
        output = {"content": response.choices[0].message.content}
        return output, token_usage
