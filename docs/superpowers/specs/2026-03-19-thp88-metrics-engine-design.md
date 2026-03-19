# THP-88 Metrics Engine Design Spec

**Goal:** Build a metrics engine with a registry pattern that computes routing-evaluation metrics over prediction results and ground-truth data.

**Approach:** Flat function registry. Each metric is a stateless function registered by name. A `DefaultMetricsEngine` class holds the registry, satisfies the `MetricsEngine` protocol, and dispatches to registered functions based on `MetricConfig` entries.

---

## Protocol Change

The `MetricsEngine` protocol in `protocols.py` gains an `examples` parameter so metrics can access ground-truth data beyond what's in `EvalResult`:

```python
class MetricsEngine(Protocol):
    def compute(
        self,
        results: list[EvalResult],
        examples: list[Example],
        metric_configs: list[MetricConfig],
    ) -> dict[str, float]: ...
```

The call site in `controller.py` (line 66) updates accordingly to pass `examples`.

## Metric Function Signature

```python
MetricFn = Callable[..., dict[str, float]]
```

Each function is called as `fn(results, examples, **config.params)` where `results` and `examples` are already filtered to error-free, ID-matched pairs.

Functions return `dict[str, float]` — a single metric may return multiple keys (e.g. per-class F1 scores). All returned dicts are merged into one flat dict.

## DefaultMetricsEngine

Single class in `odysseus/eval/metrics.py`:

```python
class DefaultMetricsEngine:
    _registry: dict[str, MetricFn]

    def __init__(self) -> None: ...
    def register(self, name: str, fn: MetricFn) -> None: ...
    def compute(self, results, examples, metric_configs) -> dict[str, float]: ...
```

### compute() behavior

1. **Pair and filter**: Match `results` to `examples` by `result.example_id == example.id`. Keep only pairs where `result.error is None`.
2. **Dispatch**: For each `MetricConfig`, look up `config.name` in `_registry`. Raise `ValueError` if not found. Call `fn(filtered_results, filtered_examples, **config.params)`.
3. **Merge**: Combine all returned dicts into one flat `dict[str, float]`.

### Factory function

```python
def create_default_engine() -> DefaultMetricsEngine:
```

Returns an engine with all built-in metrics pre-registered.

## Data Shape

Metrics operate on `EvalResult.output` and `Example.expected` with these keys:

**`output` (predicted by model):**
- `route: str` — predicted route class

**`expected` (ground truth from dataset):**
- `route: str` — ground-truth optimal route for this sample
- `routes: dict[str, {"cost": float, "quality_score": float}]` — per-class cost and quality score for this sample across all possible route classes

## Built-in Metrics

### `accuracy`

**Params:** None.

Compares `output["route"]` to `expected["route"]`. Returns:
- `accuracy`: fraction of correct predictions (`correct / total`)

### `confusion`

**Params:** None.

Builds a confusion matrix over all unique route classes. Returns flat keys:
- `confusion/{true_class}/{predicted_class}`: count for each cell

### `f1`

**Params:** None.

Computes per-class precision, recall, and F1 from confusion matrix data. Returns:
- `f1/{class_name}`: F1 score per class
- `precision/{class_name}`: precision per class
- `recall/{class_name}`: recall per class
- `f1/macro`: unweighted average F1 across classes

Edge case: if a class has zero predictions, precision is 0.0 (not undefined/NaN).

### `cost_quality_reduction`

**Params:** `baseline_class: str | None = None`

Computes cost and quality percentage change of predicted routing vs a baseline, plus oracle (theoretical optimum) reductions.

**Logic:**

1. **Determine baseline class**: If `baseline_class` is None, auto-select the class with the highest mean `quality_score` across all samples (averaging `expected["routes"][class]["quality_score"]` for each class).
2. **Baseline totals**: For each sample, sum `expected["routes"][baseline_class]["cost"]` and `["quality_score"]`.
3. **Predicted totals**: For each sample, use `output["route"]` to look up `expected["routes"][predicted_route]["cost"]` and `["quality_score"]`. Sum.
4. **Oracle totals**: For each sample, use `expected["route"]` (ground-truth optimal) to look up cost and quality. Sum.

**Returns:**
- `cost_reduction`: `(predicted_cost - baseline_cost) / baseline_cost`
- `quality_reduction`: `(predicted_quality - baseline_quality) / baseline_quality`
- `oracle_cost_reduction`: `(oracle_cost - baseline_cost) / baseline_cost`
- `oracle_quality_reduction`: `(oracle_quality - baseline_quality) / baseline_quality`

Negative `cost_reduction` = cheaper than baseline. Negative `quality_reduction` = quality loss vs baseline.

## Error Handling

- **Errored results**: Excluded from all metric computations. Paired by ID, then filtered on `error is None`.
- **Empty results after filtering**: Return 0.0 for all metrics (no division by zero).
- **Unknown metric name**: Raise `ValueError` with the unrecognized name.
- **Missing keys in output/expected**: Let the KeyError propagate — this is a data contract violation.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `odysseus/eval/metrics.py` | Create | `DefaultMetricsEngine`, all built-in metric functions, `create_default_engine()` |
| `odysseus/eval/protocols.py` | Modify | Add `examples` param to `MetricsEngine.compute()` |
| `odysseus/eval/controller.py` | Modify | Pass `examples` to `compute()` call (line 66) |
| `tests/test_metrics.py` | Create | Full test coverage |

## Testing Strategy

All tests use synthetic data with no external dependencies.

**Shared fixture:** ~10 samples, 3 route classes (`gpt-4o`, `claude-sonnet`, `haiku`), each with per-class cost/quality in `expected["routes"]`. Mix of correct and misrouted predictions.

**Test cases:**

- **accuracy**: all correct → 1.0, all wrong → 0.0, mixed → expected fraction
- **confusion**: verify cell counts against hand-computed values
- **f1**: verify per-class precision/recall/F1 and macro F1. Include a class with zero predictions to test edge handling (precision = 0.0)
- **cost_quality_reduction**:
  - Default baseline auto-selects highest quality class
  - Explicit `baseline_class` param overrides default
  - All predictions match baseline → reductions = 0.0
  - Oracle values match hand-computed percentages
- **Engine-level**:
  - Unknown metric name → `ValueError`
  - Custom metric via `register()` works
  - Errored results are filtered out
  - Empty results after filtering → graceful 0.0 returns, no division by zero
