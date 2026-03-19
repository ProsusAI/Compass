# THP-88 — Create Metrics Engine with Dynamic Metric Registration

**Type:** Task  
**Status:** To Do  
**Epic:** [THP-75](https://prosus-thymo-thesis.atlassian.net/browse/THP-75) — Eval framework Code  
**Jira:** [THP-88](https://prosus-thymo-thesis.atlassian.net/browse/THP-88)

## Description

Build the metrics engine to register and select metrics at runtime, support built-in and custom metrics, and process metric specifications from config files. Ensure metrics operate on prediction, ground truth, and metadata tuples.

## What to build

Implement a concrete class that satisfies the `MetricsEngine` protocol defined in `odysseus/eval/protocols.py`:

```python
class MetricsEngine(Protocol):
    def compute(
        self,
        results: list[EvalResult],
        metric_configs: list[MetricConfig],
    ) -> dict[str, float]: ...
```

The implementation should:

- **Registry pattern** — maintain a dict mapping metric names (strings) to callable implementations. Built-in metrics (e.g. `exact_match`, `f1`, `accuracy`) are pre-registered at import time.
- **Dynamic registration** — expose a `register(name, fn)` method so callers can add custom metrics without subclassing.
- **Metric callables** — each metric function receives `(results: list[EvalResult], **params) -> float`. It should only operate on results where `error is None`.
- **Config-driven selection** — `compute()` iterates over `metric_configs`, looks up each `config.name` in the registry, calls the function with `config.params` unpacked as kwargs, and returns a `dict[str, float]` keyed by metric name.
- **Error handling** — raise a clear `ValueError` if a requested metric name is not registered.

Suggested file: `odysseus/eval/metrics.py`

## How it links with the rest of the codebase

| Touch point | Detail |
|---|---|
| `odysseus/eval/protocols.py` | Defines the `MetricsEngine` protocol this class must satisfy. |
| `odysseus/eval/models.py` | Consumes `EvalResult` (especially `output`, `error`, `token_usage`) and `MetricConfig` (`name`, `params`). |
| `odysseus/eval/controller.py` | Calls `deps.metrics_engine.compute(list(results), config.metrics)` after all examples complete. The returned `dict[str, float]` goes directly into `RunReport.metrics`. |
| `odysseus/eval/models.py` (`RunConfig`) | `config.metrics: list[MetricConfig]` specifies which metrics to run and with what parameters. |
| `odysseus/mcp.py` | The MCP tool will wire a concrete `MetricsEngine` into `RunDependencies` before calling `run()`. |

## Dependencies between tasks

- No hard blockers — can be developed and unit-tested independently using protocol + model types.
- THP-92 (Run Controller) consumes this via `RunDependencies.metrics_engine`.
- THP-93 (Configuration Schema) defines `MetricConfig`; that model is already implemented in `models.py`.
