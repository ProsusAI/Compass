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

    def compute(
        self, results: list[EvalResult], examples: list[Example], metric_configs: list[MetricConfig]
    ) -> dict[str, float]:
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
        "output": OutputConfig(results_path="outputs/test-results.jsonl", report_path="outputs/test-report.json"),
    }
    defaults.update(overrides)
    return RunConfig(**defaults)


def _make_deps(
    backend: Any = None,
    examples: list[Example] | None = None,
    metrics: dict[str, float] | None = None,
    requests_per_minute: int = 10000,
    tokens_per_minute: int = 1_000_000,
) -> tuple[RunDependencies, MockResultsCollector]:
    collector = MockResultsCollector()
    deps = RunDependencies(
        backend=backend or MockBackend(),
        prompt_manager=MockPromptManager(),
        dataset_manager=MockDatasetManager(examples or _make_examples(5)),
        metrics_engine=MockMetricsEngine(metrics),
        results_collector=collector,
        requests_per_minute=requests_per_minute,
        tokens_per_minute=tokens_per_minute,
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
    config = _make_config(retry=RetryConfig(max_attempts=3, backoff_factor=1.0))
    deps, _ = _make_deps(backend=backend, examples=_make_examples(1))
    report = await run(config, deps)

    assert report.summary.succeeded == 1
    assert report.summary.failed == 0
    assert report.results[0].retries == 2
    assert report.results[0].error is None


async def test_exhausted_retries():
    """Backend always fails — verify error in result."""
    backend = AlwaysFailBackend()
    config = _make_config(retry=RetryConfig(max_attempts=2, backoff_factor=1.0))
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

    import types

    backend.call = types.MethodType(slow_call, backend)

    from odysseus.eval.models import ConcurrencyConfig

    config = _make_config(
        concurrency=ConcurrencyConfig(max_concurrent_requests=2),
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
        retry=RetryConfig(max_attempts=1, backoff_factor=1.0, per_call_timeout_seconds=0.1),
    )
    deps, _ = _make_deps(backend=backend, examples=_make_examples(1))
    report = await run(config, deps)

    assert report.summary.failed == 1
    assert "timeout" in (report.results[0].error or "").lower() or "TimeoutError" in (report.results[0].error or "")


async def test_rate_limiter_acquired_before_semaphore():
    """Rate limiter must be acquired before the semaphore to prevent deadlock.

    If all semaphore slots are held by coroutines blocked on rate limiting,
    no progress can be made. This test verifies the correct ordering by
    tracking acquire calls on instrumented wrappers.
    """
    acquire_order: list[str] = []
    original_semaphore_cls = asyncio.Semaphore

    class TrackingSemaphore(original_semaphore_cls):
        async def __aenter__(self):
            acquire_order.append("semaphore")
            return await super().__aenter__()

        async def __aexit__(self, *args):
            return await super().__aexit__(*args)

    from odysseus.eval.rate_limiter import TokenBucketRateLimiter

    class TrackingRateLimiter(TokenBucketRateLimiter):
        async def acquire(self):
            acquire_order.append("rate_limiter")
            await super().acquire()

    backend = MockBackend()
    retry = RetryConfig(max_attempts=1, backoff_factor=1.0)
    example = _make_examples(1)[0]
    rate_limiter = TrackingRateLimiter(requests_per_minute=10000, tokens_per_minute=1_000_000)
    semaphore = TrackingSemaphore(20)

    from odysseus.eval.controller import _eval_with_retry

    await _eval_with_retry(backend, "prompt", example, retry, rate_limiter, semaphore)

    # rate_limiter must appear before semaphore in the acquire order
    rl_idx = acquire_order.index("rate_limiter")
    sem_idx = acquire_order.index("semaphore")
    assert rl_idx < sem_idx, f"Rate limiter must be acquired before semaphore, got order: {acquire_order}"


async def test_backoff_sleeps_outside_semaphore():
    """Backoff sleep must happen outside the semaphore to free the slot."""
    semaphore_held_during_sleep = False

    class FailOnceBackend:
        @property
        def model_name(self) -> str:
            return "test-model"

        async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
            if not hasattr(self, "_called"):
                self._called = True
                raise RuntimeError("First attempt fails")
            return {"answer": "ok"}, TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5)

    import unittest.mock
    from odysseus.eval.controller import _eval_with_retry
    from odysseus.eval.rate_limiter import TokenBucketRateLimiter

    rate_limiter = TokenBucketRateLimiter(requests_per_minute=10000, tokens_per_minute=1_000_000)
    semaphore = asyncio.Semaphore(1)  # Single slot so we can detect if it's held

    original_sleep = asyncio.sleep

    async def tracking_sleep(duration):
        nonlocal semaphore_held_during_sleep
        # If semaphore can be acquired, it's not held
        acquired = semaphore._value > 0  # noqa: SLF001
        if not acquired:
            semaphore_held_during_sleep = True
        await original_sleep(0)  # Don't actually wait

    with unittest.mock.patch("asyncio.sleep", side_effect=tracking_sleep):
        result = await _eval_with_retry(
            FailOnceBackend(),
            "prompt",
            Example(id="ex-0", input={"q": "1"}, expected={"a": "1"}),
            RetryConfig(max_attempts=2, backoff_factor=1.0),
            rate_limiter,
            semaphore,
        )

    assert result.error is None, "Should succeed on second attempt"
    assert not semaphore_held_during_sleep, "Semaphore must not be held during backoff sleep"


async def test_timeout_wraps_only_backend_call():
    """Timeout should apply to backend.call() only, not rate limiter or semaphore wait."""
    from odysseus.eval.controller import _eval_with_retry
    from odysseus.eval.rate_limiter import TokenBucketRateLimiter

    class SlowAcquireRateLimiter(TokenBucketRateLimiter):
        """Rate limiter whose acquire takes longer than the call timeout."""
        async def acquire(self):
            await asyncio.sleep(0.3)  # Longer than per_call_timeout
            await super().acquire()

    backend = MockBackend()
    rate_limiter = SlowAcquireRateLimiter(requests_per_minute=10000, tokens_per_minute=1_000_000)
    semaphore = asyncio.Semaphore(20)

    # Timeout is 0.1s, but rate limiter takes 0.3s.
    # If timeout wrapped the whole thing, this would fail with TimeoutError.
    result = await _eval_with_retry(
        backend,
        "prompt",
        Example(id="ex-0", input={"q": "1"}, expected={"a": "1"}),
        RetryConfig(max_attempts=1, backoff_factor=1.0, per_call_timeout_seconds=0.1),
        rate_limiter,
        semaphore,
    )

    # Should succeed because timeout only wraps backend.call(), not acquire()
    assert result.error is None


async def test_token_accounting_post_call():
    """consume_tokens is called with the actual usage after backend.call()."""
    from odysseus.eval.controller import _eval_with_retry
    from odysseus.eval.rate_limiter import TokenBucketRateLimiter

    consumed: list[int] = []

    class TrackingRateLimiter(TokenBucketRateLimiter):
        def consume_tokens(self, tokens: int) -> None:
            consumed.append(tokens)
            super().consume_tokens(tokens)

    backend = MockBackend()  # Returns 10 input + 0 cached + 5 output = 15 total
    rate_limiter = TrackingRateLimiter(requests_per_minute=10000, tokens_per_minute=1_000_000)
    semaphore = asyncio.Semaphore(20)

    await _eval_with_retry(
        backend,
        "prompt",
        Example(id="ex-0", input={"q": "1"}, expected={"a": "1"}),
        RetryConfig(max_attempts=1, backoff_factor=1.0),
        rate_limiter,
        semaphore,
    )

    assert consumed == [15], f"Expected [15] tokens consumed, got {consumed}"
