# Review Agent Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Review Agent — a hybrid code pre-processor + LLM critic that supervises the prompt optimization search loop with block-level edit directives, regression guards, and loop control.

**Architecture:** Code layer (`review_preprocessor.py`) computes numerical analysis (metric deltas, per-class recall, diversity, diminishing returns, mutation correlation, oracle ratios) from raw ScoreReports. LLM layer (system prompt via MCP) produces qualitative ReviewResult (edit directives, promotion decisions, loop signals). Persistence layer (`review_ops.py`) manages directive history, mutation log, and round reports on disk.

**Tech Stack:** Python 3.11+, Pydantic BaseModel, difflib (stdlib), pytest, FastMCP

**Spec:** `docs/superpowers/specs/2026-03-25-review-agent-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| Create: `odysseus/agents/review_models.py` | All Pydantic models: ReviewBriefing, ReviewResult, and their components |
| Create: `odysseus/agents/review_preprocessor.py` | Pure computation functions that build ReviewBriefing from raw data |
| Create: `odysseus/agents/review_ops.py` | File-backed persistence: directive history, mutation log, round reports |
| Create: `odysseus/agents/prompts/review_agent_system.md` | LLM system prompt |
| Modify: `odysseus/mcp.py` | Add tools, prompt, resource for Review Agent |
| Modify: `odysseus/agents/__init__.py` | Export new models and functions |
| Create: `tests/test_review_models.py` | Model validation tests |
| Create: `tests/test_review_preprocessor.py` | Pre-processor computation tests |
| Create: `tests/test_review_ops.py` | Persistence operation tests |
| Modify: `tests/test_mcp.py` | MCP tool registration tests |

---

## Chunk 1: Data Models

### Task 1: ReviewBriefing Component Models

**Files:**
- Create: `odysseus/agents/review_models.py`
- Create: `tests/test_review_models.py`

- [ ] **Step 1: Write failing tests for MetricDeltas, FrontComparison, CandidateAnalysis**

```python
# tests/test_review_models.py
"""Tests for odysseus.agents.review_models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from odysseus.agents.review_models import (
    CandidateAnalysis,
    FrontComparison,
    MetricDeltas,
)
from odysseus.eval.models import RunSummary, ScoreReport


def _make_score_report(**metric_overrides: float) -> ScoreReport:
    """Helper to build a minimal ScoreReport for tests."""
    return ScoreReport(
        metrics={"accuracy": 0.80, "cost": 1.0, **metric_overrides},
        summary=RunSummary(
            total=10, succeeded=10, failed=0, total_cost=1.0,
            start_time=datetime.now(tz=timezone.utc),
            end_time=datetime.now(tz=timezone.utc),
            duration_seconds=5.0,
        ),
        errors=[],
        diff=None,
        report_path="report.json",
        results_path="results.jsonl",
    )


class TestMetricDeltas:
    def test_creates_with_all_fields(self) -> None:
        d = MetricDeltas(
            quality_delta=0.05,
            cost_delta=-0.12,
            per_class_recall_deltas={"model-a": 0.1, "model-b": -0.05},
        )
        assert d.quality_delta == 0.05
        assert d.cost_delta == -0.12
        assert d.per_class_recall_deltas["model-a"] == 0.1

    def test_empty_recall_deltas(self) -> None:
        d = MetricDeltas(quality_delta=0.0, cost_delta=0.0, per_class_recall_deltas={})
        assert d.per_class_recall_deltas == {}


class TestFrontComparison:
    def test_creates_with_all_fields(self) -> None:
        fc = FrontComparison(
            front_candidate_version="v3",
            quality_delta=0.02,
            cost_delta=-0.05,
        )
        assert fc.front_candidate_version == "v3"


class TestCandidateAnalysis:
    def test_creates_with_parent(self) -> None:
        ca = CandidateAnalysis(
            candidate_version="v5",
            parent_version="v3",
            mutation_description="Swapped Example 3 with hard negative from holdout",
            score_report=_make_score_report(accuracy=0.85),
            delta_vs_parent=MetricDeltas(
                quality_delta=0.05, cost_delta=-0.1, per_class_recall_deltas={}
            ),
            delta_vs_front=[
                FrontComparison(
                    front_candidate_version="v3", quality_delta=0.05, cost_delta=-0.1
                )
            ],
        )
        assert ca.candidate_version == "v5"
        assert ca.parent_version == "v3"
        assert len(ca.delta_vs_front) == 1

    def test_creates_without_parent(self) -> None:
        ca = CandidateAnalysis(
            candidate_version="v1",
            parent_version=None,
            mutation_description="Initial compilation",
            score_report=_make_score_report(),
            delta_vs_parent=MetricDeltas(
                quality_delta=0.0, cost_delta=0.0, per_class_recall_deltas={}
            ),
            delta_vs_front=[],
        )
        assert ca.parent_version is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'odysseus.agents.review_models'`

- [ ] **Step 3: Implement MetricDeltas, FrontComparison, CandidateAnalysis**

```python
# odysseus/agents/review_models.py
"""Data models for the Review Agent.

See docs/superpowers/specs/2026-03-25-review-agent-design.md for the full spec.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from odysseus.agents.prompt_builder_search import Candidate
from odysseus.eval.models import ScoreReport


# ---------------------------------------------------------------------------
# ReviewBriefing components
# ---------------------------------------------------------------------------


class MetricDeltas(BaseModel):
    """Metric differences between two candidates or a candidate and a reference."""

    quality_delta: float
    cost_delta: float
    per_class_recall_deltas: dict[str, float]


class FrontComparison(BaseModel):
    """How a candidate compares to a specific Pareto front member."""

    front_candidate_version: str
    quality_delta: float
    cost_delta: float


class CandidateAnalysis(BaseModel):
    """Pre-processed analysis of a single candidate in the current round."""

    candidate_version: str
    parent_version: str | None
    mutation_description: str
    score_report: ScoreReport
    delta_vs_parent: MetricDeltas
    delta_vs_front: list[FrontComparison]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review_models.py tests/test_review_models.py
git commit -m "feat(review): add MetricDeltas, FrontComparison, CandidateAnalysis models"
```

### Task 2: Remaining ReviewBriefing Component Models

**Files:**
- Modify: `odysseus/agents/review_models.py`
- Modify: `tests/test_review_models.py`

- [ ] **Step 1: Write failing tests for ClassRecallEntry, DiversityMetrics, DiminishingReturns, MutationRecord, MutationHistory, ExampleSummary, OracleMetrics**

```python
# Append to tests/test_review_models.py

from odysseus.agents.review_models import (
    ClassRecallEntry,
    DiminishingReturns,
    DiversityMetrics,
    ExampleSummary,
    MutationHistory,
    MutationRecord,
    OracleMetrics,
)


class TestClassRecallEntry:
    def test_creates_with_regression(self) -> None:
        entry = ClassRecallEntry(
            recall=0.6, support=10, trend=[0.8, 0.75, 0.6], regression_flag=True
        )
        assert entry.regression_flag is True
        assert len(entry.trend) == 3

    def test_no_regression(self) -> None:
        entry = ClassRecallEntry(
            recall=0.9, support=20, trend=[0.85, 0.9], regression_flag=False
        )
        assert entry.regression_flag is False


class TestDiversityMetrics:
    def test_creates(self) -> None:
        dm = DiversityMetrics(
            example_overlap_ratio=0.8,
            prompt_similarity=0.3,
            mutation_type_distribution={"example_swap": 3, "rule_edit": 1},
        )
        assert dm.example_overlap_ratio == 0.8


class TestDiminishingReturns:
    def test_stagnation_flagged(self) -> None:
        dr = DiminishingReturns(
            score_trajectory=[0.80, 0.82, 0.825, 0.826],
            improvement_trend=0.002,
            stagnation_flag=True,
        )
        assert dr.stagnation_flag is True


class TestMutationRecord:
    def test_with_directive_ids(self) -> None:
        mr = MutationRecord(
            child_version="v5",
            parent_version="v3",
            mutation_type="example_swap",
            description="Replaced Example 3 with holdout example H7",
            directive_ids=["d-001", "d-002"],
        )
        assert mr.directive_ids == ["d-001", "d-002"]

    def test_without_directive_ids(self) -> None:
        mr = MutationRecord(
            child_version="v2",
            parent_version="v1",
            mutation_type="rule_edit",
            description="Tightened output contract",
        )
        assert mr.directive_ids is None


class TestMutationHistory:
    def test_creates(self) -> None:
        mh = MutationHistory(
            effective_mutations=[],
            ineffective_mutations=[],
            untried_mutation_types=["schema_change", "assembly_policy"],
        )
        assert len(mh.untried_mutation_types) == 2


class TestExampleSummary:
    def test_creates(self) -> None:
        es = ExampleSummary(
            example_id="ex-42",
            route="model-a",
            ambiguity_tags=["BOUNDARY_CASE"],
        )
        assert es.route == "model-a"


class TestOracleMetrics:
    def test_with_captured_ratios(self) -> None:
        om = OracleMetrics(
            oracle_cost_reduction=0.50,
            oracle_quality_reduction=0.10,
            candidate_cost_captured=0.70,
            candidate_quality_captured=0.85,
        )
        assert om.candidate_cost_captured == 0.70

    def test_with_none_captured(self) -> None:
        om = OracleMetrics(
            oracle_cost_reduction=0.0,
            oracle_quality_reduction=0.0,
            candidate_cost_captured=None,
            candidate_quality_captured=None,
        )
        assert om.candidate_cost_captured is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_models.py -v -k "ClassRecall or Diversity or Diminishing or Mutation or Example or Oracle"`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement the models**

Append to `odysseus/agents/review_models.py`:

```python
class ClassRecallEntry(BaseModel):
    """Per-route recall with historical trend and regression detection."""

    recall: float
    support: int
    trend: list[float]
    regression_flag: bool


class DiversityMetrics(BaseModel):
    """Measures of search diversity across the Pareto front."""

    example_overlap_ratio: float  # 0.0 = no overlap, 1.0 = identical examples
    prompt_similarity: float  # 0.0 = identical, 1.0 = completely different
    mutation_type_distribution: dict[str, int]


class DiminishingReturns(BaseModel):
    """Score trajectory analysis for detecting stagnation."""

    score_trajectory: list[float]
    improvement_trend: float
    stagnation_flag: bool


MutationType = Literal[
    "example_swap", "rule_edit", "schema_change",
    "rule_add", "rule_remove", "assembly_policy",
]


class MutationRecord(BaseModel):
    """What the Prompt Builder changed and why."""

    child_version: str
    parent_version: str
    mutation_type: MutationType
    description: str
    directive_ids: list[str] | None = None


class MutationHistory(BaseModel):
    """Aggregated mutation effectiveness data."""

    effective_mutations: list[MutationRecord]
    ineffective_mutations: list[MutationRecord]
    untried_mutation_types: list[str]


class ExampleSummary(BaseModel):
    """Lightweight reference to a holdout example for the exemplar bank."""

    example_id: str
    route: str
    ambiguity_tags: list[str]


class OracleMetrics(BaseModel):
    """How much of the theoretical routing improvement has been captured."""

    oracle_cost_reduction: float
    oracle_quality_reduction: float
    candidate_cost_captured: float | None = None
    candidate_quality_captured: float | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review_models.py tests/test_review_models.py
git commit -m "feat(review): add remaining ReviewBriefing component models"
```

### Task 3: ReviewBriefing Aggregate Model

**Files:**
- Modify: `odysseus/agents/review_models.py`
- Modify: `tests/test_review_models.py`

- [ ] **Step 1: Write failing test for ReviewBriefing**

```python
# Append to tests/test_review_models.py

from odysseus.agents.review_models import ReviewBriefing


class TestReviewBriefing:
    def test_creates_full_briefing(self) -> None:
        briefing = ReviewBriefing(
            round=3,
            candidates=[],
            pareto_front=[],
            per_class_recall={},
            diversity_metrics=DiversityMetrics(
                example_overlap_ratio=0.5,
                prompt_similarity=0.4,
                mutation_type_distribution={},
            ),
            diminishing_returns=DiminishingReturns(
                score_trajectory=[0.7, 0.8],
                improvement_trend=0.1,
                stagnation_flag=False,
            ),
            mutation_history=MutationHistory(
                effective_mutations=[],
                ineffective_mutations=[],
                untried_mutation_types=[],
            ),
            oracle_metrics=OracleMetrics(
                oracle_cost_reduction=0.5,
                oracle_quality_reduction=0.1,
                candidate_cost_captured=0.6,
                candidate_quality_captured=0.8,
            ),
            prompt_versions={"v1": "## Rules\n1. Route to model-a"},
            holdout_examples=[],
        )
        assert briefing.round == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_review_models.py::TestReviewBriefing -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement ReviewBriefing**

Append to `odysseus/agents/review_models.py`:

```python
class ReviewBriefing(BaseModel):
    """Complete pre-processed input for the Review Agent LLM.

    Built by the code pre-processor from raw ScoreReports, SearchState,
    prompt texts, and historical data.
    """

    round: int
    candidates: list[CandidateAnalysis]
    pareto_front: list[Candidate]
    per_class_recall: dict[str, ClassRecallEntry]
    diversity_metrics: DiversityMetrics
    diminishing_returns: DiminishingReturns
    mutation_history: MutationHistory
    oracle_metrics: OracleMetrics
    prompt_versions: dict[str, str]
    holdout_examples: list[ExampleSummary]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review_models.py tests/test_review_models.py
git commit -m "feat(review): add ReviewBriefing aggregate model"
```

### Task 4: ReviewResult Models

**Files:**
- Modify: `odysseus/agents/review_models.py`
- Modify: `tests/test_review_models.py`

- [ ] **Step 1: Write failing tests for all ReviewResult components**

```python
# Append to tests/test_review_models.py

from odysseus.agents.review_models import (
    DirectiveOutcome,
    EditDirective,
    LoopSignal,
    PromotionDecision,
    RankedCandidate,
    RegressionFlag,
    ReviewResult,
)


class TestRankedCandidate:
    def test_creates(self) -> None:
        rc = RankedCandidate(version="v5", rank=1, rationale="Best quality-cost trade-off")
        assert rc.rank == 1


class TestEditDirective:
    def test_macro_directive(self) -> None:
        ed = EditDirective(
            directive_id="d-001",
            target_version="v5",
            block_type="example",
            block_identifier="Example 3",
            granularity="macro",
            directive="Replace with hard negative from holdout boundary bank",
            priority="high",
        )
        assert ed.granularity == "macro"

    def test_micro_directive(self) -> None:
        ed = EditDirective(
            directive_id="d-002",
            target_version="v5",
            block_type="rule",
            block_identifier="Rule 2",
            granularity="micro",
            directive="Shorten constraint wording — remove redundant clause",
            priority="low",
        )
        assert ed.granularity == "micro"


class TestPromotionDecision:
    def test_promote(self) -> None:
        pd = PromotionDecision(
            version="v5", decision="promote", reason="No regressions, strong scores"
        )
        assert pd.decision == "promote"

    def test_refine(self) -> None:
        pd = PromotionDecision(
            version="v4",
            decision="refine",
            reason="Promising structure but class-B recall dropped",
        )
        assert pd.decision == "refine"


class TestLoopSignal:
    def test_refine_with_budget(self) -> None:
        ls = LoopSignal(
            action="refine",
            reason="Untried macro mutations available",
            suggested_budget=3,
            suggested_mutation_mode="exploratory",
        )
        assert ls.suggested_budget == 3

    def test_exit(self) -> None:
        ls = LoopSignal(
            action="exit",
            reason="dominance_threshold_met",
        )
        assert ls.suggested_budget is None
        assert ls.suggested_mutation_mode is None


class TestRegressionFlag:
    def test_block_severity(self) -> None:
        rf = RegressionFlag(
            version="v5",
            metric="recall/model-b",
            previous_value=0.8,
            current_value=0.6,
            severity="block",
        )
        assert rf.severity == "block"


class TestDirectiveOutcome:
    def test_improved(self) -> None:
        do = DirectiveOutcome(
            prior_directive_id="d-001",
            was_attempted=True,
            outcome="improved",
        )
        assert do.outcome == "improved"

    def test_not_attempted(self) -> None:
        do = DirectiveOutcome(
            prior_directive_id="d-002",
            was_attempted=False,
            outcome="no_effect",
        )
        assert do.was_attempted is False


class TestReviewResult:
    def test_creates_full_result(self) -> None:
        result = ReviewResult(
            candidate_ranking=[
                RankedCandidate(version="v5", rank=1, rationale="Best overall"),
            ],
            edit_directives=[],
            promotion_decisions=[
                PromotionDecision(version="v5", decision="promote", reason="Strong"),
            ],
            loop_signal=LoopSignal(action="exit", reason="dominance_threshold_met"),
            regression_guards=[],
            directive_history_update=[],
        )
        assert result.loop_signal.action == "exit"
        assert len(result.candidate_ranking) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_models.py -v -k "Ranked or EditDirective or Promotion or LoopSignal or Regression or DirectiveOutcome or ReviewResult"`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement ReviewResult models**

Append to `odysseus/agents/review_models.py`:

```python
# ---------------------------------------------------------------------------
# ReviewResult components (LLM output)
# ---------------------------------------------------------------------------


class RankedCandidate(BaseModel):
    """A candidate with its rank and ranking rationale."""

    version: str
    rank: int
    rationale: str


class EditDirective(BaseModel):
    """A localized, block-level edit instruction for the Prompt Builder."""

    directive_id: str
    target_version: str
    block_type: Literal["rule", "example", "output_schema", "assembly_policy"]
    block_identifier: str  # "Rule 2" | "Example 5" | "Output Schema"
    granularity: Literal["macro", "micro"]
    directive: str
    priority: Literal["high", "medium", "low"]


class PromotionDecision(BaseModel):
    """Whether a candidate should be promoted, refined, or pruned."""

    version: str
    decision: Literal["promote", "prune", "refine"]
    reason: str


class LoopSignal(BaseModel):
    """Whether to continue refining or exit the search loop."""

    action: Literal["refine", "exit"]
    reason: str
    suggested_budget: int | None = None
    suggested_mutation_mode: Literal["targeted", "exploratory"] | None = None


class RegressionFlag(BaseModel):
    """A metric regression that may block promotion."""

    version: str
    metric: str
    previous_value: float
    current_value: float
    severity: Literal["warning", "block"]


class DirectiveOutcome(BaseModel):
    """Tracks whether a prior directive was attempted and its effect."""

    prior_directive_id: str
    was_attempted: bool
    outcome: Literal["improved", "no_effect", "regressed"]


class ReviewResult(BaseModel):
    """Complete structured output from the Review Agent LLM."""

    candidate_ranking: list[RankedCandidate]
    edit_directives: list[EditDirective]
    promotion_decisions: list[PromotionDecision]
    loop_signal: LoopSignal
    regression_guards: list[RegressionFlag]
    directive_history_update: list[DirectiveOutcome]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review_models.py tests/test_review_models.py
git commit -m "feat(review): add ReviewResult models"
```

---

## Chunk 2: Persistence Operations

### Task 5: Directive History Persistence

**Files:**
- Create: `odysseus/agents/review_ops.py`
- Create: `tests/test_review_ops.py`

- [ ] **Step 1: Write failing tests for directive history load/save**

```python
# tests/test_review_ops.py
"""Tests for odysseus.agents.review_ops."""

from __future__ import annotations

import pytest

from odysseus.agents.review_models import DirectiveOutcome
from odysseus.agents.review_ops import (
    load_directive_history,
    save_directive_history,
)


class TestDirectiveHistoryPersistence:
    def test_save_and_load_roundtrip(self, tmp_path) -> None:
        history = [
            DirectiveOutcome(
                prior_directive_id="d-001", was_attempted=True, outcome="improved"
            ),
            DirectiveOutcome(
                prior_directive_id="d-002", was_attempted=False, outcome="no_effect"
            ),
        ]
        save_directive_history("search-abc", history, output_dir=tmp_path)
        loaded = load_directive_history("search-abc", output_dir=tmp_path)
        assert len(loaded) == 2
        assert loaded[0].prior_directive_id == "d-001"
        assert loaded[1].was_attempted is False

    def test_load_returns_empty_when_no_file(self, tmp_path) -> None:
        (tmp_path / "search-abc").mkdir()
        loaded = load_directive_history("search-abc", output_dir=tmp_path)
        assert loaded == []

    def test_append_to_existing(self, tmp_path) -> None:
        initial = [
            DirectiveOutcome(
                prior_directive_id="d-001", was_attempted=True, outcome="improved"
            ),
        ]
        save_directive_history("search-abc", initial, output_dir=tmp_path)

        additional = [
            DirectiveOutcome(
                prior_directive_id="d-003", was_attempted=True, outcome="regressed"
            ),
        ]
        save_directive_history(
            "search-abc", initial + additional, output_dir=tmp_path
        )
        loaded = load_directive_history("search-abc", output_dir=tmp_path)
        assert len(loaded) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_ops.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement directive history persistence**

```python
# odysseus/agents/review_ops.py
"""File-backed persistence for Review Agent state.

Follows the same pattern as prompt_builder_search_ops.py:
pure functions, file-backed, no in-memory state.
"""

from __future__ import annotations

import json
from pathlib import Path

from odysseus.agents.review_models import (
    DirectiveOutcome,
    MutationRecord,
)

_DEFAULT_OUTPUT_DIR = Path("outputs")


def _search_dir(search_state_id: str, output_dir: Path) -> Path:
    return output_dir / search_state_id


def _directive_history_path(search_state_id: str, output_dir: Path) -> Path:
    return _search_dir(search_state_id, output_dir) / "directive_history.json"


def save_directive_history(
    search_state_id: str,
    history: list[DirectiveOutcome],
    *,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
) -> None:
    """Save the full directive history to disk."""
    path = _directive_history_path(search_state_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [h.model_dump(mode="json") for h in history]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_directive_history(
    search_state_id: str,
    *,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
) -> list[DirectiveOutcome]:
    """Load directive history from disk. Returns empty list if no file exists."""
    path = _directive_history_path(search_state_id, output_dir)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [DirectiveOutcome.model_validate(d) for d in data]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_ops.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review_ops.py tests/test_review_ops.py
git commit -m "feat(review): add directive history persistence"
```

### Task 6: Mutation Log Persistence

**Files:**
- Modify: `odysseus/agents/review_ops.py`
- Modify: `tests/test_review_ops.py`

- [ ] **Step 1: Write failing tests for mutation log load/save**

```python
# Append to tests/test_review_ops.py

from odysseus.agents.review_models import MutationRecord
from odysseus.agents.review_ops import load_mutation_log, save_mutation_log


class TestMutationLogPersistence:
    def test_save_and_load_roundtrip(self, tmp_path) -> None:
        log = [
            MutationRecord(
                child_version="v2",
                parent_version="v1",
                mutation_type="rule_edit",
                description="Tightened output contract",
                directive_ids=["d-001"],
            ),
        ]
        save_mutation_log("search-abc", log, output_dir=tmp_path)
        loaded = load_mutation_log("search-abc", output_dir=tmp_path)
        assert len(loaded) == 1
        assert loaded[0].mutation_type == "rule_edit"
        assert loaded[0].directive_ids == ["d-001"]

    def test_load_returns_empty_when_no_file(self, tmp_path) -> None:
        (tmp_path / "search-abc").mkdir()
        loaded = load_mutation_log("search-abc", output_dir=tmp_path)
        assert loaded == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_ops.py::TestMutationLogPersistence -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement mutation log persistence**

Add to `odysseus/agents/review_ops.py`:

```python
def _mutation_log_path(search_state_id: str, output_dir: Path) -> Path:
    return _search_dir(search_state_id, output_dir) / "mutation_log.json"


def save_mutation_log(
    search_state_id: str,
    log: list[MutationRecord],
    *,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
) -> None:
    """Save the full mutation log to disk."""
    path = _mutation_log_path(search_state_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [r.model_dump(mode="json") for r in log]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_mutation_log(
    search_state_id: str,
    *,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
) -> list[MutationRecord]:
    """Load mutation log from disk. Returns empty list if no file exists."""
    path = _mutation_log_path(search_state_id, output_dir)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [MutationRecord.model_validate(d) for d in data]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_ops.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review_ops.py tests/test_review_ops.py
git commit -m "feat(review): add mutation log persistence"
```

### Task 7: Round Reports Persistence

**Files:**
- Modify: `odysseus/agents/review_ops.py`
- Modify: `tests/test_review_ops.py`

- [ ] **Step 1: Write failing tests for round report save/load**

```python
# Append to tests/test_review_ops.py

from odysseus.agents.review_ops import load_round_reports, save_round_report


class TestRoundReportsPersistence:
    def test_save_and_load_single_round(self, tmp_path) -> None:
        reports = {
            "v3": {"metrics": {"accuracy": 0.85, "cost": 1.2}},
            "v4": {"metrics": {"accuracy": 0.87, "cost": 1.1}},
        }
        save_round_report("search-abc", round_num=2, reports=reports, output_dir=tmp_path)
        loaded = load_round_reports("search-abc", output_dir=tmp_path)
        assert 2 in loaded
        assert loaded[2]["v3"]["metrics"]["accuracy"] == 0.85

    def test_save_multiple_rounds(self, tmp_path) -> None:
        save_round_report(
            "search-abc", round_num=1,
            reports={"v1": {"metrics": {"accuracy": 0.7}}},
            output_dir=tmp_path,
        )
        save_round_report(
            "search-abc", round_num=2,
            reports={"v2": {"metrics": {"accuracy": 0.8}}},
            output_dir=tmp_path,
        )
        loaded = load_round_reports("search-abc", output_dir=tmp_path)
        assert len(loaded) == 2
        assert 1 in loaded
        assert 2 in loaded

    def test_load_returns_empty_when_no_dir(self, tmp_path) -> None:
        (tmp_path / "search-abc").mkdir()
        loaded = load_round_reports("search-abc", output_dir=tmp_path)
        assert loaded == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_ops.py::TestRoundReportsPersistence -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement round reports persistence**

Add to `odysseus/agents/review_ops.py`:

```python
from typing import Any


def _round_reports_dir(search_state_id: str, output_dir: Path) -> Path:
    return _search_dir(search_state_id, output_dir) / "round_reports"


def save_round_report(
    search_state_id: str,
    round_num: int,
    reports: dict[str, dict[str, Any]],
    *,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
) -> None:
    """Save a round's ScoreReports (serialized) to disk."""
    dir_path = _round_reports_dir(search_state_id, output_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / f"round_{round_num}.json"
    path.write_text(json.dumps(reports, indent=2), encoding="utf-8")


def load_round_reports(
    search_state_id: str,
    *,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
) -> dict[int, dict[str, dict[str, Any]]]:
    """Load all historical round reports. Returns {round_num: {version: report_dict}}."""
    dir_path = _round_reports_dir(search_state_id, output_dir)
    if not dir_path.exists():
        return {}
    result: dict[int, dict[str, dict[str, Any]]] = {}
    for path in sorted(dir_path.glob("round_*.json")):
        round_num = int(path.stem.split("_")[1])
        result[round_num] = json.loads(path.read_text(encoding="utf-8"))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_ops.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review_ops.py tests/test_review_ops.py
git commit -m "feat(review): add round reports persistence"
```

---

## Chunk 3: Code Pre-Processor — Computation Functions

### Task 8: build_candidate_comparisons

**Files:**
- Create: `odysseus/agents/review_preprocessor.py`
- Create: `tests/test_review_preprocessor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_review_preprocessor.py
"""Tests for odysseus.agents.review_preprocessor."""

from __future__ import annotations

import pytest

from odysseus.agents.review_preprocessor import build_candidate_comparisons


class TestBuildCandidateComparisons:
    def test_single_candidate_no_parent_no_front(self) -> None:
        """First round: one candidate, no parent, empty front."""
        score_reports = {
            "v1": {
                "metrics": {"accuracy": 0.80, "cost": 1.50},
            },
        }
        mutation_descriptions = {"v1": "Initial compilation"}
        parent_versions = {"v1": None}
        front_versions = []

        result = build_candidate_comparisons(
            score_reports=score_reports,
            mutation_descriptions=mutation_descriptions,
            parent_versions=parent_versions,
            front_versions=front_versions,
            primary_metric="accuracy",
        )

        assert len(result) == 1
        assert result[0].candidate_version == "v1"
        assert result[0].parent_version is None
        assert result[0].delta_vs_parent.quality_delta == 0.0
        assert result[0].delta_vs_front == []

    def test_candidate_with_parent_and_front(self) -> None:
        """Later round: candidate has parent, front has members."""
        score_reports = {
            "v3": {"metrics": {"accuracy": 0.85, "cost": 1.20}},
            "v1": {"metrics": {"accuracy": 0.80, "cost": 1.50}},  # front member
            "v2": {"metrics": {"accuracy": 0.82, "cost": 1.30}},  # parent + front
        }
        mutation_descriptions = {"v3": "Swapped Example 3"}
        parent_versions = {"v3": "v2"}
        front_versions = ["v1", "v2"]

        result = build_candidate_comparisons(
            score_reports=score_reports,
            mutation_descriptions=mutation_descriptions,
            parent_versions=parent_versions,
            front_versions=front_versions,
            primary_metric="accuracy",
        )

        assert len(result) == 1
        ca = result[0]
        assert ca.candidate_version == "v3"
        assert ca.delta_vs_parent.quality_delta == pytest.approx(0.03)
        assert ca.delta_vs_parent.cost_delta == pytest.approx(-0.10)
        assert len(ca.delta_vs_front) == 2

    def test_multiple_candidates(self) -> None:
        """Multiple candidates in one round."""
        score_reports = {
            "v3": {"metrics": {"accuracy": 0.85, "cost": 1.20}},
            "v4": {"metrics": {"accuracy": 0.83, "cost": 1.10}},
            "v2": {"metrics": {"accuracy": 0.82, "cost": 1.30}},
        }
        mutation_descriptions = {
            "v3": "Swapped Example 3",
            "v4": "Pruned Rule 2",
        }
        parent_versions = {"v3": "v2", "v4": "v2"}
        front_versions = ["v2"]

        result = build_candidate_comparisons(
            score_reports=score_reports,
            mutation_descriptions=mutation_descriptions,
            parent_versions=parent_versions,
            front_versions=front_versions,
            primary_metric="accuracy",
        )

        assert len(result) == 2
        versions = {ca.candidate_version for ca in result}
        assert versions == {"v3", "v4"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_preprocessor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement build_candidate_comparisons**

```python
# odysseus/agents/review_preprocessor.py
"""Code pre-processor for the Review Agent.

Pure computation functions that transform raw ScoreReports, SearchState,
and historical data into a ReviewBriefing. No external dependencies
beyond stdlib (difflib).
"""

from __future__ import annotations

from typing import Any

from odysseus.agents.review_models import (
    CandidateAnalysis,
    FrontComparison,
    MetricDeltas,
)


def _extract_metric(report: dict[str, Any], metric: str) -> float:
    """Extract a metric value from a ScoreReport dict, defaulting to 0.0."""
    return float(report.get("metrics", {}).get(metric, 0.0))


def _compute_recall_deltas(
    candidate_report: dict[str, Any],
    reference_report: dict[str, Any],
) -> dict[str, float]:
    """Compute per-class recall deltas between two reports."""
    candidate_metrics = candidate_report.get("metrics", {})
    reference_metrics = reference_report.get("metrics", {})

    deltas: dict[str, float] = {}
    for key, value in candidate_metrics.items():
        if key.startswith("recall/"):
            route = key.removeprefix("recall/")
            ref_value = reference_metrics.get(key, 0.0)
            deltas[route] = value - ref_value
    return deltas


def build_candidate_comparisons(
    *,
    score_reports: dict[str, dict[str, Any]],
    mutation_descriptions: dict[str, str],
    parent_versions: dict[str, str | None],
    front_versions: list[str],
    primary_metric: str = "accuracy",
) -> list[CandidateAnalysis]:
    """Build per-candidate analysis with deltas vs parent and front.

    Args:
        score_reports: All available reports keyed by version (candidates + front).
        mutation_descriptions: What changed, keyed by candidate version.
        parent_versions: Parent version for each candidate.
        front_versions: Versions currently on the Pareto front.
        primary_metric: The quality metric to use for deltas.
    """
    candidate_versions = list(mutation_descriptions.keys())
    results: list[CandidateAnalysis] = []

    for version in candidate_versions:
        report = score_reports[version]
        parent = parent_versions.get(version)

        # Delta vs parent
        if parent and parent in score_reports:
            parent_report = score_reports[parent]
            delta_parent = MetricDeltas(
                quality_delta=_extract_metric(report, primary_metric)
                - _extract_metric(parent_report, primary_metric),
                cost_delta=_extract_metric(report, "cost")
                - _extract_metric(parent_report, "cost"),
                per_class_recall_deltas=_compute_recall_deltas(report, parent_report),
            )
        else:
            delta_parent = MetricDeltas(
                quality_delta=0.0, cost_delta=0.0, per_class_recall_deltas={}
            )

        # Delta vs each front member
        delta_front: list[FrontComparison] = []
        for fv in front_versions:
            if fv in score_reports:
                front_report = score_reports[fv]
                delta_front.append(
                    FrontComparison(
                        front_candidate_version=fv,
                        quality_delta=_extract_metric(report, primary_metric)
                        - _extract_metric(front_report, primary_metric),
                        cost_delta=_extract_metric(report, "cost")
                        - _extract_metric(front_report, "cost"),
                    )
                )

        results.append(
            CandidateAnalysis(
                candidate_version=version,
                parent_version=parent,
                mutation_description=mutation_descriptions[version],
                score_report=report,
                delta_vs_parent=delta_parent,
                delta_vs_front=delta_front,
            )
        )

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_preprocessor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review_preprocessor.py tests/test_review_preprocessor.py
git commit -m "feat(review): add build_candidate_comparisons pre-processor"
```

### Task 9: extract_per_class_recall

**Files:**
- Modify: `odysseus/agents/review_preprocessor.py`
- Modify: `tests/test_review_preprocessor.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_review_preprocessor.py

from odysseus.agents.review_preprocessor import extract_per_class_recall


class TestExtractPerClassRecall:
    def test_single_round_no_regression(self) -> None:
        current_reports = {
            "v1": {
                "metrics": {
                    "recall/model-a": 0.9,
                    "recall/model-b": 0.7,
                    "support/model-a": 15,
                    "support/model-b": 5,
                },
            },
        }
        historical: dict[int, dict[str, dict[str, Any]]] = {}

        result = extract_per_class_recall(
            current_reports=current_reports,
            historical_reports=historical,
            current_round=1,
        )

        assert "model-a" in result
        assert result["model-a"].recall == 0.9
        assert result["model-a"].support == 15
        assert result["model-a"].trend == [0.9]
        assert result["model-a"].regression_flag is False

    def test_multiple_rounds_with_regression(self) -> None:
        historical = {
            1: {"v1": {"metrics": {"recall/model-b": 0.8, "support/model-b": 5}}},
            2: {"v2": {"metrics": {"recall/model-b": 0.75, "support/model-b": 5}}},
        }
        current_reports = {
            "v3": {"metrics": {"recall/model-b": 0.6, "support/model-b": 5}},
        }

        result = extract_per_class_recall(
            current_reports=current_reports,
            historical_reports=historical,
            current_round=3,
        )

        assert result["model-b"].recall == 0.6
        assert result["model-b"].trend == [0.8, 0.75, 0.6]
        assert result["model-b"].regression_flag is True

    def test_best_candidate_used_per_round(self) -> None:
        """When multiple candidates exist in a round, use the best recall per class."""
        current_reports = {
            "v3": {"metrics": {"recall/model-a": 0.85, "support/model-a": 10}},
            "v4": {"metrics": {"recall/model-a": 0.90, "support/model-a": 10}},
        }

        result = extract_per_class_recall(
            current_reports=current_reports,
            historical_reports={},
            current_round=1,
        )

        assert result["model-a"].recall == 0.90
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_preprocessor.py::TestExtractPerClassRecall -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement extract_per_class_recall**

Add to `odysseus/agents/review_preprocessor.py`:

```python
from odysseus.agents.review_models import ClassRecallEntry


def _best_recall_per_class(
    reports: dict[str, dict[str, Any]],
) -> dict[str, tuple[float, int]]:
    """From a set of reports, get the best recall and support per class."""
    best: dict[str, tuple[float, int]] = {}
    for report in reports.values():
        metrics = report.get("metrics", {})
        for key, value in metrics.items():
            if key.startswith("recall/"):
                route = key.removeprefix("recall/")
                support_key = f"support/{route}"
                support = int(metrics.get(support_key, 0))
                if route not in best or value > best[route][0]:
                    best[route] = (value, support)
    return best


def extract_per_class_recall(
    *,
    current_reports: dict[str, dict[str, Any]],
    historical_reports: dict[int, dict[str, dict[str, Any]]],
    current_round: int,
) -> dict[str, ClassRecallEntry]:
    """Extract per-route recall with trends and regression flags.

    Uses the best recall per class across candidates in each round
    to build the trend. Regression is flagged when the current round's
    best recall is lower than the previous round's best.
    """
    # Build trend: best recall per class for each historical round
    all_rounds: dict[int, dict[str, tuple[float, int]]] = {}
    for round_num, reports in historical_reports.items():
        all_rounds[round_num] = _best_recall_per_class(reports)
    all_rounds[current_round] = _best_recall_per_class(current_reports)

    # Collect all known classes
    all_classes: set[str] = set()
    for round_data in all_rounds.values():
        all_classes.update(round_data.keys())

    result: dict[str, ClassRecallEntry] = {}
    for route in sorted(all_classes):
        trend: list[float] = []
        support = 0
        for round_num in sorted(all_rounds.keys()):
            if route in all_rounds[round_num]:
                recall_val, support_val = all_rounds[round_num][route]
                trend.append(recall_val)
                support = support_val  # Use latest support count

        current_recall = trend[-1] if trend else 0.0
        previous_recall = trend[-2] if len(trend) >= 2 else current_recall
        regression_flag = current_recall < previous_recall

        result[route] = ClassRecallEntry(
            recall=current_recall,
            support=support,
            trend=trend,
            regression_flag=regression_flag,
        )

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_preprocessor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review_preprocessor.py tests/test_review_preprocessor.py
git commit -m "feat(review): add extract_per_class_recall pre-processor"
```

### Task 10: compute_diversity_metrics

**Files:**
- Modify: `odysseus/agents/review_preprocessor.py`
- Modify: `tests/test_review_preprocessor.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_review_preprocessor.py

from odysseus.agents.review_preprocessor import compute_diversity_metrics
from odysseus.agents.review_models import MutationRecord


class TestComputeDiversityMetrics:
    def test_identical_prompts(self) -> None:
        prompt_texts = {
            "v1": "## Rules\n1. Route to A\n\n## Examples\n### Example 1\nfoo",
            "v2": "## Rules\n1. Route to A\n\n## Examples\n### Example 1\nfoo",
        }
        result = compute_diversity_metrics(
            prompt_texts=prompt_texts,
            mutation_log=[],
        )
        assert result.prompt_similarity == 0.0  # identical = no diversity
        assert result.example_overlap_ratio == 1.0  # fully overlapping

    def test_completely_different_prompts(self) -> None:
        prompt_texts = {
            "v1": "## Rules\n1. Route to A\n\n## Examples\n### Example 1\nalpha",
            "v2": "## Rules\n1. Route to Z\n\n## Examples\n### Example 9\nomega",
        }
        result = compute_diversity_metrics(
            prompt_texts=prompt_texts,
            mutation_log=[],
        )
        assert result.prompt_similarity > 0.0

    def test_mutation_type_distribution(self) -> None:
        log = [
            MutationRecord(
                child_version="v2", parent_version="v1",
                mutation_type="example_swap", description="swap",
            ),
            MutationRecord(
                child_version="v3", parent_version="v2",
                mutation_type="example_swap", description="swap",
            ),
            MutationRecord(
                child_version="v4", parent_version="v2",
                mutation_type="rule_edit", description="edit",
            ),
        ]
        result = compute_diversity_metrics(
            prompt_texts={"v1": "a", "v2": "b"},
            mutation_log=log,
        )
        assert result.mutation_type_distribution == {"example_swap": 2, "rule_edit": 1}

    def test_single_prompt_on_front(self) -> None:
        result = compute_diversity_metrics(
            prompt_texts={"v1": "## Rules\n1. Route to A"},
            mutation_log=[],
        )
        assert result.prompt_similarity == 0.0
        assert result.example_overlap_ratio == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_preprocessor.py::TestComputeDiversityMetrics -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement compute_diversity_metrics**

Add to `odysseus/agents/review_preprocessor.py`:

```python
import difflib
import re
from collections import Counter

from odysseus.agents.review_models import DiversityMetrics, MutationRecord


def _extract_example_ids(prompt_text: str) -> set[str]:
    """Extract example identifiers from a prompt following the Markdown convention."""
    return set(re.findall(r"###\s+Example\s+(\S+)", prompt_text))


def _pairwise_dissimilarity(texts: list[str]) -> float:
    """Average pairwise dissimilarity (1 - SequenceMatcher ratio) across texts."""
    if len(texts) < 2:
        return 0.0
    total = 0.0
    pairs = 0
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            ratio = difflib.SequenceMatcher(None, texts[i], texts[j]).ratio()
            total += 1.0 - ratio
            pairs += 1
    return total / pairs if pairs > 0 else 0.0


def _example_overlap_ratio(prompt_texts: dict[str, str]) -> float:
    """Fraction of examples shared across all prompts on the front."""
    if len(prompt_texts) < 2:
        return 1.0
    example_sets = [_extract_example_ids(text) for text in prompt_texts.values()]
    all_examples = set().union(*example_sets) if example_sets else set()
    if not all_examples:
        return 1.0
    shared = set.intersection(*example_sets) if example_sets else set()
    return len(shared) / len(all_examples)


def compute_diversity_metrics(
    *,
    prompt_texts: dict[str, str],
    mutation_log: list[MutationRecord],
) -> DiversityMetrics:
    """Compute diversity metrics across Pareto front prompts.

    prompt_similarity: 0.0 = identical, approaching 1.0 = very different.
    example_overlap_ratio: 1.0 = all prompts use same examples, 0.0 = no overlap.
    """
    texts = list(prompt_texts.values())
    type_counts = Counter(m.mutation_type for m in mutation_log)

    return DiversityMetrics(
        example_overlap_ratio=_example_overlap_ratio(prompt_texts),
        prompt_similarity=_pairwise_dissimilarity(texts),
        mutation_type_distribution=dict(type_counts),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_preprocessor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review_preprocessor.py tests/test_review_preprocessor.py
git commit -m "feat(review): add compute_diversity_metrics pre-processor"
```

### Task 11: compute_diminishing_returns

**Files:**
- Modify: `odysseus/agents/review_preprocessor.py`
- Modify: `tests/test_review_preprocessor.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_review_preprocessor.py

from odysseus.agents.review_preprocessor import compute_diminishing_returns


class TestComputeDiminishingReturns:
    def test_improving_trajectory(self) -> None:
        result = compute_diminishing_returns(
            score_trajectory=[0.70, 0.75, 0.80, 0.85],
            stagnation_threshold=0.005,
        )
        assert result.improvement_trend > 0.01
        assert result.stagnation_flag is False

    def test_stagnating_trajectory(self) -> None:
        result = compute_diminishing_returns(
            score_trajectory=[0.85, 0.851, 0.852, 0.852],
            stagnation_threshold=0.005,
        )
        assert result.improvement_trend < 0.005
        assert result.stagnation_flag is True

    def test_single_point(self) -> None:
        result = compute_diminishing_returns(
            score_trajectory=[0.80],
            stagnation_threshold=0.005,
        )
        assert result.improvement_trend == 0.0
        assert result.stagnation_flag is False  # Can't determine stagnation from one point

    def test_empty_trajectory(self) -> None:
        result = compute_diminishing_returns(
            score_trajectory=[],
            stagnation_threshold=0.005,
        )
        assert result.improvement_trend == 0.0
        assert result.stagnation_flag is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_preprocessor.py::TestComputeDiminishingReturns -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement compute_diminishing_returns**

Add to `odysseus/agents/review_preprocessor.py`:

```python
from odysseus.agents.review_models import DiminishingReturns


def compute_diminishing_returns(
    *,
    score_trajectory: list[float],
    stagnation_threshold: float = 0.005,
) -> DiminishingReturns:
    """Analyze score trajectory for diminishing returns.

    improvement_trend is the average improvement over the last 3 rounds
    (or fewer if not enough data). stagnation_flag is True when improvement
    is below the threshold and there are at least 2 data points.
    """
    if len(score_trajectory) < 2:
        return DiminishingReturns(
            score_trajectory=score_trajectory,
            improvement_trend=0.0,
            stagnation_flag=False,
        )

    # Use last 3 rounds for trend (or all if fewer)
    window = score_trajectory[-min(4, len(score_trajectory)) :]
    deltas = [window[i] - window[i - 1] for i in range(1, len(window))]
    trend = sum(deltas) / len(deltas) if deltas else 0.0

    return DiminishingReturns(
        score_trajectory=score_trajectory,
        improvement_trend=trend,
        stagnation_flag=trend < stagnation_threshold,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_preprocessor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review_preprocessor.py tests/test_review_preprocessor.py
git commit -m "feat(review): add compute_diminishing_returns pre-processor"
```

### Task 12: correlate_mutations

**Files:**
- Modify: `odysseus/agents/review_preprocessor.py`
- Modify: `tests/test_review_preprocessor.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_review_preprocessor.py

from odysseus.agents.review_preprocessor import correlate_mutations


class TestCorrelateMutations:
    def test_classifies_effective_and_ineffective(self) -> None:
        log = [
            MutationRecord(
                child_version="v2", parent_version="v1",
                mutation_type="example_swap", description="swap ex 3",
            ),
            MutationRecord(
                child_version="v3", parent_version="v2",
                mutation_type="rule_edit", description="tighten rule 1",
            ),
        ]
        # v2 improved over v1, v3 did not improve over v2
        score_history = {
            "v1": 0.80,
            "v2": 0.85,
            "v3": 0.84,
        }

        result = correlate_mutations(
            mutation_log=log,
            score_history=score_history,
        )

        assert len(result.effective_mutations) == 1
        assert result.effective_mutations[0].child_version == "v2"
        assert len(result.ineffective_mutations) == 1
        assert result.ineffective_mutations[0].child_version == "v3"

    def test_identifies_untried_types(self) -> None:
        log = [
            MutationRecord(
                child_version="v2", parent_version="v1",
                mutation_type="example_swap", description="swap",
            ),
        ]
        all_mutation_types = [
            "example_swap", "rule_edit", "schema_change",
            "rule_add", "rule_remove", "assembly_policy",
        ]

        result = correlate_mutations(
            mutation_log=log,
            score_history={"v1": 0.8, "v2": 0.85},
            all_mutation_types=all_mutation_types,
        )

        assert "rule_edit" in result.untried_mutation_types
        assert "example_swap" not in result.untried_mutation_types

    def test_empty_log(self) -> None:
        result = correlate_mutations(mutation_log=[], score_history={})
        assert result.effective_mutations == []
        assert result.ineffective_mutations == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_preprocessor.py::TestCorrelateMutations -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement correlate_mutations**

Add to `odysseus/agents/review_preprocessor.py`:

```python
from odysseus.agents.review_models import MutationHistory

_ALL_MUTATION_TYPES = [
    "example_swap",
    "rule_edit",
    "schema_change",
    "rule_add",
    "rule_remove",
    "assembly_policy",
]


def correlate_mutations(
    *,
    mutation_log: list[MutationRecord],
    score_history: dict[str, float],
    all_mutation_types: list[str] | None = None,
) -> MutationHistory:
    """Classify mutations as effective or ineffective based on score changes.

    A mutation is effective if the child's score exceeds the parent's score.

    Args:
        mutation_log: All mutations recorded so far.
        score_history: version → primary metric score.
        all_mutation_types: Full list of possible mutation types (defaults to built-in list).
    """
    if all_mutation_types is None:
        all_mutation_types = _ALL_MUTATION_TYPES

    effective: list[MutationRecord] = []
    ineffective: list[MutationRecord] = []
    tried_types: set[str] = set()

    for mutation in mutation_log:
        tried_types.add(mutation.mutation_type)
        child_score = score_history.get(mutation.child_version, 0.0)
        parent_score = score_history.get(mutation.parent_version, 0.0)
        if child_score > parent_score:
            effective.append(mutation)
        else:
            ineffective.append(mutation)

    untried = [t for t in all_mutation_types if t not in tried_types]

    return MutationHistory(
        effective_mutations=effective,
        ineffective_mutations=ineffective,
        untried_mutation_types=untried,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_preprocessor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review_preprocessor.py tests/test_review_preprocessor.py
git commit -m "feat(review): add correlate_mutations pre-processor"
```

### Task 13: compute_oracle_metrics

**Files:**
- Modify: `odysseus/agents/review_preprocessor.py`
- Modify: `tests/test_review_preprocessor.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_review_preprocessor.py

from odysseus.agents.review_preprocessor import (
    compute_oracle_metrics,
    compute_oracle_metrics_from_report,
)


class TestComputeOracleMetrics:
    def test_normal_case(self) -> None:
        result = compute_oracle_metrics(
            oracle_cost_reduction=0.50,
            oracle_quality_reduction=0.10,
            candidate_cost_reduction=0.35,
            candidate_quality_reduction=0.085,
        )
        assert result.oracle_cost_reduction == 0.50
        assert result.candidate_cost_captured == pytest.approx(0.70)
        assert result.candidate_quality_captured == pytest.approx(0.85)

    def test_zero_oracle_returns_none(self) -> None:
        result = compute_oracle_metrics(
            oracle_cost_reduction=0.0,
            oracle_quality_reduction=0.0,
            candidate_cost_reduction=0.10,
            candidate_quality_reduction=0.05,
        )
        assert result.candidate_cost_captured is None
        assert result.candidate_quality_captured is None

    def test_partial_zero(self) -> None:
        result = compute_oracle_metrics(
            oracle_cost_reduction=0.50,
            oracle_quality_reduction=0.0,
            candidate_cost_reduction=0.25,
            candidate_quality_reduction=0.0,
        )
        assert result.candidate_cost_captured == pytest.approx(0.50)
        assert result.candidate_quality_captured is None

    def test_missing_metrics_raises(self) -> None:
        """compute_oracle_metrics_from_report should raise if keys are absent."""
        with pytest.raises(ValueError, match="oracle"):
            compute_oracle_metrics_from_report(metrics={})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_preprocessor.py::TestComputeOracleMetrics -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement compute_oracle_metrics**

Add to `odysseus/agents/review_preprocessor.py`:

```python
from odysseus.agents.review_models import OracleMetrics


def compute_oracle_metrics(
    *,
    oracle_cost_reduction: float,
    oracle_quality_reduction: float,
    candidate_cost_reduction: float,
    candidate_quality_reduction: float,
) -> OracleMetrics:
    """Compute how much of the theoretical routing improvement has been captured."""
    return OracleMetrics(
        oracle_cost_reduction=oracle_cost_reduction,
        oracle_quality_reduction=oracle_quality_reduction,
        candidate_cost_captured=(
            candidate_cost_reduction / oracle_cost_reduction
            if oracle_cost_reduction != 0.0
            else None
        ),
        candidate_quality_captured=(
            candidate_quality_reduction / oracle_quality_reduction
            if oracle_quality_reduction != 0.0
            else None
        ),
    )


def compute_oracle_metrics_from_report(
    *,
    metrics: dict[str, float],
) -> OracleMetrics:
    """Extract oracle metrics from a ScoreReport metrics dict.

    Raises ValueError if oracle metric keys are absent.
    """
    required = ["oracle_cost_reduction", "oracle_quality_reduction",
                "cost_reduction", "quality_reduction"]
    missing = [k for k in required if k not in metrics]
    if missing:
        msg = f"oracle metrics missing from ScoreReport: {missing}"
        raise ValueError(msg)

    return compute_oracle_metrics(
        oracle_cost_reduction=metrics["oracle_cost_reduction"],
        oracle_quality_reduction=metrics["oracle_quality_reduction"],
        candidate_cost_reduction=metrics["cost_reduction"],
        candidate_quality_reduction=metrics["quality_reduction"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_preprocessor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review_preprocessor.py tests/test_review_preprocessor.py
git commit -m "feat(review): add compute_oracle_metrics pre-processor"
```

### Task 14: build_review_briefing Orchestrator

**Files:**
- Modify: `odysseus/agents/review_preprocessor.py`
- Modify: `tests/test_review_preprocessor.py`

- [ ] **Step 1: Write failing test for the orchestrator**

```python
# Append to tests/test_review_preprocessor.py

from odysseus.agents.prompt_builder_search import Candidate, SearchState
from odysseus.agents.review_preprocessor import build_review_briefing
from odysseus.agents.review_models import ExampleSummary, DirectiveOutcome


def _make_search_state(**overrides) -> SearchState:
    """Helper to build a minimal SearchState for tests."""
    defaults = dict(
        search_state_id="test-search",
        backend="anthropic",
        round=1,
        pareto_front=[],
        round_history=[],
        stagnation_count=0,
        stagnation_limit=3,
        convergence_limit=5,
        max_rounds=50,
        mutation_mode="targeted",
        converged=False,
    )
    defaults.update(overrides)
    return SearchState(**defaults)


class TestBuildReviewBriefing:
    def test_builds_complete_briefing(self) -> None:
        """Integration test: all components assembled into a ReviewBriefing."""
        search_state = _make_search_state(
            round=2,
            pareto_front=[
                Candidate(
                    prompt_version="v1", quality_score=0.80, cost=1.50,
                    round_introduced=1, dominated=False,
                ),
            ],
        )
        score_reports = {
            "v2": {
                "metrics": {
                    "accuracy": 0.85,
                    "cost": 1.20,
                    "recall/model-a": 0.9,
                    "support/model-a": 10,
                    "oracle_cost_reduction": 0.50,
                    "oracle_quality_reduction": 0.10,
                    "cost_reduction": 0.35,
                    "quality_reduction": 0.085,
                },
            },
            "v1": {
                "metrics": {
                    "accuracy": 0.80,
                    "cost": 1.50,
                    "recall/model-a": 0.85,
                    "support/model-a": 10,
                    "oracle_cost_reduction": 0.50,
                    "oracle_quality_reduction": 0.10,
                    "cost_reduction": 0.20,
                    "quality_reduction": 0.05,
                },
            },
        }
        historical_reports = {
            1: {
                "v1": score_reports["v1"],
            },
        }
        prompt_texts = {
            "v1": "## Rules\n1. Route to A\n\n## Examples\n### Example 1\nfoo",
            "v2": "## Rules\n1. Route to A\n2. Prefer B for complex\n\n## Examples\n### Example 1\nfoo",
        }
        mutation_log = [
            MutationRecord(
                child_version="v2", parent_version="v1",
                mutation_type="rule_add", description="Added complexity routing rule",
            ),
        ]

        briefing = build_review_briefing(
            search_state=search_state,
            score_reports=score_reports,
            historical_reports=historical_reports,
            prompt_texts=prompt_texts,
            mutation_log=mutation_log,
            directive_history=[],
            holdout_examples=[
                ExampleSummary(example_id="h1", route="model-a", ambiguity_tags=[]),
            ],
            candidate_versions=["v2"],
            parent_versions={"v2": "v1"},
        )

        assert briefing.round == 2
        assert len(briefing.candidates) == 1
        assert briefing.candidates[0].candidate_version == "v2"
        assert briefing.oracle_metrics.oracle_cost_reduction == 0.50
        assert briefing.oracle_metrics.candidate_cost_captured is not None
        assert len(briefing.per_class_recall) > 0
        assert "model-a" in briefing.per_class_recall
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_review_preprocessor.py::TestBuildReviewBriefing -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement build_review_briefing**

Add to `odysseus/agents/review_preprocessor.py`:

```python
from odysseus.agents.prompt_builder_search import Candidate, SearchState
from odysseus.agents.review_models import (
    DirectiveOutcome,
    ExampleSummary,
    ReviewBriefing,
)


def _build_score_trajectory(
    historical_reports: dict[int, dict[str, dict[str, Any]]],
    current_reports: dict[str, dict[str, Any]],
    current_round: int,
    primary_metric: str,
) -> list[float]:
    """Build a score trajectory: best primary metric per round."""
    trajectory: list[float] = []
    for round_num in sorted(historical_reports.keys()):
        reports = historical_reports[round_num]
        best = max(
            (_extract_metric(r, primary_metric) for r in reports.values()),
            default=0.0,
        )
        trajectory.append(best)
    # Current round
    best_current = max(
        (_extract_metric(r, primary_metric) for r in current_reports.values()),
        default=0.0,
    )
    trajectory.append(best_current)
    return trajectory


def _build_score_history(
    historical_reports: dict[int, dict[str, dict[str, Any]]],
    current_reports: dict[str, dict[str, Any]],
    primary_metric: str,
) -> dict[str, float]:
    """Build a flat version → score map from all reports."""
    scores: dict[str, float] = {}
    for reports in historical_reports.values():
        for version, report in reports.items():
            scores[version] = _extract_metric(report, primary_metric)
    for version, report in current_reports.items():
        scores[version] = _extract_metric(report, primary_metric)
    return scores


def build_review_briefing(
    *,
    search_state: SearchState,
    score_reports: dict[str, dict[str, Any]],
    historical_reports: dict[int, dict[str, dict[str, Any]]],
    prompt_texts: dict[str, str],
    mutation_log: list[MutationRecord],
    directive_history: list[DirectiveOutcome],
    holdout_examples: list[ExampleSummary],
    candidate_versions: list[str],
    parent_versions: dict[str, str | None],
) -> ReviewBriefing:
    """Assemble a complete ReviewBriefing from raw pipeline data.

    This is the main orchestrator that calls all computation functions.
    """
    current_round: int = search_state.round
    primary_metric: str = search_state.primary_metric_name or "accuracy"
    pareto_front = search_state.pareto_front
    front_versions = [c.prompt_version for c in pareto_front]

    # Mutation descriptions for current candidates
    mutation_descriptions: dict[str, str] = {}
    for version in candidate_versions:
        matching = [m for m in mutation_log if m.child_version == version]
        mutation_descriptions[version] = (
            matching[-1].description if matching else "No mutation record"
        )

    # 1. Candidate comparisons
    candidates = build_candidate_comparisons(
        score_reports=score_reports,
        mutation_descriptions=mutation_descriptions,
        parent_versions=parent_versions,
        front_versions=front_versions,
        primary_metric=primary_metric,
    )

    # 2. Per-class recall
    per_class_recall = extract_per_class_recall(
        current_reports=score_reports,
        historical_reports=historical_reports,
        current_round=current_round,
    )

    # 3. Diversity metrics (front prompts only)
    front_prompt_texts = {v: prompt_texts[v] for v in front_versions if v in prompt_texts}
    diversity_metrics = compute_diversity_metrics(
        prompt_texts=front_prompt_texts,
        mutation_log=mutation_log,
    )

    # 4. Diminishing returns
    score_trajectory = _build_score_trajectory(
        historical_reports, score_reports, current_round, primary_metric,
    )
    diminishing_returns = compute_diminishing_returns(
        score_trajectory=score_trajectory,
    )

    # 5. Mutation correlation
    score_history = _build_score_history(
        historical_reports, score_reports, primary_metric,
    )
    mutation_history = correlate_mutations(
        mutation_log=mutation_log,
        score_history=score_history,
    )

    # 6. Oracle metrics — use the best current candidate's report
    best_candidate = max(
        candidate_versions,
        key=lambda v: _extract_metric(score_reports.get(v, {}), primary_metric),
    )
    oracle_metrics = compute_oracle_metrics_from_report(
        metrics=score_reports[best_candidate].get("metrics", {}),
    )

    return ReviewBriefing(
        round=current_round,
        candidates=candidates,
        pareto_front=pareto_front,
        per_class_recall=per_class_recall,
        diversity_metrics=diversity_metrics,
        diminishing_returns=diminishing_returns,
        mutation_history=mutation_history,
        oracle_metrics=oracle_metrics,
        prompt_versions=prompt_texts,
        holdout_examples=holdout_examples,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_review_preprocessor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review_preprocessor.py tests/test_review_preprocessor.py
git commit -m "feat(review): add build_review_briefing orchestrator"
```

---

## Chunk 4: System Prompt & MCP Integration

### Task 15: Review Agent System Prompt

**Files:**
- Create: `odysseus/agents/prompts/review_agent_system.md`

- [ ] **Step 1: Write the system prompt**

Create `odysseus/agents/prompts/review_agent_system.md` following the format in existing prompts (e.g., `prompt_builder_system.md`, `eval_runner_system.md`). The prompt should contain:

1. **Role introduction** — You are the Review Agent, a prompt-program critic
2. **Input contract table** — ReviewBriefing fields with Type, Source, Description columns
3. **Output contract** — ReviewResult JSON schema with field-level instructions. Instruct the LLM to emit valid JSON matching the schema.
4. **Evaluation priorities** (ordered):
   - Exploration vs exploitation balance (use diversity_metrics, diminishing_returns, oracle gap)
   - Oracle gap analysis (candidate_cost_captured, candidate_quality_captured ratios)
   - Per-candidate assessment (edit directives targeting specific blocks, regression flags)
   - Regression guards (block promotion only, not exploration)
5. **Edit directive guidelines** — Reference blocks by Markdown section name and numbered sub-items. Classify as macro/micro. Include priority.
6. **Promotion decision rules** — promote (no regressions), refine (tolerate regression if structurally novel), prune (dominated + no novelty)
7. **Loop signal rules** — When to exit vs refine, budget granting, mutation mode suggestion
8. **Anti-patterns** — The five anti-patterns from the spec
9. **Worked examples** — 2-3 ReviewBriefing → ReviewResult examples showing different scenarios (exit, refine with macro edit, regression guard blocking promotion)

Refer to the spec at `docs/superpowers/specs/2026-03-25-review-agent-design.md` for all details.

- [ ] **Step 2: Commit**

```bash
git add odysseus/agents/prompts/review_agent_system.md
git commit -m "feat(review): add review agent system prompt"
```

### Task 16: MCP Tool — build_review_briefing_tool

**Files:**
- Modify: `odysseus/mcp.py`
- Modify: `tests/test_mcp.py`

- [ ] **Step 1: Write failing test for tool registration**

Check the pattern in `tests/test_mcp.py` for how existing tools are tested. Add a test that verifies `build_review_briefing_tool` is registered:

```python
# Append to tests/test_mcp.py (following existing test patterns)

def test_build_review_briefing_tool_registered() -> None:
    """Verify build_review_briefing_tool is a registered MCP tool."""
    from odysseus.mcp import mcp
    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    assert "build_review_briefing_tool" in tool_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mcp.py::test_build_review_briefing_tool_registered -v`
Expected: FAIL — `AssertionError`

- [ ] **Step 3: Add tool to mcp.py**

Add to `odysseus/mcp.py`, following the pattern of existing search tools (e.g., `advance_round_tool` at line 379):

```python
from odysseus.agents.review_preprocessor import build_review_briefing
from odysseus.agents.review_ops import (
    load_directive_history,
    load_mutation_log,
    load_round_reports,
    save_round_report,
)


@mcp.tool()
async def build_review_briefing_tool(
    search_state_id: str,
    candidate_versions: list[str],
    parent_versions: dict[str, str | None],
    report_paths: dict[str, str],
    holdout_card_set_path: str = "",
    output_dir: str = "outputs",
) -> str:
    """Build a ReviewBriefing for the Review Agent by pre-processing all numerical data.

    Loads search state, score reports, prompt texts, mutation log, and directive
    history, then computes candidate comparisons, per-class recall, diversity
    metrics, diminishing returns, mutation correlation, and oracle metrics.

    Args:
        search_state_id: The search state to review.
        candidate_versions: Versions evaluated in the current round.
        parent_versions: Mapping of candidate → parent version.
        report_paths: Mapping of version → path to its ScoreReport JSON.
        holdout_card_set_path: Path to holdout rationale card set JSON (optional).
        output_dir: Output directory (default "outputs").

    Returns:
        JSON-serialized ReviewBriefing.
    """
    from pathlib import Path

    from odysseus.agents.prompt_builder_search_ops import get_search_state
    from odysseus.agents.review_models import ExampleSummary
    from odysseus.eval.models import ScoreReport
    from odysseus.prompts.manager import FilePromptManager

    out = Path(output_dir)

    # Load search state
    state = get_search_state(search_state_id, output_dir=out)

    # Load score reports for current candidates + front
    all_versions = set(candidate_versions)
    for c in state.pareto_front:
        all_versions.add(c.prompt_version)

    # Load historical round reports
    historical = load_round_reports(search_state_id, output_dir=out)

    # Load current round reports via ScoreReport.report_path convention
    # The orchestrator must pass report_paths for each candidate evaluated this round
    score_reports: dict[str, dict[str, Any]] = {}
    for version in all_versions:
        # Check current round reports first (passed via report_paths param)
        if version in report_paths:
            rp = Path(report_paths[version])
            if rp.exists():
                score_reports[version] = json.loads(rp.read_text(encoding="utf-8"))
        # Fall back to historical reports for front members
        elif version not in score_reports:
            for round_data in historical.values():
                if version in round_data:
                    score_reports[version] = round_data[version]
                    break

    # Load prompt texts
    prompt_mgr = FilePromptManager("prompts/")
    prompt_texts: dict[str, str] = {}
    for version in all_versions:
        try:
            prompt_texts[version] = prompt_mgr.load(version)
        except FileNotFoundError:
            pass

    # Load mutation log and directive history
    mutation_log = load_mutation_log(search_state_id, output_dir=out)
    directive_history = load_directive_history(search_state_id, output_dir=out)

    # Load holdout examples from rationale card set if path provided
    holdout_examples: list[ExampleSummary] = []
    if holdout_card_set_path:
        card_set_data = json.loads(Path(holdout_card_set_path).read_text(encoding="utf-8"))
        for card_id, card in card_set_data.get("cards", {}).items():
            holdout_examples.append(
                ExampleSummary(
                    example_id=card_id,
                    route=card.get("assigned_route", ""),
                    ambiguity_tags=card.get("ambiguity_tags", []),
                )
            )

    # Build briefing
    briefing = build_review_briefing(
        search_state=state,
        score_reports=score_reports,
        historical_reports=historical,
        prompt_texts=prompt_texts,
        mutation_log=mutation_log,
        directive_history=directive_history,
        holdout_examples=holdout_examples,
        candidate_versions=candidate_versions,
        parent_versions=parent_versions,
    )

    # Save current round's reports for future historical access
    current_round_reports = {v: score_reports[v] for v in candidate_versions if v in score_reports}
    save_round_report(search_state_id, state.round, current_round_reports, output_dir=out)

    return briefing.model_dump_json(indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mcp.py::test_build_review_briefing_tool_registered -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/mcp.py tests/test_mcp.py
git commit -m "feat(review): add build_review_briefing_tool to MCP"
```

### Task 17: MCP Tool — record_directive_outcomes_tool

**Files:**
- Modify: `odysseus/mcp.py`
- Modify: `tests/test_mcp.py`

- [ ] **Step 1: Write failing test**

```python
# Append to tests/test_mcp.py

def test_record_directive_outcomes_tool_registered() -> None:
    from odysseus.mcp import mcp
    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    assert "record_directive_outcomes_tool" in tool_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mcp.py::test_record_directive_outcomes_tool_registered -v`
Expected: FAIL

- [ ] **Step 3: Add tool to mcp.py**

```python
from odysseus.agents.review_models import DirectiveOutcome
from odysseus.agents.review_ops import load_directive_history, save_directive_history


@mcp.tool()
async def record_directive_outcomes_tool(
    search_state_id: str,
    outcomes: list[dict[str, Any]],
    output_dir: str = "outputs",
) -> str:
    """Record the outcomes of prior Review Agent directives.

    Called by the orchestrator after the Prompt Builder has acted on directives
    and the resulting candidates have been evaluated.

    Args:
        search_state_id: The search state this belongs to.
        outcomes: List of directive outcome dicts matching DirectiveOutcome schema.
        output_dir: Output directory (default "outputs").

    Returns:
        Confirmation with count of outcomes recorded.
    """
    from pathlib import Path

    out = Path(output_dir)
    parsed = [DirectiveOutcome.model_validate(o) for o in outcomes]

    existing = load_directive_history(search_state_id, output_dir=out)
    save_directive_history(search_state_id, existing + parsed, output_dir=out)

    return json.dumps({"recorded": len(parsed), "total": len(existing) + len(parsed)})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mcp.py::test_record_directive_outcomes_tool_registered -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/mcp.py tests/test_mcp.py
git commit -m "feat(review): add record_directive_outcomes_tool to MCP"
```

### Task 18: MCP Prompt & Resource Registration

**Files:**
- Modify: `odysseus/mcp.py`
- Modify: `tests/test_mcp.py`

- [ ] **Step 1: Write failing tests for prompt and resource**

```python
# Append to tests/test_mcp.py

def test_review_agent_prompt_registered() -> None:
    from odysseus.mcp import mcp
    prompt_names = [p.name for p in mcp._prompt_manager.list_prompts()]
    assert "odysseus_review_agent" in prompt_names


def test_review_agent_guidelines_resource_registered() -> None:
    from odysseus.mcp import mcp
    resource_uris = [str(r.uri) for r in mcp._resource_manager.list_resources()]
    assert "odysseus://agents/review-agent/guidelines" in resource_uris
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mcp.py -v -k "review_agent_prompt or review_agent_guidelines"`
Expected: FAIL

- [ ] **Step 3: Add prompt and resource to mcp.py**

Following the existing patterns at lines 69-98 (prompts) and 101-140 (resources):

```python
@mcp.prompt()
async def odysseus_review_agent() -> list[Message]:
    """System prompt for the Review Agent — supervises the prompt optimization search loop."""
    return [UserMessage(content=_load_text("odysseus/agents/prompts/review_agent_system.md"))]


@mcp.resource("odysseus://agents/review-agent/guidelines")
async def review_agent_guidelines() -> str:
    """Review criteria and evaluation priority reference for the Review Agent."""
    return _load_text("odysseus/agents/prompts/review_agent_system.md")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mcp.py -v -k "review_agent"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/mcp.py tests/test_mcp.py
git commit -m "feat(review): add MCP prompt and resource for review agent"
```

---

## Chunk 5: Package Exports & Documentation

### Task 19: Update Package Exports

**Files:**
- Modify: `odysseus/agents/__init__.py`

- [ ] **Step 1: Add review models and functions to exports**

Add to the imports and `__all__` in `odysseus/agents/__init__.py`:

```python
from odysseus.agents.review_models import (
    CandidateAnalysis,
    ClassRecallEntry,
    DirectiveOutcome,
    DiversityMetrics,
    EditDirective,
    ExampleSummary,
    LoopSignal,
    MetricDeltas,
    MutationHistory,
    MutationRecord,
    OracleMetrics,
    PromotionDecision,
    RankedCandidate,
    RegressionFlag,
    ReviewBriefing,
    ReviewResult,
)
```

Add these names to `__all__`.

- [ ] **Step 2: Run full test suite to verify nothing is broken**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/__init__.py
git commit -m "feat(review): export review models from agents package"
```

### Task 20: Update Architecture Documentation

**Files:**
- Modify: `docs/architecture.md`

- [ ] **Step 1: Update the architecture doc**

Add the Review Agent to:
1. The agent table — type: Hybrid (code + LLM), status: Done, module: `review_preprocessor.py` + `review_agent_system.md`
2. The Zone 4 pipeline diagram — show Review Agent between `advance_round` and Prompt Builder
3. The context keys table — add `review_briefing` and `review_result` keys
4. The MCP surface tables — add the new tools, prompt, and resource

Follow the existing formatting conventions (tables, backticks for code references, concise descriptions).

- [ ] **Step 2: Run linting to verify formatting**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: add review agent to architecture documentation"
```

### Task 21: Add Integration Test Scenarios

**Files:**
- Create: `tests/scenarios/51_review_agent_basic_review.md`
- Create: `tests/scenarios/52_review_agent_regression_guard.md`
- Create: `tests/scenarios/53_review_agent_loop_exit.md`
- Modify: `tests/scenarios/README.md`

- [ ] **Step 1: Create scenario files**

Following the existing scenario format (see `tests/scenarios/README.md`), create three scenarios:

**51 — Basic Review:** After a round with 2 candidates, call `build_review_briefing_tool`, invoke review agent prompt, verify ReviewResult has candidate ranking, edit directives, and a loop signal.

**52 — Regression Guard:** Set up a candidate that improves accuracy but drops rare-class recall. Verify the review agent flags it with a `severity="block"` regression guard and sets `decision="refine"` (not "promote").

**53 — Loop Exit:** Set up a scenario where oracle captured ratios are high (>0.9) and diversity is collapsing. Verify the review agent signals `action="exit"` with `reason="dominance_threshold_met"`.

Each file has four sections: `## Setup`, `## Scenario Description`, `## User Simulator`, `## Verification Criteria`.

- [ ] **Step 2: Update the scenario index in README**

Add the three new scenarios to the table in `tests/scenarios/README.md`.

- [ ] **Step 3: Commit**

```bash
git add tests/scenarios/51_review_agent_basic_review.md tests/scenarios/52_review_agent_regression_guard.md tests/scenarios/53_review_agent_loop_exit.md tests/scenarios/README.md
git commit -m "test(review): add integration test scenarios for review agent"
```
