"""Data models for the Final Report Agent briefing."""

from __future__ import annotations

from pydantic import BaseModel


class DatasetOverview(BaseModel):
    """Dataset size and distribution summary."""

    total_examples: int
    dev_count: int
    holdout_count: int
    route_distribution: dict[str, dict[str, int]]
    routes: list[str]
    dimensions: list[str]


class PromptSummary(BaseModel):
    """A single prompt on the Pareto front."""

    version: str
    quality_score: float
    cost: float
    round_introduced: int


class OptimizationJourney(BaseModel):
    """Search loop progression and convergence info."""

    total_rounds: int
    convergence_reason: str
    stagnation_count: int
    mutation_mode: str
    best_quality_per_round: list[float]
    best_cost_per_round: list[float]
    pareto_front_size_per_round: list[int]
    mutation_type_counts: dict[str, int]
    effective_mutation_types: list[str]
    ineffective_mutation_types: list[str]


class EvalMetricComparison(BaseModel):
    """Single metric compared between dev and holdout eval."""

    metric: str
    dev_value: float
    holdout_value: float
    delta: float


class PerClassPerformance(BaseModel):
    """Per-route holdout performance."""

    route: str
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    support: int | None = None


class OracleAnalysis(BaseModel):
    """How close the best prompt is to the theoretical optimum."""

    oracle_cost_reduction: float
    oracle_quality_reduction: float
    candidate_cost_reduction: float | None = None
    candidate_cost_reduction_with_overhead: float | None = None
    candidate_quality_reduction: float | None = None


class ConfusionEntry(BaseModel):
    """Single cell in the confusion matrix."""

    expected: str
    predicted: str
    count: int


class ErrorAnalysis(BaseModel):
    """Holdout error analysis with confusion matrix."""

    total_evaluated: int
    total_errors: int
    error_rate: float
    confusion_matrix: list[ConfusionEntry]


class ChartPaths(BaseModel):
    """Paths to generated chart images (relative to run_dir)."""

    quality_progression: str | None = None
    cost_progression: str | None = None
    pareto_front: str | None = None


class FinalReportBriefing(BaseModel):
    """Complete pre-processed briefing for the Final Report Agent."""

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
    oracle_analysis: OracleAnalysis | None = None
    error_analysis: ErrorAnalysis
    charts: ChartPaths
