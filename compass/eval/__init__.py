# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Evaluation engine for routing prompt assessment."""

from compass.eval.collector import JsonResultsCollector
from compass.eval.controller import run
from compass.eval.diff import MetricDiff, OverheadDiff, compute_metric_diffs, compute_overhead_diff
from compass.eval.models import (
    ConcurrencyConfig,
    ErrorBreakdown,
    EvalResult,
    Example,
    Expected,
    MetricConfig,
    ModelCostQuality,
    OutputConfig,
    RetryConfig,
    RunConfig,
    RunDiff,
    RunReport,
    RunSummary,
    ScoreReport,
    TokenUsage,
)
from compass.eval.pricing import ModelPricing, compute_cost
from compass.eval.protocols import (
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
    "Expected",
    "JsonResultsCollector",
    "ModelCostQuality",
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
