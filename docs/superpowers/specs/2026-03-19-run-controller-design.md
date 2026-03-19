# THP-92 — Run Controller Orchestrator Design

**Date:** 2026-03-19
**Status:** Approved
**Ticket:** [THP-92](https://prosus-thymo-thesis.atlassian.net/browse/THP-92)

## Overview

A Run Controller that loads configuration, initializes components via protocol-based dependency injection, executes the evaluation loop with concurrency and retry, triggers scoring, writes outputs, and returns a structured report. All dependencies are defined as `typing.Protocol` classes — no concrete implementations are built in this ticket.

## Design Decisions

- **Protocol-based DI** over ABCs or callbacks — maximally testable, pyright-friendly, no inheritance coupling
- **Pydantic config model** as the core API, with a `RunConfig.from_yaml(path)` classmethod for loading from YAML files
- **Single async function** `run(config, deps) -> RunReport` — no class instantiation needed
- **LiteLLM** for multi-provider backend support — wraps `litellm.acompletion()` behind the `Backend` protocol. Note: `litellm` must be added to `pyproject.toml` dependencies.
- **Retry then continue** error handling — retry with exponential backoff, then record failures and compute metrics on successes only
- **Controller writes outputs** — JSONL results + JSON report to paths from config, creating parent directories if needed
- **`RunDependencies` uses `dataclasses.dataclass`** instead of Pydantic `BaseModel` because protocol types cannot be validated by Pydantic
- **Config shape supersedes README** — the `RunConfig` model here is the source of truth; the README's YAML example is illustrative and may diverge

## Data Models (`odysseus/eval/models.py`)

### RunConfig

```python
class RunConfig(BaseModel):
    backend: str                    # Label for record-keeping in the report (not used for dispatch — Backend is injected via deps)
    prompt_version: str = "latest"  # Passed to PromptManager.load(), which resolves "latest" to a concrete version
    data_source: str                # Path to JSONL file
    data_split: Literal["dev", "holdout"]
    metrics: list[MetricConfig]
    concurrency: ConcurrencyConfig = ConcurrencyConfig()
    retry: RetryConfig = RetryConfig()
    output: OutputConfig = OutputConfig()

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RunConfig":
        """Load config from a YAML file. Validates via Pydantic on construction."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)
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
    per_call_timeout_seconds: float = 60.0  # Timeout for a single backend.call()

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
    input_tokens: int      # Excludes cached tokens (disjoint with cached_tokens)
    cached_tokens: int     # Tokens served from cache (disjoint with input_tokens)
    output_tokens: int

class EvalResult(BaseModel):
    example_id: str
    model: str                          # Model used for this evaluation
    output: dict[str, Any] | None
    error: str | None
    latency_ms: float                   # Latency of the single successful call (not including prior failed retries)
    retries: int                        # Number of retry attempts before success/failure (0 = first attempt succeeded)
    token_usage: TokenUsage | None
    cost: float | None                  # Computed in _eval_with_retry from model + token_usage via MODEL_PRICING

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

def compute_cost(model: str, usage: TokenUsage) -> float | None:
    """Returns cost if model is in MODEL_PRICING, None otherwise."""
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return None
    return pricing.compute_cost(usage)
```

## Protocols (`odysseus/eval/protocols.py`)

```python
class Backend(Protocol):
    @property
    def model_name(self) -> str: ...

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]: ...

class PromptManager(Protocol):
    def load(self, version: str) -> str: ...
    # "latest" resolution is the PromptManager's responsibility

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

1. **Load prompt** — `deps.prompt_manager.load(config.prompt_version)` (PromptManager resolves `"latest"`)
2. **Load data** — `deps.dataset_manager.load(config.data_source, config.data_split)`
3. **Create parent directories** for output paths if they don't exist
4. **Evaluate** — fan out all examples via `asyncio.gather(*tasks)`:
   - Each example dispatched to `_eval_with_retry(backend, prompt, example, retry_config, rate_limiter, semaphore)`
   - Per attempt: rate limiter `acquire()` first (checks both request slot + token balance), then semaphore — this ordering prevents deadlock
   - `asyncio.wait_for(backend.call(), timeout)` for per-call timeout
   - Token usage deducted **post-call** via `rate_limiter.consume_tokens()` since exact count is unknown before the call
   - On failure: retry with exponential backoff (semaphore released during backoff), after exhausting retries record error in `EvalResult`
   - Cost computed via `pricing.compute_cost(model, usage)`. Returns `None` if model not in `MODEL_PRICING`.
5. **Compute metrics** — `deps.metrics_engine.compute(results, config.metrics)`
6. **Write outputs** — results JSONL + report JSON via `deps.results_collector`
7. **Return `RunReport`**

### Internal Components

**Token-bucket rate limiter** (not exposed as protocol):
- Single class with two internal buckets: requests/min and tokens/min
- `async def acquire()` — waits until both a request slot AND positive token balance are available. Initial capacity for each = their per-minute limit. Refills at the per-minute rate over 60 seconds.
- `def consume_tokens(tokens: int)` — deducts tokens after a call completes (synchronous, non-blocking). May drive token balance negative, which causes subsequent `acquire()` calls to wait until refill restores positive balance.
- Refill is computed from elapsed time since last refill, capped at max capacity.
- The `TokenUsage` contract is Anthropic-style (disjoint): total tokens consumed = `input_tokens + cached_tokens + output_tokens`. The LiteLLM `Backend` implementation must normalize provider responses to this convention.

**Retry wrapper:**
- `async def _eval_with_retry(backend, prompt, example, retry_config, rate_limiter, semaphore) -> EvalResult`
- Each attempt: acquire rate limiter → acquire semaphore → `asyncio.wait_for(backend.call(), timeout=retry_config.per_call_timeout_seconds)` → release semaphore → consume_tokens from rate limiter
- Semaphore is acquired and released per-attempt (not held across retries) so slots are freed during backoff waits
- `latency_ms` records the duration of the final attempt only (successful or last failure)
- `retries` records how many attempts preceded the final one (0 = succeeded on first try)
- Exponential backoff: `backoff_factor ** attempt` seconds between retries (1-indexed, so first retry waits `backoff_factor` seconds)
- Returns error result after `max_attempts` exhausted

**Logging:**
- Uses `logging.getLogger(__name__)` for structured logging
- Logs at INFO: run start/end, total examples, summary metrics
- Logs at WARNING: individual example failures, retries
- Logs at DEBUG: per-example completion

## File Layout

```
odysseus/eval/
  models.py        # Pydantic models
  protocols.py     # Protocol classes + RunDependencies
  controller.py    # run(), rate limiter, retry logic
  pricing.py       # ModelPricing, MODEL_PRICING dict, compute_cost()

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
6. **Timeout** — backend hangs past `per_call_timeout_seconds`; verify timeout recorded as error
7. **YAML loading** — `RunConfig.from_yaml()` with valid YAML; verify round-trips correctly. Invalid YAML raises Pydantic `ValidationError`.
