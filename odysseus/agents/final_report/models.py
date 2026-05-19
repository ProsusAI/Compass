"""Data models for the Final Report Agent briefing."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from odysseus.eval.models import ConfidenceInterval


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
    best_prompt: PromptSummary
    best_prompt_text: str
    pareto_front: list[PromptSummary]
    eval_comparison: list[EvalMetricComparison]
    per_class_performance: list[PerClassPerformance]
    error_analysis: ErrorAnalysis
    baseline_comparison: BaselineComparison | None = None
    dev_score_report_md: str = ""
    holdout_score_report_md: str = ""
    baseline_comparison_md: str = ""
    confidence_intervals: dict[str, ConfidenceInterval] | None = None
    charts: ChartPaths
