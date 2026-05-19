"""Anthropic backend — direct SDK client for Anthropic API."""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from odysseus.eval.backends.profile import BackendProfile
from odysseus.eval.models import Example, TokenUsage
from odysseus.eval.pricing import ModelPricing

REASONING_BUDGET_MAP: dict[str, int] = {"low": 1024, "medium": 4096, "high": 16384}


class AnthropicBackend:
    def __init__(self, profile: BackendProfile) -> None:
        self._profile = profile
        api_key: str | None = None
        if profile.api_key_env:
            api_key = os.environ.get(profile.api_key_env)
            if api_key is None:
                raise ValueError(
                    f"Environment variable '{profile.api_key_env}' is not set. "
                    f"Add it to your MCP server's env configuration (mcp.json)."
                )

        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if profile.api_base:
            client_kwargs["base_url"] = profile.api_base
        client_kwargs.update(profile.provider_params)

        self._client = anthropic.AsyncAnthropic(**client_kwargs)

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
        if self._profile.reasoning_level is not None:
            budget = REASONING_BUDGET_MAP[self._profile.reasoning_level]
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}

        response = await self._client.messages.create(
            model=self._profile.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )

        usage = response.usage
        cache_creation = getattr(usage, "cache_creation", None)
        token_usage = TokenUsage(
            input_tokens=usage.input_tokens,
            cached_tokens=getattr(usage, "cache_read_input_tokens", 0),
            cache_write_5m_tokens=getattr(cache_creation, "ephemeral_5m_input_tokens", 0) if cache_creation else 0,
            cache_write_1h_tokens=getattr(cache_creation, "ephemeral_1h_input_tokens", 0) if cache_creation else 0,
            output_tokens=usage.output_tokens,
        )
        content = response.content[0].text
        try:
            output: dict[str, Any] = json.loads(content)
        except (json.JSONDecodeError, ValueError) as err:
            raise ValueError(f"Model returned non-JSON output: {content[:200]}") from err
        if "route" not in output:
            raise ValueError(f"Model output missing 'route' key: {json.dumps(output)[:200]}")
        return output, token_usage
