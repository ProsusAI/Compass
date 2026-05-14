"""Protocol definitions for evaluation engine dependencies."""

from __future__ import annotations

import dataclasses
from typing import Any, Protocol, runtime_checkable

# TC001: These imports must be at runtime (not under TYPE_CHECKING) for @runtime_checkable
# isinstance checks to work correctly with the protocol classes.
from odysseus.eval.models import (  # noqa: TC001
    ConfidenceInterval,
    EvalResult,
    Example,
    MetricConfig,
    RunFingerprint,
    RunReport,
    TokenUsage,
)
from odysseus.eval.pricing import ModelPricing  # noqa: TC001
from odysseus.eval.rate_limiter import TokenBucketRateLimiter  # noqa: TC001


@runtime_checkable
class Backend(Protocol):
    """LLM backend that evaluates a single example."""

    @property
    def model_name(self) -> str: ...

    @property
    def pricing(self) -> ModelPricing | None: ...

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]: ...


@runtime_checkable
class PromptManager(Protocol):
    """Loads versioned prompt templates. Resolves 'latest' internally."""

    def load(self, version: str) -> str: ...


@runtime_checkable
class DatasetManager(Protocol):
    """Loads evaluation datasets."""

    def load(self, path: str) -> list[Example]: ...


@runtime_checkable
class MetricsEngine(Protocol):
    """Computes metrics over evaluation results."""

    def compute(
        self,
        results: list[EvalResult],
        examples: list[Example],
        metric_configs: list[MetricConfig],
    ) -> dict[str, float]: ...

    def compute_cis(
        self,
        results: list[EvalResult],
        examples: list[Example],
        metric_configs: list[MetricConfig],
        n_bootstrap: int | None = None,
        ci_level: float = 0.95,
    ) -> dict[str, ConfidenceInterval]: ...


@runtime_checkable
class ResultsCollector(Protocol):
    """Persists evaluation results and reports to disk."""

    def write_results(
        self, results: list[EvalResult], path: str, fingerprint: RunFingerprint | None = None
    ) -> None: ...

    def write_report(self, report: RunReport, path: str) -> None: ...

    def append_result(self, result: EvalResult, path: str) -> None: ...

    def read_completed_ids(self, path: str) -> set[str]: ...

    def write_fingerprint(self, fingerprint: RunFingerprint, path: str) -> None: ...

    def read_fingerprint(self, path: str) -> RunFingerprint | None: ...


@dataclasses.dataclass
class RunDependencies:
    """Container for all injected dependencies required by the run controller."""

    backend: Backend
    prompt_manager: PromptManager
    dataset_manager: DatasetManager
    metrics_engine: MetricsEngine
    results_collector: ResultsCollector
    requests_per_minute: int
    tokens_per_minute: int
    rate_limiter: TokenBucketRateLimiter | None = None
