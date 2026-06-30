# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Data models for the Final Report Agent briefing."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from compass.eval.models import ConfidenceInterval


class DatasetOverview(BaseModel):
    """Dataset size and distribution summary."""

    model_config = ConfigDict(extra="forbid")

    total_examples: int
    dev_count: int
    holdout_count: int
    route_distribution: dict[str, dict[str, int]]
    routes: list[str]
    dimensions: list[str]


class PromptSummary(BaseModel):
    """A single prompt on the Pareto front."""

    model_config = ConfigDict(extra="forbid")

    version: str
    quality_score: float
    cost: float  # signed cost-change fraction (more-negative is better)
    round_introduced: int


class OptimizationJourney(BaseModel):
    """Search loop progression and convergence info."""

    model_config = ConfigDict(extra="forbid")

    total_rounds: int
    convergence_reason: str
    stagnation_count: int
    best_quality_per_round: list[float]
    best_cost_per_round: list[float]
    pareto_front_size_per_round: list[int]
    oracle_cost_change: float | None = None
    oracle_quality_change: float | None = None


class EvalMetricComparison(BaseModel):
    """Single metric compared between dev and holdout eval."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    dev_value: float
    holdout_value: float
    delta: float


class PerClassPerformance(BaseModel):
    """Per-route holdout performance."""

    model_config = ConfigDict(extra="forbid")

    route: str
    precision: float | None = Field(default=None, ge=0.0, le=1.0)
    recall: float | None = Field(default=None, ge=0.0, le=1.0)
    f1: float | None = Field(default=None, ge=0.0, le=1.0)
    support: int | None = None


class ConfusionEntry(BaseModel):
    """Single cell in the confusion matrix."""

    model_config = ConfigDict(extra="forbid")

    expected: str
    predicted: str
    count: int


class ErrorAnalysis(BaseModel):
    """Holdout error analysis with confusion matrix."""

    model_config = ConfigDict(extra="forbid")

    total_evaluated: int
    total_errors: int
    error_rate: float = Field(ge=0.0, le=1.0)
    confusion_matrix: list[ConfusionEntry]


class BaselineResult(BaseModel):
    """Performance of a single baseline strategy."""

    model_config = ConfigDict(extra="forbid")

    strategy: str
    route: str
    quality_score: float
    cost: float = Field(ge=0.0)


class BaselineComparison(BaseModel):
    """Comparison of optimized prompt against naive baselines."""

    model_config = ConfigDict(extra="forbid")

    baselines: list[BaselineResult]
    optimized: BaselineResult


class ChartPaths(BaseModel):
    """Paths to generated chart images (relative to run_dir)."""

    model_config = ConfigDict(extra="forbid")

    quality_progression: str | None = None
    cost_progression: str | None = None
    pareto_front: str | None = None


class FinalReportBriefing(BaseModel):
    """Complete pre-processed briefing for the Final Report Agent."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    backend_name: str
    problem_summary: str
    dataset_overview: DatasetOverview
    optimization_journey: OptimizationJourney
    evaluated_versions: list[str]
    evaluated_prompts: dict[str, PromptSummary]
    prompt_texts: dict[str, str]
    pareto_front: list[PromptSummary]
    eval_comparison: dict[str, list[EvalMetricComparison]]
    per_class_performance: dict[str, list[PerClassPerformance]]
    error_analysis: dict[str, ErrorAnalysis]
    baseline_comparison: dict[str, BaselineComparison | None] = Field(default_factory=dict)
    dev_score_report_md: dict[str, str] = Field(default_factory=dict)
    holdout_score_report_md: dict[str, str] = Field(default_factory=dict)
    baseline_comparison_md: dict[str, str] = Field(default_factory=dict)
    confidence_intervals: dict[str, dict[str, ConfidenceInterval]] = Field(default_factory=dict)
    holdout_report_paths: dict[str, str] = Field(default_factory=dict)
    charts: ChartPaths
