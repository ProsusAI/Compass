"""Tests for the run controller."""

import asyncio
from typing import Any, Literal

from odysseus.eval.controller import run
from odysseus.eval.models import (
    EvalResult,
    Example,
    MetricConfig,
    OutputConfig,
    RetryConfig,
    RunConfig,
    RunReport,
    TokenUsage,
)
from odysseus.eval.protocols import RunDependencies

# --- Mock implementations ---


class MockBackend:
    def __init__(self, responses: dict[str, tuple[dict[str, Any], TokenUsage]] | None = None, fail_count: int = 0):
        self._responses = responses or {}
        self._fail_count = fail_count
        self._attempt_counts: dict[str, int] = {}
        self._concurrent = 0
        self._max_concurrent = 0
        self._lock = asyncio.Lock()

    @property
    def model_name(self) -> str:
        return "test-model"

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        async with self._lock:
            self._concurrent += 1
            self._max_concurrent = max(self._max_concurrent, self._concurrent)

        try:
            self._attempt_counts.setdefault(example.id, 0)
            self._attempt_counts[example.id] += 1
            if self._attempt_counts[example.id] <= self._fail_count:
                raise RuntimeError(f"Simulated failure for {example.id}")

            if example.id in self._responses:
                return self._responses[example.id]

            usage = TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5)
            return {"answer": "default"}, usage
        finally:
            async with self._lock:
                self._concurrent -= 1


class HangingBackend:
    """Backend that hangs forever (for timeout tests)."""

    @property
    def model_name(self) -> str:
        return "hanging-model"

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        await asyncio.sleep(3600)
        raise AssertionError("Should not reach here")


class AlwaysFailBackend:
    """Backend that always raises."""

    @property
    def model_name(self) -> str:
        return "fail-model"

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        raise RuntimeError("Always fails")


class MockPromptManager:
    def __init__(self, prompt: str = "You are an evaluator."):
        self._prompt = prompt

    def load(self, version: str) -> str:
        return self._prompt


class MockDatasetManager:
    def __init__(self, examples: list[Example] | None = None):
        self._examples = examples or []

    def load(self, path: str, split: Literal["dev", "holdout"]) -> list[Example]:
        return self._examples


class MockMetricsEngine:
    def __init__(self, metrics: dict[str, float] | None = None):
        self._metrics = metrics or {"accuracy": 1.0}

    def compute(self, results: list[EvalResult], metric_configs: list[MetricConfig]) -> dict[str, float]:
        return self._metrics


class MockResultsCollector:
    def __init__(self):
        self.written_results: list[EvalResult] | None = None
        self.written_report: RunReport | None = None

    def write_results(self, results: list[EvalResult], path: str) -> None:
        self.written_results = results

    def write_report(self, report: RunReport, path: str) -> None:
        self.written_report = report


# --- Helpers ---


def _make_examples(n: int) -> list[Example]:
    return [Example(id=f"ex-{i}", input={"question": f"q{i}"}, expected={"answer": f"a{i}"}) for i in range(n)]


def _make_config(**overrides: Any) -> RunConfig:
    defaults: dict[str, Any] = {
        "backend": "test-model",
        "data_source": "data/test.jsonl",
        "data_split": "dev",
        "metrics": [MetricConfig(name="accuracy")],
        "output": OutputConfig(results_path="/dev/null", report_path="/dev/null"),
    }
    defaults.update(overrides)
    return RunConfig(**defaults)


def _make_deps(
    backend: Any = None,
    examples: list[Example] | None = None,
    metrics: dict[str, float] | None = None,
) -> tuple[RunDependencies, MockResultsCollector]:
    collector = MockResultsCollector()
    deps = RunDependencies(
        backend=backend or MockBackend(),
        prompt_manager=MockPromptManager(),
        dataset_manager=MockDatasetManager(examples or _make_examples(5)),
        metrics_engine=MockMetricsEngine(metrics),
        results_collector=collector,
    )
    return deps, collector


# --- Tests ---


async def test_happy_path():
    """All examples succeed — verify report counts, metrics, and cost."""
    deps, collector = _make_deps()
    config = _make_config()
    report = await run(config, deps)

    assert report.summary.total == 5
    assert report.summary.succeeded == 5
    assert report.summary.failed == 0
    assert report.metrics == {"accuracy": 1.0}
    assert all(r.error is None for r in report.results)
    assert all(r.model == "test-model" for r in report.results)
    assert all(r.retries == 0 for r in report.results)
    assert collector.written_results is not None
    assert collector.written_report is not None


async def test_retry_then_succeed():
    """Backend fails twice then succeeds — verify retry count."""
    backend = MockBackend(fail_count=2)
    config = _make_config(retry=RetryConfig(max_attempts=3, backoff_factor=0.01))
    deps, _ = _make_deps(backend=backend, examples=_make_examples(1))
    report = await run(config, deps)

    assert report.summary.succeeded == 1
    assert report.summary.failed == 0
    assert report.results[0].retries == 2
    assert report.results[0].error is None


async def test_exhausted_retries():
    """Backend always fails — verify error in result."""
    backend = AlwaysFailBackend()
    config = _make_config(retry=RetryConfig(max_attempts=2, backoff_factor=0.01))
    deps, _ = _make_deps(backend=backend, examples=_make_examples(2))
    report = await run(config, deps)

    assert report.summary.succeeded == 0
    assert report.summary.failed == 2
    assert all(r.error is not None for r in report.results)
    assert all(r.output is None for r in report.results)


async def test_concurrency_limit():
    """Semaphore limits max concurrent backend calls."""
    backend = MockBackend()

    async def slow_call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        async with self._lock:
            self._concurrent += 1
            self._max_concurrent = max(self._max_concurrent, self._concurrent)
        await asyncio.sleep(0.05)
        async with self._lock:
            self._concurrent -= 1
        self._attempt_counts.setdefault(example.id, 0)
        self._attempt_counts[example.id] += 1
        return {"answer": "ok"}, TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5)

    # Monkey-patch call to add a delay
    import types

    backend.call = types.MethodType(slow_call, backend)

    from odysseus.eval.models import ConcurrencyConfig

    config = _make_config(
        concurrency=ConcurrencyConfig(
            max_concurrent_requests=2,
            requests_per_minute=10000,
            tokens_per_minute=1_000_000,
        ),
    )
    deps, _ = _make_deps(backend=backend, examples=_make_examples(6))
    await run(config, deps)

    assert backend._max_concurrent <= 2


async def test_output_writing():
    """Results collector receives correct data."""
    deps, collector = _make_deps()
    config = _make_config()
    await run(config, deps)

    assert collector.written_results is not None
    assert len(collector.written_results) == 5
    assert collector.written_report is not None
    assert collector.written_report.summary.total == 5


async def test_timeout():
    """Backend that hangs should be timed out."""
    backend = HangingBackend()
    config = _make_config(
        retry=RetryConfig(max_attempts=1, backoff_factor=0.01, per_call_timeout_seconds=0.1),
    )
    deps, _ = _make_deps(backend=backend, examples=_make_examples(1))
    report = await run(config, deps)

    assert report.summary.failed == 1
    assert "timeout" in (report.results[0].error or "").lower() or "TimeoutError" in (report.results[0].error or "")
