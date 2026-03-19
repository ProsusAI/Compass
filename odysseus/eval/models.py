"""Data models for the evaluation engine."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class MetricConfig(BaseModel):
    """Configuration for a single metric."""

    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class ConcurrencyConfig(BaseModel):
    """Concurrency and rate limiting settings."""

    max_concurrent_requests: int = 20
    requests_per_minute: int = 500
    tokens_per_minute: int = 100_000


class RetryConfig(BaseModel):
    """Retry behavior for failed backend calls."""

    max_attempts: int = 3
    backoff_factor: float = 2.0
    per_call_timeout_seconds: float = 60.0


class OutputConfig(BaseModel):
    """Paths for writing evaluation outputs."""

    results_path: str = "outputs/results.jsonl"
    report_path: str = "outputs/report.json"


class RunConfig(BaseModel):
    """Top-level configuration for an evaluation run."""

    backend: str
    prompt_version: str = "latest"
    data_source: str
    data_split: Literal["dev", "holdout"]
    metrics: list[MetricConfig]
    concurrency: ConcurrencyConfig = ConcurrencyConfig()
    retry: RetryConfig = RetryConfig()
    output: OutputConfig = OutputConfig()

    @classmethod
    def from_yaml(cls, path: str | Path) -> RunConfig:
        """Load config from a YAML file. Validates via Pydantic on construction."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)


class Example(BaseModel):
    """A single evaluation example."""

    id: str
    input: dict[str, Any]
    expected: dict[str, Any]


class TokenUsage(BaseModel):
    """Token usage for a single API call. Fields are disjoint (Anthropic-style)."""

    input_tokens: int
    cached_tokens: int
    output_tokens: int


class EvalResult(BaseModel):
    """Result of evaluating a single example."""

    example_id: str
    model: str
    output: dict[str, Any] | None
    error: str | None
    latency_ms: float
    retries: int
    token_usage: TokenUsage | None
    cost: float | None


class RunSummary(BaseModel):
    """Aggregate summary of an evaluation run."""

    total: int
    succeeded: int
    failed: int
    total_cost: float
    start_time: datetime
    end_time: datetime
    duration_seconds: float


class RunReport(BaseModel):
    """Complete report for an evaluation run."""

    config: RunConfig
    metrics: dict[str, float]
    results: list[EvalResult]
    summary: RunSummary
