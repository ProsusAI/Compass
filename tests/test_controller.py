"""Tests for the run controller.

Backend classes remain as mocks (API call boundary).
All other dependencies use real implementations with temp files.
"""

import asyncio
import json
import unittest.mock
from pathlib import Path
from typing import Any

from odysseus.eval.collector import JsonResultsCollector
from odysseus.eval.controller import _eval_with_retry, run
from odysseus.eval.dataset import JsonlDatasetManager
from odysseus.eval.metrics import create_default_engine
from odysseus.eval.models import (
    ConcurrencyConfig,
    Example,
    MetricConfig,
    OutputConfig,
    RetryConfig,
    RunConfig,
    TokenUsage,
)
from odysseus.eval.pricing import ModelPricing
from odysseus.eval.protocols import RunDependencies
from odysseus.eval.rate_limiter import TokenBucketRateLimiter
from odysseus.prompts.manager import FilePromptManager

# --- Mock backends (API call boundary) ---

PROMPT_TEXT = "You are an evaluator."


class MockBackend:
    """Simulates a successful backend that echoes the expected route."""

    def __init__(self, fail_count: int = 0):
        self._fail_count = fail_count
        self._attempt_counts: dict[str, int] = {}
        self._concurrent = 0
        self._max_concurrent = 0
        self._lock = asyncio.Lock()

    @property
    def model_name(self) -> str:
        return "test-model"

    @property
    def pricing(self) -> ModelPricing | None:
        return None

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        async with self._lock:
            self._concurrent += 1
            self._max_concurrent = max(self._max_concurrent, self._concurrent)

        try:
            self._attempt_counts.setdefault(example.id, 0)
            self._attempt_counts[example.id] += 1
            if self._attempt_counts[example.id] <= self._fail_count:
                raise RuntimeError(f"Simulated failure for {example.id}")

            route = example.expected.get("route", "default")
            usage = TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5)
            return {"route": route}, usage
        finally:
            async with self._lock:
                self._concurrent -= 1


class HangingBackend:
    """Backend that hangs forever (for timeout tests)."""

    @property
    def model_name(self) -> str:
        return "hanging-model"

    @property
    def pricing(self) -> ModelPricing | None:
        return None

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        await asyncio.sleep(3600)
        raise AssertionError("Should not reach here")


class AlwaysFailBackend:
    """Backend that always raises."""

    @property
    def model_name(self) -> str:
        return "fail-model"

    @property
    def pricing(self) -> ModelPricing | None:
        return None

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        raise RuntimeError("Always fails")


class FailOnceBackend:
    """Backend that fails on first call then succeeds."""

    @property
    def model_name(self) -> str:
        return "test-model"

    @property
    def pricing(self) -> ModelPricing | None:
        return None

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        if not hasattr(self, "_called"):
            self._called = True
            raise RuntimeError("First attempt fails")
        return {"route": "a"}, TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5)


# --- Helpers ---


def _make_examples(n: int) -> list[Example]:
    return [Example(id=f"ex-{i}", input={"question": f"q{i}"}, expected={"route": f"class-{i % 3}"}) for i in range(n)]


def _write_jsonl(path: Path, examples: list[Example], split: str = "dev") -> None:
    """Write examples to a JSONL file with the split field required by JsonlDatasetManager."""
    with open(path, "w") as f:
        for ex in examples:
            record = {"id": ex.id, "input": ex.input, "expected": ex.expected, "split": split}
            f.write(json.dumps(record) + "\n")


def _setup_prompt_dir(tmp_path: Path) -> FilePromptManager:
    """Create a temp prompts directory with a single prompt file."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "v1.txt").write_text(PROMPT_TEXT)
    return FilePromptManager(prompts_dir)


def _make_config(tmp_path: Path, **overrides: Any) -> RunConfig:
    defaults: dict[str, Any] = {
        "backend": "test-model",
        "data_source": str(tmp_path / "data.jsonl"),
        "data_split": "dev",
        "metrics": [MetricConfig(name="accuracy")],
        "output": OutputConfig(
            results_path=str(tmp_path / "outputs" / "results.jsonl"),
            report_path=str(tmp_path / "outputs" / "report.json"),
        ),
    }
    defaults.update(overrides)
    return RunConfig(**defaults)


def _make_deps(
    tmp_path: Path,
    backend: Any = None,
    examples: list[Example] | None = None,
    requests_per_minute: int = 10000,
    tokens_per_minute: int = 1_000_000,
) -> RunDependencies:
    examples = examples or _make_examples(5)

    # Write JSONL data file for the real dataset manager
    _write_jsonl(tmp_path / "data.jsonl", examples)

    return RunDependencies(
        backend=backend or MockBackend(),
        prompt_manager=_setup_prompt_dir(tmp_path),
        dataset_manager=JsonlDatasetManager(),
        metrics_engine=create_default_engine(),
        results_collector=JsonResultsCollector(),
        requests_per_minute=requests_per_minute,
        tokens_per_minute=tokens_per_minute,
    )


# --- Tests: full pipeline (run) ---


async def test_happy_path(tmp_path: Path):
    """All examples succeed — verify report counts, metrics, and cost."""
    deps = _make_deps(tmp_path)
    config = _make_config(tmp_path)
    report = await run(config, deps)

    assert report.summary.total == 5
    assert report.summary.succeeded == 5
    assert report.summary.failed == 0
    assert report.metrics == {"accuracy": 1.0}
    assert all(r.error is None for r in report.results)
    assert all(r.model == "test-model" for r in report.results)
    assert all(r.retries == 0 for r in report.results)


async def test_retry_then_succeed(tmp_path: Path):
    """Backend fails twice then succeeds — verify retry count."""
    backend = MockBackend(fail_count=2)
    examples = _make_examples(1)
    config = _make_config(tmp_path, retry=RetryConfig(max_attempts=3, backoff_factor=1.0))
    deps = _make_deps(tmp_path, backend=backend, examples=examples)
    report = await run(config, deps)

    assert report.summary.succeeded == 1
    assert report.summary.failed == 0
    assert report.results[0].retries == 2
    assert report.results[0].error is None


async def test_exhausted_retries(tmp_path: Path):
    """Backend always fails — verify error in result."""
    backend = AlwaysFailBackend()
    examples = _make_examples(2)
    config = _make_config(tmp_path, retry=RetryConfig(max_attempts=2, backoff_factor=1.0))
    deps = _make_deps(tmp_path, backend=backend, examples=examples)
    report = await run(config, deps)

    assert report.summary.succeeded == 0
    assert report.summary.failed == 2
    assert all(r.error is not None for r in report.results)
    assert all(r.output is None for r in report.results)


async def test_concurrency_limit(tmp_path: Path):
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
        return {"route": "class-0"}, TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5)

    import types

    backend.call = types.MethodType(slow_call, backend)

    examples = _make_examples(6)
    config = _make_config(tmp_path, concurrency=ConcurrencyConfig(max_concurrent_requests=2))
    deps = _make_deps(tmp_path, backend=backend, examples=examples)
    await run(config, deps)

    assert backend._max_concurrent <= 2


async def test_output_writing(tmp_path: Path):
    """JsonResultsCollector writes results and report to disk."""
    deps = _make_deps(tmp_path)
    config = _make_config(tmp_path)
    await run(config, deps)

    results_path = Path(config.output.results_path)
    report_path = Path(config.output.report_path)

    # Verify results JSONL was written
    assert results_path.exists()
    lines = [line for line in results_path.read_text().splitlines() if line.strip()]
    assert len(lines) == 5
    for line in lines:
        result = json.loads(line)
        assert "example_id" in result
        assert "model" in result

    # Verify report JSON was written
    assert report_path.exists()
    report_data = json.loads(report_path.read_text())
    assert report_data["summary"]["total"] == 5
    assert report_data["summary"]["succeeded"] == 5


async def test_timeout(tmp_path: Path):
    """Backend that hangs should be timed out."""
    backend = HangingBackend()
    examples = _make_examples(1)
    config = _make_config(
        tmp_path,
        retry=RetryConfig(max_attempts=1, backoff_factor=1.0, per_call_timeout_seconds=0.1),
    )
    deps = _make_deps(tmp_path, backend=backend, examples=examples)
    report = await run(config, deps)

    assert report.summary.failed == 1
    assert "timeout" in (report.results[0].error or "").lower() or "TimeoutError" in (report.results[0].error or "")


# --- Tests: _eval_with_retry (unit-level) ---


async def test_rate_limiter_acquired_before_semaphore():
    """Rate limiter must be acquired before the semaphore to prevent deadlock."""
    acquire_order: list[str] = []
    original_semaphore_cls = asyncio.Semaphore

    class TrackingSemaphore(original_semaphore_cls):
        async def __aenter__(self):
            acquire_order.append("semaphore")
            return await super().__aenter__()

        async def __aexit__(self, *args):
            return await super().__aexit__(*args)

    class TrackingRateLimiter(TokenBucketRateLimiter):
        async def acquire(self):
            acquire_order.append("rate_limiter")
            await super().acquire()

    backend = MockBackend()
    retry = RetryConfig(max_attempts=1, backoff_factor=1.0)
    example = _make_examples(1)[0]
    rate_limiter = TrackingRateLimiter(requests_per_minute=10000, tokens_per_minute=1_000_000)
    semaphore = TrackingSemaphore(20)

    await _eval_with_retry(backend, "prompt", example, retry, rate_limiter, semaphore)

    rl_idx = acquire_order.index("rate_limiter")
    sem_idx = acquire_order.index("semaphore")
    assert rl_idx < sem_idx, f"Rate limiter must be acquired before semaphore, got order: {acquire_order}"


async def test_backoff_sleeps_outside_semaphore():
    """Backoff sleep must happen outside the semaphore to free the slot."""
    semaphore_held_during_sleep = False

    rate_limiter = TokenBucketRateLimiter(requests_per_minute=10000, tokens_per_minute=1_000_000)
    semaphore = asyncio.Semaphore(1)  # Single slot so we can detect if it's held

    original_sleep = asyncio.sleep

    async def tracking_sleep(duration):
        nonlocal semaphore_held_during_sleep
        if semaphore._value <= 0:  # noqa: SLF001
            semaphore_held_during_sleep = True
        await original_sleep(0)  # Don't actually wait

    with unittest.mock.patch("asyncio.sleep", side_effect=tracking_sleep):
        result = await _eval_with_retry(
            FailOnceBackend(),
            "prompt",
            Example(id="ex-0", input={"q": "1"}, expected={"route": "a"}),
            RetryConfig(max_attempts=2, backoff_factor=1.0),
            rate_limiter,
            semaphore,
        )

    assert result.error is None, "Should succeed on second attempt"
    assert not semaphore_held_during_sleep, "Semaphore must not be held during backoff sleep"


async def test_timeout_wraps_only_backend_call():
    """Timeout should apply to backend.call() only, not rate limiter or semaphore wait."""

    class SlowAcquireRateLimiter(TokenBucketRateLimiter):
        """Rate limiter whose acquire takes longer than the call timeout."""

        async def acquire(self):
            await asyncio.sleep(0.3)  # Longer than per_call_timeout
            await super().acquire()

    backend = MockBackend()
    rate_limiter = SlowAcquireRateLimiter(requests_per_minute=10000, tokens_per_minute=1_000_000)
    semaphore = asyncio.Semaphore(20)

    result = await _eval_with_retry(
        backend,
        "prompt",
        Example(id="ex-0", input={"q": "1"}, expected={"route": "a"}),
        RetryConfig(max_attempts=1, backoff_factor=1.0, per_call_timeout_seconds=0.1),
        rate_limiter,
        semaphore,
    )

    assert result.error is None


async def test_token_accounting_post_call():
    """consume_tokens is called with the actual usage after backend.call()."""
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
        Example(id="ex-0", input={"q": "1"}, expected={"route": "a"}),
        RetryConfig(max_attempts=1, backoff_factor=1.0),
        rate_limiter,
        semaphore,
    )

    assert consumed == [15], f"Expected [15] tokens consumed, got {consumed}"
