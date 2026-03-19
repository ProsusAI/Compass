"""Protocol definitions for evaluation engine dependencies."""

from __future__ import annotations

import dataclasses
from typing import Any, Literal, Protocol, runtime_checkable

# TC001: These imports must be at runtime (not under TYPE_CHECKING) for @runtime_checkable
# isinstance checks to work correctly with the protocol classes.
from odysseus.eval.models import (  # noqa: TC001
    EvalResult,
    Example,
    MetricConfig,
    RunReport,
    TokenUsage,
)


@runtime_checkable
class Backend(Protocol):
    """LLM backend that evaluates a single example."""

    @property
    def model_name(self) -> str: ...

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]: ...


@runtime_checkable
class PromptManager(Protocol):
    """Loads versioned prompt templates. Resolves 'latest' internally."""

    def load(self, version: str) -> str: ...


@runtime_checkable
class DatasetManager(Protocol):
    """Loads and splits evaluation datasets."""

    def load(self, path: str, split: Literal["dev", "holdout"]) -> list[Example]: ...


@runtime_checkable
class MetricsEngine(Protocol):
    """Computes metrics over evaluation results."""

    def compute(
        self,
        results: list[EvalResult],
        examples: list[Example],
        metric_configs: list[MetricConfig],
    ) -> dict[str, float]: ...


@runtime_checkable
class ResultsCollector(Protocol):
    """Persists evaluation results and reports to disk."""

    def write_results(self, results: list[EvalResult], path: str) -> None: ...

    def write_report(self, report: RunReport, path: str) -> None: ...


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

    def __post_init__(self) -> None:
        if self.requests_per_minute < 1:
            raise ValueError("requests_per_minute must be >= 1")
        if self.tokens_per_minute < 1:
            raise ValueError("tokens_per_minute must be >= 1")
