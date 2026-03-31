# Stage 5: Final Report Redesign — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign Stage 5 final report with inverted-pyramid structure, fix the route_distribution bug, add confusion matrix and baseline comparison, strip optimizer internals, and provide a concrete report template.

**Architecture:** Each task changes models AND their consumers atomically so every commit leaves the test suite green. Models + preprocessor are updated together, then baseline computation is added to the holdout eval tool, then agent prompts/template are rewritten.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, uv

**Spec:** `docs/superpowers/specs/2026-03-31-stage5-final-report-redesign.md`

---

## Chunk 1: Bug Fix and Error Analysis Refactor

### Task 1: Fix `DatasetOverview.route_distribution` type and test fixture

**Files:**
- Modify: `odysseus/agents/final_report/models.py:14`
- Modify: `tests/test_final_report_preprocessor.py:35-39`

- [ ] **Step 1: Fix the model type annotation**

In `odysseus/agents/final_report/models.py`, change line 14:

```python
# Before:
route_distribution: dict[str, int]

# After:
route_distribution: dict[str, dict[str, int]]
```

- [ ] **Step 2: Fix the test fixture**

In `tests/test_final_report_preprocessor.py`, replace the split_report fixture (lines 35-39):

```python
# Before:
(run_dir / "analysis" / "split_report.json").write_text(
    json.dumps(
        {"dev_count": 80, "holdout_count": 20, "route_distribution": {"haiku": 60, "sonnet": 30, "opus": 10}}
    )
)

# After:
(run_dir / "analysis" / "split_report.json").write_text(
    json.dumps(
        {
            "dev_count": 80,
            "holdout_count": 20,
            "route_distribution": {
                "haiku": {"dev": 48, "holdout": 12},
                "sonnet": {"dev": 24, "holdout": 6},
                "opus": {"dev": 8, "holdout": 2},
            },
        }
    )
)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_final_report_preprocessor.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add odysseus/agents/final_report/models.py tests/test_final_report_preprocessor.py
git commit -m "fix: DatasetOverview.route_distribution type to match nested pipeline output"
```

---

### Task 2: Replace ErrorSummary with ErrorAnalysis + confusion matrix (model + preprocessor atomic)

This task changes the model AND the preprocessor together so every commit is green.

**Files:**
- Modify: `odysseus/agents/final_report/models.py:72-87` (replace ErrorSummary/MisroutedExample)
- Modify: `odysseus/agents/final_report/models.py:98-113` (FinalReportBriefing field rename)
- Modify: `odysseus/agents/final_report/preprocessor.py:15-26` (imports)
- Modify: `odysseus/agents/final_report/preprocessor.py:389-456` (replace _build_error_summary)
- Modify: `odysseus/agents/final_report/preprocessor.py:60,77` (orchestration)
- Modify: `tests/test_final_report_preprocessor.py`

- [ ] **Step 1: Write test for confusion matrix error analysis**

In `tests/test_final_report_preprocessor.py`, add:

```python
class TestErrorAnalysis:
    def test_confusion_matrix_computed(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        ea = briefing.error_analysis
        assert ea.total_evaluated == 20
        assert ea.total_errors == 3
        matrix_dict = {(e.expected, e.predicted): e.count for e in ea.confusion_matrix}
        assert matrix_dict[("sonnet", "sonnet")] == 17
        assert matrix_dict[("sonnet", "haiku")] == 3

    def test_empty_results(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        (run_dir / "holdout_eval" / "results.jsonl").unlink()
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.error_analysis.total_evaluated == 0
        assert briefing.error_analysis.confusion_matrix == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_final_report_preprocessor.py::TestErrorAnalysis -v`
Expected: FAIL

- [ ] **Step 3: Update models — replace ErrorSummary/MisroutedExample with ErrorAnalysis/ConfusionEntry**

In `odysseus/agents/final_report/models.py`, replace `MisroutedExample` and `ErrorSummary` classes (lines 72-87) with:

```python
class ConfusionEntry(BaseModel):
    """Single cell in the confusion matrix."""

    expected: str
    predicted: str
    count: int


class ErrorAnalysis(BaseModel):
    """Holdout error analysis with confusion matrix."""

    total_evaluated: int
    total_errors: int
    error_rate: float
    confusion_matrix: list[ConfusionEntry]
```

In `FinalReportBriefing`, rename: `error_summary: ErrorSummary` → `error_analysis: ErrorAnalysis`

- [ ] **Step 4: Update preprocessor imports**

In `odysseus/agents/final_report/preprocessor.py`, update the import block (lines 15-26). Replace `ErrorSummary`, `MisroutedExample` with `ErrorAnalysis`, `ConfusionEntry`. Remove the `OracleAnalysis` import (will be needed for Task 3 anyway, keep for now if needed).

- [ ] **Step 5: Replace `_build_error_summary` with `_build_error_analysis` in preprocessor**

Replace the `_build_error_summary` function (lines 389-456) with:

```python
def _build_error_analysis(run_dir: Path) -> ErrorAnalysis:
    """Build confusion matrix from holdout eval results."""
    from collections import Counter

    examples_by_id: dict[str, dict] = {}
    holdout_path = run_dir / "analysis" / "holdout.jsonl"
    try:
        for line in holdout_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            ex = json.loads(stripped)
            examples_by_id[ex.get("id", "")] = ex
    except Exception:
        pass

    eval_results: list[dict] = []
    results_path = run_dir / "holdout_eval" / "results.jsonl"
    try:
        for line in results_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            if row.get("meta") == "__meta__":
                continue
            eval_results.append(row)
    except Exception:
        return ErrorAnalysis(total_evaluated=0, total_errors=0, error_rate=0.0, confusion_matrix=[])

    if not eval_results:
        return ErrorAnalysis(total_evaluated=0, total_errors=0, error_rate=0.0, confusion_matrix=[])

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

- [ ] **Step 6: Update `build_final_report_briefing` orchestration**

- Line 60: `error_summary = _build_error_summary(run_dir)` → `error_analysis = _build_error_analysis(run_dir)`
- Line 77 in constructor: `error_summary=error_summary` → `error_analysis=error_analysis`

- [ ] **Step 7: Update existing tests that reference error_summary**

- Delete `test_error_summary` method (lines 282-287)
- In `TestGracefulDegradation::test_missing_holdout_results`: change `briefing.error_summary` → `briefing.error_analysis`

- [ ] **Step 8: Run tests**

Run: `uv run pytest tests/test_final_report_preprocessor.py -v`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add odysseus/agents/final_report/models.py odysseus/agents/final_report/preprocessor.py tests/test_final_report_preprocessor.py
git commit -m "feat: replace ErrorSummary with ErrorAnalysis and confusion matrix"
```

---

### Task 3: Strip mutation fields from OptimizationJourney, fold oracle, remove OracleAnalysis (model + preprocessor atomic)

**Files:**
- Modify: `odysseus/agents/final_report/models.py:28-41` (OptimizationJourney)
- Modify: `odysseus/agents/final_report/models.py:62-69` (remove OracleAnalysis)
- Modify: `odysseus/agents/final_report/models.py` (FinalReportBriefing — remove oracle_analysis)
- Modify: `odysseus/agents/final_report/preprocessor.py:150-226` (_build_optimization_journey)
- Modify: `odysseus/agents/final_report/preprocessor.py:364-381` (remove _extract_oracle_analysis)
- Modify: `odysseus/agents/final_report/preprocessor.py:36-79` (orchestration)
- Modify: `tests/test_final_report_preprocessor.py`

- [ ] **Step 1: Write tests for updated journey**

In `tests/test_final_report_preprocessor.py`, add:

```python
class TestOptimizationJourneyUpdated:
    def test_no_mutation_fields(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        journey = briefing.optimization_journey
        assert journey.total_rounds == 3
        assert "Stagnation" in journey.convergence_reason
        assert "mutation_type_counts" not in journey.model_fields

    def test_oracle_in_journey(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.optimization_journey.oracle_cost_reduction == -0.4
        assert briefing.optimization_journey.oracle_quality_reduction == 0.0

    def test_no_standalone_oracle(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert "oracle_analysis" not in briefing.model_fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_final_report_preprocessor.py::TestOptimizationJourneyUpdated -v`
Expected: FAIL

- [ ] **Step 3: Update OptimizationJourney model**

Replace `OptimizationJourney` class in `models.py`:

```python
class OptimizationJourney(BaseModel):
    """Search loop progression and convergence info."""

    total_rounds: int
    convergence_reason: str
    stagnation_count: int
    best_quality_per_round: list[float]
    best_cost_per_round: list[float]
    pareto_front_size_per_round: list[int]
    oracle_cost_reduction: float | None = None
    oracle_quality_reduction: float | None = None
```

- [ ] **Step 4: Remove OracleAnalysis model and oracle_analysis field from FinalReportBriefing**

Delete the `OracleAnalysis` class. Remove `oracle_analysis: OracleAnalysis | None = None` from `FinalReportBriefing`. Remove the `OracleAnalysis` import from preprocessor.

- [ ] **Step 5: Update `_build_optimization_journey` in preprocessor**

Replace the function — remove `mutation_log` parameter, remove all mutation analysis code, add `holdout_report` parameter, extract oracle fields:

```python
def _build_optimization_journey(
    search_state: dict | list | None,
    holdout_report: dict | list | None,
) -> OptimizationJourney:
    """Extract optimization journey from search state."""
    if not search_state or not isinstance(search_state, dict):
        return OptimizationJourney(
            total_rounds=0,
            convergence_reason="unknown",
            stagnation_count=0,
            best_quality_per_round=[],
            best_cost_per_round=[],
            pareto_front_size_per_round=[],
        )

    round_history: list[dict] = search_state.get("round_history", [])
    total_rounds = search_state.get("round", 0)

    stagnation_count = search_state.get("stagnation_count", 0)
    convergence_limit = search_state.get("convergence_limit", 5)
    max_rounds = search_state.get("max_rounds", 50)
    if stagnation_count >= convergence_limit:
        convergence_reason = f"Stagnation limit reached ({stagnation_count} rounds without Pareto improvement)"
    elif total_rounds >= max_rounds:
        convergence_reason = f"Maximum rounds reached ({max_rounds})"
    else:
        convergence_reason = "Loop exited by Review Agent"

    best_quality: list[float] = []
    best_cost: list[float] = []
    front_sizes: list[int] = []
    for rh in round_history:
        front_sizes.append(rh.get("front_size", 0))

    pareto_front: list[dict] = search_state.get("pareto_front", [])
    _build_quality_cost_trajectory(pareto_front, total_rounds, best_quality, best_cost)

    oracle_cost: float | None = None
    oracle_quality: float | None = None
    if isinstance(holdout_report, dict):
        metrics = holdout_report.get("metrics", {})
        oracle_cost = metrics.get("oracle_cost_reduction")
        oracle_quality = metrics.get("oracle_quality_reduction")

    return OptimizationJourney(
        total_rounds=total_rounds,
        convergence_reason=convergence_reason,
        stagnation_count=stagnation_count,
        best_quality_per_round=best_quality,
        best_cost_per_round=best_cost,
        pareto_front_size_per_round=front_sizes,
        oracle_cost_reduction=oracle_cost,
        oracle_quality_reduction=oracle_quality,
    )
```

- [ ] **Step 6: Update `build_final_report_briefing` orchestration**

- Remove: `mutation_log = _load_json(run_dir / "search" / "mutation_log.json", default=[])` (line 50)
- Change: `_build_optimization_journey(search_state, mutation_log)` → `_build_optimization_journey(search_state, holdout_report)` (line 54)
- Remove: `oracle_analysis = _extract_oracle_analysis(holdout_report)` (line 59)
- Remove: `oracle_analysis=oracle_analysis` from constructor (line 76)

- [ ] **Step 7: Delete `_extract_oracle_analysis` function**

Remove entire function (lines 364-381).

- [ ] **Step 8: Delete obsolete tests**

- Delete `test_oracle_analysis` (lines 276-280)
- Delete `test_mutation_analysis` (lines 299-309)
- Delete `TestGracefulDegradation::test_missing_mutation_log` (lines 313-318)

- [ ] **Step 9: Run tests**

Run: `uv run pytest tests/test_final_report_preprocessor.py -v`
Expected: ALL PASS

- [ ] **Step 10: Commit**

```bash
git add odysseus/agents/final_report/models.py odysseus/agents/final_report/preprocessor.py tests/test_final_report_preprocessor.py
git commit -m "feat: strip mutation analysis, fold oracle into OptimizationJourney, remove OracleAnalysis"
```

---

## Chunk 2: Baseline Comparison

### Task 4: Add BaselineResult/BaselineComparison models and preprocessor loader

**Files:**
- Modify: `odysseus/agents/final_report/models.py`
- Modify: `odysseus/agents/final_report/preprocessor.py`
- Modify: `tests/test_final_report_preprocessor.py`

- [ ] **Step 1: Write tests**

```python
class TestBaselineComparison:
    def test_loads_baseline_comparison(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        (run_dir / "holdout_eval" / "baseline_comparison.json").write_text(
            json.dumps(
                {
                    "baselines": [
                        {"strategy": "always_cheapest", "route": "haiku", "quality_score": 0.65, "cost": 0.1},
                        {"strategy": "always_capable", "route": "opus", "quality_score": 0.95, "cost": 0.9},
                    ],
                    "optimized": {"strategy": "optimized_prompt", "route": "mixed", "quality_score": 0.88, "cost": 0.35},
                }
            )
        )
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.baseline_comparison is not None
        assert len(briefing.baseline_comparison.baselines) == 2
        assert briefing.baseline_comparison.optimized.cost == 0.35

    def test_missing_baseline_returns_none(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.baseline_comparison is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_final_report_preprocessor.py::TestBaselineComparison -v`
Expected: FAIL

- [ ] **Step 3: Add models**

In `odysseus/agents/final_report/models.py`, add after `ErrorAnalysis`:

```python
class BaselineResult(BaseModel):
    """Performance of a single baseline strategy."""

    strategy: str
    route: str
    quality_score: float
    cost: float


class BaselineComparison(BaseModel):
    """Comparison of optimized prompt against naive baselines."""

    baselines: list[BaselineResult]
    optimized: BaselineResult
```

Add to `FinalReportBriefing`: `baseline_comparison: BaselineComparison | None = None`

- [ ] **Step 4: Add `_build_baseline_comparison` to preprocessor and wire in**

Add to preprocessor:

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

In `build_final_report_briefing()`, add:
- `baseline_comparison = _build_baseline_comparison(run_dir)` after the error_analysis line
- `baseline_comparison=baseline_comparison` in the FinalReportBriefing constructor

Update imports to include `BaselineComparison`.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_final_report_preprocessor.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add odysseus/agents/final_report/models.py odysseus/agents/final_report/preprocessor.py tests/test_final_report_preprocessor.py
git commit -m "feat: add BaselineComparison model and preprocessor loader"
```

---

### Task 5: Add `_compute_baselines` to `final_report_tools.py`

**Files:**
- Modify: `odysseus/mcp/final_report_tools.py`
- Create: `tests/test_compute_baselines.py`

Note: `_compute_baselines` is a private function in a module that registers MCP tools on import. The test imports it directly. If MCP registration causes test issues, extract the function to a utility module.

- [ ] **Step 1: Write tests**

Create `tests/test_compute_baselines.py`:

```python
"""Tests for baseline computation in holdout eval."""

from odysseus.mcp.final_report_tools import _compute_baselines

ROUTES = {
    "haiku": {"cost": 0.1, "quality_score": 0.6},
    "sonnet": {"cost": 0.5, "quality_score": 0.8},
    "opus": {"cost": 1.0, "quality_score": 0.95},
}


def _make_example(eid: str, expected_route: str, routes: dict) -> dict:
    return {"id": eid, "input": f"request {eid}", "expected": {"route": expected_route, "routes": routes}}


def _make_result(eid: str, predicted_route: str) -> dict:
    return {"example_id": eid, "output": {"route": predicted_route}, "error": None}


class TestComputeBaselines:
    def test_identifies_cheapest_and_capable(self) -> None:
        examples = [_make_example(f"e{i}", "sonnet", ROUTES) for i in range(10)]
        results = [_make_result(f"e{i}", "sonnet") for i in range(10)]
        baselines = _compute_baselines(examples, results)
        assert baselines is not None
        strategies = {b["strategy"]: b for b in baselines["baselines"]}
        assert strategies["always_cheapest"]["route"] == "haiku"
        assert strategies["always_capable"]["route"] == "opus"

    def test_optimized_uses_actual_results(self) -> None:
        examples = [
            _make_example("e0", "haiku", ROUTES),
            _make_example("e1", "opus", ROUTES),
        ]
        results = [
            _make_result("e0", "haiku"),
            _make_result("e1", "sonnet"),
        ]
        baselines = _compute_baselines(examples, results)
        assert baselines is not None
        opt = baselines["optimized"]
        assert opt["cost"] == round((0.1 + 0.5) / 2, 4)
        assert opt["quality_score"] == round((0.6 + 0.8) / 2, 4)

    def test_empty_examples_returns_none(self) -> None:
        assert _compute_baselines([], []) is None

    def test_skips_errored_results(self) -> None:
        examples = [_make_example("e0", "sonnet", ROUTES)]
        results = [{"example_id": "e0", "output": None, "error": "timeout"}]
        baselines = _compute_baselines(examples, results)
        assert baselines is not None
        assert baselines["optimized"]["cost"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_compute_baselines.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement `_compute_baselines`**

Add to `odysseus/mcp/final_report_tools.py`, before the tool decorators:

```python
def _compute_baselines(
    holdout_examples: list[dict],
    eval_results: list[dict],
) -> dict | None:
    """Compute baseline strategy performance on holdout set.

    Invariant: every example has every route in its expected.routes dict.
    This is guaranteed by the data validation stage (stratified_split).
    """
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

    cheapest_route = min(route_cost_sums, key=lambda r: route_cost_sums[r] / n)
    cheapest_quality = route_quality_sums[cheapest_route] / n
    cheapest_cost = route_cost_sums[cheapest_route] / n

    capable_route = min(route_quality_sums, key=lambda r: (-route_quality_sums[r] / n, r))
    capable_quality = route_quality_sums[capable_route] / n
    capable_cost = route_cost_sums[capable_route] / n

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

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_compute_baselines.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/mcp/final_report_tools.py tests/test_compute_baselines.py
git commit -m "feat: add _compute_baselines function for holdout eval"
```

---

### Task 6: Wire `_compute_baselines` into `run_holdout_eval`

**Files:**
- Modify: `odysseus/mcp/final_report_tools.py:208-219`

- [ ] **Step 1: Add baseline computation after eval completes**

In `run_holdout_eval()`, insert between `score_report = ...` (line 208) and `return json.dumps(...)` (line 209):

```python
    # Compute and write baseline comparison
    try:
        holdout_jsonl_path = project_dir / "outputs" / run_id / "analysis" / "holdout.jsonl"
        holdout_text = holdout_jsonl_path.read_text(encoding="utf-8")
        holdout_examples = [json.loads(line) for line in holdout_text.splitlines() if line.strip()]

        results_path = project_dir / "outputs" / run_id / "holdout_eval" / "results.jsonl"
        results_text = results_path.read_text(encoding="utf-8")
        eval_result_rows = [
            json.loads(line)
            for line in results_text.splitlines()
            if line.strip() and '"__meta__"' not in line
        ]

        baseline_data = _compute_baselines(holdout_examples, eval_result_rows)
        if baseline_data:
            baseline_path = project_dir / "outputs" / run_id / "holdout_eval" / "baseline_comparison.json"
            baseline_path.write_text(json.dumps(baseline_data, indent=2), encoding="utf-8")
    except Exception:
        import logging
        logging.getLogger(__name__).debug("Failed to compute baselines", exc_info=True)
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/ -v --timeout=30 -x`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add odysseus/mcp/final_report_tools.py
git commit -m "feat: wire baseline computation into run_holdout_eval"
```

---

## Chunk 3: Support Field Fix and Agent Prompts

### Task 7: Populate `PerClassPerformance.support` from confusion matrix

**Files:**
- Modify: `odysseus/agents/final_report/preprocessor.py` (_extract_per_class_performance)
- Modify: `tests/test_final_report_preprocessor.py`

The spec notes that `compute_f1` in `metrics.py` does not emit `support/<class>` keys, so support is always `None`. Fix this by deriving support from the confusion matrix (sum of each expected-route row).

- [ ] **Step 1: Write test**

Add to `tests/test_final_report_preprocessor.py`:

```python
class TestSupportFromConfusionMatrix:
    def test_support_populated(self, tmp_path: Path) -> None:
        """Support field is derived from confusion matrix when metrics lack support/."""
        run_dir = _setup_minimal_run(tmp_path)
        # Remove support/ keys from holdout report to simulate real compute_f1 output
        import json as _json
        report_path = run_dir / "holdout_eval" / "report.json"
        report = _json.loads(report_path.read_text())
        metrics = report["metrics"]
        for key in list(metrics):
            if key.startswith("support/"):
                del metrics[key]
        report_path.write_text(_json.dumps(report))

        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        # All holdout examples are "sonnet", with 3 misrouted to "haiku"
        # So sonnet support = 20 (all examples have expected route "sonnet")
        sonnet = next(p for p in briefing.per_class_performance if p.route == "sonnet")
        assert sonnet.support == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_final_report_preprocessor.py::TestSupportFromConfusionMatrix -v`
Expected: FAIL (support is None)

- [ ] **Step 3: Update `_extract_per_class_performance` to derive support**

In `odysseus/agents/final_report/preprocessor.py`, update `_extract_per_class_performance` (around line 335) to accept the `ErrorAnalysis` and compute support from it:

Change the function signature to also accept the error analysis, and add support computation:

```python
def _extract_per_class_performance(
    holdout_report: dict | list | None,
    error_analysis: ErrorAnalysis,
) -> list[PerClassPerformance]:
    """Extract per-route precision, recall, F1, support from holdout metrics."""
    if not isinstance(holdout_report, dict):
        return []

    metrics = holdout_report.get("metrics", {})
    route_names: set[str] = set()
    for key in metrics:
        for prefix in ("recall/", "precision/", "f1/"):
            if key.startswith(prefix) and not key.endswith("/macro"):
                route_names.add(key[len(prefix):])

    # Derive support from confusion matrix (sum of each expected-route row)
    support_by_route: dict[str, int] = {}
    for entry in error_analysis.confusion_matrix:
        support_by_route[entry.expected] = support_by_route.get(entry.expected, 0) + entry.count

    results: list[PerClassPerformance] = []
    for route in sorted(route_names):
        support = int(metrics[f"support/{route}"]) if f"support/{route}" in metrics else support_by_route.get(route)
        results.append(
            PerClassPerformance(
                route=route,
                precision=metrics.get(f"precision/{route}"),
                recall=metrics.get(f"recall/{route}"),
                f1=metrics.get(f"f1/{route}"),
                support=support,
            )
        )
    return results
```

- [ ] **Step 4: Update call site in `build_final_report_briefing`**

Change: `per_class = _extract_per_class_performance(holdout_report)` → `per_class = _extract_per_class_performance(holdout_report, error_analysis)`

Make sure `error_analysis` is computed before this call (it already should be from Task 2).

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_final_report_preprocessor.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add odysseus/agents/final_report/preprocessor.py tests/test_final_report_preprocessor.py
git commit -m "feat: populate PerClassPerformance.support from confusion matrix"
```

---

### Task 8: Create report template

**Files:**
- Create: `odysseus/agents/prompts/final_report_template.md`

- [ ] **Step 1: Write the template**

Create `odysseus/agents/prompts/final_report_template.md` with the full template from the spec (see spec lines 417-519 for the complete content). The template includes:
- Inverted pyramid section order
- Cross-link from Recommended Prompt to Usage Guide
- Conditional section markers (HTML comments)
- Confusion matrix table format
- Baseline comparison table
- Dataset overview with per-split breakdown

- [ ] **Step 2: Commit**

```bash
git add odysseus/agents/prompts/final_report_template.md
git commit -m "feat: add concrete final report template"
```

---

### Task 9: Update agent system prompt

**Files:**
- Modify: `odysseus/agents/prompts/final_report_system.md`

- [ ] **Step 1: Rewrite report template section**

Key changes to `odysseus/agents/prompts/final_report_system.md`:

1. **Replace inline template** (lines 36-92) with reference: "Follow the report structure defined in `final_report_template.md`. Use it as the skeleton — fill in data from the briefing JSON. Omit sections where data is null."
2. **Remove** line 54 ("What mutation strategies were effective vs ineffective") and line 55 ("Final mutation mode and stagnation count")
3. **Remove** lines 76-77 (misrouted example instructions)
4. **Add** confusion matrix instruction: "Render `error_analysis.confusion_matrix` as a proper matrix table with expected routes as rows and predicted routes as columns."
5. **Add** baseline instruction: "If `baseline_comparison` is present, render the comparison table showing always-cheapest, always-capable, and optimized strategies."
6. **Add** cross-link instruction: "The Recommended Prompt section must include: `> See [Usage Guide](#usage-guide) for deployment instructions and limitations.`"
7. **Update** sign convention note (lines 96-103) to mention oracle values appearing in the optimization section

- [ ] **Step 2: Verify prompt is valid**

Run: `uv run python -c "from pathlib import Path; t = Path('odysseus/agents/prompts/final_report_system.md').read_text(); assert 'final_report_template.md' in t; assert 'mutation strategies' not in t; assert 'misrouted' not in t.lower(); print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/prompts/final_report_system.md
git commit -m "feat: update final report system prompt for inverted pyramid and template reference"
```

---

## Chunk 4: Documentation and Verification

### Task 10: Update `docs/architecture.md`

**Files:**
- Modify: `docs/architecture.md`

- [ ] **Step 1: Update Stage 5 references**

Update:
- Agent Registry table row for Final Report: add `odysseus/agents/prompts/final_report_template.md` to modules
- Add `baseline_comparison.json` to the writes for the stage
- Model references: `ErrorAnalysis` replaces `ErrorSummary`, `BaselineComparison` is new, `OracleAnalysis` removed
- Tool table: note `run_holdout_eval` now also computes and writes baselines

- [ ] **Step 2: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: update architecture.md for Stage 5 redesign"
```

---

### Task 11: Full verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: Run linter**

Run: `uv run ruff check .`
Expected: No errors (fix any found)

- [ ] **Step 3: Run formatter**

Run: `uv run ruff format --check .`
Expected: No reformatting needed (run `uv run ruff format .` if needed)

- [ ] **Step 4: Run type checker**

Run: `uv run pyright`
Expected: No new errors related to changed files

- [ ] **Step 5: Fix any issues and commit**

```bash
git commit -m "fix: resolve lint/type issues from Stage 5 redesign"
```
