# Stage 5: Final Report Redesign

## Overview

Redesign the Stage 5 final report to surface actionable information first (inverted pyramid), fix the `route_distribution` validation bug, add baseline comparison and confusion matrix, strip optimizer internals, and provide the agent with a concrete report template.

## Bug Fix

### `DatasetOverview.route_distribution` type mismatch

**Problem:** `stratified_split()` in `split.py` produces `route_distribution` as `dict[str, dict[str, int]]` (nested with dev/holdout counts), but `DatasetOverview` in `models.py` declares it as `dict[str, int]`. The preprocessor passes it through without transforming, causing Pydantic validation failure in `build_final_report_briefing`.

**Root cause:** `_load_dataset_overview()` in `preprocessor.py` (line ~131) reads the nested dict from `split_report.json` and passes it directly to `DatasetOverview`.

**Fix:** Change `DatasetOverview.route_distribution` to `dict[str, dict[str, int]]` to match the actual pipeline output. The report template will show both totals and per-split breakdown.

**Test fix:** Update `tests/test_final_report_preprocessor.py` which currently uses flat format. Corrected fixture:

```json
{
  "dev_count": 80,
  "holdout_count": 20,
  "route_distribution": {
    "haiku": {"dev": 48, "holdout": 12},
    "sonnet": {"dev": 24, "holdout": 6},
    "opus": {"dev": 8, "holdout": 2}
  }
}
```

## Report Structure

Restructured as an inverted pyramid: actionable content at top, supporting detail below.

### Top: Actionable

| # | Section | Description |
|---|---------|-------------|
| 1 | Executive Summary | 3-5 sentences: problem, outcome, recommendation |
| 2 | Recommended Prompt | Full prompt text in code block. Cross-link: "See [Usage Guide](#usage-guide) for deployment instructions and limitations." |
| 3 | Results | Best prompt version, quality, cost, round. Dev vs holdout metric table with deltas (flag >5% as overfitting signal) |
| 4 | Per-Class Performance | Table: route, precision, recall, F1, support |
| 5 | Strengths & Weaknesses | Agent synthesis of high/low performing routes, cost tradeoffs, recommendations |
| 6 | Error Analysis | Overall error rate + confusion matrix (expected vs predicted route counts). No sample examples. |

### Bottom: Supporting Detail

| # | Section | Description |
|---|---------|-------------|
| 7 | Baseline Comparison | **New.** Table comparing: always-cheapest, always-capable, optimized prompt. Quality and cost for each. |
| 8 | Problem Definition | From `input_report.md` |
| 9 | Dataset Overview | Total, dev/holdout counts, route distribution (per-split breakdown) |
| 10 | Optimization Process | Rounds, convergence reason, stagnation count, quality/cost progression charts. No mutation analysis. Oracle as brief note. |
| 11 | Pareto Front | Scatter chart + table of all Pareto members |
| 12 | Usage Guide | Deployment instructions, expected accuracy/cost, when to re-run, limitations |

## Model Changes

### File: `odysseus/agents/final_report/models.py`

#### `DatasetOverview` — fix route_distribution type

```python
class DatasetOverview(BaseModel):
    """Dataset size and distribution summary."""
    total_examples: int
    dev_count: int
    holdout_count: int
    route_distribution: dict[str, dict[str, int]]  # Changed: nested {route: {dev: N, holdout: N}}
    routes: list[str]
    dimensions: list[str]
```

#### `ConfusionEntry` — new model

```python
class ConfusionEntry(BaseModel):
    """Single cell in the confusion matrix."""
    expected: str
    predicted: str
    count: int
```

#### `ErrorAnalysis` — replaces `ErrorSummary`

```python
class ErrorAnalysis(BaseModel):
    """Holdout error analysis with confusion matrix."""
    total_evaluated: int
    total_errors: int
    error_rate: float
    confusion_matrix: list[ConfusionEntry]
```

Drop `MisroutedExample` model and `misrouted_samples` field entirely.

#### `BaselineResult` — new model

```python
class BaselineResult(BaseModel):
    """Performance of a single baseline strategy."""
    strategy: str          # e.g., "always_cheapest", "always_capable"
    route: str             # Which route this strategy always picks
    quality_score: float   # Mean quality across holdout examples
    cost: float            # Mean cost across holdout examples
```

#### `BaselineComparison` — new model, optional on briefing

```python
class BaselineComparison(BaseModel):
    """Comparison of optimized prompt against naive baselines."""
    baselines: list[BaselineResult]
    optimized: BaselineResult
```

**Note:** `baseline_comparison` is `BaselineComparison | None = None` on `FinalReportBriefing` for graceful degradation when running on older pipeline outputs that lack `baseline_comparison.json`.

#### `OptimizationJourney` — strip mutation fields, add oracle

Remove:
- `mutation_type_counts: dict[str, int]`
- `effective_mutation_types: list[str]`
- `ineffective_mutation_types: list[str]`
- `mutation_mode: str`

Keep:
- `total_rounds: int`
- `convergence_reason: str`
- `stagnation_count: int`
- `best_quality_per_round: list[float]`
- `best_cost_per_round: list[float]`
- `pareto_front_size_per_round: list[int]`

Add (folded from `OracleAnalysis`):
- `oracle_cost_reduction: float | None = None`
- `oracle_quality_reduction: float | None = None`

#### `OracleAnalysis` — remove standalone model

The `candidate_*` fields (`candidate_cost_reduction`, `candidate_cost_reduction_with_overhead`, `candidate_quality_reduction`) are intentionally dropped from the briefing model. These values duplicate what's already in `eval_comparison` (the `cost_reduction` and `quality_reduction` metrics appear in the dev vs holdout comparison table). Only the oracle ceiling values are retained as a brief note in the optimization section.

#### `FinalReportBriefing` — update field references

```python
class FinalReportBriefing(BaseModel):
    """Complete pre-processed briefing for the Final Report Agent."""
    run_id: str
    backend_name: str
    problem_summary: str
    dataset_overview: DatasetOverview
    optimization_journey: OptimizationJourney       # Now includes oracle note
    best_prompt: PromptSummary
    best_prompt_text: str
    pareto_front: list[PromptSummary]
    eval_comparison: list[EvalMetricComparison]
    per_class_performance: list[PerClassPerformance]
    baseline_comparison: BaselineComparison | None = None  # New, optional for back-compat
    error_analysis: ErrorAnalysis                          # Renamed from error_summary
    charts: ChartPaths
```

## Preprocessor Changes

### File: `odysseus/agents/final_report/preprocessor.py`

#### Import updates

Replace:
```python
from odysseus.agents.final_report.models import (
    ErrorSummary, MisroutedExample, OracleAnalysis, ...
)
```
With:
```python
from odysseus.agents.final_report.models import (
    ErrorAnalysis, ConfusionEntry, BaselineComparison, BaselineResult, ...
)
```

#### `build_final_report_briefing()` — update orchestration

- Remove `mutation_log = _load_json(run_dir / "search" / "mutation_log.json", default=[])` (line 50)
- Remove `mutation_log` argument from `_build_optimization_journey()` call
- Replace `oracle_analysis = _extract_oracle_analysis(holdout_report)` — fold oracle into journey
- Replace `error_summary = _build_error_summary(run_dir)` with `error_analysis = _build_error_analysis(run_dir)`
- Add `baseline_comparison = _build_baseline_comparison(run_dir)`
- Update `FinalReportBriefing(...)` constructor kwargs:
  - `error_summary=error_summary` → `error_analysis=error_analysis`
  - Remove `oracle_analysis=oracle_analysis`
  - Add `baseline_comparison=baseline_comparison`

#### `_load_dataset_overview()` — no change needed

The nested `route_distribution` from `split_report.json` is already passed through as-is. The fix is purely in the model type annotation.

#### `_build_optimization_journey()` — strip mutation, add oracle

- Remove `mutation_log` parameter entirely
- Remove all mutation analysis code (lines 199-225)
- Accept `holdout_report` as a new parameter
- Extract `oracle_cost_reduction` and `oracle_quality_reduction` from `holdout_report.get("metrics", {})` and pass to `OptimizationJourney` constructor

#### `_build_error_analysis()` — replaces `_build_error_summary()`

```python
def _build_error_analysis(run_dir: Path) -> ErrorAnalysis:
    """Build confusion matrix from holdout eval results."""
    # Load holdout examples by ID for expected routes
    examples_by_id = _load_holdout_examples(run_dir)
    eval_results = _load_eval_results(run_dir)

    if not eval_results:
        return ErrorAnalysis(total_evaluated=0, total_errors=0, error_rate=0.0, confusion_matrix=[])

    # Build (expected, predicted) pairs
    pairs: list[tuple[str, str]] = []
    for r in eval_results:
        eid = r.get("example_id", "")
        ex = examples_by_id.get(eid, {})
        expected = ex.get("expected", {}).get("route", "unknown")
        output = r.get("output")
        error = r.get("error")
        if error:
            predicted = "(error)"
        elif output:
            predicted = output.get("route", "(no route)")
        else:
            predicted = "(no output)"
        pairs.append((expected, predicted))

    # Count each (expected, predicted) combination
    from collections import Counter
    counts = Counter(pairs)
    confusion_matrix = [
        ConfusionEntry(expected=exp, predicted=pred, count=cnt)
        for (exp, pred), cnt in sorted(counts.items())
    ]

    total = len(pairs)
    errors = sum(1 for exp, pred in pairs if exp != pred)

    return ErrorAnalysis(
        total_evaluated=total,
        total_errors=errors,
        error_rate=round(errors / total, 4) if total > 0 else 0.0,
        confusion_matrix=confusion_matrix,
    )
```

#### `_build_baseline_comparison()` — new function

```python
def _build_baseline_comparison(run_dir: Path) -> BaselineComparison | None:
    """Load baseline comparison results computed during holdout eval."""
    data = _load_json(run_dir / "holdout_eval" / "baseline_comparison.json")
    if not data or not isinstance(data, dict):
        return None
    try:
        return BaselineComparison(**data)
    except Exception:
        logger.debug("Could not parse baseline_comparison.json")
        return None
```

#### Remove `_extract_oracle_analysis()` function entirely

## Holdout Eval Changes

### File: `odysseus/mcp/final_report_tools.py`

#### `run_holdout_eval()` — compute baselines after eval completes

Baseline computation happens in the `run_holdout_eval` tool function, **after** `EvalRunnerAgent.run()` returns and before the tool returns its result. This keeps `EvalRunnerAgent` unchanged.

**Concrete computation logic** (mirrors `compute_cost_quality_reduction` in `odysseus/eval/metrics.py`):

```python
def _compute_baselines(
    holdout_examples: list[dict],
    eval_results: list[dict],
) -> dict | None:
    """Compute baseline strategy performance on holdout set.

    Uses the same per-example route cost/quality data that the main eval uses.

    Invariant: every example has every route in its expected.routes dict.
    This is guaranteed by the data validation stage (stratified_split).
    The existing compute_cost_quality_reduction in metrics.py relies on
    the same invariant (it accesses routes[baseline_class] without guard).
    """
    # For each example, ex["expected"]["routes"][route] has .cost and .quality_score

    route_cost_sums: dict[str, float] = {}
    route_quality_sums: dict[str, float] = {}

    for ex in holdout_examples:
        routes = ex.get("expected", {}).get("routes", {})
        for route_name, route_data in routes.items():
            cost = route_data.get("cost", 0.0) or 0.0
            quality = route_data.get("quality_score", 0.0) or 0.0
            route_cost_sums[route_name] = route_cost_sums.get(route_name, 0.0) + cost
            route_quality_sums[route_name] = route_quality_sums.get(route_name, 0.0) + quality

    n = len(holdout_examples)
    if n == 0:
        return None

    # Always-cheapest: route with lowest mean cost
    cheapest_route = min(
        route_cost_sums,
        key=lambda r: route_cost_sums[r] / n,
    )
    cheapest_quality = route_quality_sums[cheapest_route] / n
    cheapest_cost = route_cost_sums[cheapest_route] / n

    # Always-capable: route with highest mean quality_score
    # (matches _select_baseline_class logic in metrics.py)
    capable_route = min(
        route_quality_sums,
        key=lambda r: (-route_quality_sums[r] / n, r),
    )
    capable_quality = route_quality_sums[capable_route] / n
    capable_cost = route_cost_sums[capable_route] / n

    # 4. Optimized prompt: actual holdout eval results
    optimized_cost = 0.0
    optimized_quality = 0.0
    counted = 0
    example_by_id = {ex.get("id"): ex for ex in holdout_examples}
    for r in eval_results:
        if r.get("error"):
            continue
        eid = r.get("example_id")
        ex = example_by_id.get(eid)
        if not ex:
            continue
        pred_route = r.get("output", {}).get("route")
        routes = ex.get("expected", {}).get("routes", {})
        if pred_route and pred_route in routes:
            optimized_cost += routes[pred_route].get("cost", 0.0) or 0.0
            optimized_quality += routes[pred_route].get("quality_score", 0.0) or 0.0
            counted += 1

    if counted > 0:
        optimized_cost /= counted
        optimized_quality /= counted

    return {
        "baselines": [
            {
                "strategy": "always_cheapest",
                "route": cheapest_route,
                "quality_score": round(cheapest_quality, 4),
                "cost": round(cheapest_cost, 4),
            },
            {
                "strategy": "always_capable",
                "route": capable_route,
                "quality_score": round(capable_quality, 4),
                "cost": round(capable_cost, 4),
            },
        ],
        "optimized": {
            "strategy": "optimized_prompt",
            "route": "mixed",
            "quality_score": round(optimized_quality, 4),
            "cost": round(optimized_cost, 4),
        },
    }
```

After computing, write to `run_dir / "holdout_eval" / "baseline_comparison.json"`.

**Integration point in `run_holdout_eval`:** Insert baseline computation between the `score_report` extraction and the return statement (current lines ~208-209 in `final_report_tools.py`):

```python
# After: score_report = ScoreReport(...)
# Before: return score_report.model_dump_json(...)

# Compute and write baseline comparison
holdout_examples = [json.loads(line) for line in holdout_jsonl_text.splitlines() if line.strip()]
eval_result_lines = (run_dir / "holdout_eval" / "results.jsonl").read_text().splitlines()
eval_results = [json.loads(l) for l in eval_result_lines if l.strip() and '"__meta__"' not in l]
baseline_data = _compute_baselines(holdout_examples, eval_results)
if baseline_data:
    (run_dir / "holdout_eval" / "baseline_comparison.json").write_text(
        json.dumps(baseline_data, indent=2)
    )
```

**Data sources within `run_holdout_eval`:**
- `holdout_examples`: already loaded from `analysis/holdout.jsonl` (used for the eval itself)
- `eval_results`: available from `results.jsonl` after eval completes

#### `build_final_report_briefing` — no artifact check change needed

The `baseline_comparison` field is optional (`| None = None`), so a missing `baseline_comparison.json` simply results in `None` — consistent with the graceful degradation pattern used throughout the preprocessor.

## Agent Prompt Changes

### File: `odysseus/agents/prompts/final_report_system.md`

- Update report generation instructions to reference the new section order
- Remove mutation analysis and sample misrouted example instructions
- Add confusion matrix rendering instructions: "Render confusion_matrix as a proper matrix table with expected routes as rows and predicted routes as columns"
- Add baseline comparison section instructions
- Add cross-link instruction: "The Recommended Prompt section must include a link to the Usage Guide: `See [Usage Guide](#usage-guide) for deployment instructions and limitations.`"
- Replace inline template description with: "Follow the report structure in `final_report_template.md`. Use it as the skeleton — fill in data from the briefing JSON, omit sections where data is null."
- Update sign convention note to cover oracle values in optimization section

### File: `odysseus/agents/prompts/final_report_template.md` — new

A concrete markdown skeleton the agent follows. Placeholders for dynamic content, exact heading structure, cross-links. Conditional sections marked with comments.

```markdown
# Routing Prompt Optimization Report

## Executive Summary

{3-5 sentences: what problem was solved, what was achieved, what to do next}

## Recommended Prompt

> See [Usage Guide](#usage-guide) for deployment instructions and limitations.

\`\`\`
{best_prompt_text}
\`\`\`

## Results

**Best prompt:** {version} | Quality: {quality_score} | Cost: {cost} | Introduced: round {round}

| Metric | Dev | Holdout | Delta |
|--------|-----|---------|-------|
| {metric} | {dev_value} | {holdout_value} | {delta} |

{Flag any |delta| >5% as potential overfitting signal}

## Per-Class Performance

| Route | Precision | Recall | F1 | Support |
|-------|-----------|--------|----|---------|
| {route} | {precision} | {recall} | {f1} | {support} |

## Strengths & Weaknesses

{Agent synthesis: high-performing routes, cost savings, low-recall routes, actionable recommendations}

## Error Analysis

**Error rate:** {error_rate}% ({total_errors}/{total_evaluated})

**Confusion Matrix:**

| Expected \ Predicted | {route_1} | {route_2} | ... |
|---------------------|-----------|-----------|-----|
| {route_1}           | {count}   | {count}   | ... |

{Brief interpretation of dominant misclassification patterns}

---

<!-- Sections below are supporting detail -->

<!-- Include only if baseline_comparison is not null -->
## Baseline Comparison

| Strategy | Quality | Cost |
|----------|---------|------|
| Always cheapest ({route}) | {quality} | {cost} |
| Always most capable ({route}) | {quality} | {cost} |
| **Optimized prompt ({version})** | **{quality}** | **{cost}** |

{Contextual sentence positioning the optimized prompt between the two baselines}

## Problem Definition

{problem_summary from input_report.md}

## Dataset Overview

| | Total | Dev | Holdout |
|--|-------|-----|---------|
| Examples | {total} | {dev_count} | {holdout_count} |
| {route} | {dev + holdout} | {dev} | {holdout} |

**Routes:** {routes}
**Dimensions:** {dimensions}

## Optimization Process

**Rounds:** {total_rounds} | **Converged:** {convergence_reason} | **Stagnation:** {stagnation_count}

<!-- Include only if oracle values are not null -->
**Oracle note:** Theoretical optimum would achieve {oracle_cost_reduction}% cost reduction with {oracle_quality_reduction}% quality change. Negative cost = cheaper (good). Positive quality = better (good).

<!-- Include only if chart paths are not null -->
![Quality Progression](charts/quality_progression.png)
![Cost Progression](charts/cost_progression.png)

## Pareto Front

<!-- Include only if chart path is not null -->
![Pareto Front](charts/pareto_front.png)

| Version | Quality | Cost | Round |
|---------|---------|------|-------|
| {version} | {quality} | {cost} | {round} |

## Usage Guide

- **Deployment:** {how to use the prompt in production}
- **Expected performance:** accuracy ~{X}%, cost ~${Y}/request
- **When to re-run:** {triggers for re-optimization}
- **Limitations:** {known weaknesses, edge cases}
```

## Test Changes

### File: `tests/test_final_report_preprocessor.py`

- Fix `split_report.json` fixtures to use nested `route_distribution` format (see Bug Fix section for corrected fixture)
- Add test for `_build_error_analysis()`:
  - Happy path: 3 routes, some misrouted, verify confusion matrix entries and counts
  - Edge case: route with zero errors (diagonal only)
  - Edge case: empty results → zero totals
- Add test for `_build_baseline_comparison()`:
  - Happy path: loads valid `baseline_comparison.json`
  - Missing file → returns `None`
- Remove tests for `MisroutedExample` sampling
- Remove tests for mutation analysis fields on `OptimizationJourney`
- Update `DatasetOverview` assertions: `route_distribution` values are now dicts, not ints
- Update `OptimizationJourney` assertions: no mutation fields, oracle fields added
- Update `FinalReportBriefing` assertions: `error_analysis` instead of `error_summary`, no `oracle_analysis`

### Pre-existing gap: `support/` metric not emitted

`compute_f1` in `metrics.py` does not emit `support/<class>` keys, so `PerClassPerformance.support` is always `None`. To populate this in the report, add support count computation to `_extract_per_class_performance` using the confusion matrix data (sum of row for each expected class). This is a pre-existing issue but should be fixed as part of this work since we're already computing the confusion matrix.

### Integration test considerations

- Baseline computation in `run_holdout_eval`: add scenario in `tests/scenarios/` verifying `baseline_comparison.json` is written
- Confusion matrix edge: route not in predictions (e.g., hallucinated route)

## Documentation Updates

Per project rules, update in same commit as interface changes:
- `docs/architecture.md` — update Stage 5 section if it references report structure or models
- `odysseus/agents/final_report/` README if one exists — update model descriptions

## Files Changed

| File | Change |
|------|--------|
| `odysseus/agents/final_report/models.py` | Fix DatasetOverview, add ConfusionEntry/ErrorAnalysis/BaselineResult/BaselineComparison, strip OptimizationJourney mutation fields, add oracle fields to OptimizationJourney, remove OracleAnalysis/MisroutedExample/ErrorSummary |
| `odysseus/agents/final_report/preprocessor.py` | Update imports, fix build_final_report_briefing orchestration (drop mutation_log, rename error_summary→error_analysis, add baseline_comparison), replace _build_error_summary with _build_error_analysis, add _build_baseline_comparison, remove _extract_oracle_analysis, update _build_optimization_journey (drop mutation param, add holdout_report param for oracle) |
| `odysseus/mcp/final_report_tools.py` | Add _compute_baselines function, call after eval in run_holdout_eval, write baseline_comparison.json |
| `odysseus/agents/prompts/final_report_system.md` | Update section order, reference template, add confusion matrix/baseline/cross-link instructions, remove mutation/example instructions |
| `odysseus/agents/prompts/final_report_template.md` | New: concrete report skeleton with conditional sections |
| `tests/test_final_report_preprocessor.py` | Fix fixtures, add confusion matrix + baseline tests, remove obsolete tests, update assertions |
| `docs/architecture.md` | Update Stage 5 model/section references |
