"""Backend profile model — validated configuration loaded from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from compass.eval.pricing import ModelPricing


class BackendProfile(BaseModel):
    """Validated backend configuration loaded from YAML."""

    model: str
    provider: Literal["anthropic", "openai", "bedrock", "mock_echo"] = "anthropic"
    pricing: ModelPricing | None = None
    api_key_env: str | None = None
    api_base: str | None = None

    requests_per_minute: int
    tokens_per_minute: int

    max_tokens: int | None = None
    temperature: float | None = None
    reasoning_level: Literal["low", "medium", "high"] | None = None
    extra_params: dict[str, Any] = Field(default_factory=dict)
    provider_params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model")
    @classmethod
    def model_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("model must be non-empty")
        return v.strip()

    @field_validator("requests_per_minute", "tokens_per_minute")
    @classmethod
    def rate_limits_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("must be >= 1")
        return v

    @classmethod
    def from_yaml(cls, path: str | Path) -> BackendProfile:
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Expected a YAML mapping in {path}, got {type(data).__name__}")
        return cls(**data)
