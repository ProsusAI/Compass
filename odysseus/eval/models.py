"""Data models for the evaluation engine."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class MetricConfig(BaseModel):
    """Configuration for a single metric.

    Fields:
        name: Metric name (non-empty, whitespace stripped).
        params: Optional metric parameters. Default: {}.
    """

    name: str
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must be non-empty")
        return v.strip()


class ConcurrencyConfig(BaseModel):
    """Concurrency and rate limiting settings.

    Fields:
        max_concurrent_requests: Max parallel requests (>= 1). Default: 20.
        requests_per_minute: RPM rate limit (>= 1). Default: 500.
        tokens_per_minute: TPM rate limit (>= 1). Default: 100_000.
    """

    max_concurrent_requests: int = 20
    requests_per_minute: int = 500
    tokens_per_minute: int = 100_000

    @field_validator("max_concurrent_requests", "requests_per_minute", "tokens_per_minute")
    @classmethod
    def must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("must be >= 1")
        return v


class RetryConfig(BaseModel):
    """Retry behavior for failed backend calls.

    Fields:
        max_attempts: Number of attempts (>= 1). Default: 3.
        backoff_factor: Exponential backoff base (>= 1.0). Default: 2.0.
        per_call_timeout_seconds: Timeout per call in seconds (> 0, <= 300). Default: 60.0.

    Cross-field validation:
        Total worst-case duration (all backoff waits + all timeouts) must be <= 1800s.
    """

    max_attempts: int = 3
    backoff_factor: float = 2.0
    per_call_timeout_seconds: float = 60.0

    @field_validator("max_attempts")
    @classmethod
    def max_attempts_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_attempts must be >= 1")
        return v

    @field_validator("backoff_factor")
    @classmethod
    def backoff_factor_must_be_at_least_one(cls, v: float) -> float:
        if v < 1.0:
            raise ValueError("backoff_factor must be >= 1.0")
        return v

    @field_validator("per_call_timeout_seconds")
    @classmethod
    def timeout_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("per_call_timeout_seconds must be > 0")
        return v

    @model_validator(mode="after")
    def check_retry_bounds(self) -> RetryConfig:
        if self.per_call_timeout_seconds > 300:
            raise ValueError(
                f"per_call_timeout_seconds ({self.per_call_timeout_seconds}) must be <= 300"
            )
        total_backoff = sum(
            self.backoff_factor**i for i in range(1, self.max_attempts)
        )
        total_worst_case = total_backoff + self.max_attempts * self.per_call_timeout_seconds
        if total_worst_case > 1800:
            raise ValueError(
                f"total worst-case retry duration ({total_worst_case:.0f}s) exceeds 1800s limit"
            )
        return self


class OutputConfig(BaseModel):
    """Paths for writing evaluation outputs.

    Fields:
        results_path: Path for results file (must end with .jsonl). Default: outputs/results.jsonl.
        report_path: Path for report file (must end with .json). Default: outputs/report.json.
    """

    results_path: str = "outputs/results.jsonl"
    report_path: str = "outputs/report.json"

    @field_validator("results_path")
    @classmethod
    def results_path_must_be_jsonl(cls, v: str) -> str:
        if not v.endswith(".jsonl"):
            raise ValueError("results_path must end with .jsonl")
        return v

    @field_validator("report_path")
    @classmethod
    def report_path_must_be_json(cls, v: str) -> str:
        if not v.endswith(".json"):
            raise ValueError("report_path must end with .json")
        return v


class RunConfig(BaseModel):
    """Top-level configuration for an evaluation run.

    Fields:
        backend: Backend identifier (non-empty). Required.
        prompt_version: Prompt version string (non-empty). Default: "latest".
        data_source: Path to dataset (non-empty). Required.
        data_split: "dev" or "holdout". Required.
        metrics: At least one MetricConfig. Required.
        concurrency: ConcurrencyConfig. Default: ConcurrencyConfig().
        retry: RetryConfig. Default: RetryConfig().
        output: OutputConfig. Default: OutputConfig().
    """

    backend: str
    prompt_version: str = "latest"
    data_source: str
    data_split: Literal["dev", "holdout"]
    metrics: list[MetricConfig]
    concurrency: ConcurrencyConfig = ConcurrencyConfig()
    retry: RetryConfig = RetryConfig()
    output: OutputConfig = OutputConfig()

    @field_validator("backend", "prompt_version", "data_source")
    @classmethod
    def string_fields_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v.strip()

    @field_validator("metrics")
    @classmethod
    def metrics_must_be_non_empty(cls, v: list[MetricConfig]) -> list[MetricConfig]:
        if len(v) == 0:
            raise ValueError("at least one metric is required")
        return v

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
