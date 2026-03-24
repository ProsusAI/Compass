"""Data models for the evaluation engine."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from odysseus.eval.diff import MetricDiff, OverheadDiff, compute_metric_diffs, compute_overhead_diff


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
    """Concurrency settings.

    Fields:
        max_concurrent_requests: Max parallel requests (>= 1). Default: 20.
    """

    model_config = ConfigDict(extra="forbid")

    max_concurrent_requests: int = 20

    @field_validator("max_concurrent_requests")
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
            raise ValueError(f"per_call_timeout_seconds ({self.per_call_timeout_seconds}) must be <= 300")
        total_backoff = sum(self.backoff_factor**i for i in range(1, self.max_attempts))
        total_worst_case = total_backoff + self.max_attempts * self.per_call_timeout_seconds
        if total_worst_case > 1800:
            raise ValueError(f"total worst-case retry duration ({total_worst_case:.0f}s) exceeds 1800s limit")
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


class ModelCostQuality(BaseModel):
    """Per-model cost and quality data for a routing option."""

    cost: float | None = None
    quality_score: float | None = None


class Expected(BaseModel):
    """Expected routing outcome for an evaluation example."""

    route: str
    routes: dict[str, ModelCostQuality]

    @model_validator(mode="after")
    def validate_routes_not_empty(self) -> Expected:
        if not self.routes:
            raise ValueError("routes must contain at least one entry")
        return self


class Example(BaseModel):
    """A single evaluation example."""

    id: str
    input: str
    expected: Expected
    split: Literal["dev", "holdout"]
    metadata: dict[str, Any] | None = None


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


class ErrorBreakdown(BaseModel):
    """Summary of a single failed evaluation example."""

    example_id: str
    error: str
    retries: int


class RunDiff(BaseModel):
    """Run-over-run comparison data."""

    metric_diffs: list[MetricDiff]
    overhead_diff: OverheadDiff | None


class ScoreReport(BaseModel):
    """Score report passed from EvalRunnerAgent to Review agent via pipeline context.

    This is the contract between the two agents. The Review agent consumes
    this structure to decide whether the prompt iteration improved.
    """

    CONTEXT_KEY: ClassVar[str] = "eval_score_report"

    metrics: dict[str, float]
    summary: RunSummary
    errors: list[ErrorBreakdown]
    diff: RunDiff | None
    report_path: str
    results_path: str

    @classmethod
    def from_run_report(
        cls,
        report: RunReport,
        *,
        report_path: str,
        results_path: str,
        previous_report: RunReport | None = None,
    ) -> ScoreReport:
        """Build a ScoreReport from a RunReport and optional previous run."""
        errors = [
            ErrorBreakdown(
                example_id=r.example_id,
                error=r.error,  # type: ignore[arg-type]
                retries=r.retries,
            )
            for r in report.results
            if r.error is not None
        ]

        diff: RunDiff | None = None
        if previous_report is not None:
            metric_diffs = compute_metric_diffs(previous_report.metrics, report.metrics)
            overhead_diff = compute_overhead_diff(
                old_cost=previous_report.summary.total_cost,
                old_duration=previous_report.summary.duration_seconds,
                new_cost=report.summary.total_cost,
                new_duration=report.summary.duration_seconds,
            )
            diff = RunDiff(metric_diffs=metric_diffs, overhead_diff=overhead_diff)

        return cls(
            metrics=report.metrics,
            summary=report.summary,
            errors=errors,
            diff=diff,
            report_path=report_path,
            results_path=results_path,
        )
