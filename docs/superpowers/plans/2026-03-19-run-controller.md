# Run Controller Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Run Controller Orchestrator (THP-92) — a single `async run()` function that orchestrates evaluation via protocol-based dependency injection.

**Architecture:** Protocol-based DI with five dependency contracts (Backend, PromptManager, DatasetManager, MetricsEngine, ResultsCollector). A single `run(config, deps)` async function handles the full lifecycle: load prompt, load data, fan out concurrent evaluations with rate limiting and retry, compute metrics, write outputs.

**Tech Stack:** Python 3.11+, asyncio, Pydantic v2, PyYAML, pytest + pytest-asyncio, ruff, pyright

**Spec:** `docs/superpowers/specs/2026-03-19-run-controller-design.md`

---

## Chunk 1: Data Models, Pricing, and Protocols

### Task 1: Add `litellm` dependency

**Files:**
- Modify: `pyproject.toml:7-14`

- [ ] **Step 1: Add litellm to dependencies**

In `pyproject.toml`, add `litellm` to the dependencies list:

```toml
dependencies = [
    "mcp[cli]>=1.0.0",
    "anthropic>=0.40.0",
    "openai>=1.0.0",
    "aiohttp>=3.9.0",
    "pyyaml>=6.0",
    "pydantic>=2.0.0",
    "litellm>=1.50.0",
]
```

- [ ] **Step 2: Sync dependencies**

Run: `uv sync`
Expected: Resolves and installs litellm successfully.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add litellm dependency for multi-provider backend support"
```

---

### Task 2: Data models — config types

**Files:**
- Create: `odysseus/eval/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write tests for config models**

Create `tests/test_models.py`:

```python
"""Tests for evaluation data models."""

from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

from odysseus.eval.models import (
    ConcurrencyConfig,
    MetricConfig,
    OutputConfig,
    RetryConfig,
    RunConfig,
)


def test_metric_config_defaults():
    mc = MetricConfig(name="accuracy")
    assert mc.name == "accuracy"
    assert mc.params == {}


def test_metric_config_with_params():
    mc = MetricConfig(name="f1", params={"average": "macro"})
    assert mc.params == {"average": "macro"}


def test_concurrency_config_defaults():
    cc = ConcurrencyConfig()
    assert cc.max_concurrent_requests == 20
    assert cc.requests_per_minute == 500
    assert cc.tokens_per_minute == 100_000


def test_retry_config_defaults():
    rc = RetryConfig()
    assert rc.max_attempts == 3
    assert rc.backoff_factor == 2.0
    assert rc.per_call_timeout_seconds == 60.0


def test_output_config_defaults():
    oc = OutputConfig()
    assert oc.results_path == "outputs/results.jsonl"
    assert oc.report_path == "outputs/report.json"


def test_run_config_minimal():
    config = RunConfig(
        backend="claude-sonnet",
        data_source="data/test.jsonl",
        data_split="dev",
        metrics=[MetricConfig(name="accuracy")],
    )
    assert config.prompt_version == "latest"
    assert config.concurrency.max_concurrent_requests == 20
    assert config.retry.max_attempts == 3


def test_run_config_from_yaml():
    data = {
        "backend": "claude-sonnet",
        "data_source": "data/test.jsonl",
        "data_split": "dev",
        "metrics": [{"name": "accuracy"}],
        "concurrency": {"max_concurrent_requests": 10},
    }
    with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        path = Path(f.name)

    config = RunConfig.from_yaml(path)
    assert config.backend == "claude-sonnet"
    assert config.concurrency.max_concurrent_requests == 10
    assert config.retry.max_attempts == 3  # default

    path.unlink()


def test_run_config_from_yaml_invalid():
    import pytest

    data = {"backend": "claude-sonnet"}  # missing required fields
    with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        path = Path(f.name)

    with pytest.raises(Exception):  # ValidationError
        RunConfig.from_yaml(path)

    path.unlink()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `odysseus.eval.models` does not exist yet.

- [ ] **Step 3: Implement config models**

Create `odysseus/eval/models.py`:

```python
"""Data models for the evaluation engine."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class MetricConfig(BaseModel):
    """Configuration for a single metric."""

    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class ConcurrencyConfig(BaseModel):
    """Concurrency and rate limiting settings."""

    max_concurrent_requests: int = 20
    requests_per_minute: int = 500
    tokens_per_minute: int = 100_000


class RetryConfig(BaseModel):
    """Retry behavior for failed backend calls."""

    max_attempts: int = 3
    backoff_factor: float = 2.0
    per_call_timeout_seconds: float = 60.0


class OutputConfig(BaseModel):
    """Paths for writing evaluation outputs."""

    results_path: str = "outputs/results.jsonl"
    report_path: str = "outputs/report.json"


class RunConfig(BaseModel):
    """Top-level configuration for an evaluation run."""

    backend: str
    prompt_version: str = "latest"
    data_source: str
    data_split: Literal["dev", "holdout"]
    metrics: list[MetricConfig]
    concurrency: ConcurrencyConfig = ConcurrencyConfig()
    retry: RetryConfig = RetryConfig()
    output: OutputConfig = OutputConfig()

    @classmethod
    def from_yaml(cls, path: str | Path) -> RunConfig:
        """Load config from a YAML file. Validates via Pydantic on construction."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)


class Example(BaseModel):
    """A single evaluation example."""

    id: str
    input: dict[str, Any]
    expected: dict[str, Any]


class TokenUsage(BaseModel):
    """Token usage for a single API call. Fields are disjoint (Anthropic-style)."""

    input_tokens: int
    cached_tokens: int
    output_tokens: int


class EvalResult(BaseModel):
    """Result of evaluating a single example."""

    example_id: str
    model: str
    output: dict[str, Any] | None
    error: str | None
    latency_ms: float
    retries: int
    token_usage: TokenUsage | None
    cost: float | None


class RunSummary(BaseModel):
    """Aggregate summary of an evaluation run."""

    total: int
    succeeded: int
    failed: int
    total_cost: float
    start_time: datetime
    end_time: datetime
    duration_seconds: float


class RunReport(BaseModel):
    """Complete report for an evaluation run."""

    config: RunConfig
    metrics: dict[str, float]
    results: list[EvalResult]
    summary: RunSummary
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Run linting and type checking**

Run: `uv run ruff check odysseus/eval/models.py tests/test_models.py && uv run pyright odysseus/eval/models.py`
Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add odysseus/eval/models.py tests/test_models.py
git commit -m "feat: add evaluation data models with YAML config loader"
```

---

### Task 3: Pricing module

**Files:**
- Create: `odysseus/eval/pricing.py`
- Create: `tests/test_pricing.py`

- [ ] **Step 1: Write tests for pricing**

Create `tests/test_pricing.py`:

```python
"""Tests for model pricing."""

from odysseus.eval.models import TokenUsage
from odysseus.eval.pricing import MODEL_PRICING, ModelPricing, compute_cost


def test_model_pricing_compute_cost():
    pricing = ModelPricing(
        input_cost_per_token=3.0 / 1_000_000,
        cached_cost_per_token=0.3 / 1_000_000,
        output_cost_per_token=15.0 / 1_000_000,
    )
    usage = TokenUsage(input_tokens=1000, cached_tokens=500, output_tokens=200)
    cost = pricing.compute_cost(usage)
    expected = (3.0 * 1000 + 0.3 * 500 + 15.0 * 200) / 1_000_000
    assert abs(cost - expected) < 1e-12


def test_compute_cost_known_model():
    usage = TokenUsage(input_tokens=100, cached_tokens=0, output_tokens=50)
    cost = compute_cost("claude-sonnet-4-20250514", usage)
    assert cost is not None
    assert cost > 0


def test_compute_cost_unknown_model():
    usage = TokenUsage(input_tokens=100, cached_tokens=0, output_tokens=50)
    cost = compute_cost("unknown-model", usage)
    assert cost is None


def test_model_pricing_dict_not_empty():
    assert len(MODEL_PRICING) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pricing.py -v`
Expected: FAIL — `odysseus.eval.pricing` does not exist yet.

- [ ] **Step 3: Implement pricing module**

Create `odysseus/eval/pricing.py`:

```python
"""Model pricing for cost computation."""

from __future__ import annotations

from odysseus.eval.models import TokenUsage
from pydantic import BaseModel


class ModelPricing(BaseModel):
    """Per-token pricing for a model."""

    input_cost_per_token: float
    cached_cost_per_token: float
    output_cost_per_token: float

    def compute_cost(self, usage: TokenUsage) -> float:
        """Compute total cost from token usage."""
        return (
            self.input_cost_per_token * usage.input_tokens
            + self.cached_cost_per_token * usage.cached_tokens
            + self.output_cost_per_token * usage.output_tokens
        )


MODEL_PRICING: dict[str, ModelPricing] = {
    "claude-sonnet-4-20250514": ModelPricing(
        input_cost_per_token=3.0 / 1_000_000,
        cached_cost_per_token=0.3 / 1_000_000,
        output_cost_per_token=15.0 / 1_000_000,
    ),
    "claude-haiku-4-5-20251001": ModelPricing(
        input_cost_per_token=0.80 / 1_000_000,
        cached_cost_per_token=0.08 / 1_000_000,
        output_cost_per_token=4.0 / 1_000_000,
    ),
    "gpt-4o": ModelPricing(
        input_cost_per_token=2.50 / 1_000_000,
        cached_cost_per_token=1.25 / 1_000_000,
        output_cost_per_token=10.0 / 1_000_000,
    ),
    "gpt-4o-mini": ModelPricing(
        input_cost_per_token=0.15 / 1_000_000,
        cached_cost_per_token=0.075 / 1_000_000,
        output_cost_per_token=0.60 / 1_000_000,
    ),
}


def compute_cost(model: str, usage: TokenUsage) -> float | None:
    """Returns cost if model is in MODEL_PRICING, None otherwise."""
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return None
    return pricing.compute_cost(usage)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pricing.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/pricing.py tests/test_pricing.py
git commit -m "feat: add model pricing module with cost computation"
```

---

### Task 4: Protocols and RunDependencies

**Files:**
- Create: `odysseus/eval/protocols.py`
- Create: `tests/test_protocols.py`

- [ ] **Step 1: Write tests for protocols**

Create `tests/test_protocols.py`:

```python
"""Tests for protocol conformance and RunDependencies."""

from typing import Any, Literal

from odysseus.eval.models import (
    EvalResult,
    Example,
    MetricConfig,
    RunReport,
    TokenUsage,
)
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

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        return {"answer": "test"}, TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5)


class StubPromptManager:
    def load(self, version: str) -> str:
        return "test prompt"


class StubDatasetManager:
    def load(self, path: str, split: Literal["dev", "holdout"]) -> list[Example]:
        return []


class StubMetricsEngine:
    def compute(self, results: list[EvalResult], metric_configs: list[MetricConfig]) -> dict[str, float]:
        return {"accuracy": 1.0}


class StubResultsCollector:
    def write_results(self, results: list[EvalResult], path: str) -> None:
        pass

    def write_report(self, report: RunReport, path: str) -> None:
        pass


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
    )
    assert deps.backend.model_name == "test-model"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_protocols.py -v`
Expected: FAIL — `odysseus.eval.protocols` does not exist yet.

- [ ] **Step 3: Implement protocols**

Create `odysseus/eval/protocols.py`:

```python
"""Protocol definitions for evaluation engine dependencies."""

from __future__ import annotations

import dataclasses
from typing import Any, Literal, Protocol, runtime_checkable

from odysseus.eval.models import (
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

    def compute(self, results: list[EvalResult], metric_configs: list[MetricConfig]) -> dict[str, float]: ...


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_protocols.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Run linting and type checking**

Run: `uv run ruff check odysseus/eval/protocols.py tests/test_protocols.py && uv run pyright odysseus/eval/protocols.py`
Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add odysseus/eval/protocols.py tests/test_protocols.py
git commit -m "feat: add protocol definitions and RunDependencies container"
```

---

## Chunk 2: Run Controller

### Task 5: Token-bucket rate limiter

**Files:**
- Create: `odysseus/eval/rate_limiter.py`
- Create: `tests/test_rate_limiter.py`

- [ ] **Step 1: Write tests for rate limiter**

Create `tests/test_rate_limiter.py`:

```python
"""Tests for the token-bucket rate limiter."""

import asyncio
import time

from odysseus.eval.rate_limiter import TokenBucketRateLimiter


async def test_acquire_basic():
    """Basic acquire should succeed immediately when capacity is available."""
    limiter = TokenBucketRateLimiter(requests_per_minute=60, tokens_per_minute=10_000)
    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.1  # Should be near-instant


async def test_acquire_respects_request_limit():
    """After exhausting request capacity, acquire should block."""
    limiter = TokenBucketRateLimiter(requests_per_minute=2, tokens_per_minute=100_000)
    # Exhaust request capacity
    await limiter.acquire()
    await limiter.acquire()
    # Third should block
    start = time.monotonic()
    await asyncio.wait_for(limiter.acquire(), timeout=2.0)
    elapsed = time.monotonic() - start
    assert elapsed > 0.3  # Had to wait for refill


async def test_consume_tokens_drives_negative():
    """Consuming more tokens than available should make subsequent acquire wait."""
    limiter = TokenBucketRateLimiter(requests_per_minute=100, tokens_per_minute=100)
    await limiter.acquire()
    limiter.consume_tokens(200)  # Drive token balance negative
    start = time.monotonic()
    await asyncio.wait_for(limiter.acquire(), timeout=3.0)
    elapsed = time.monotonic() - start
    assert elapsed > 0.3  # Had to wait for token refill


async def test_concurrent_acquire():
    """Multiple concurrent acquires should be serialized by capacity."""
    limiter = TokenBucketRateLimiter(requests_per_minute=5, tokens_per_minute=100_000)
    results: list[float] = []

    async def worker():
        await limiter.acquire()
        results.append(time.monotonic())

    tasks = [asyncio.create_task(worker()) for _ in range(5)]
    await asyncio.gather(*tasks)
    assert len(results) == 5  # All completed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rate_limiter.py -v`
Expected: FAIL — `odysseus.eval.rate_limiter` does not exist yet.

- [ ] **Step 3: Implement rate limiter**

Create `odysseus/eval/rate_limiter.py`:

```python
"""Token-bucket rate limiter with request and token budgets."""

from __future__ import annotations

import asyncio
import time


class TokenBucketRateLimiter:
    """Dual-bucket rate limiter: requests/min and tokens/min.

    - acquire() blocks until both a request slot and positive token balance are available.
    - consume_tokens() deducts tokens after a call completes (non-blocking).
    """

    def __init__(self, requests_per_minute: int, tokens_per_minute: int) -> None:
        self._rpm = requests_per_minute
        self._tpm = tokens_per_minute

        self._request_balance: float = float(requests_per_minute)
        self._token_balance: float = float(tokens_per_minute)

        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        """Refill both buckets based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now

        self._request_balance = min(
            float(self._rpm),
            self._request_balance + elapsed * self._rpm / 60.0,
        )
        self._token_balance = min(
            float(self._tpm),
            self._token_balance + elapsed * self._tpm / 60.0,
        )

    async def acquire(self) -> None:
        """Wait until both a request slot and positive token balance are available."""
        while True:
            async with self._lock:
                self._refill()
                if self._request_balance >= 1.0 and self._token_balance > 0:
                    self._request_balance -= 1.0
                    return

                # Calculate wait time for whichever bucket is limiting
                wait_request = (1.0 - self._request_balance) / (self._rpm / 60.0) if self._request_balance < 1.0 else 0
                wait_tokens = (-self._token_balance) / (self._tpm / 60.0) if self._token_balance <= 0 else 0
                wait = max(wait_request, wait_tokens, 0.01)

            await asyncio.sleep(wait)

    def consume_tokens(self, tokens: int) -> None:
        """Deduct tokens after a call completes. May drive balance negative."""
        self._token_balance -= tokens
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rate_limiter.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/rate_limiter.py tests/test_rate_limiter.py
git commit -m "feat: add token-bucket rate limiter with dual request/token budgets"
```

---

### Task 6: Run controller — core `run()` function

**Files:**
- Create: `odysseus/eval/controller.py`
- Create: `tests/test_controller.py`

This is the largest task. The test file uses the same stub classes from Task 4 but extended for controller testing.

- [ ] **Step 1: Write tests for the controller**

Create `tests/test_controller.py`:

```python
"""Tests for the run controller."""

import asyncio
from datetime import datetime, timezone
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
    return [
        Example(id=f"ex-{i}", input={"question": f"q{i}"}, expected={"answer": f"a{i}"})
        for i in range(n)
    ]


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
        concurrency=ConcurrencyConfig(max_concurrent_requests=2, requests_per_minute=1000, tokens_per_minute=1_000_000),
    )
    deps, _ = _make_deps(backend=backend, examples=_make_examples(6))
    await run(config, deps)

    assert backend._max_concurrent <= 2


async def test_output_writing():
    """Results collector receives correct data."""
    deps, collector = _make_deps()
    config = _make_config()
    report = await run(config, deps)

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_controller.py -v`
Expected: FAIL — `odysseus.eval.controller` does not exist yet.

- [ ] **Step 3: Implement the run controller**

Create `odysseus/eval/controller.py`:

```python
"""Run controller — orchestrates a single evaluation run."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from odysseus.eval.models import (
    EvalResult,
    Example,
    RetryConfig,
    RunConfig,
    RunReport,
    RunSummary,
    TokenUsage,
)
from odysseus.eval.pricing import compute_cost
from odysseus.eval.protocols import RunDependencies
from odysseus.eval.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


async def run(config: RunConfig, deps: RunDependencies) -> RunReport:
    """Execute a full evaluation run.

    1. Load prompt and data
    2. Fan out concurrent evaluations with rate limiting and retry
    3. Compute metrics
    4. Write outputs
    5. Return report
    """
    start_time = datetime.now(timezone.utc)
    logger.info("Starting evaluation run: backend=%s, data=%s, split=%s", config.backend, config.data_source, config.data_split)

    # 1. Load prompt and data
    prompt = deps.prompt_manager.load(config.prompt_version)
    examples = deps.dataset_manager.load(config.data_source, config.data_split)
    logger.info("Loaded %d examples", len(examples))

    # 2. Create parent directories for output
    Path(config.output.results_path).parent.mkdir(parents=True, exist_ok=True)
    Path(config.output.report_path).parent.mkdir(parents=True, exist_ok=True)

    # 3. Evaluate
    rate_limiter = TokenBucketRateLimiter(
        requests_per_minute=config.concurrency.requests_per_minute,
        tokens_per_minute=config.concurrency.tokens_per_minute,
    )
    semaphore = asyncio.Semaphore(config.concurrency.max_concurrent_requests)

    tasks = [
        _eval_with_retry(deps.backend, prompt, example, config.retry, rate_limiter, semaphore)
        for example in examples
    ]
    results = await asyncio.gather(*tasks)

    # 4. Compute metrics
    metrics = deps.metrics_engine.compute(list(results), config.metrics)

    # 5. Build report
    end_time = datetime.now(timezone.utc)
    succeeded = sum(1 for r in results if r.error is None)
    failed = len(results) - succeeded
    total_cost = sum(r.cost or 0.0 for r in results)

    summary = RunSummary(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        total_cost=total_cost,
        start_time=start_time,
        end_time=end_time,
        duration_seconds=(end_time - start_time).total_seconds(),
    )

    report = RunReport(
        config=config,
        metrics=metrics,
        results=list(results),
        summary=summary,
    )

    logger.info(
        "Run complete: %d/%d succeeded, cost=$%.4f, duration=%.1fs",
        succeeded, len(results), total_cost, summary.duration_seconds,
    )

    # 6. Write outputs
    deps.results_collector.write_results(list(results), config.output.results_path)
    deps.results_collector.write_report(report, config.output.report_path)

    return report


async def _eval_with_retry(
    backend: Any,
    prompt: str,
    example: Example,
    retry_config: RetryConfig,
    rate_limiter: TokenBucketRateLimiter,
    semaphore: asyncio.Semaphore,
) -> EvalResult:
    """Evaluate a single example with retry and rate limiting."""
    model_name: str = backend.model_name
    last_error: str | None = None
    latency_ms: float = 0.0

    for attempt in range(1, retry_config.max_attempts + 1):
        await rate_limiter.acquire()
        async with semaphore:
            start = time.monotonic()
            try:
                output, usage = await asyncio.wait_for(
                    backend.call(prompt, example),
                    timeout=retry_config.per_call_timeout_seconds,
                )
                latency_ms = (time.monotonic() - start) * 1000

                # Post-call token accounting
                total_tokens = usage.input_tokens + usage.cached_tokens + usage.output_tokens
                rate_limiter.consume_tokens(total_tokens)

                cost = compute_cost(model_name, usage)

                logger.debug("Example %s succeeded on attempt %d", example.id, attempt)
                return EvalResult(
                    example_id=example.id,
                    model=model_name,
                    output=output,
                    error=None,
                    latency_ms=latency_ms,
                    retries=attempt - 1,
                    token_usage=usage,
                    cost=cost,
                )

            except Exception as exc:
                latency_ms = (time.monotonic() - start) * 1000
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("Example %s failed on attempt %d: %s", example.id, attempt, last_error)

        # Backoff before retry (outside semaphore)
        if attempt < retry_config.max_attempts:
            backoff = retry_config.backoff_factor ** attempt
            await asyncio.sleep(backoff)

    # All retries exhausted
    return EvalResult(
        example_id=example.id,
        model=model_name,
        output=None,
        error=last_error,
        latency_ms=latency_ms,
        retries=retry_config.max_attempts - 1,
        token_usage=None,
        cost=None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_controller.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Run linting and type checking on all new files**

Run: `uv run ruff check odysseus/eval/ tests/ && uv run pyright odysseus/eval/`
Expected: No errors (or minor issues to fix).

- [ ] **Step 6: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests pass (including existing `test_mcp.py`).

- [ ] **Step 7: Commit**

```bash
git add odysseus/eval/controller.py tests/test_controller.py
git commit -m "feat: implement run controller with concurrency, retry, and rate limiting"
```

---

## Chunk 3: Integration and Cleanup

### Task 7: Update eval package `__init__.py` with public exports

**Files:**
- Modify: `odysseus/eval/__init__.py`

- [ ] **Step 1: Update eval `__init__.py`**

Replace the contents of `odysseus/eval/__init__.py` with:

```python
"""Evaluation engine for routing prompt assessment."""

from odysseus.eval.controller import run
from odysseus.eval.models import (
    ConcurrencyConfig,
    EvalResult,
    Example,
    MetricConfig,
    OutputConfig,
    RetryConfig,
    RunConfig,
    RunReport,
    RunSummary,
    TokenUsage,
)
from odysseus.eval.pricing import MODEL_PRICING, ModelPricing, compute_cost
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
    "DatasetManager",
    "EvalResult",
    "Example",
    "MetricConfig",
    "MetricsEngine",
    "MODEL_PRICING",
    "ModelPricing",
    "OutputConfig",
    "PromptManager",
    "ResultsCollector",
    "RetryConfig",
    "RunConfig",
    "RunDependencies",
    "RunReport",
    "RunSummary",
    "TokenUsage",
    "compute_cost",
]
```

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests pass.

- [ ] **Step 3: Run full linting and type checking**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pyright odysseus/`
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add odysseus/eval/__init__.py
git commit -m "feat: export evaluation engine public API from eval package"
```

---

### Task 8: Final verification

- [ ] **Step 1: Run complete verification**

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright odysseus/
uv run pytest -v
```

Expected: All green — no lint errors, no type errors, all tests pass.

- [ ] **Step 2: Review git log**

Run: `git log --oneline feature/eval-framework`

Verify the commit history is clean and tells the story of the implementation.
