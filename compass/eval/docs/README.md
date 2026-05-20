# Eval Framework

The `compass.eval` package implements an automated evaluation loop for routing-prompt optimisation. Given a versioned prompt, a dataset, and a backend, it fans out concurrent LLM calls, computes routing metrics, and writes a structured report. The pipeline is intentionally narrow: it evaluates one prompt version against one dataset split and returns a `RunReport` — the optimisation loop that iterates over prompt versions lives above this layer.

## Module inventory

| Module | Class / function | Role |
|--------|-----------------|------|
| `eval/controller.py` | `run()`, `_eval_with_retry()` | Orchestrates a full evaluation run |
| `eval/models.py` | `RunConfig`, `ConcurrencyConfig`, `RetryConfig`, `OutputConfig`, `MetricConfig`, `Example`, `TokenUsage`, `EvalResult`, `RunSummary`, `RunReport` | All Pydantic config and result models |
| `eval/protocols.py` | `Backend`, `PromptManager`, `DatasetManager`, `MetricsEngine`, `ResultsCollector`, `RunDependencies` | Protocol interfaces + dependency-injection container |
| `eval/rate_limiter.py` | `TokenBucketRateLimiter` | Dual-bucket rate limiter (requests/min + tokens/min) |
| `eval/metrics.py` | `DefaultMetricsEngine`, `create_default_engine()` | Registry-based metrics engine with 4 built-in metrics |
| `eval/dataset.py` | `JsonlDatasetManager` | JSONL dataset loader with dev/holdout split filtering |
| `eval/collector.py` | `JsonResultsCollector` | Writes JSONL results and JSON report; diffs vs previous run |
| `eval/pricing.py` | `ModelPricing`, `compute_cost()` | Per-token cost model and cost computation |
| `eval/backends/` | `BackendProfile`, `BackendRegistry`, `AnthropicBackend`, `OpenAIBackend`, `BedrockBackend` | YAML-driven backend registry with direct provider SDK clients |
| `prompts/manager.py` | `FilePromptManager` | Versioned prompt loading from disk with hot-reload |

## Documentation

- [architecture.md](architecture.md) — system design, data flow, full component and field reference
- [backends.md](backends.md) — backend registry deep-dive: YAML format, provider examples, error reference

## Quick-start

```python
import asyncio
from pathlib import Path

from compass.eval import run
from compass.eval.models import RunConfig, MetricConfig
from compass.eval.protocols import RunDependencies
from compass.eval.backends import BackendRegistry
from compass.eval.metrics import create_default_engine
from compass.eval.dataset import JsonlDatasetManager
from compass.eval.collector import JsonResultsCollector
from compass.prompts.manager import FilePromptManager

async def main() -> None:
    # 1. Load the backend profile from YAML
    registry = BackendRegistry.from_directory(Path("backends"))
    profile = registry.get_profile("claude-sonnet")
    backend = registry.create_backend("claude-sonnet")

    # 2. Assemble dependencies
    deps = RunDependencies(
        backend=backend,
        prompt_manager=FilePromptManager("prompts"),
        dataset_manager=JsonlDatasetManager(),
        metrics_engine=create_default_engine(),
        results_collector=JsonResultsCollector(),
        requests_per_minute=profile.requests_per_minute,
        tokens_per_minute=profile.tokens_per_minute,
    )

    # 3. Define the run
    config = RunConfig(
        backend="claude-sonnet",
        prompt_version="latest",
        data_source="data/routing.jsonl",
        data_split="dev",
        metrics=[MetricConfig(name="accuracy"), MetricConfig(name="f1")],
    )

    # 4. Run and inspect
    report = await run(config, deps)
    print(f"Accuracy: {report.metrics['accuracy']:.3f}")
    print(f"Cost: ${report.summary.total_cost:.4f}")

asyncio.run(main())
```

The `backends/` directory must contain at least one `.yaml` profile file. See [backends.md](backends.md) for the YAML format and provider examples.
