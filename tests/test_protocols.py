"""Tests for protocol conformance and RunDependencies."""

from typing import Any

from odysseus.eval.models import (
    ConfidenceInterval,
    EvalResult,
    Example,
    MetricConfig,
    RunReport,
    TokenUsage,
)
from odysseus.eval.pricing import ModelPricing
from odysseus.eval.protocols import (
    Backend,
    DatasetManager,
    MetricsEngine,
    PromptManager,
    ResultsCollector,
    RunDependencies,
)


class StubBackend:
    @property
    def model_name(self) -> str:
        return "test-model"

    @property
    def pricing(self) -> ModelPricing | None:
        return None

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        return {"answer": "test"}, TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5)


class StubPromptManager:
    def load(self, version: str) -> str:
        return "test prompt"


class StubDatasetManager:
    def load(self, path: str) -> list[Example]:
        return []


class StubMetricsEngine:
    def compute(
        self, results: list[EvalResult], examples: list[Example], metric_configs: list[MetricConfig]
    ) -> dict[str, float]:
        return {"accuracy": 1.0}

    def compute_cis(
        self,
        results: list[EvalResult],
        examples: list[Example],
        metric_configs: list[MetricConfig],
        n_bootstrap: int | None = None,
        ci_level: float = 0.95,
    ) -> dict[str, ConfidenceInterval]:
        return {}


class StubResultsCollector:
    def write_results(self, results: list[EvalResult], path: str, fingerprint: Any = None) -> None:
        pass

    def write_report(self, report: RunReport, path: str) -> None:
        pass

    def append_result(self, result: EvalResult, path: str) -> None:
        pass

    def read_completed_ids(self, path: str) -> set[str]:
        return set()

    def write_fingerprint(self, fingerprint: Any, path: str) -> None:
        pass

    def read_fingerprint(self, path: str) -> Any:
        return None


def _check_protocol(obj: object, protocol: type) -> bool:
    """Verify an object structurally conforms to a protocol via isinstance."""
    return isinstance(obj, protocol)


def test_stub_backend_conforms():
    assert _check_protocol(StubBackend(), Backend)


def test_stub_prompt_manager_conforms():
    assert _check_protocol(StubPromptManager(), PromptManager)


def test_stub_dataset_manager_conforms():
    assert _check_protocol(StubDatasetManager(), DatasetManager)


def test_stub_metrics_engine_conforms():
    assert _check_protocol(StubMetricsEngine(), MetricsEngine)


def test_stub_results_collector_conforms():
    assert _check_protocol(StubResultsCollector(), ResultsCollector)


def test_run_dependencies_construction():
    deps = RunDependencies(
        backend=StubBackend(),
        prompt_manager=StubPromptManager(),
        dataset_manager=StubDatasetManager(),
        metrics_engine=StubMetricsEngine(),
        results_collector=StubResultsCollector(),
        requests_per_minute=100,
        tokens_per_minute=50000,
    )
    assert deps.backend.model_name == "test-model"
