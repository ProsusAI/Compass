# THP-116: Score Report Format Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define the `ScoreReport` Pydantic model — the exact schema that `EvalRunnerAgent` outputs into the pipeline context dict for the Review agent to consume.

**Architecture:** A new `ScoreReport` model in `odysseus/eval/models.py` extracts and reshapes the key fields from `RunReport` into a pipeline-friendly format. It includes aggregate metrics, run summary, per-example error breakdown, and an optional run-over-run diff. A `from_run_report()` factory classmethod builds it from a `RunReport` and optional previous report. The diff computation is extracted from `JsonResultsCollector` into a shared helper so both the collector (disk logging) and `ScoreReport` (pipeline context) can use it.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest

---

## File Structure

| File | Responsibility |
|------|---------------|
| `odysseus/eval/models.py` | Add `ErrorBreakdown`, `RunDiff`, `ScoreReport` models |
| `odysseus/eval/diff.py` | Extract diff logic from collector; defines `MetricDiff`, `OverheadDiff` models and `compute_*` functions |
| `odysseus/eval/collector.py` | Refactor to use shared diff functions from `diff.py` |
| `tests/test_score_report.py` | Tests for `ScoreReport` construction and edge cases |
| `tests/test_diff.py` | Tests for extracted diff functions |
| `tests/test_collector.py` | Verify collector still works after refactor |

---

## Chunk 1: Extract diff logic into shared module

### Task 1: Create `odysseus/eval/diff.py` with diff computation functions

**Files:**
- Create: `odysseus/eval/diff.py`
- Test: `tests/test_diff.py`

The collector currently computes diffs and logs them directly. We need these computations reusable for `ScoreReport`. Extract pure functions that return structured data instead of logging.

- [ ] **Step 1: Write failing tests for `compute_metric_diffs`**

Create `tests/test_diff.py`:

```python
"""Tests for odysseus.eval.diff — shared diff computation."""

from odysseus.eval.diff import MetricDiff, compute_metric_diffs


class TestComputeMetricDiffs:
    def test_changed_metric(self) -> None:
        old = {"accuracy": 0.82}
        new = {"accuracy": 0.85}
        result = compute_metric_diffs(old, new)
        assert result == [MetricDiff(key="accuracy", old=0.82, new=0.85, status="changed")]

    def test_added_metric(self) -> None:
        old: dict[str, float] = {}
        new = {"accuracy": 0.85}
        result = compute_metric_diffs(old, new)
        assert result == [MetricDiff(key="accuracy", old=None, new=0.85, status="added")]

    def test_removed_metric(self) -> None:
        old = {"accuracy": 0.82}
        new: dict[str, float] = {}
        result = compute_metric_diffs(old, new)
        assert result == [MetricDiff(key="accuracy", old=0.82, new=None, status="removed")]

    def test_unchanged_metric_excluded(self) -> None:
        old = {"accuracy": 0.85}
        new = {"accuracy": 0.85}
        result = compute_metric_diffs(old, new)
        assert result == []

    def test_multiple_metrics_sorted_by_key(self) -> None:
        old = {"f1/macro": 0.7, "accuracy": 0.8}
        new = {"f1/macro": 0.75, "accuracy": 0.85}
        result = compute_metric_diffs(old, new)
        assert result[0].key == "accuracy"
        assert result[1].key == "f1/macro"

    def test_both_empty(self) -> None:
        assert compute_metric_diffs({}, {}) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_diff.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'odysseus.eval.diff'`

- [ ] **Step 3: Write failing tests for `compute_overhead_diff`**

Append to `tests/test_diff.py`:

```python
from odysseus.eval.diff import OverheadDiff, compute_overhead_diff


class TestComputeOverheadDiff:
    def test_cost_and_duration_changed(self) -> None:
        result = compute_overhead_diff(
            old_cost=0.05, old_duration=12.0,
            new_cost=0.04, new_duration=10.0,
        )
        assert result == OverheadDiff(
            old_cost=0.05, new_cost=0.04,
            old_duration=12.0, new_duration=10.0,
        )

    def test_no_change_returns_none(self) -> None:
        result = compute_overhead_diff(
            old_cost=0.05, old_duration=12.0,
            new_cost=0.05, new_duration=12.0,
        )
        assert result is None

    def test_only_cost_changed(self) -> None:
        result = compute_overhead_diff(
            old_cost=0.05, old_duration=12.0,
            new_cost=0.04, new_duration=12.0,
        )
        assert result is not None
        assert result.old_cost == 0.05
        assert result.new_cost == 0.04
```

- [ ] **Step 4: Write minimal implementation of `diff.py`**

Create `odysseus/eval/diff.py`:

```python
"""Shared diff computation for run-over-run comparison."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class MetricDiff(BaseModel):
    """A single metric change between two runs."""

    key: str
    old: float | None
    new: float | None
    status: Literal["changed", "added", "removed"]


class OverheadDiff(BaseModel):
    """Cost and duration change between two runs."""

    old_cost: float
    new_cost: float
    old_duration: float
    new_duration: float


def compute_metric_diffs(
    old: dict[str, float], new: dict[str, float]
) -> list[MetricDiff]:
    """Compare two metric dicts. Returns only changed/added/removed entries, sorted by key."""
    all_keys = sorted(set(old) | set(new))
    diffs: list[MetricDiff] = []
    for key in all_keys:
        if key in old and key in new:
            if old[key] != new[key]:
                diffs.append(MetricDiff(key=key, old=old[key], new=new[key], status="changed"))
        elif key in new:
            diffs.append(MetricDiff(key=key, old=None, new=new[key], status="added"))
        else:
            diffs.append(MetricDiff(key=key, old=old[key], new=None, status="removed"))
    return diffs


def compute_overhead_diff(
    *,
    old_cost: float,
    old_duration: float,
    new_cost: float,
    new_duration: float,
) -> OverheadDiff | None:
    """Compare cost and duration. Returns None if nothing changed."""
    if old_cost == new_cost and old_duration == new_duration:
        return None
    return OverheadDiff(
        old_cost=old_cost,
        new_cost=new_cost,
        old_duration=old_duration,
        new_duration=new_duration,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_diff.py -v`
Expected: All 9 tests PASS

- [ ] **Step 6: Commit**

```bash
git add odysseus/eval/diff.py tests/test_diff.py
git commit -m "feat(eval): add shared diff computation module"
```

### Task 2: Refactor `JsonResultsCollector` to use shared diff functions

**Files:**
- Modify: `odysseus/eval/collector.py` (full file rewrite — `_log_metric_diff` and `_log_overhead_diff` now delegate to `diff.py`)
- Test: `tests/test_collector.py` (existing — must still pass)

- [ ] **Step 1: Run existing collector tests to confirm green baseline**

Run: `uv run pytest tests/test_collector.py -v`
Expected: All existing tests PASS (there are tests for write_results, write_report, metric diff logging, and overhead diff logging)

- [ ] **Step 2: Rewrite collector to delegate to `diff.py`**

Replace the entire contents of `odysseus/eval/collector.py` with the following (this is a full file replacement, not a partial edit):

```python
"""Concrete ResultsCollector implementation — writes JSONL results and JSON reports."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from odysseus.eval.diff import compute_metric_diffs, compute_overhead_diff
from odysseus.eval.models import EvalResult, RunReport

logger = logging.getLogger(__name__)


class JsonResultsCollector:
    """Persists evaluation results as JSONL and reports as pretty-printed JSON."""

    def write_results(self, results: list[EvalResult], path: str) -> None:
        """Write each EvalResult as a JSON line to *path*."""
        with open(path, "w") as f:
            for result in results:
                f.write(result.model_dump_json() + "\n")

    def write_report(self, report: RunReport, path: str) -> None:
        """Write the full RunReport as pretty-printed JSON to *path*.

        If a previous report exists at *path*, log a human-readable diff
        of changed metrics and router overhead at INFO level.
        """
        previous = self._read_previous_report(path)

        with open(path, "w") as f:
            f.write(report.model_dump_json(indent=2) + "\n")

        if previous is not None:
            old_metrics = previous.get("metrics")
            if old_metrics is not None:
                self._log_metric_diff(old_metrics, report.metrics)

            old_summary = previous.get("summary")
            if old_summary is not None:
                self._log_overhead_diff(
                    old_summary, report.summary.total_cost, report.summary.duration_seconds
                )

    @staticmethod
    def _read_previous_report(path: str) -> dict[str, Any] | None:
        """Read the full previous report dict, or return None."""
        p = Path(path)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _log_metric_diff(old: dict[str, float], new: dict[str, float]) -> None:
        """Log changed, added, and removed metrics."""
        diffs = compute_metric_diffs(old, new)
        if not diffs:
            return
        lines: list[str] = []
        for d in diffs:
            if d.status == "changed":
                lines.append(f"  {d.key}: {d.old} → {d.new}")
            elif d.status == "added":
                lines.append(f"  {d.key}: (new) {d.new}")
            else:
                lines.append(f"  {d.key}: {d.old} (removed)")
        logger.info("Metric diff vs previous run:\n%s", "\n".join(lines))

    @staticmethod
    def _log_overhead_diff(
        old_summary: dict[str, Any],
        new_cost: float,
        new_duration: float,
    ) -> None:
        """Log router overhead changes (cost and latency).

        Preserves original behavior: logs cost diff even if old_duration is
        missing, and vice versa.
        """
        old_cost = old_summary.get("total_cost")
        old_duration = old_summary.get("duration_seconds")
        diffs: list[str] = []
        if old_cost is not None and old_cost != new_cost:
            diffs.append(f"  cost: ${old_cost:.4f} → ${new_cost:.4f}")
        if old_duration is not None and old_duration != new_duration:
            diffs.append(f"  latency: {old_duration}s → {new_duration}s")
        if diffs:
            logger.info("Router overhead diff vs previous run:\n%s", "\n".join(diffs))
```

- [ ] **Step 3: Run collector tests to verify refactor is safe**

Run: `uv run pytest tests/test_collector.py -v`
Expected: All existing tests PASS (identical behavior)

- [ ] **Step 4: Commit**

```bash
git add odysseus/eval/collector.py
git commit -m "refactor(eval): delegate collector diff to shared diff module"
```

---

## Chunk 2: Define `ScoreReport` model and pipeline context schema

### Task 3: Define `ErrorBreakdown` and `ScoreReport` models

**Files:**
- Modify: `odysseus/eval/models.py` (append after `RunReport`, line 218)
- Test: `tests/test_score_report.py`

The `ScoreReport` is the contract between `EvalRunnerAgent` and the Review agent. It carries:
- `metrics`: the aggregate metrics dict (e.g. `{"accuracy": 0.85, "f1/macro": 0.78}`)
- `summary`: the `RunSummary` (total, succeeded, failed, cost, duration)
- `errors`: list of `ErrorBreakdown` — one per failed example, so the Review agent knows what went wrong
- `diff`: optional `RunDiff` containing metric diffs and overhead diff vs previous run
- `report_path`: path to full report on disk for deeper inspection

The pipeline context key is `"eval_score_report"`.

- [ ] **Step 1: Write failing tests for `ErrorBreakdown`**

Create `tests/test_score_report.py`:

```python
"""Tests for ScoreReport and ErrorBreakdown models."""

from odysseus.eval.models import ErrorBreakdown


class TestErrorBreakdown:
    def test_construction(self) -> None:
        eb = ErrorBreakdown(example_id="ex-1", error="timeout", retries=3)
        assert eb.example_id == "ex-1"
        assert eb.error == "timeout"
        assert eb.retries == 3

    def test_serialization_roundtrip(self) -> None:
        eb = ErrorBreakdown(example_id="ex-1", error="timeout", retries=2)
        data = eb.model_dump()
        assert data == {"example_id": "ex-1", "error": "timeout", "retries": 2}
        assert ErrorBreakdown(**data) == eb
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_score_report.py::TestErrorBreakdown -v`
Expected: FAIL with `ImportError: cannot import name 'ErrorBreakdown'`

- [ ] **Step 3: Implement `ErrorBreakdown` in models.py**

Append to `odysseus/eval/models.py` (after `RunReport` at line 218):

```python


class ErrorBreakdown(BaseModel):
    """Summary of a single failed evaluation example."""

    example_id: str
    error: str
    retries: int
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_score_report.py::TestErrorBreakdown -v`
Expected: 2 tests PASS

- [ ] **Step 5: Write failing tests for `RunDiff`**

Append to `tests/test_score_report.py`:

```python
from odysseus.eval.diff import MetricDiff, OverheadDiff
from odysseus.eval.models import RunDiff


class TestRunDiff:
    def test_construction_with_all_fields(self) -> None:
        rd = RunDiff(
            metric_diffs=[MetricDiff(key="accuracy", old=0.8, new=0.85, status="changed")],
            overhead_diff=OverheadDiff(old_cost=0.05, new_cost=0.04, old_duration=12.0, new_duration=10.0),
        )
        assert len(rd.metric_diffs) == 1
        assert rd.overhead_diff is not None

    def test_construction_no_overhead(self) -> None:
        rd = RunDiff(
            metric_diffs=[MetricDiff(key="accuracy", old=0.8, new=0.85, status="changed")],
            overhead_diff=None,
        )
        assert rd.overhead_diff is None

    def test_empty_diffs(self) -> None:
        rd = RunDiff(metric_diffs=[], overhead_diff=None)
        assert rd.metric_diffs == []
```

- [ ] **Step 6: Implement `RunDiff` in models.py**

Append to `odysseus/eval/models.py` (after `ErrorBreakdown`):

First, add the import to the top of `odysseus/eval/models.py`. Insert after line 10 (`from pydantic import ...`):

```python
from odysseus.eval.diff import MetricDiff, OverheadDiff
```

Then append after `ErrorBreakdown`:

```python
class RunDiff(BaseModel):
    """Run-over-run comparison data."""

    metric_diffs: list[MetricDiff]
    overhead_diff: OverheadDiff | None
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_score_report.py -v`
Expected: 5 tests PASS

- [ ] **Step 8: Commit**

```bash
git add odysseus/eval/models.py tests/test_score_report.py
git commit -m "feat(eval): add ErrorBreakdown and RunDiff models"
```

### Task 4: Define `ScoreReport` model with `from_run_report` factory

**Files:**
- Modify: `odysseus/eval/models.py` (append after `RunDiff`)
- Test: `tests/test_score_report.py`

- [ ] **Step 1: Write failing tests for `ScoreReport` construction**

Append to `tests/test_score_report.py`:

```python
from datetime import datetime, timezone

from odysseus.eval.models import (
    EvalResult,
    RunConfig,
    RunReport,
    RunSummary,
    ScoreReport,
    TokenUsage,
    MetricConfig,
)


def _make_run_report(
    *,
    num_succeeded: int = 8,
    num_failed: int = 2,
    metrics: dict[str, float] | None = None,
) -> RunReport:
    """Helper to build a RunReport for testing."""
    results: list[EvalResult] = []
    for i in range(num_succeeded):
        results.append(
            EvalResult(
                example_id=f"ok-{i}",
                model="test-model",
                output={"route": "classA"},
                error=None,
                latency_ms=100.0,
                retries=0,
                token_usage=TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5),
                cost=0.001,
            )
        )
    for i in range(num_failed):
        results.append(
            EvalResult(
                example_id=f"fail-{i}",
                model="test-model",
                output=None,
                error="timeout" if i % 2 == 0 else "rate_limit",
                latency_ms=60000.0,
                retries=3,
                token_usage=None,
                cost=None,
            )
        )
    return RunReport(
        config=RunConfig(
            backend="test-backend",
            data_source="data/test.jsonl",
            data_split="dev",
            metrics=[MetricConfig(name="accuracy")],
        ),
        metrics=metrics or {"accuracy": 0.85},
        results=results,
        summary=RunSummary(
            total=num_succeeded + num_failed,
            succeeded=num_succeeded,
            failed=num_failed,
            total_cost=0.008,
            start_time=datetime(2026, 3, 19, 10, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 3, 19, 10, 1, 0, tzinfo=timezone.utc),
            duration_seconds=60.0,
        ),
    )


class TestScoreReport:
    def test_from_run_report_basic(self) -> None:
        report = _make_run_report()
        score = ScoreReport.from_run_report(report, report_path="outputs/report.json")

        assert score.metrics == {"accuracy": 0.85}
        assert score.summary.total == 10
        assert score.summary.succeeded == 8
        assert score.summary.failed == 2
        assert score.report_path == "outputs/report.json"
        assert score.diff is None

    def test_errors_extracted(self) -> None:
        report = _make_run_report(num_failed=3)
        score = ScoreReport.from_run_report(report, report_path="outputs/report.json")

        assert len(score.errors) == 3
        assert score.errors[0].example_id == "fail-0"
        assert score.errors[0].error == "timeout"
        assert score.errors[0].retries == 3
        assert score.errors[1].error == "rate_limit"

    def test_no_errors_when_all_succeed(self) -> None:
        report = _make_run_report(num_succeeded=5, num_failed=0)
        score = ScoreReport.from_run_report(report, report_path="outputs/report.json")
        assert score.errors == []

    def test_with_previous_report_generates_diff(self) -> None:
        current = _make_run_report(metrics={"accuracy": 0.85})
        previous = _make_run_report(metrics={"accuracy": 0.80})
        score = ScoreReport.from_run_report(
            current,
            report_path="outputs/report.json",
            previous_report=previous,
        )

        assert score.diff is not None
        assert len(score.diff.metric_diffs) == 1
        assert score.diff.metric_diffs[0].key == "accuracy"
        assert score.diff.metric_diffs[0].old == 0.80
        assert score.diff.metric_diffs[0].new == 0.85

    def test_context_key(self) -> None:
        """The pipeline context key must be 'eval_score_report'."""
        assert ScoreReport.CONTEXT_KEY == "eval_score_report"

    def test_context_key_excluded_from_serialization(self) -> None:
        report = _make_run_report()
        score = ScoreReport.from_run_report(report, report_path="outputs/report.json")
        assert "CONTEXT_KEY" not in score.model_dump()

    def test_serialization_roundtrip(self) -> None:
        report = _make_run_report()
        score = ScoreReport.from_run_report(report, report_path="outputs/report.json")
        data = score.model_dump()
        restored = ScoreReport(**data)
        assert restored == score
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_score_report.py::TestScoreReport -v`
Expected: FAIL with `ImportError: cannot import name 'ScoreReport'`

- [ ] **Step 3: Implement `ScoreReport` in models.py**

Append to `odysseus/eval/models.py` (after `RunDiff`):

Note: Add `ClassVar` to the existing typing import at line 7 of `models.py`: change `from typing import Any, Literal` to `from typing import Any, ClassVar, Literal`.

```python
class ScoreReport(BaseModel):
    """Score report passed from EvalRunnerAgent to Review agent via pipeline context.

    This is the contract between the two agents. The Review agent consumes
    this structure to decide whether the prompt iteration improved.
    """

    CONTEXT_KEY: ClassVar[str] = "eval_score_report"

    metrics: dict[str, float]
    summary: RunSummary
    errors: list[ErrorBreakdown]
    diff: RunDiff | None
    report_path: str

    @classmethod
    def from_run_report(
        cls,
        report: RunReport,
        *,
        report_path: str,
        previous_report: RunReport | None = None,
    ) -> ScoreReport:
        """Build a ScoreReport from a RunReport and optional previous run."""
        errors = [
            ErrorBreakdown(
                example_id=r.example_id,
                error=r.error,  # type: ignore[arg-type]
                retries=r.retries,
            )
            for r in report.results
            if r.error is not None
        ]

        diff: RunDiff | None = None
        if previous_report is not None:
            metric_diffs = compute_metric_diffs(previous_report.metrics, report.metrics)
            overhead_diff = compute_overhead_diff(
                old_cost=previous_report.summary.total_cost,
                old_duration=previous_report.summary.duration_seconds,
                new_cost=report.summary.total_cost,
                new_duration=report.summary.duration_seconds,
            )
            diff = RunDiff(metric_diffs=metric_diffs, overhead_diff=overhead_diff)

        return cls(
            metrics=report.metrics,
            summary=report.summary,
            errors=errors,
            diff=diff,
            report_path=report_path,
        )
```

Note: `ClassVar` is already imported in the standard library `typing` module. Add it to the existing `from typing import ...` line at the top of `odysseus/eval/models.py` (line 7). Also update the diff import (added in Task 3 Step 6) to include the factory functions:

Replace:
```python
from odysseus.eval.diff import MetricDiff, OverheadDiff
```

With:
```python
from odysseus.eval.diff import MetricDiff, OverheadDiff, compute_metric_diffs, compute_overhead_diff
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_score_report.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Run full test suite to verify nothing is broken**

Run: `uv run pytest --ignore=tests/test_backends.py --ignore=tests/test_prompt_manager.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add odysseus/eval/models.py tests/test_score_report.py
git commit -m "feat(eval): add ScoreReport model with from_run_report factory"
```

---

## Chunk 3: Export and document the pipeline context contract

### Task 5: Add `ScoreReport` to package exports

**Files:**
- Modify: `odysseus/eval/__init__.py`
- Test: `tests/test_score_report.py`

- [ ] **Step 1: Write failing import test**

Append to `tests/test_score_report.py`:

```python
class TestExports:
    def test_score_report_importable_from_eval(self) -> None:
        from odysseus.eval import ScoreReport as Exported

        assert Exported is ScoreReport

    def test_error_breakdown_importable_from_eval(self) -> None:
        from odysseus.eval import ErrorBreakdown as Exported

        assert Exported is ErrorBreakdown

    def test_run_diff_importable_from_eval(self) -> None:
        from odysseus.eval import RunDiff as Exported

        assert Exported is RunDiff
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_score_report.py::TestExports -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Read current `odysseus/eval/__init__.py`**

Read the file to see existing exports before modifying.

- [ ] **Step 4: Add exports to `odysseus/eval/__init__.py`**

Add to the existing exports in `odysseus/eval/__init__.py`:

```python
from odysseus.eval.models import ErrorBreakdown, RunDiff, ScoreReport
```

Also export the diff helpers for downstream use:

```python
from odysseus.eval.diff import MetricDiff, OverheadDiff, compute_metric_diffs, compute_overhead_diff
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_score_report.py -v`
Expected: All 15 tests PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest --ignore=tests/test_backends.py --ignore=tests/test_prompt_manager.py -v`
Expected: All tests PASS

- [ ] **Step 7: Run linting and type checking**

Run: `uv run ruff check . && uv run pyright`
Expected: No errors

- [ ] **Step 8: Commit**

```bash
git add odysseus/eval/__init__.py
git commit -m "feat(eval): export ScoreReport and diff types from eval package"
```

---

## Pipeline Context Contract (Reference for THP-104 and THP-129)

The `EvalRunnerAgent` MUST place a `ScoreReport` into the pipeline context under the key `"eval_score_report"`:

```python
# In EvalRunnerAgent.run() (THP-130), after calling run_eval tool (THP-129):
context["eval_score_report"] = score_report.model_dump()
```

The Review agent reads from `context["eval_score_report"]` and can reconstruct via:

```python
score = ScoreReport(**context["eval_score_report"])
```

### Context dict schema

```python
{
    "eval_score_report": {
        "metrics": {"accuracy": 0.85, "f1/macro": 0.78, ...},
        "summary": {
            "total": 100,
            "succeeded": 95,
            "failed": 5,
            "total_cost": 0.42,
            "start_time": "2026-03-19T10:00:00Z",
            "end_time": "2026-03-19T10:01:00Z",
            "duration_seconds": 60.0,
        },
        "errors": [
            {"example_id": "ex-42", "error": "timeout", "retries": 3},
            ...
        ],
        "diff": {  # null if no previous run
            "metric_diffs": [
                {"key": "accuracy", "old": 0.80, "new": 0.85, "status": "changed"},
                ...
            ],
            "overhead_diff": {  # null if unchanged
                "old_cost": 0.50, "new_cost": 0.42,
                "old_duration": 65.0, "new_duration": 60.0,
            },
        },
        "report_path": "outputs/report.json",
    }
}
```
