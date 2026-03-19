"""Evaluation engine for routing prompt assessment."""

from odysseus.eval.collector import JsonResultsCollector
from odysseus.eval.controller import run
from odysseus.eval.diff import MetricDiff, OverheadDiff, compute_metric_diffs, compute_overhead_diff
from odysseus.eval.models import (
    ConcurrencyConfig,
    ErrorBreakdown,
    EvalResult,
    Example,
    MetricConfig,
    OutputConfig,
    RetryConfig,
    RunConfig,
    RunDiff,
    RunReport,
    RunSummary,
    ScoreReport,
    TokenUsage,
)
from odysseus.eval.pricing import ModelPricing, compute_cost
from odysseus.eval.protocols import (
    Backend,
    DatasetManager,
    MetricsEngine,
    PromptManager,
    ResultsCollector,
    RunDependencies,
)

__all__ = [
    "run",
    "Backend",
    "ConcurrencyConfig",
    "compute_metric_diffs",
    "compute_overhead_diff",
    "compute_cost",
    "DatasetManager",
    "ErrorBreakdown",
    "EvalResult",
    "Example",
    "JsonResultsCollector",
    "MetricConfig",
    "MetricDiff",
    "MetricsEngine",
    "ModelPricing",
    "OutputConfig",
    "OverheadDiff",
    "PromptManager",
    "ResultsCollector",
    "RetryConfig",
    "RunConfig",
    "RunDependencies",
    "RunDiff",
    "RunReport",
    "RunSummary",
    "ScoreReport",
    "TokenUsage",
]
