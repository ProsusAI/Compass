# THP-92 — Run Controller Orchestrator Design

**Date:** 2026-03-19
**Status:** Approved
**Ticket:** [THP-92](https://prosus-thymo-thesis.atlassian.net/browse/THP-92)

## Overview

A Run Controller that loads configuration, initializes components via protocol-based dependency injection, executes the evaluation loop with concurrency and retry, triggers scoring, writes outputs, and returns a structured report. All dependencies are defined as `typing.Protocol` classes — no concrete implementations are built in this ticket.

## Design Decisions

- **Protocol-based DI** over ABCs or callbacks — maximally testable, pyright-friendly, no inheritance coupling
- **Pydantic config model** as the core API — no YAML loader in scope (can be added later as a classmethod)
- **Single async function** `run(config, deps) -> RunReport` — no class instantiation needed
- **LiteLLM** for multi-provider backend support — wraps `litellm.acompletion()` behind the `Backend` protocol
- **Retry then continue** error handling — retry with exponential backoff, then record failures and compute metrics on successes only
- **Controller writes outputs** — JSONL results + JSON report to paths from config

## Data Models (`odysseus/eval/models.py`)

### RunConfig

```python
class RunConfig(BaseModel):
    backend: str                    # Name from backend registry
    prompt_version: str = "latest"  # Version identifier
    data_source: str                # Path to JSONL file
    data_split: Literal["dev", "holdout"]
    metrics: list[MetricConfig]
    concurrency: ConcurrencyConfig = ConcurrencyConfig()
    retry: RetryConfig = RetryConfig()
    output: OutputConfig = OutputConfig()
```

### Supporting Config Models

```python
class MetricConfig(BaseModel):
    name: str
    params: dict[str, Any] = {}

class ConcurrencyConfig(BaseModel):
    max_concurrent_requests: int = 20
    requests_per_minute: int = 500
    tokens_per_minute: int = 100_000

class RetryConfig(BaseModel):
    max_attempts: int = 3
    backoff_factor: float = 2.0

class OutputConfig(BaseModel):
    results_path: str = "outputs/results.jsonl"
    report_path: str = "outputs/report.json"
```

### Example & Results

```python
class Example(BaseModel):
    id: str
    input: dict[str, Any]
    expected: dict[str, Any]

class TokenUsage(BaseModel):
    input_tokens: int
    cached_tokens: int
    output_tokens: int

class EvalResult(BaseModel):
    example_id: str
    model: str                          # Model used for this evaluation
    output: dict[str, Any] | None
    error: str | None
    latency_ms: float
    token_usage: TokenUsage | None
    cost: float | None                  # Computed from model + token_usage via MODEL_PRICING

class RunSummary(BaseModel):
    total: int
    succeeded: int
    failed: int
    total_cost: float
    start_time: datetime
    end_time: datetime
    duration_seconds: float

class RunReport(BaseModel):
    config: RunConfig
    metrics: dict[str, float]
    results: list[EvalResult]
    summary: RunSummary
```

## Pricing (`odysseus/eval/pricing.py`)

```python
class ModelPricing(BaseModel):
    input_cost_per_token: float
    cached_cost_per_token: float
    output_cost_per_token: float

    def compute_cost(self, usage: TokenUsage) -> float:
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
    # Add more models as needed
}
```

## Protocols (`odysseus/eval/protocols.py`)

```python
class Backend(Protocol):
    @property
    def model_name(self) -> str: ...

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]: ...

class PromptManager(Protocol):
    def load(self, version: str) -> str: ...

class DatasetManager(Protocol):
    def load(self, path: str, split: Literal["dev", "holdout"]) -> list[Example]: ...

class MetricsEngine(Protocol):
    def compute(self, results: list[EvalResult], metric_configs: list[MetricConfig]) -> dict[str, float]: ...

class ResultsCollector(Protocol):
    def write_results(self, results: list[EvalResult], path: str) -> None: ...
    def write_report(self, report: RunReport, path: str) -> None: ...
```

Grouped into:

```python
@dataclasses.dataclass
class RunDependencies:
    backend: Backend
    prompt_manager: PromptManager
    dataset_manager: DatasetManager
    metrics_engine: MetricsEngine
    results_collector: ResultsCollector
```

## Run Controller (`odysseus/eval/controller.py`)

### Public Interface

```python
async def run(config: RunConfig, deps: RunDependencies) -> RunReport
```

### Flow

1. **Load prompt** — `deps.prompt_manager.load(config.prompt_version)`
2. **Load data** — `deps.dataset_manager.load(config.data_source, config.data_split)`
3. **Evaluate** — fan out all examples concurrently:
   - `asyncio.Semaphore(config.concurrency.max_concurrent_requests)` for concurrency control
   - Token-bucket rate limiter for `requests_per_minute` and `tokens_per_minute`
   - Per-example: call backend, wrap into `EvalResult` with model name, latency, token usage, computed cost
   - On failure: retry with exponential backoff, after exhausting retries record error in `EvalResult`
4. **Compute metrics** — `deps.metrics_engine.compute(results, config.metrics)`
5. **Write outputs** — results JSONL + report JSON via `deps.results_collector`
6. **Return `RunReport`**

### Internal Components

**Token-bucket rate limiter** (not exposed as protocol):
- Two buckets: requests/min and tokens/min
- `async def acquire(self, tokens: int = 1)` — waits until capacity available
- Refills based on elapsed time

**Retry wrapper:**
- `async def _eval_with_retry(backend, prompt, example, retry_config) -> EvalResult`
- Exponential backoff: `backoff_factor ** attempt` seconds between retries
- Returns error result after `max_attempts` exhausted

## File Layout

```
odysseus/eval/
  models.py        # Pydantic models
  protocols.py     # Protocol classes + RunDependencies
  controller.py    # run(), rate limiter, retry logic
  pricing.py       # ModelPricing, MODEL_PRICING dict

tests/
  test_controller.py
```

## Testing Strategy

All dependencies mocked via simple classes conforming to protocols. No disk I/O, no real API calls.

**Test cases:**
1. **Happy path** — 5 examples all succeed; verify report counts, metrics, total cost
2. **Partial failure with retry** — backend fails twice then succeeds; verify retry fires, result is successful
3. **Exhausted retries** — backend always fails; verify error in result, metrics on successes only
4. **Concurrency** — verify semaphore limits max concurrent calls
5. **Output writing** — verify results collector receives correct data
