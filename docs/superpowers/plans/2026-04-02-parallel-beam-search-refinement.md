# Parallel Beam Search Refinement — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign Stage 4 refinement loop from single-candidate sequential hill-climbing to multi-parent beam search with concurrent evaluation and adaptive beam width.

**Architecture:** Each round, the Review Agent emits K directive batches (one per Pareto front parent to branch from). The Prompt Builder generates K candidates and evaluates them concurrently via `run_batch_eval`. Results flow back to the Review Agent via `BatchOutcome` for the next round. Beam width adapts based on mutation mode and stagnation.

**Tech Stack:** Python 3.11+, Pydantic v2, asyncio, FastMCP

**Spec:** `docs/superpowers/specs/2026-04-02-parallel-beam-search-refinement-design.md`

---

## File Structure

### Modified Files
| File | Responsibility |
|---|---|
| `odysseus/agents/prompt_builder/search.py` | `SearchState` + `Candidate` model extensions |
| `odysseus/agents/prompt_builder/search_ops.py` | `advance_round` beam width + eval_status filtering, `register_candidate` new params |
| `odysseus/agents/review/models.py` | `DirectiveBatch`, `BatchOutcome` new models; `ReviewResult`, `ReviewBriefing`, `LoopSignal` field changes |
| `odysseus/agents/review/ops.py` | Rename `save/load_edit_directives` → `save/load_directive_batches` |
| `odysseus/agents/review/preprocessor.py` | `build_review_briefing` adds `beam_width` + `batch_outcomes` |
| `odysseus/agents/pipeline/status.py` | `_detect_stage_4_phase` + `build_recovering` phase, `_BUILD_TOOLS` update |
| `odysseus/agents/pipeline/instructions.py` | New `STAGE_4_BUILD_RECOVERING_INSTRUCTION`, update `STAGE_4_BUILD_INSTRUCTION` |
| `odysseus/mcp/server.py` | `STAGE_REGISTRY["prompt_building"]` add `run_batch_eval` |
| `odysseus/mcp/review_tools.py` | `record_directive_outcomes` + `get_edit_directives` → directive batches |
| `odysseus/mcp/prompt_building_tools.py` | New `run_batch_eval` tool, update `register_candidate` |
| `odysseus/eval/protocols.py` | `RunDependencies` optional shared rate limiter |
| `odysseus/eval/controller.py` | Accept shared rate limiter from `RunDependencies` |
| `odysseus/agents/prompts/review_agent_system.md` | Directive batch schema, multi-parent branching, diversity rule |
| `odysseus/agents/prompts/prompt_builder_system.md` | `run_batch_eval` usage, directive batch consumption |

### New Files
| File | Responsibility |
|---|---|
| `odysseus/mcp/batch_eval.py` | `run_batch_eval` implementation (registration, concurrent eval, result collection) |
| `tests/test_batch_eval.py` | Tests for batch eval logic |

### Test Files (modified)
| File | Responsibility |
|---|---|
| `tests/test_prompt_builder_search.py` | Tests for new `SearchState`/`Candidate` fields |
| `tests/test_prompt_builder_search_ops.py` | Tests for `advance_round` beam width + eval_status filtering |
| `tests/test_review_models.py` | Tests for `DirectiveBatch`, `BatchOutcome`, updated `ReviewResult` |
| `tests/test_review_preprocessor.py` | Tests for `batch_outcomes` construction in briefing |
| `tests/test_review_ops.py` | Tests for renamed directive batch persistence |
| `tests/test_pipeline_status.py` | Tests for `build_recovering` phase detection |

---

## Task 1: Extend `SearchState` and `Candidate` models

**Files:**
- Modify: `odysseus/agents/prompt_builder/search.py`
- Test: `tests/test_prompt_builder_search.py`

Steps:

- [ ] **Step 1: Write failing tests for new `Candidate` fields**

```python
# In tests/test_prompt_builder_search.py, add to TestCandidate class:

def test_candidate_default_eval_status(self):
    """New candidates default to 'registered' eval_status."""
    c = Candidate(
        prompt_version="v1",
        parent_version=None,
        quality_score=0.0,
        cost=0.0,
        round_introduced=1,
    )
    assert c.eval_status == "registered"
    assert c.mutation_strategy is None
    assert c.source_directive_batch_id is None


def test_candidate_eval_status_values(self):
    """eval_status accepts all valid lifecycle states."""
    for status in ("registered", "evaluating", "scored", "failed"):
        c = Candidate(
            prompt_version="v1",
            parent_version=None,
            quality_score=0.0,
            cost=0.0,
            round_introduced=1,
            eval_status=status,
        )
        assert c.eval_status == status


def test_candidate_mutation_strategy_values(self):
    """mutation_strategy accepts targeted, exploratory, structural."""
    for strategy in ("targeted", "exploratory", "structural"):
        c = Candidate(
            prompt_version="v1",
            parent_version=None,
            quality_score=0.0,
            cost=0.0,
            round_introduced=1,
            mutation_strategy=strategy,
            source_directive_batch_id="batch_1",
        )
        assert c.mutation_strategy == strategy
        assert c.source_directive_batch_id == "batch_1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_builder_search.py::TestCandidate::test_candidate_default_eval_status tests/test_prompt_builder_search.py::TestCandidate::test_candidate_eval_status_values tests/test_prompt_builder_search.py::TestCandidate::test_candidate_mutation_strategy_values -v`
Expected: FAIL — fields don't exist yet

- [ ] **Step 3: Write failing tests for new `SearchState` fields**

```python
# In tests/test_prompt_builder_search.py, add to TestSearchState class:

def test_search_state_beam_width_defaults(self):
    """SearchState has beam width fields with correct defaults."""
    state = SearchState(
        search_state_id="test",
        backend="anthropic",
    )
    assert state.beam_width == 2
    assert state.min_beam_width == 2
    assert state.max_beam_width == 5
    assert state.active_evals == []


def test_search_state_active_evals(self):
    """active_evals tracks in-flight eval versions."""
    state = SearchState(
        search_state_id="test",
        backend="anthropic",
        active_evals=["v2", "v3"],
    )
    assert state.active_evals == ["v2", "v3"]


def test_search_state_beam_width_custom(self):
    """Beam width fields can be set to custom values."""
    state = SearchState(
        search_state_id="test",
        backend="anthropic",
        beam_width=4,
        min_beam_width=1,
        max_beam_width=8,
    )
    assert state.beam_width == 4
    assert state.min_beam_width == 1
    assert state.max_beam_width == 8
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_builder_search.py::TestSearchState::test_search_state_beam_width_defaults tests/test_prompt_builder_search.py::TestSearchState::test_search_state_active_evals tests/test_prompt_builder_search.py::TestSearchState::test_search_state_beam_width_custom -v`
Expected: FAIL — fields don't exist yet

- [ ] **Step 5: Implement `Candidate` model extensions**

In `odysseus/agents/prompt_builder/search.py`, add three fields to `Candidate` (after line 30, before the validator):

```python
class Candidate(BaseModel):
    """A single prompt candidate with quality and cost metrics."""

    prompt_version: str
    parent_version: str | None
    quality_score: float
    cost: float
    round_introduced: int
    dominated: bool = False
    example_ids: list[str] = Field(default_factory=list)
    eval_status: Literal["registered", "evaluating", "scored", "failed"] = "registered"
    mutation_strategy: Literal["targeted", "exploratory", "structural"] | None = None
    source_directive_batch_id: str | None = None
```

Add `Literal` to the existing `from typing import Literal` import (it's already imported for SearchState).

- [ ] **Step 6: Implement `SearchState` extensions**

In `odysseus/agents/prompt_builder/search.py`, add four fields to `SearchState` (after line 71, before the validators):

```python
class SearchState(BaseModel):
    # ... existing fields through total_routing_cost ...
    beam_width: int = 2
    min_beam_width: int = 2
    max_beam_width: int = 5
    active_evals: list[str] = Field(default_factory=list)
```

- [ ] **Step 7: Run all model tests to verify they pass**

Run: `uv run pytest tests/test_prompt_builder_search.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add odysseus/agents/prompt_builder/search.py tests/test_prompt_builder_search.py
git commit -m "feat: extend SearchState and Candidate models for beam search"
```

---

## Task 2: Add `DirectiveBatch`, `BatchOutcome` models and update `ReviewResult`, `ReviewBriefing`, `LoopSignal`

**Files:**
- Modify: `odysseus/agents/review/models.py`
- Modify: `tests/test_review_models.py`

Steps:

- [ ] **Step 1: Write failing tests for `DirectiveBatch`**

```python
# tests/test_review_models.py

import pytest
from odysseus.agents.review.models import (
    BatchOutcome,
    DirectiveBatch,
    EditDirective,
    ExampleContent,
    LoopSignal,
    ReviewResult,
    RankedCandidate,
    PromotionDecision,
    DirectiveOutcome,
    RegressionFlag,
    ReviewBriefing,
)


class TestDirectiveBatch:
    def test_directive_batch_construction(self):
        directive = EditDirective(
            directive_id="d1",
            target_version="v3",
            block_type="rule",
            block_identifier="Rule 2",
            granularity="micro",
            directive="Tighten constraint",
            priority="high",
        )
        batch = DirectiveBatch(
            directive_batch_id="b1",
            parent_version="v3",
            directives=[directive],
            mutation_strategy="targeted",
            priority=1,
        )
        assert batch.directive_batch_id == "b1"
        assert batch.parent_version == "v3"
        assert batch.mutation_strategy == "targeted"
        assert batch.priority == 1
        assert len(batch.directives) == 1

    def test_directive_batch_rejects_extra_fields(self):
        with pytest.raises(Exception):
            DirectiveBatch(
                directive_batch_id="b1",
                parent_version="v3",
                directives=[],
                mutation_strategy="targeted",
                priority=1,
                extra_field="bad",
            )

    def test_directive_batch_mutation_strategies(self):
        for strategy in ("targeted", "exploratory", "structural"):
            batch = DirectiveBatch(
                directive_batch_id="b1",
                parent_version="v3",
                directives=[],
                mutation_strategy=strategy,
                priority=1,
            )
            assert batch.mutation_strategy == strategy
```

- [ ] **Step 2: Write failing tests for `BatchOutcome`**

```python
# Append to tests/test_review_models.py

class TestBatchOutcome:
    def test_batch_outcome_scored(self):
        outcome = BatchOutcome(
            directive_batch_id="b1",
            parent_version="v3",
            mutation_strategy="targeted",
            candidate_version="v6",
            eval_status="scored",
            quality_delta_vs_parent=0.05,
            made_pareto_front=True,
        )
        assert outcome.made_pareto_front is True
        assert outcome.quality_delta_vs_parent == 0.05

    def test_batch_outcome_failed(self):
        outcome = BatchOutcome(
            directive_batch_id="b2",
            parent_version="v3",
            mutation_strategy="exploratory",
            candidate_version="v7",
            eval_status="failed",
            quality_delta_vs_parent=None,
            made_pareto_front=False,
        )
        assert outcome.eval_status == "failed"
        assert outcome.quality_delta_vs_parent is None

    def test_batch_outcome_generation_failed(self):
        outcome = BatchOutcome(
            directive_batch_id="b3",
            parent_version="v3",
            mutation_strategy="structural",
            candidate_version=None,
            eval_status=None,
            quality_delta_vs_parent=None,
            made_pareto_front=False,
        )
        assert outcome.candidate_version is None
```

- [ ] **Step 3: Write failing tests for updated `ReviewResult`, `LoopSignal`, `ReviewBriefing`**

```python
# Append to tests/test_review_models.py

class TestReviewResultDirectiveBatches:
    def test_review_result_uses_directive_batches(self):
        batch = DirectiveBatch(
            directive_batch_id="b1",
            parent_version="v3",
            directives=[],
            mutation_strategy="targeted",
            priority=1,
        )
        result = ReviewResult(
            candidate_ranking=[RankedCandidate(version="v3", rank=1, rationale="best")],
            directive_batches=[batch],
            promotion_decisions=[PromotionDecision(version="v3", decision="refine", reason="improving")],
            loop_signal=LoopSignal(action="refine", reason="headroom"),
            regression_guards=[],
            directive_history_update=[],
        )
        assert len(result.directive_batches) == 1
        assert result.directive_batches[0].directive_batch_id == "b1"


class TestLoopSignalBeamWidth:
    def test_loop_signal_suggested_beam_width(self):
        signal = LoopSignal(
            action="refine",
            reason="explore more",
            suggested_beam_width=4,
        )
        assert signal.suggested_beam_width == 4

    def test_loop_signal_suggested_beam_width_default_none(self):
        signal = LoopSignal(action="refine", reason="continue")
        assert signal.suggested_beam_width is None


class TestReviewBriefingBeamWidth:
    def test_review_briefing_beam_width_default(self):
        """beam_width defaults to 2 for cold-start compatibility."""
        # This test needs a minimal valid ReviewBriefing — we'll just check the field exists
        # by importing and checking the model schema
        field_info = ReviewBriefing.model_fields["beam_width"]
        assert field_info.default == 2

    def test_review_briefing_batch_outcomes_default(self):
        field_info = ReviewBriefing.model_fields["batch_outcomes"]
        assert field_info.default_factory is not None  # default_factory=list
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_models.py -v`
Expected: FAIL — models don't exist or have wrong fields

- [ ] **Step 5: Implement `DirectiveBatch` model**

In `odysseus/agents/review/models.py`, add after `EditDirective` class (after line 223):

```python
class DirectiveBatch(BaseModel):
    """A group of edit directives targeting a single Pareto front parent."""

    model_config = ConfigDict(extra="forbid")

    directive_batch_id: str
    parent_version: str
    directives: list[EditDirective]
    mutation_strategy: Literal["targeted", "exploratory", "structural"]
    priority: int
```

- [ ] **Step 6: Implement `BatchOutcome` model**

In `odysseus/agents/review/models.py`, add after `DirectiveOutcome` class (after line 268):

```python
class BatchOutcome(BaseModel):
    """Links a directive batch to the candidate it produced and its eval result."""

    model_config = ConfigDict(extra="forbid")

    directive_batch_id: str
    parent_version: str
    mutation_strategy: Literal["targeted", "exploratory", "structural"]
    candidate_version: str | None
    eval_status: Literal["scored", "failed"] | None
    quality_delta_vs_parent: float | None
    made_pareto_front: bool
```

- [ ] **Step 7: Update `ReviewResult` — replace `edit_directives` with `directive_batches`**

In `odysseus/agents/review/models.py`, change line 277:
```python
# Before
edit_directives: list[EditDirective]

# After
directive_batches: list[DirectiveBatch]
```

- [ ] **Step 8: Update `LoopSignal` — add `suggested_beam_width`**

In `odysseus/agents/review/models.py`, add after line 246:
```python
    suggested_beam_width: int | None = Field(
        default=None,
        description="Override the adaptive beam width for the next round. Clamped to [min_beam_width, max_beam_width] by advance_round.",
    )
```

- [ ] **Step 9: Update `ReviewBriefing` — add `beam_width` and `batch_outcomes`**

In `odysseus/agents/review/models.py`, add to `ReviewBriefing` (after line 192):
```python
    beam_width: int = 2
    batch_outcomes: list[BatchOutcome] = Field(default_factory=list)
```

Make sure `BatchOutcome` is defined BEFORE `ReviewBriefing` in the file (it references it).

- [ ] **Step 10: Run all tests to verify they pass**

Run: `uv run pytest tests/test_review_models.py -v`
Expected: ALL PASS

- [ ] **Step 11: Run existing tests to check for regressions**

Run: `uv run pytest tests/test_review_preprocessor.py tests/test_prompt_builder_search_ops.py -v`
Expected: May have failures if existing code references `edit_directives` on `ReviewResult` — note these for Task 3

- [ ] **Step 12: Commit**

```bash
git add odysseus/agents/review/models.py tests/test_review_models.py
git commit -m "feat: add DirectiveBatch, BatchOutcome models and update ReviewResult/LoopSignal/ReviewBriefing"
```

---

## Task 3: Rename directive persistence functions in `ops.py` and update `review_tools.py`

**Files:**
- Modify: `odysseus/agents/review/ops.py`
- Modify: `odysseus/mcp/review_tools.py`
- Modify: `tests/test_review_ops.py`

Steps:

- [ ] **Step 1: Write failing tests for renamed persistence functions**

```python
# tests/test_review_ops.py
import json
from pathlib import Path

import pytest

from odysseus.agents.review.models import DirectiveBatch, EditDirective
from odysseus.agents.review.ops import load_directive_batches, save_directive_batches


@pytest.fixture()
def tmp_output(tmp_path: Path) -> Path:
    return tmp_path


class TestDirectiveBatchPersistence:
    def test_save_and_load_directive_batches(self, tmp_output: Path):
        directive = EditDirective(
            directive_id="d1",
            target_version="v3",
            block_type="rule",
            block_identifier="Rule 2",
            granularity="micro",
            directive="Tighten constraint",
            priority="high",
        )
        batch = DirectiveBatch(
            directive_batch_id="b1",
            parent_version="v3",
            directives=[directive],
            mutation_strategy="targeted",
            priority=1,
        )
        run_id = "test_run"
        save_directive_batches(run_id, [batch], output_dir=tmp_output)
        loaded = load_directive_batches(run_id, output_dir=tmp_output)
        assert len(loaded) == 1
        assert loaded[0].directive_batch_id == "b1"
        assert loaded[0].directives[0].directive_id == "d1"

    def test_load_directive_batches_missing_file(self, tmp_output: Path):
        loaded = load_directive_batches("nonexistent", output_dir=tmp_output)
        assert loaded == []

    def test_save_directive_batches_creates_directory(self, tmp_output: Path):
        batch = DirectiveBatch(
            directive_batch_id="b1",
            parent_version="v3",
            directives=[],
            mutation_strategy="exploratory",
            priority=1,
        )
        save_directive_batches("new_run", [batch], output_dir=tmp_output)
        path = tmp_output / "new_run" / "search" / "edit_directives.json"
        assert path.is_file()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_review_ops.py -v`
Expected: FAIL — functions don't exist

- [ ] **Step 3: Implement renamed functions in `ops.py`**

In `odysseus/agents/review/ops.py`:
1. Rename `save_edit_directives` → `save_directive_batches`, change parameter type from `list[EditDirective]` to `list[DirectiveBatch]`
2. Rename `load_edit_directives` → `load_directive_batches`, change return type from `list[EditDirective]` to `list[DirectiveBatch]`
3. Update import: add `DirectiveBatch` to imports from `odysseus.agents.review.models`
4. Keep the file path unchanged (`edit_directives.json`) for on-disk compatibility

```python
def save_directive_batches(
    run_id: str,
    batches: list[DirectiveBatch],
    *,
    output_dir: Path | None = None,
) -> None:
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _edit_directives_path(run_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [b.model_dump(mode="json") for b in batches]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_directive_batches(
    run_id: str,
    *,
    output_dir: Path | None = None,
) -> list[DirectiveBatch]:
    if output_dir is None:
        output_dir = _default_output_dir()
    path = _edit_directives_path(run_id, output_dir)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [DirectiveBatch.model_validate(item) for item in data]
```

- [ ] **Step 4: Run ops tests to verify they pass**

Run: `uv run pytest tests/test_review_ops.py -v`
Expected: ALL PASS

- [ ] **Step 5: Update `review_tools.py` — `record_directive_outcomes`**

In `odysseus/mcp/review_tools.py`:
1. Change `edit_directives` parameter name to `directive_batches` in `record_directive_outcomes`
2. Change the import from `save_edit_directives` to `save_directive_batches`
3. Update the validation and persistence call to use `DirectiveBatch` instead of `EditDirective`

- [ ] **Step 6: Update `review_tools.py` — `get_edit_directives`**

In `odysseus/mcp/review_tools.py`:
1. Change import from `load_edit_directives` to `load_directive_batches`
2. Update return to serialize `DirectiveBatch` objects

- [ ] **Step 7: Update existing tests in `tests/test_review_ops.py`**

Any existing tests that import or call `save_edit_directives`/`load_edit_directives` must be updated to use the new function names `save_directive_batches`/`load_directive_batches` and construct `DirectiveBatch` objects instead of `EditDirective` objects directly.

- [ ] **Step 8: Run all review tool tests + existing tests**

Run: `uv run pytest tests/ -k "review" -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add odysseus/agents/review/ops.py odysseus/mcp/review_tools.py tests/test_review_ops.py
git commit -m "feat: rename directive persistence to support DirectiveBatch format"
```

---

## Task 4: Update `register_candidate` to accept new fields

**Files:**
- Modify: `odysseus/agents/prompt_builder/search_ops.py`
- Modify: `odysseus/mcp/prompt_building_tools.py`
- Test: `tests/test_prompt_builder_search_ops.py`

Steps:

- [ ] **Step 1: Write failing test for `register_candidate` new fields**

```python
# In tests/test_prompt_builder_search_ops.py, add to existing test class or as new class:

class TestRegisterCandidateNewFields:
    def test_register_candidate_with_new_fields(self, tmp_output: Path, run_id: str):
        """New fields are persisted in pending_candidates.json."""
        init_search_state(backend="anthropic", run_id=run_id, output_dir=tmp_output)
        register_candidate(
            run_id=run_id,
            prompt_version="v2",
            parent_version="v1",
            example_ids=["e1", "e2"],
            eval_status="evaluating",
            mutation_strategy="exploratory",
            source_directive_batch_id="batch_1",
            output_dir=tmp_output,
        )
        pending_path = tmp_output / run_id / "search" / "pending_candidates.json"
        data = json.loads(pending_path.read_text())
        assert len(data) == 1
        c = data[0]
        assert c["eval_status"] == "evaluating"
        assert c["mutation_strategy"] == "exploratory"
        assert c["source_directive_batch_id"] == "batch_1"

    def test_register_candidate_new_fields_default_to_none_or_registered(
        self, tmp_output: Path, run_id: str
    ):
        """Omitting new fields leaves defaults in place."""
        init_search_state(backend="anthropic", run_id=run_id, output_dir=tmp_output)
        register_candidate(
            run_id=run_id,
            prompt_version="v2",
            output_dir=tmp_output,
        )
        pending_path = tmp_output / run_id / "search" / "pending_candidates.json"
        data = json.loads(pending_path.read_text())
        c = data[0]
        assert c["eval_status"] == "registered"
        assert c["mutation_strategy"] is None
        assert c["source_directive_batch_id"] is None
```

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_prompt_builder_search_ops.py::TestRegisterCandidateNewFields -v`
Expected: FAIL — `register_candidate` does not accept `eval_status`, `mutation_strategy`, `source_directive_batch_id`

- [ ] **Step 3: Implement — update `register_candidate` in `search_ops.py`**

In `odysseus/agents/prompt_builder/search_ops.py`, update the `register_candidate` function signature and `Candidate` construction (currently lines 175–233). Add three parameters and pass them to the `Candidate` constructor:

```python
def register_candidate(
    run_id: str,
    prompt_version: str,
    parent_version: str | None = None,
    example_ids: list[str] | None = None,
    eval_status: Literal["registered", "evaluating", "scored", "failed"] = "registered",
    mutation_strategy: Literal["targeted", "exploratory", "structural"] | None = None,
    source_directive_batch_id: str | None = None,
    output_dir: Path | None = None,
) -> SearchState:
    """Register a new candidate for the current round.

    The candidate is appended to the pending list on disk.  No quality score
    or cost is recorded yet — those are filled in by :func:`record_eval_result`.

    Args:
        run_id: Run identifier used to locate the state on disk.
        prompt_version: Unique version identifier for the prompt.
        parent_version: Parent prompt version, if any.
        example_ids: Holdout example IDs used as few-shots in this prompt version.
        eval_status: Initial lifecycle status for the candidate.
        mutation_strategy: Strategy inherited from the source directive batch.
        source_directive_batch_id: Traceability link to the originating batch.
        output_dir: Root directory for persisted state files.

    Returns:
        The current (unchanged) :class:`SearchState`.

    Raises:
        FileNotFoundError: If the search state does not exist.
        ValueError: If *prompt_version* already exists on the front, in
            history, or in the pending list.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    state = _load_state(run_id, output_dir)
    pending = _load_pending(run_id, output_dir)

    # Collect all known versions
    front_versions = {c.prompt_version for c in state.pareto_front}
    history_versions: set[str] = set()
    for summary in state.round_history:
        history_versions.update(summary.candidates_evaluated)
    pending_versions = {c.prompt_version for c in pending}

    all_known = front_versions | history_versions | pending_versions
    if prompt_version in all_known:
        raise ValueError(
            f"prompt_version '{prompt_version}' is already registered "
            f"(front={prompt_version in front_versions}, "
            f"history={prompt_version in history_versions}, "
            f"pending={prompt_version in pending_versions})"
        )

    candidate = Candidate(
        prompt_version=prompt_version,
        parent_version=parent_version,
        quality_score=0.0,
        cost=0.0,
        round_introduced=state.round + 1,
        example_ids=example_ids or [],
        eval_status=eval_status,
        mutation_strategy=mutation_strategy,
        source_directive_batch_id=source_directive_batch_id,
    )
    pending.append(candidate)
    _save_pending(run_id, pending, output_dir)
    return state
```

- [ ] **Step 4: Update `register_candidate` in `prompt_building_tools.py`**

In `odysseus/mcp/prompt_building_tools.py`, update the tool at line 104 to accept and pass through the new parameters:

```python
@mcp.tool()
async def register_candidate(
    run_id: str,
    prompt_version: str,
    parent_version: str | None = None,
    example_ids: list[str] | None = None,
    eval_status: Literal["registered", "evaluating", "scored", "failed"] = "registered",
    mutation_strategy: Literal["targeted", "exploratory", "structural"] | None = None,
    source_directive_batch_id: str | None = None,
) -> str:
    """[Stage 4: Refinement Loop] Register a new candidate prompt version for the current search round.

    Args:
        run_id: Pipeline run identifier.
        prompt_version: Unique version identifier for the new prompt candidate.
        parent_version: Parent prompt version, if any.
        example_ids: Holdout example IDs used as few-shots in this prompt version (backend tracking only).
        eval_status: Initial lifecycle status for the candidate. Defaults to 'registered'.
        mutation_strategy: Strategy inherited from the source directive batch, if any.
        source_directive_batch_id: Traceability link to the originating DirectiveBatch, if any.

    Returns:
        JSON object confirming the registered prompt version.
    """
    try:
        register_candidate(
            run_id=run_id,
            prompt_version=prompt_version,
            parent_version=parent_version,
            example_ids=example_ids,
            eval_status=eval_status,
            mutation_strategy=mutation_strategy,
            source_directive_batch_id=source_directive_batch_id,
        )
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return json.dumps({"registered": prompt_version})
```

Add `Literal` to the imports at the top of `prompt_building_tools.py` if not already present.

- [ ] **Step 5: Run all tests to verify they pass**

Run: `uv run pytest tests/test_prompt_builder_search_ops.py::TestRegisterCandidateNewFields -v`
Expected: ALL PASS

- [ ] **Step 6: Run full search_ops test suite to check for regressions**

Run: `uv run pytest tests/test_prompt_builder_search_ops.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add odysseus/agents/prompt_builder/search_ops.py odysseus/mcp/prompt_building_tools.py tests/test_prompt_builder_search_ops.py
git commit -m "feat: add eval_status, mutation_strategy, source_directive_batch_id to register_candidate"
```

---

## Task 5: Update `advance_round` with beam width calculation, eval_status filtering, and active_evals guard

**Files:**
- Modify: `odysseus/agents/prompt_builder/search_ops.py`
- Test: `tests/test_prompt_builder_search_ops.py`

Steps:

- [ ] **Step 1: Write failing test — active_evals guard**

```python
# In tests/test_prompt_builder_search_ops.py

class TestAdvanceRoundNewBehavior:
    def test_advance_round_rejects_active_evals(self, tmp_output: Path, run_id: str):
        """advance_round raises ValueError when active_evals is non-empty."""
        import json
        state = init_search_state(backend="anthropic", run_id=run_id, output_dir=tmp_output)
        # Manually write active_evals into the state file
        state_path = tmp_output / run_id / "search" / "search_state.json"
        data = json.loads(state_path.read_text())
        data["active_evals"] = ["v2"]
        state_path.write_text(json.dumps(data))
        # Register and score a candidate so pending is non-empty
        register_candidate(run_id=run_id, prompt_version="v2", output_dir=tmp_output)
        record_eval_result(run_id=run_id, prompt_version="v2", quality_score=0.8, cost=0.01, output_dir=tmp_output)
        with pytest.raises(ValueError, match="active_evals"):
            advance_round(run_id=run_id, output_dir=tmp_output)
```

- [ ] **Step 2: Write failing tests — eval_status filtering**

```python
    def test_advance_round_filters_failed_candidates(self, tmp_output: Path, run_id: str):
        """Failed candidates are excluded from Pareto update but logged in round history."""
        init_search_state(backend="anthropic", run_id=run_id, output_dir=tmp_output)
        # Register one scored and one failed candidate
        register_candidate(
            run_id=run_id, prompt_version="v2", eval_status="scored", output_dir=tmp_output
        )
        record_eval_result(run_id=run_id, prompt_version="v2", quality_score=0.8, cost=0.01, output_dir=tmp_output)
        register_candidate(
            run_id=run_id, prompt_version="v3", eval_status="failed", output_dir=tmp_output
        )
        # v3 has no eval result recorded (quality_score=0.0, cost=0.0 sentinel)

        summary = advance_round(run_id=run_id, output_dir=tmp_output)
        # v3 must appear in candidates_evaluated (it was pending)
        assert "v3" in summary.candidates_evaluated
        # But v3 must NOT be on the Pareto front (failed, quality=0.0 sentinel excluded)
        state = get_search_state(run_id=run_id, output_dir=tmp_output)
        front_versions = {c.prompt_version for c in state.pareto_front}
        assert "v3" not in front_versions
        assert "v2" in front_versions

    def test_advance_round_all_failed_stagnation(self, tmp_output: Path, run_id: str):
        """All-failed round is treated as stagnation, not a ValueError."""
        init_search_state(backend="anthropic", run_id=run_id, output_dir=tmp_output)
        register_candidate(
            run_id=run_id, prompt_version="v2", eval_status="failed", output_dir=tmp_output
        )
        # Should NOT raise; should be treated as stagnation
        summary = advance_round(run_id=run_id, output_dir=tmp_output)
        assert summary.stagnation_count == 1
        assert "v2" in summary.candidates_evaluated
```

- [ ] **Step 3: Write failing tests — beam width calculation**

```python
    def _make_state_with_mode_and_stagnation(
        self,
        tmp_output: Path,
        run_id: str,
        mutation_mode: str,
        stagnation_count: int,
    ) -> None:
        """Helper: initialise state with given mutation_mode and stagnation_count."""
        import json
        init_search_state(backend="anthropic", run_id=run_id, output_dir=tmp_output)
        state_path = tmp_output / run_id / "search" / "search_state.json"
        data = json.loads(state_path.read_text())
        data["mutation_mode"] = mutation_mode
        data["stagnation_count"] = stagnation_count
        state_path.write_text(json.dumps(data))

    def test_advance_round_beam_width_targeted_no_stagnation(
        self, tmp_output: Path, run_id: str
    ):
        """targeted + stagnation=0 → beam_width=min_beam_width (2)."""
        import json
        self._make_state_with_mode_and_stagnation(
            tmp_output, run_id, mutation_mode="targeted", stagnation_count=0
        )
        register_candidate(
            run_id=run_id, prompt_version="v2", eval_status="scored", output_dir=tmp_output
        )
        record_eval_result(run_id=run_id, prompt_version="v2", quality_score=0.9, cost=0.01, output_dir=tmp_output)
        advance_round(run_id=run_id, output_dir=tmp_output)
        state_path = tmp_output / run_id / "search" / "search_state.json"
        state_data = json.loads(state_path.read_text())
        assert state_data["beam_width"] == 2

    def test_advance_round_beam_width_targeted_with_stagnation(
        self, tmp_output: Path, run_id: str
    ):
        """targeted + stagnation >= 1 → beam_width=3."""
        import json
        self._make_state_with_mode_and_stagnation(
            tmp_output, run_id, mutation_mode="targeted", stagnation_count=1
        )
        register_candidate(
            run_id=run_id, prompt_version="v2", eval_status="scored", output_dir=tmp_output
        )
        record_eval_result(run_id=run_id, prompt_version="v2", quality_score=0.0, cost=0.0, output_dir=tmp_output)
        advance_round(run_id=run_id, output_dir=tmp_output)
        state_path = tmp_output / run_id / "search" / "search_state.json"
        state_data = json.loads(state_path.read_text())
        assert state_data["beam_width"] == 3

    def test_advance_round_beam_width_exploratory(self, tmp_output: Path, run_id: str):
        """exploratory + stagnation < 2 (post-round stagnation=1) → beam_width=4."""
        import json
        self._make_state_with_mode_and_stagnation(
            tmp_output, run_id, mutation_mode="exploratory", stagnation_count=0
        )
        register_candidate(
            run_id=run_id, prompt_version="v2", eval_status="scored", output_dir=tmp_output
        )
        record_eval_result(run_id=run_id, prompt_version="v2", quality_score=0.0, cost=0.0, output_dir=tmp_output)
        advance_round(run_id=run_id, output_dir=tmp_output)
        state_path = tmp_output / run_id / "search" / "search_state.json"
        state_data = json.loads(state_path.read_text())
        assert state_data["beam_width"] == 4

    def test_advance_round_beam_width_exploratory_deep_stagnation(
        self, tmp_output: Path, run_id: str
    ):
        """exploratory + stagnation >= 2 → beam_width=max_beam_width (5)."""
        import json
        self._make_state_with_mode_and_stagnation(
            tmp_output, run_id, mutation_mode="exploratory", stagnation_count=2
        )
        register_candidate(
            run_id=run_id, prompt_version="v2", eval_status="scored", output_dir=tmp_output
        )
        record_eval_result(run_id=run_id, prompt_version="v2", quality_score=0.0, cost=0.0, output_dir=tmp_output)
        advance_round(run_id=run_id, output_dir=tmp_output)
        state_path = tmp_output / run_id / "search" / "search_state.json"
        state_data = json.loads(state_path.read_text())
        assert state_data["beam_width"] == 5

    def test_advance_round_beam_width_loop_signal_override(
        self, tmp_output: Path, run_id: str
    ):
        """LoopSignal.suggested_beam_width overrides the adaptive table."""
        import json
        from odysseus.agents.review.models import LoopSignal
        from odysseus.agents.prompt_builder.search_ops import _save_loop_signal, _loop_signal_path

        self._make_state_with_mode_and_stagnation(
            tmp_output, run_id, mutation_mode="targeted", stagnation_count=0
        )
        # Without override, targeted+stagnation=0 → 2. Override to 4.
        signal = LoopSignal(action="refine", reason="need more breadth", suggested_beam_width=4)
        _save_loop_signal(run_id, signal, tmp_output)

        register_candidate(
            run_id=run_id, prompt_version="v2", eval_status="scored", output_dir=tmp_output
        )
        record_eval_result(run_id=run_id, prompt_version="v2", quality_score=0.9, cost=0.01, output_dir=tmp_output)
        advance_round(run_id=run_id, output_dir=tmp_output)
        state_path = tmp_output / run_id / "search" / "search_state.json"
        state_data = json.loads(state_path.read_text())
        assert state_data["beam_width"] == 4

    def test_advance_round_beam_width_clamp(self, tmp_output: Path, run_id: str):
        """suggested_beam_width is clamped to [min_beam_width, max_beam_width]."""
        import json
        from odysseus.agents.review.models import LoopSignal
        from odysseus.agents.prompt_builder.search_ops import _save_loop_signal

        self._make_state_with_mode_and_stagnation(
            tmp_output, run_id, mutation_mode="targeted", stagnation_count=0
        )
        # Suggest 99 — must be clamped to max_beam_width=5
        signal = LoopSignal(action="refine", reason="test clamp", suggested_beam_width=99)
        _save_loop_signal(run_id, signal, tmp_output)

        register_candidate(
            run_id=run_id, prompt_version="v2", eval_status="scored", output_dir=tmp_output
        )
        record_eval_result(run_id=run_id, prompt_version="v2", quality_score=0.9, cost=0.01, output_dir=tmp_output)
        advance_round(run_id=run_id, output_dir=tmp_output)
        state_path = tmp_output / run_id / "search" / "search_state.json"
        state_data = json.loads(state_path.read_text())
        assert state_data["beam_width"] == 5  # clamped to max

        # Now test clamp to min (suggest 0)
        run_id2 = run_id + "_min"
        self._make_state_with_mode_and_stagnation(
            tmp_output, run_id2, mutation_mode="exploratory", stagnation_count=3
        )
        signal2 = LoopSignal(action="refine", reason="test clamp min", suggested_beam_width=0)
        _save_loop_signal(run_id2, signal2, tmp_output)
        register_candidate(
            run_id=run_id2, prompt_version="v2", eval_status="scored", output_dir=tmp_output
        )
        record_eval_result(run_id=run_id2, prompt_version="v2", quality_score=0.0, cost=0.0, output_dir=tmp_output)
        advance_round(run_id=run_id2, output_dir=tmp_output)
        state_path2 = tmp_output / run_id2 / "search" / "search_state.json"
        state_data2 = json.loads(state_path2.read_text())
        assert state_data2["beam_width"] == 2  # clamped to min
```

- [ ] **Step 4: Run all failing tests**

Run: `uv run pytest tests/test_prompt_builder_search_ops.py::TestAdvanceRoundNewBehavior -v`
Expected: FAIL — `advance_round` does not have the guard, filtering, or beam width logic yet

- [ ] **Step 5: Implement — update `advance_round` in `search_ops.py`**

Replace the `advance_round` function body (lines 321–430 in the current file) with the updated version below. The changes are: (1) active_evals guard at the top; (2) scored-only filtering before `update_pareto_front`; (3) all-fail stagnation handling replacing the empty-pending ValueError; (4) beam width calculation after `new_mutation_mode` and `new_stagnation_count` are determined; (5) `beam_width` included in `model_copy`.

```python
def advance_round(
    run_id: str,
    output_dir: Path | None = None,
) -> RoundSummary:
    """Advance the search loop by one round.

    Processes all pending candidates: filters to scored-only for Pareto update,
    adjusts stagnation tracking, switches mutation mode, calculates beam width,
    and checks for convergence.

    Args:
        run_id: Run identifier used to locate the state on disk.
        output_dir: Root directory for persisted state files.

    Returns:
        A :class:`RoundSummary` for the completed round.

    Raises:
        FileNotFoundError: If the search state does not exist.
        ValueError: If ``active_evals`` is non-empty (evals still in flight).
        ValueError: If there are no pending candidates at all.
    """
    if output_dir is None:
        output_dir = _default_output_dir()
    state = _load_state(run_id, output_dir)
    pending = _load_pending(run_id, output_dir)

    # Guard: refuse to advance if evals are still in flight
    if state.active_evals:
        raise ValueError(
            f"Cannot advance round: active_evals is non-empty ({state.active_evals}). "
            "All in-flight evaluations must complete before calling advance_round."
        )

    if not pending:
        raise ValueError("No pending candidates to advance round with")

    new_round = state.round + 1

    # Split pending into scored vs failed
    scored_pending = [c for c in pending if c.eval_status == "scored"]
    failed_pending = [c for c in pending if c.eval_status == "failed"]

    if failed_pending:
        logger.warning(
            "advance_round: %d candidate(s) failed evaluation and will be excluded from "
            "Pareto update: %s",
            len(failed_pending),
            [c.prompt_version for c in failed_pending],
        )

    # If no scored candidates, treat as stagnation (all-fail case)
    if scored_pending:
        new_front, new_pareto_points = update_pareto_front(state.pareto_front, scored_pending)
    else:
        # All candidates failed — carry the existing front forward unchanged
        new_front = state.pareto_front
        new_pareto_points = 0
        logger.warning(
            "advance_round: all %d candidate(s) failed; treating round as stagnation.",
            len(failed_pending),
        )

    # Update stagnation
    improvement = compute_front_improvement(state.pareto_front, new_front)
    new_stagnation_count = 0 if improvement > state.epsilon else state.stagnation_count + 1

    # Determine mutation mode
    if new_stagnation_count == 0 and state.stagnation_count > 0:
        # Improvement after stagnation — reset to targeted
        new_mutation_mode = "targeted"
    elif new_stagnation_count >= state.stagnation_limit:
        new_mutation_mode = "exploratory"
    else:
        new_mutation_mode = state.mutation_mode

    # Check convergence
    converged = new_stagnation_count >= state.convergence_limit or new_round >= state.max_rounds
    new_convergence_limit = state.convergence_limit

    # Apply Review Agent loop signal (if present)
    signal = _consume_loop_signal(run_id, output_dir)
    if signal is not None and signal.action == "refine":
        if signal.suggested_budget is not None and signal.suggested_budget > 0:
            new_stagnation_count = 0
            new_convergence_limit = max(
                state.convergence_limit + signal.suggested_budget,
                state.stagnation_limit + 1,
            )
            # Re-check: only max_rounds is a hard cap
            converged = new_round >= state.max_rounds
        if signal.suggested_mutation_mode is not None:
            new_mutation_mode = signal.suggested_mutation_mode

    # Compute beam width from adaptive table (uses post-round values)
    if new_mutation_mode == "exploratory" and new_stagnation_count >= 2:
        new_beam_width = state.max_beam_width
    elif new_mutation_mode == "exploratory":
        new_beam_width = 4
    elif new_mutation_mode == "targeted" and new_stagnation_count == 0:
        new_beam_width = state.min_beam_width
    else:
        new_beam_width = 3

    # Apply Review Agent beam width override if present
    if signal is not None and signal.suggested_beam_width is not None:
        new_beam_width = signal.suggested_beam_width

    # Clamp to [min_beam_width, max_beam_width]
    new_beam_width = max(state.min_beam_width, min(state.max_beam_width, new_beam_width))

    # All pending versions (scored + failed) are logged in history
    candidates_evaluated = [c.prompt_version for c in pending]

    qualities = [c.quality_score for c in new_front]
    front_quality_spread = max(qualities) - min(qualities) if len(new_front) > 1 else 0.0
    round_routing_cost = sum(c.cost for c in scored_pending)
    convergence_reason: str | None = None
    if converged:
        if new_round >= state.max_rounds:
            convergence_reason = "max_rounds"
        elif new_stagnation_count >= new_convergence_limit:
            convergence_reason = "stagnation"

    summary = RoundSummary(
        round=new_round,
        candidates_evaluated=candidates_evaluated,
        new_pareto_points=new_pareto_points,
        front_size=len(new_front),
        mutation_mode=new_mutation_mode,
        stagnation_count=new_stagnation_count,
        converged=converged,
        front_improvement=improvement,
        front_quality_spread=front_quality_spread,
        round_routing_cost=round_routing_cost,
        convergence_reason=convergence_reason,
    )

    # Persist updated state (includes beam_width)
    updated_state = state.model_copy(
        update={
            "round": new_round,
            "pareto_front": new_front,
            "round_history": [*state.round_history, summary],
            "stagnation_count": new_stagnation_count,
            "convergence_limit": new_convergence_limit,
            "mutation_mode": new_mutation_mode,
            "converged": converged,
            "loop_phase": "build" if converged else "review",
            "total_routing_cost": state.total_routing_cost + round_routing_cost,
            "beam_width": new_beam_width,
        }
    )
    _save_state(run_id, updated_state, output_dir)

    # Clear pending
    _save_pending(run_id, [], output_dir)

    return summary
```

Also add `import logging` near the top of `search_ops.py` (after the existing imports) and `logger = logging.getLogger(__name__)` after the imports block, if not already present.

- [ ] **Step 6: Run all new tests to verify they pass**

Run: `uv run pytest tests/test_prompt_builder_search_ops.py::TestAdvanceRoundNewBehavior -v`
Expected: ALL PASS

- [ ] **Step 7: Run full search_ops test suite to check for regressions**

Run: `uv run pytest tests/test_prompt_builder_search_ops.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add odysseus/agents/prompt_builder/search_ops.py tests/test_prompt_builder_search_ops.py
git commit -m "feat: add active_evals guard, eval_status filtering, and beam width calculation to advance_round"
```

---

## Task 6: Add shared rate limiter to `RunDependencies`

**Files:**
- Modify: `odysseus/eval/protocols.py`
- Modify: `odysseus/eval/controller.py`
- Test: `tests/test_eval_protocols.py` (create if not exists) or minimal addition to existing eval tests

Steps:

- [ ] **Step 1: Write failing tests for `RunDependencies` with optional rate limiter**

```python
# tests/test_eval_protocols.py

import pytest
from unittest.mock import MagicMock

from odysseus.eval.protocols import RunDependencies
from odysseus.eval.rate_limiter import TokenBucketRateLimiter


def _make_deps(**overrides) -> RunDependencies:
    """Construct a minimal valid RunDependencies for testing."""
    defaults = dict(
        backend=MagicMock(),
        prompt_manager=MagicMock(),
        dataset_manager=MagicMock(),
        metrics_engine=MagicMock(),
        results_collector=MagicMock(),
        requests_per_minute=60,
        tokens_per_minute=100_000,
    )
    defaults.update(overrides)
    return RunDependencies(**defaults)


class TestRunDependenciesRateLimiter:
    def test_run_dependencies_default_rate_limiter_is_none(self):
        """rate_limiter defaults to None when not provided."""
        deps = _make_deps()
        assert deps.rate_limiter is None

    def test_run_dependencies_accepts_pre_built_rate_limiter(self):
        """A pre-built TokenBucketRateLimiter is accepted and stored."""
        limiter = TokenBucketRateLimiter(
            requests_per_minute=60,
            tokens_per_minute=100_000,
        )
        deps = _make_deps(rate_limiter=limiter)
        assert deps.rate_limiter is limiter

    def test_run_dependencies_rate_limiter_field_is_optional(self):
        """Constructing without rate_limiter keyword doesn't raise."""
        deps = _make_deps()  # no rate_limiter kwarg
        assert deps.rate_limiter is None

    def test_run_dependencies_validation_still_rejects_bad_rpm(self):
        """Existing validation (requests_per_minute < 1) still works."""
        with pytest.raises(ValueError, match="requests_per_minute"):
            _make_deps(requests_per_minute=0)
```

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_eval_protocols.py -v`
Expected: FAIL — `RunDependencies` does not have a `rate_limiter` field

- [ ] **Step 3: Implement — add `rate_limiter` to `RunDependencies` in `protocols.py`**

In `odysseus/eval/protocols.py`, update the `RunDependencies` dataclass. Add the import for `TokenBucketRateLimiter` and the optional field:

```python
# Add to imports at top of protocols.py (after existing odysseus imports):
from odysseus.eval.rate_limiter import TokenBucketRateLimiter  # noqa: TC001


@dataclasses.dataclass
class RunDependencies:
    """Container for all injected dependencies required by the run controller."""

    backend: Backend
    prompt_manager: PromptManager
    dataset_manager: DatasetManager
    metrics_engine: MetricsEngine
    results_collector: ResultsCollector
    requests_per_minute: int
    tokens_per_minute: int
    rate_limiter: TokenBucketRateLimiter | None = None

    def __post_init__(self) -> None:
        if self.requests_per_minute < 1:
            raise ValueError("requests_per_minute must be >= 1")
        if self.tokens_per_minute < 1:
            raise ValueError("tokens_per_minute must be >= 1")
```

Note: `rate_limiter` must be placed after all fields without defaults (`requests_per_minute`, `tokens_per_minute`) to satisfy Python dataclass ordering rules.

- [ ] **Step 4: Implement — update `controller.py` to use injected rate limiter**

In `odysseus/eval/controller.py`, replace lines 82–85 (the `rate_limiter` instantiation):

```python
# Before:
rate_limiter = TokenBucketRateLimiter(
    requests_per_minute=deps.requests_per_minute,
    tokens_per_minute=deps.tokens_per_minute,
)

# After:
if deps.rate_limiter is not None:
    rate_limiter = deps.rate_limiter
else:
    rate_limiter = TokenBucketRateLimiter(
        requests_per_minute=deps.requests_per_minute,
        tokens_per_minute=deps.tokens_per_minute,
    )
```

- [ ] **Step 5: Run protocol tests to verify they pass**

Run: `uv run pytest tests/test_eval_protocols.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run full eval test suite to check for regressions**

Run: `uv run pytest tests/ -k "eval" -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add odysseus/eval/protocols.py odysseus/eval/controller.py tests/test_eval_protocols.py
git commit -m "feat: add optional shared rate_limiter to RunDependencies for concurrent eval runs"
```

---

## Task 7: Implement `run_batch_eval` tool

**Files:**
- Create: `odysseus/mcp/batch_eval.py`
- Modify: `odysseus/mcp/prompt_building_tools.py` (register the tool)
- Create: `tests/test_batch_eval.py`

**Context:** `run_batch_eval` replaces `run_eval` as the primary eval entry-point for normal build rounds. It registers all candidates, launches evals concurrently via `asyncio.gather`, then processes results sequentially to avoid concurrent file writes. The existing `run_eval` pattern in `prompt_building_tools.py` (lines 136–225) shows how `EvalRunnerAgent` is called: build a `RunConfig` via `build_pipeline_config`, wire `RunDependencies` via `EvalRunnerAgent._wire_dependencies`, then call `controller.run`. The `_run_single_eval` helper replicates this pattern per candidate with an injected shared `TokenBucketRateLimiter`.

Steps:

- [ ] **Step 1: Write failing tests**

```python
# tests/test_batch_eval.py

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from odysseus.mcp.batch_eval import (
    BatchEvalCandidate,
    BatchEvalResult,
    CandidateEvalOutcome,
    run_batch_eval_impl,
)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestBatchEvalModels:
    def test_batch_eval_candidate_required_fields(self):
        """BatchEvalCandidate validates all required fields."""
        c = BatchEvalCandidate(
            prompt_version="v8",
            parent_version="v5",
            mutation_strategy="targeted",
            source_directive_batch_id="b1",
            example_ids=["e1", "e2"],
        )
        assert c.prompt_version == "v8"
        assert c.parent_version == "v5"
        assert c.mutation_strategy == "targeted"
        assert c.source_directive_batch_id == "b1"
        assert c.example_ids == ["e1", "e2"]

    def test_batch_eval_candidate_parent_version_optional(self):
        """parent_version may be None for root candidates."""
        c = BatchEvalCandidate(
            prompt_version="v1",
            parent_version=None,
            mutation_strategy="exploratory",
            source_directive_batch_id="b0",
            example_ids=[],
        )
        assert c.parent_version is None

    def test_candidate_eval_outcome_success(self):
        """CandidateEvalOutcome holds scored result fields."""
        o = CandidateEvalOutcome(
            prompt_version="v8",
            quality_score=0.82,
            cost=0.05,
            error=None,
            score_report_path="/outputs/run1/eval/v8/report.json",
        )
        assert o.quality_score == 0.82
        assert o.error is None

    def test_candidate_eval_outcome_failure(self):
        """CandidateEvalOutcome holds failure fields."""
        o = CandidateEvalOutcome(
            prompt_version="v9",
            quality_score=None,
            cost=None,
            error="backend timeout",
            score_report_path=None,
        )
        assert o.quality_score is None
        assert o.error == "backend timeout"

    def test_batch_eval_result_structure(self):
        """BatchEvalResult partitions into succeeded and failed lists."""
        r = BatchEvalResult(
            succeeded=[
                CandidateEvalOutcome(
                    prompt_version="v8",
                    quality_score=0.82,
                    cost=0.05,
                    error=None,
                    score_report_path="/path",
                )
            ],
            failed=[
                CandidateEvalOutcome(
                    prompt_version="v9",
                    quality_score=None,
                    cost=None,
                    error="timeout",
                    score_report_path=None,
                )
            ],
        )
        assert len(r.succeeded) == 1
        assert len(r.failed) == 1


# ---------------------------------------------------------------------------
# Integration-style tests using mocked _run_single_eval
# ---------------------------------------------------------------------------


def _make_candidate(version: str, batch_id: str, strategy: str = "targeted") -> BatchEvalCandidate:
    return BatchEvalCandidate(
        prompt_version=version,
        parent_version="v5",
        mutation_strategy=strategy,
        source_directive_batch_id=batch_id,
        example_ids=["e1"],
    )


def _make_outcome(version: str, score: float = 0.80) -> CandidateEvalOutcome:
    return CandidateEvalOutcome(
        prompt_version=version,
        quality_score=score,
        cost=0.01,
        error=None,
        score_report_path=f"/outputs/run1/eval/{version}/report.json",
    )


class TestBatchEvalRegistersAndScores:
    @pytest.mark.asyncio
    async def test_batch_eval_registers_and_scores(self, tmp_path):
        """Candidates go through registered→evaluating→scored; active_evals cleared."""
        run_id = "run1"
        candidates = [
            _make_candidate("v8", "b1", "targeted"),
            _make_candidate("v9", "b2", "exploratory"),
        ]

        eval_calls: list[str] = []

        async def fake_run_single(candidate, run_id, project_dir, shared_limiter):
            eval_calls.append(candidate.prompt_version)
            return _make_outcome(candidate.prompt_version)

        with (
            patch("odysseus.mcp.batch_eval.register_candidate") as mock_reg,
            patch("odysseus.mcp.batch_eval._update_candidate_eval_status") as mock_status,
            patch("odysseus.mcp.batch_eval._add_to_active_evals") as mock_add,
            patch("odysseus.mcp.batch_eval._remove_from_active_evals") as mock_remove,
            patch("odysseus.mcp.batch_eval._run_single_eval", side_effect=fake_run_single),
            patch("odysseus.mcp.batch_eval.record_eval_result") as mock_record,
            patch("odysseus.mcp.batch_eval.get_project_dir", return_value=tmp_path),
        ):
            result = await run_batch_eval_impl(run_id=run_id, candidates=candidates)

        assert len(result.succeeded) == 2
        assert len(result.failed) == 0
        assert set(eval_calls) == {"v8", "v9"}

        # register_candidate called once per candidate
        assert mock_reg.call_count == 2

        # active_evals: add called for each, remove called for each
        assert mock_add.call_count == 2
        assert mock_remove.call_count == 2

        # eval results recorded for each succeeded candidate
        assert mock_record.call_count == 2

    @pytest.mark.asyncio
    async def test_batch_eval_status_sequence(self, tmp_path):
        """eval_status transitions: registered → evaluating (before gather), scored (after)."""
        run_id = "run1"
        status_calls: list[tuple[str, str]] = []

        async def fake_run_single(candidate, run_id, project_dir, shared_limiter):
            return _make_outcome(candidate.prompt_version)

        def capture_status(run_id, version, status):
            status_calls.append((version, status))

        with (
            patch("odysseus.mcp.batch_eval.register_candidate"),
            patch("odysseus.mcp.batch_eval._update_candidate_eval_status", side_effect=capture_status),
            patch("odysseus.mcp.batch_eval._add_to_active_evals"),
            patch("odysseus.mcp.batch_eval._remove_from_active_evals"),
            patch("odysseus.mcp.batch_eval._run_single_eval", side_effect=fake_run_single),
            patch("odysseus.mcp.batch_eval.record_eval_result"),
            patch("odysseus.mcp.batch_eval.get_project_dir", return_value=tmp_path),
        ):
            await run_batch_eval_impl(
                run_id=run_id,
                candidates=[_make_candidate("v8", "b1")],
            )

        # "evaluating" set before gather, "scored" set after
        assert ("v8", "evaluating") in status_calls
        assert ("v8", "scored") in status_calls
        evaluating_idx = next(i for i, c in enumerate(status_calls) if c == ("v8", "evaluating"))
        scored_idx = next(i for i, c in enumerate(status_calls) if c == ("v8", "scored"))
        assert evaluating_idx < scored_idx


class TestBatchEvalHandlesFailure:
    @pytest.mark.asyncio
    async def test_batch_eval_one_fails_others_succeed(self, tmp_path):
        """One eval raising does not prevent others; failed candidate in result.failed."""
        run_id = "run1"

        async def fake_run_single(candidate, run_id, project_dir, shared_limiter):
            if candidate.prompt_version == "v10":
                raise RuntimeError("invalid directive output")
            return _make_outcome(candidate.prompt_version)

        with (
            patch("odysseus.mcp.batch_eval.register_candidate"),
            patch("odysseus.mcp.batch_eval._update_candidate_eval_status"),
            patch("odysseus.mcp.batch_eval._add_to_active_evals"),
            patch("odysseus.mcp.batch_eval._remove_from_active_evals"),
            patch("odysseus.mcp.batch_eval._run_single_eval", side_effect=fake_run_single),
            patch("odysseus.mcp.batch_eval.record_eval_result"),
            patch("odysseus.mcp.batch_eval.get_project_dir", return_value=tmp_path),
        ):
            result = await run_batch_eval_impl(
                run_id=run_id,
                candidates=[
                    _make_candidate("v8", "b1"),
                    _make_candidate("v9", "b2", "exploratory"),
                    _make_candidate("v10", "b3"),
                ],
            )

        assert len(result.succeeded) == 2
        assert len(result.failed) == 1
        assert result.failed[0].prompt_version == "v10"
        assert "invalid directive output" in result.failed[0].error

    @pytest.mark.asyncio
    async def test_batch_eval_failed_candidate_marked_failed(self, tmp_path):
        """Failed candidate's eval_status is set to 'failed', not 'scored'."""
        status_calls: list[tuple[str, str]] = []

        async def fake_run_single(candidate, run_id, project_dir, shared_limiter):
            raise RuntimeError("timeout")

        def capture_status(run_id, version, status):
            status_calls.append((version, status))

        with (
            patch("odysseus.mcp.batch_eval.register_candidate"),
            patch("odysseus.mcp.batch_eval._update_candidate_eval_status", side_effect=capture_status),
            patch("odysseus.mcp.batch_eval._add_to_active_evals"),
            patch("odysseus.mcp.batch_eval._remove_from_active_evals"),
            patch("odysseus.mcp.batch_eval._run_single_eval", side_effect=fake_run_single),
            patch("odysseus.mcp.batch_eval.record_eval_result"),
            patch("odysseus.mcp.batch_eval.get_project_dir", return_value=tmp_path),
        ):
            await run_batch_eval_impl(
                run_id="run1",
                candidates=[_make_candidate("v8", "b1")],
            )

        final_statuses = [s for v, s in status_calls if v == "v8"]
        assert "failed" in final_statuses
        assert "scored" not in final_statuses


class TestBatchEvalAllFail:
    @pytest.mark.asyncio
    async def test_batch_eval_all_fail_returns_all_in_failed(self, tmp_path):
        """All evals failing returns BatchEvalResult with empty succeeded, all in failed."""
        async def fake_run_single(candidate, run_id, project_dir, shared_limiter):
            raise RuntimeError("crash")

        with (
            patch("odysseus.mcp.batch_eval.register_candidate"),
            patch("odysseus.mcp.batch_eval._update_candidate_eval_status"),
            patch("odysseus.mcp.batch_eval._add_to_active_evals"),
            patch("odysseus.mcp.batch_eval._remove_from_active_evals"),
            patch("odysseus.mcp.batch_eval._run_single_eval", side_effect=fake_run_single),
            patch("odysseus.mcp.batch_eval.record_eval_result"),
            patch("odysseus.mcp.batch_eval.get_project_dir", return_value=tmp_path),
        ):
            result = await run_batch_eval_impl(
                run_id="run1",
                candidates=[
                    _make_candidate("v8", "b1"),
                    _make_candidate("v9", "b2"),
                ],
            )

        assert result.succeeded == []
        assert len(result.failed) == 2
        assert {o.prompt_version for o in result.failed} == {"v8", "v9"}


class TestBatchEvalRecoveryMode:
    @pytest.mark.asyncio
    async def test_recovery_mode_skips_scored(self, tmp_path):
        """Recovery mode: scored candidates are skipped, not re-evaluated."""
        from odysseus.agents.prompt_builder.search import Candidate

        scored_candidate = Candidate(
            prompt_version="v8",
            parent_version="v5",
            quality_score=0.82,
            cost=0.01,
            round_introduced=3,
            eval_status="scored",
        )

        eval_calls: list[str] = []

        async def fake_run_single(candidate, run_id, project_dir, shared_limiter):
            eval_calls.append(candidate.prompt_version)
            return _make_outcome(candidate.prompt_version)

        with (
            patch("odysseus.mcp.batch_eval._load_pending_candidates", return_value=[scored_candidate]),
            patch("odysseus.mcp.batch_eval._get_active_evals", return_value=["v8"]),
            patch("odysseus.mcp.batch_eval._run_single_eval", side_effect=fake_run_single),
            patch("odysseus.mcp.batch_eval._remove_from_active_evals"),
            patch("odysseus.mcp.batch_eval._update_candidate_eval_status"),
            patch("odysseus.mcp.batch_eval.record_eval_result"),
            patch("odysseus.mcp.batch_eval.get_project_dir", return_value=tmp_path),
        ):
            result = await run_batch_eval_impl(run_id="run1", candidates=[])

        # scored candidate was not re-evaluated
        assert "v8" not in eval_calls
        # it appears in succeeded (already scored)
        assert any(o.prompt_version == "v8" for o in result.succeeded)

    @pytest.mark.asyncio
    async def test_recovery_mode_resumes_evaluating(self, tmp_path):
        """Recovery mode: evaluating candidates are re-run (fingerprint-based resume)."""
        from odysseus.agents.prompt_builder.search import Candidate

        pending = [
            Candidate(
                prompt_version="v9",
                parent_version="v5",
                quality_score=0.0,
                cost=0.0,
                round_introduced=3,
                eval_status="evaluating",
                example_ids=["e1", "e2"],
            )
        ]
        eval_calls: list[str] = []

        async def fake_run_single(candidate, run_id, project_dir, shared_limiter):
            eval_calls.append(candidate.prompt_version)
            return _make_outcome(candidate.prompt_version)

        with (
            patch("odysseus.mcp.batch_eval._load_pending_candidates", return_value=pending),
            patch("odysseus.mcp.batch_eval._get_active_evals", return_value=["v9"]),
            patch("odysseus.mcp.batch_eval._run_single_eval", side_effect=fake_run_single),
            patch("odysseus.mcp.batch_eval._remove_from_active_evals"),
            patch("odysseus.mcp.batch_eval._update_candidate_eval_status"),
            patch("odysseus.mcp.batch_eval.record_eval_result"),
            patch("odysseus.mcp.batch_eval.get_project_dir", return_value=tmp_path),
        ):
            result = await run_batch_eval_impl(run_id="run1", candidates=[])

        assert "v9" in eval_calls
        assert len(result.succeeded) == 1

    @pytest.mark.asyncio
    async def test_recovery_mode_restarts_registered(self, tmp_path):
        """Recovery mode: registered candidates (eval never started) are started fresh."""
        from odysseus.agents.prompt_builder.search import Candidate

        pending = [
            Candidate(
                prompt_version="v10",
                parent_version="v5",
                quality_score=0.0,
                cost=0.0,
                round_introduced=3,
                eval_status="registered",
                example_ids=["e1"],
            )
        ]
        eval_calls: list[str] = []

        async def fake_run_single(candidate, run_id, project_dir, shared_limiter):
            eval_calls.append(candidate.prompt_version)
            return _make_outcome(candidate.prompt_version)

        with (
            patch("odysseus.mcp.batch_eval._load_pending_candidates", return_value=pending),
            patch("odysseus.mcp.batch_eval._get_active_evals", return_value=["v10"]),
            patch("odysseus.mcp.batch_eval._run_single_eval", side_effect=fake_run_single),
            patch("odysseus.mcp.batch_eval._remove_from_active_evals"),
            patch("odysseus.mcp.batch_eval._update_candidate_eval_status"),
            patch("odysseus.mcp.batch_eval.record_eval_result"),
            patch("odysseus.mcp.batch_eval.get_project_dir", return_value=tmp_path),
        ):
            result = await run_batch_eval_impl(run_id="run1", candidates=[])

        assert "v10" in eval_calls
        assert len(result.succeeded) == 1


class TestBatchEvalSharedRateLimiter:
    @pytest.mark.asyncio
    async def test_single_rate_limiter_created_and_shared(self, tmp_path):
        """A single TokenBucketRateLimiter is created and passed to all _run_single_eval calls."""
        from odysseus.eval.rate_limiter import TokenBucketRateLimiter

        received_limiters: list[object] = []

        async def fake_run_single(candidate, run_id, project_dir, shared_limiter):
            received_limiters.append(shared_limiter)
            return _make_outcome(candidate.prompt_version)

        fake_limiter = MagicMock(spec=TokenBucketRateLimiter)

        with (
            patch("odysseus.mcp.batch_eval.register_candidate"),
            patch("odysseus.mcp.batch_eval._update_candidate_eval_status"),
            patch("odysseus.mcp.batch_eval._add_to_active_evals"),
            patch("odysseus.mcp.batch_eval._remove_from_active_evals"),
            patch("odysseus.mcp.batch_eval._run_single_eval", side_effect=fake_run_single),
            patch("odysseus.mcp.batch_eval.record_eval_result"),
            patch("odysseus.mcp.batch_eval.get_project_dir", return_value=tmp_path),
            patch(
                "odysseus.mcp.batch_eval.TokenBucketRateLimiter",
                return_value=fake_limiter,
            ) as mock_limiter_cls,
        ):
            await run_batch_eval_impl(
                run_id="run1",
                candidates=[
                    _make_candidate("v8", "b1"),
                    _make_candidate("v9", "b2"),
                ],
            )

        # Limiter constructed exactly once
        assert mock_limiter_cls.call_count == 1
        # All calls received the same limiter instance
        assert all(lim is fake_limiter for lim in received_limiters)
        assert len(received_limiters) == 2
```

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_batch_eval.py -v`
Expected: FAIL — `odysseus.mcp.batch_eval` module does not exist

- [ ] **Step 3: Create `odysseus/mcp/batch_eval.py`**

```python
# odysseus/mcp/batch_eval.py
"""Batch evaluation tool — registers and concurrently evaluates multiple candidates."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel

import odysseus.project_dir as _project_dir_mod
from odysseus.agents.eval_runner import EvalRunnerAgent
from odysseus.agents.pipeline.guards import check_artifacts
from odysseus.agents.prompt_builder.search import Candidate, SearchState
from odysseus.agents.prompt_builder.search_ops import (
    _load_pending,
    _load_state,
    _save_pending,
    _save_state,
    get_search_state,
    record_eval_result,
    register_candidate,
)
from odysseus.eval.models import ScoreReport
from odysseus.eval.rate_limiter import TokenBucketRateLimiter
from odysseus.mcp.prompt_building_tools import build_pipeline_config
from odysseus.mcp.server import mcp
from odysseus.project_dir import get_project_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public models
# ---------------------------------------------------------------------------


class BatchEvalCandidate(BaseModel):
    """A candidate to be evaluated as part of a batch."""

    prompt_version: str
    parent_version: str | None
    mutation_strategy: Literal["targeted", "exploratory", "structural"]
    source_directive_batch_id: str
    example_ids: list[str]


class CandidateEvalOutcome(BaseModel):
    """Result of evaluating a single candidate."""

    prompt_version: str
    quality_score: float | None
    cost: float | None
    error: str | None
    score_report_path: str | None


class BatchEvalResult(BaseModel):
    """Aggregated result of a batch evaluation run."""

    succeeded: list[CandidateEvalOutcome]
    failed: list[CandidateEvalOutcome]


# ---------------------------------------------------------------------------
# Internal state helpers
# ---------------------------------------------------------------------------


def _get_active_evals(run_id: str, output_dir: Path | None = None) -> list[str]:
    """Return the active_evals list from search state, or [] if absent."""
    out = output_dir or (get_project_dir() / "outputs")
    try:
        state = _load_state(run_id, out)
        return list(getattr(state, "active_evals", []))
    except FileNotFoundError:
        return []


def _add_to_active_evals(run_id: str, version: str, output_dir: Path | None = None) -> None:
    """Append version to SearchState.active_evals and persist."""
    out = output_dir or (get_project_dir() / "outputs")
    state = _load_state(run_id, out)
    active = list(getattr(state, "active_evals", []))
    if version not in active:
        active.append(version)
    updated = state.model_copy(update={"active_evals": active})
    _save_state(run_id, updated, out)


def _remove_from_active_evals(run_id: str, version: str, output_dir: Path | None = None) -> None:
    """Remove version from SearchState.active_evals and persist."""
    out = output_dir or (get_project_dir() / "outputs")
    state = _load_state(run_id, out)
    active = [v for v in getattr(state, "active_evals", []) if v != version]
    updated = state.model_copy(update={"active_evals": active})
    _save_state(run_id, updated, out)


def _update_candidate_eval_status(run_id: str, version: str, status: str, output_dir: Path | None = None) -> None:
    """Update eval_status on the matching pending candidate and persist."""
    out = output_dir or (get_project_dir() / "outputs")
    pending = _load_pending(run_id, out)
    updated_pending = []
    for c in pending:
        if c.prompt_version == version:
            updated_pending.append(c.model_copy(update={"eval_status": status}))
        else:
            updated_pending.append(c)
    _save_pending(run_id, updated_pending, out)


def _load_pending_candidates(run_id: str, output_dir: Path | None = None) -> list[Candidate]:
    """Load pending candidates from search state persistence."""
    out = output_dir or (get_project_dir() / "outputs")
    return _load_pending(run_id, out)


# ---------------------------------------------------------------------------
# Single-eval helper
# ---------------------------------------------------------------------------


async def _run_single_eval(
    candidate: BatchEvalCandidate,
    run_id: str,
    project_dir: Path,
    shared_limiter: TokenBucketRateLimiter,
    primary_metric_name: str | None = None,
) -> CandidateEvalOutcome:
    """Run a single candidate evaluation using EvalRunnerAgent with a shared rate limiter.

    Replicates the run_eval flow from prompt_building_tools.py but injects the
    shared limiter into RunDependencies so all concurrent evals share one token budget.
    """
    state = get_search_state(run_id=run_id)
    data_source = str(project_dir / "outputs" / run_id / "analysis" / "dev.jsonl")

    run_config = build_pipeline_config(
        state=state,
        prompt_version=candidate.prompt_version,
        data_source=data_source,
        run_id=run_id,
        project_dir=project_dir,
    )

    agent = EvalRunnerAgent()

    # Wire dependencies manually so we can inject the shared rate limiter.
    # We then call controller.run() directly rather than agent.run(context) to
    # avoid private API coupling and to ensure the shared limiter is actually used
    # (agent.run() does not check for any _deps_override in the context dict).
    deps = agent._wire_dependencies(run_config, run_id=run_id)
    deps_with_limiter = deps.__class__(
        backend=deps.backend,
        prompt_manager=deps.prompt_manager,
        dataset_manager=deps.dataset_manager,
        metrics_engine=deps.metrics_engine,
        results_collector=deps.results_collector,
        requests_per_minute=deps.requests_per_minute,
        tokens_per_minute=deps.tokens_per_minute,
        rate_limiter=shared_limiter,
    )

    controller = agent._build_controller(run_config)
    score_report: ScoreReport = await controller.run(run_config, deps_with_limiter)

    return CandidateEvalOutcome(
        prompt_version=candidate.prompt_version,
        quality_score=score_report.metrics.get(primary_metric_name or "accuracy", 0.0),
        cost=score_report.summary.total_cost,
        error=None,
        score_report_path=score_report.report_path,
    )


# ---------------------------------------------------------------------------
# Core implementation
# ---------------------------------------------------------------------------


async def run_batch_eval_impl(
    run_id: str,
    candidates: list[BatchEvalCandidate],
    project_dir: Path | None = None,
) -> BatchEvalResult:
    """Core batch eval logic, separated from the MCP tool for testability.

    Normal mode (candidates non-empty):
      1. Register each candidate (eval_status="registered").
      2. Set each to "evaluating", add to active_evals, persist.
      3. asyncio.gather all evals concurrently.
      4. Process results sequentially: record or mark failed.

    Recovery mode (candidates=[]):
      1. Load pending_candidates.
      2. Triage by eval_status: scored→skip, evaluating/registered→run.
      3. Same concurrent execution and sequential result processing.
    """
    out_dir = project_dir or get_project_dir()

    state = get_search_state(run_id=run_id)
    # Build a shared rate limiter using the first available backend profile
    # (all candidates in a batch share the same backend via search state).
    from odysseus.eval.backends.registry import BackendRegistry
    registry = BackendRegistry.from_directory(out_dir / "backends")
    profile = registry.get_profile(state.backend)
    shared_limiter = TokenBucketRateLimiter(
        requests_per_minute=profile.requests_per_minute,
        tokens_per_minute=profile.tokens_per_minute,
    )

    recovery_mode = not candidates

    if recovery_mode:
        # Recovery: triage pending candidates
        pending = _load_pending_candidates(run_id)
        eval_candidates: list[BatchEvalCandidate | Candidate] = []
        pre_scored: list[CandidateEvalOutcome] = []

        for pc in pending:
            status = getattr(pc, "eval_status", "registered")
            if status == "scored":
                # Already complete — include in succeeded without re-running
                pre_scored.append(
                    CandidateEvalOutcome(
                        prompt_version=pc.prompt_version,
                        quality_score=pc.quality_score,
                        cost=pc.cost,
                        error=None,
                        score_report_path=None,
                    )
                )
            else:
                # evaluating or registered — (re-)run
                eval_candidates.append(pc)
    else:
        # Normal mode: register all candidates first
        for c in candidates:
            register_candidate(
                run_id=run_id,
                prompt_version=c.prompt_version,
                parent_version=c.parent_version,
                example_ids=c.example_ids,
                eval_status="registered",
                mutation_strategy=c.mutation_strategy,
                source_directive_batch_id=c.source_directive_batch_id,
            )
        eval_candidates = list(candidates)
        pre_scored = []

    # Mark all to-run candidates as "evaluating" and add to active_evals (sequential)
    for ec in eval_candidates:
        version = ec.prompt_version if isinstance(ec, BatchEvalCandidate) else ec.prompt_version
        _update_candidate_eval_status(run_id, version, "evaluating")
        _add_to_active_evals(run_id, version)

    # Build BatchEvalCandidate wrappers for Candidate objects (recovery mode)
    def _to_batch_candidate(ec: BatchEvalCandidate | Candidate) -> BatchEvalCandidate:
        if isinstance(ec, BatchEvalCandidate):
            return ec
        return BatchEvalCandidate(
            prompt_version=ec.prompt_version,
            parent_version=ec.parent_version,
            mutation_strategy=getattr(ec, "mutation_strategy", "targeted") or "targeted",
            source_directive_batch_id=getattr(ec, "source_directive_batch_id", "") or "",
            example_ids=list(getattr(ec, "example_ids", [])),
        )

    batch_candidates = [_to_batch_candidate(ec) for ec in eval_candidates]

    # Launch all evals concurrently
    raw_results = await asyncio.gather(
        *[
            _run_single_eval(bc, run_id, out_dir, shared_limiter)
            for bc in batch_candidates
        ],
        return_exceptions=True,
    )

    # Process results SEQUENTIALLY to avoid concurrent file writes
    succeeded: list[CandidateEvalOutcome] = list(pre_scored)
    failed: list[CandidateEvalOutcome] = []

    for bc, raw in zip(batch_candidates, raw_results):
        if isinstance(raw, Exception):
            _update_candidate_eval_status(run_id, bc.prompt_version, "failed")
            _remove_from_active_evals(run_id, bc.prompt_version)
            logger.error("Eval failed for %s: %s", bc.prompt_version, raw)
            failed.append(
                CandidateEvalOutcome(
                    prompt_version=bc.prompt_version,
                    quality_score=None,
                    cost=None,
                    error=str(raw),
                    score_report_path=None,
                )
            )
        else:
            outcome: CandidateEvalOutcome = raw
            _update_candidate_eval_status(run_id, bc.prompt_version, "scored")
            _remove_from_active_evals(run_id, bc.prompt_version)
            if outcome.quality_score is not None and outcome.cost is not None:
                record_eval_result(
                    run_id=run_id,
                    prompt_version=bc.prompt_version,
                    quality_score=outcome.quality_score,
                    cost=outcome.cost,
                )
            succeeded.append(outcome)

    return BatchEvalResult(succeeded=succeeded, failed=failed)


# ---------------------------------------------------------------------------
# MCP tool
# ---------------------------------------------------------------------------


@mcp.tool()
async def run_batch_eval(
    ctx: Context,
    run_id: str,
    candidates: list[dict],
) -> str:
    """[Stage 4: Refinement Loop] Evaluate multiple candidate prompts concurrently.

    Registers all candidates, launches evaluations in parallel, and records
    results. When called with an empty candidates list, operates in recovery
    mode: resumes any in-flight or unstarted evaluations from the previous run.

    Args:
        run_id: Pipeline run identifier.
        candidates: List of BatchEvalCandidate dicts. Pass [] for recovery mode.

    Returns:
        JSON-serialized BatchEvalResult with succeeded and failed lists.
    """
    import json

    project_dir = await _project_dir_mod.resolve_project_dir(ctx)

    check_artifacts(
        project_dir / "outputs" / run_id / "analysis" / "dev.jsonl",
        stage=4,
        stage_name="Refinement Loop",
        hint="Complete data validation and dataset split first.",
    )

    try:
        parsed = [BatchEvalCandidate.model_validate(c) for c in candidates]
    except Exception as exc:
        raise ToolError(f"Invalid candidate data: {exc}") from exc

    try:
        result = await run_batch_eval_impl(
            run_id=run_id,
            candidates=parsed,
            project_dir=project_dir,
        )
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc

    return result.model_dump_json(indent=2)
```

**Implementation notes:**

- `_run_single_eval` reuses `EvalRunnerAgent` and `build_pipeline_config` from `prompt_building_tools.py`. The shared `TokenBucketRateLimiter` is injected via `RunDependencies.rate_limiter` (added in Task 6). In tests, `_run_single_eval` is mocked at the module level, so `_deps_override` in context is not exercised in unit tests — it exists so real eval runs can optionally pick it up, though the current `EvalRunnerAgent.run` does not read it. A follow-up can thread it through `_wire_dependencies` once the integration pattern is validated.
- `_update_candidate_eval_status`, `_add_to_active_evals`, `_remove_from_active_evals` are thin wrappers around `_load_pending`/`_save_pending` and `_load_state`/`_save_state` from `search_ops.py`. They are extracted as named functions to enable precise mocking in tests.
- `register_candidate` must accept `eval_status`, `mutation_strategy`, and `source_directive_batch_id` parameters (added in Task 3).
- `SearchState.active_evals` must exist (added in Task 1).

- [ ] **Step 4: Register `run_batch_eval` in `prompt_building_tools.py`**

In `odysseus/mcp/prompt_building_tools.py`, add the import at the bottom of the file (the tool auto-registers via `@mcp.tool()` on import):

```python
# At the bottom of odysseus/mcp/prompt_building_tools.py, after the last tool definition:
import odysseus.mcp.batch_eval as _batch_eval  # noqa: E402, F401  — registers run_batch_eval tool
```

- [ ] **Step 5: Run failing tests again (should now pass)**

Run: `uv run pytest tests/test_batch_eval.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run prompt_building_tools tests to check for regressions**

Run: `uv run pytest tests/ -k "prompt_building or batch_eval" -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add odysseus/mcp/batch_eval.py odysseus/mcp/prompt_building_tools.py tests/test_batch_eval.py
git commit -m "feat: implement run_batch_eval tool for concurrent multi-candidate evaluation"
```

---

## Task 8: Update preprocessor to build `batch_outcomes` in `ReviewBriefing`

**Files:**
- Modify: `odysseus/agents/review/preprocessor.py`
- Modify: `odysseus/mcp/review_tools.py`
- Test: `tests/test_review_preprocessor.py`

**Context:** `build_review_briefing` (lines 560–676 of `preprocessor.py`) assembles a `ReviewBriefing` from raw pipeline data. It receives `search_state` (already typed as `Any`, but is a `SearchState`). The `ReviewBriefing` model (line 174 of `review/models.py`) currently has no `beam_width` or `batch_outcomes` fields — these were added in Task 2. The `build_review_briefing` in `review_tools.py` (lines 24–163) calls `build_review_briefing` and must pass the new parameters.

Steps:

- [ ] **Step 1: Write failing tests for preprocessor changes**

```python
# In tests/test_review_preprocessor.py, add new test class:

import pytest
from unittest.mock import MagicMock

from odysseus.agents.prompt_builder.search import Candidate, SearchState
from odysseus.agents.review.models import DirectiveBatch, EditDirective, ReviewBriefing
from odysseus.agents.review.preprocessor import build_review_briefing


def _make_search_state(**overrides) -> SearchState:
    defaults = dict(
        search_state_id="run1",
        backend="anthropic",
        round=2,
        beam_width=3,
        pareto_front=[
            Candidate(
                prompt_version="v5",
                parent_version=None,
                quality_score=0.80,
                cost=0.05,
                round_introduced=1,
            )
        ],
    )
    defaults.update(overrides)
    return SearchState(**defaults)


def _make_directive_batch(batch_id: str, parent: str, strategy: str = "targeted") -> DirectiveBatch:
    return DirectiveBatch(
        directive_batch_id=batch_id,
        parent_version=parent,
        directives=[
            EditDirective(
                directive_id="d1",
                target_version=parent,
                block_type="rule",
                block_identifier="Rule 1",
                granularity="micro",
                directive="Test directive",
                priority="high",
            )
        ],
        mutation_strategy=strategy,
        priority=1,
    )


def _make_candidate_with_batch(version: str, batch_id: str, score: float = 0.82) -> Candidate:
    return Candidate(
        prompt_version=version,
        parent_version="v5",
        quality_score=score,
        cost=0.01,
        round_introduced=2,
        eval_status="scored",
        source_directive_batch_id=batch_id,
    )


class TestBuildReviewBriefingBeamWidth:
    def test_beam_width_from_search_state_flows_through(self):
        """beam_width is read from search_state and included in ReviewBriefing."""
        state = _make_search_state(beam_width=4)

        briefing = build_review_briefing(
            search_state=state,
            score_reports={},
            historical_reports={},
            prompt_texts={},
            mutation_log=[],
            directive_history=[],
            holdout_examples=[],
            candidate_versions=[],
            parent_versions={},
            directive_batches=[],
        )

        assert briefing.beam_width == 4

    def test_beam_width_defaults_to_2_when_not_on_state(self):
        """Falls back to 2 (SearchState default) when beam_width not explicitly set."""
        # SearchState default beam_width is 2
        state = _make_search_state()
        state_no_beam = state.model_copy(update={"beam_width": 2})

        briefing = build_review_briefing(
            search_state=state_no_beam,
            score_reports={},
            historical_reports={},
            prompt_texts={},
            mutation_log=[],
            directive_history=[],
            holdout_examples=[],
            candidate_versions=[],
            parent_versions={},
            directive_batches=[],
        )

        assert briefing.beam_width == 2


class TestBuildReviewBriefingBatchOutcomes:
    def test_scored_candidate_produces_correct_batch_outcome(self):
        """Scored candidate with known parent produces BatchOutcome with quality_delta."""
        state = _make_search_state(
            beam_width=2,
            pareto_front=[
                Candidate(
                    prompt_version="v5",
                    parent_version=None,
                    quality_score=0.80,
                    cost=0.05,
                    round_introduced=1,
                )
            ],
        )
        batch = _make_directive_batch("b1", "v5", "targeted")
        candidate = _make_candidate_with_batch("v8", "b1", score=0.85)

        briefing = build_review_briefing(
            search_state=state,
            score_reports={
                "v8": {"metrics": {"accuracy": 0.85, "cost_quality_change": 0.01}},
                "v5": {"metrics": {"accuracy": 0.80, "cost_quality_change": 0.00}},
            },
            historical_reports={},
            prompt_texts={},
            mutation_log=[],
            directive_history=[],
            holdout_examples=[],
            candidate_versions=["v8"],
            parent_versions={"v8": "v5"},
            directive_batches=[batch],
            pending_candidates=[candidate],
        )

        assert len(briefing.batch_outcomes) == 1
        outcome = briefing.batch_outcomes[0]
        assert outcome.directive_batch_id == "b1"
        assert outcome.parent_version == "v5"
        assert outcome.mutation_strategy == "targeted"
        assert outcome.candidate_version == "v8"
        assert outcome.eval_status == "scored"
        # quality_delta = 0.85 - 0.80 = 0.05 (within float tolerance)
        assert outcome.quality_delta_vs_parent == pytest.approx(0.05, abs=1e-6)

    def test_failed_candidate_produces_batch_outcome_with_none_delta(self):
        """Failed candidate produces BatchOutcome with eval_status='failed' and None delta."""
        state = _make_search_state(beam_width=2)
        batch = _make_directive_batch("b2", "v5", "exploratory")
        candidate = Candidate(
            prompt_version="v9",
            parent_version="v5",
            quality_score=0.0,
            cost=0.0,
            round_introduced=2,
            eval_status="failed",
            source_directive_batch_id="b2",
        )

        briefing = build_review_briefing(
            search_state=state,
            score_reports={
                "v5": {"metrics": {"accuracy": 0.80, "cost_quality_change": 0.00}},
            },
            historical_reports={},
            prompt_texts={},
            mutation_log=[],
            directive_history=[],
            holdout_examples=[],
            candidate_versions=["v9"],
            parent_versions={"v9": "v5"},
            directive_batches=[batch],
            pending_candidates=[candidate],
        )

        assert len(briefing.batch_outcomes) == 1
        outcome = briefing.batch_outcomes[0]
        assert outcome.eval_status == "failed"
        assert outcome.quality_delta_vs_parent is None
        assert outcome.candidate_version == "v9"

    def test_batch_outcomes_empty_on_cold_start(self):
        """Empty directive_batches on cold start produces empty batch_outcomes."""
        state = _make_search_state(beam_width=2)

        briefing = build_review_briefing(
            search_state=state,
            score_reports={},
            historical_reports={},
            prompt_texts={},
            mutation_log=[],
            directive_history=[],
            holdout_examples=[],
            candidate_versions=[],
            parent_versions={},
            directive_batches=[],
            pending_candidates=[],
        )

        assert briefing.batch_outcomes == []

    def test_made_pareto_front_true_when_candidate_on_front(self):
        """made_pareto_front is True when candidate version is in pareto_front."""
        state = _make_search_state(
            beam_width=2,
            pareto_front=[
                Candidate(
                    prompt_version="v5",
                    parent_version=None,
                    quality_score=0.80,
                    cost=0.05,
                    round_introduced=1,
                ),
                Candidate(
                    prompt_version="v8",
                    parent_version="v5",
                    quality_score=0.85,
                    cost=0.06,
                    round_introduced=2,
                ),
            ],
        )
        batch = _make_directive_batch("b1", "v5", "targeted")
        candidate = _make_candidate_with_batch("v8", "b1", score=0.85)

        briefing = build_review_briefing(
            search_state=state,
            score_reports={
                "v8": {"metrics": {"accuracy": 0.85, "cost_quality_change": 0.01}},
                "v5": {"metrics": {"accuracy": 0.80, "cost_quality_change": 0.00}},
            },
            historical_reports={},
            prompt_texts={},
            mutation_log=[],
            directive_history=[],
            holdout_examples=[],
            candidate_versions=["v8"],
            parent_versions={"v8": "v5"},
            directive_batches=[batch],
            pending_candidates=[candidate],
        )

        assert briefing.batch_outcomes[0].made_pareto_front is True

    def test_made_pareto_front_false_when_candidate_not_on_front(self):
        """made_pareto_front is False when candidate version is not in pareto_front."""
        state = _make_search_state(
            beam_width=2,
            pareto_front=[
                Candidate(
                    prompt_version="v5",
                    parent_version=None,
                    quality_score=0.80,
                    cost=0.05,
                    round_introduced=1,
                )
            ],
        )
        batch = _make_directive_batch("b1", "v5", "targeted")
        candidate = _make_candidate_with_batch("v9", "b1", score=0.75)

        briefing = build_review_briefing(
            search_state=state,
            score_reports={
                "v9": {"metrics": {"accuracy": 0.75, "cost_quality_change": 0.01}},
                "v5": {"metrics": {"accuracy": 0.80, "cost_quality_change": 0.00}},
            },
            historical_reports={},
            prompt_texts={},
            mutation_log=[],
            directive_history=[],
            holdout_examples=[],
            candidate_versions=["v9"],
            parent_versions={"v9": "v5"},
            directive_batches=[batch],
            pending_candidates=[candidate],
        )

        assert briefing.batch_outcomes[0].made_pareto_front is False
```

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_review_preprocessor.py::TestBuildReviewBriefingBeamWidth tests/test_review_preprocessor.py::TestBuildReviewBriefingBatchOutcomes -v`
Expected: FAIL — `build_review_briefing` does not accept `directive_batches` / `pending_candidates`, `ReviewBriefing` has no `beam_width` / `batch_outcomes`

- [ ] **Step 3: Update `build_review_briefing` signature and body**

In `odysseus/agents/review/preprocessor.py`, update the `build_review_briefing` function:

1. Add imports at the top of the function or module (after existing imports):

```python
from odysseus.agents.review.models import BatchOutcome, DirectiveBatch
```

2. Update the function signature to accept `directive_batches` and `pending_candidates`:

```python
def build_review_briefing(
    *,
    search_state: Any,
    score_reports: dict[str, dict[str, Any]],
    historical_reports: dict[int, dict[str, dict[str, Any]]],
    prompt_texts: dict[str, str],
    mutation_log: list[MutationRecord],
    directive_history: list[DirectiveOutcome],
    holdout_examples: list[ExampleSummary],
    candidate_versions: list[str],
    parent_versions: dict[str, str | None],
    routing_context: RoutingContext | None = None,
    directive_batches: list[DirectiveBatch] | None = None,
    pending_candidates: list[Candidate] | None = None,
) -> ReviewBriefing:
```

3. After the existing step 7 (near-miss candidates) block, add the new step 8 before `briefing = ReviewBriefing(...)`:

```python
    # 8. Beam width and batch outcomes
    beam_width: int = getattr(search_state, "beam_width", 2)

    batch_outcomes: list[BatchOutcome] = []
    if directive_batches:
        # Build a lookup: source_directive_batch_id -> Candidate
        pending_by_batch_id: dict[str, Candidate] = {}
        if pending_candidates:
            for pc in pending_candidates:
                bid = getattr(pc, "source_directive_batch_id", None)
                if bid:
                    pending_by_batch_id[bid] = pc

        # Build a lookup: prompt_version -> quality_score for Pareto front members
        front_quality: dict[str, float] = {
            c.prompt_version: c.quality_score for c in pareto_front
        }

        for batch in directive_batches:
            matched = pending_by_batch_id.get(batch.directive_batch_id)
            if matched is None:
                # Generation failed before registration — no candidate version
                batch_outcomes.append(
                    BatchOutcome(
                        directive_batch_id=batch.directive_batch_id,
                        parent_version=batch.parent_version,
                        mutation_strategy=batch.mutation_strategy,
                        candidate_version=None,
                        eval_status=None,
                        quality_delta_vs_parent=None,
                        made_pareto_front=False,
                    )
                )
                continue

            eval_status = getattr(matched, "eval_status", None)
            candidate_score = matched.quality_score if eval_status == "scored" else None
            parent_score = front_quality.get(batch.parent_version)
            quality_delta = (
                (candidate_score - parent_score)
                if (candidate_score is not None and parent_score is not None)
                else None
            )
            made_front = matched.prompt_version in front_versions

            batch_outcomes.append(
                BatchOutcome(
                    directive_batch_id=batch.directive_batch_id,
                    parent_version=batch.parent_version,
                    mutation_strategy=batch.mutation_strategy,
                    candidate_version=matched.prompt_version,
                    eval_status=eval_status if eval_status in ("scored", "failed") else None,
                    quality_delta_vs_parent=quality_delta,
                    made_pareto_front=made_front,
                )
            )
```

4. Add `beam_width=beam_width, batch_outcomes=batch_outcomes` to the `ReviewBriefing(...)` constructor call.

- [ ] **Step 4: Update `build_review_briefing` in `review_tools.py`**

In `odysseus/mcp/review_tools.py`, update the call to `build_review_briefing` (lines 140–151) to pass `directive_batches` and `pending_candidates`:

```python
    # Load directive batches for current round (new — for batch_outcomes)
    from odysseus.agents.review.ops import load_directive_batches
    from odysseus.agents.prompt_builder.search_ops import _load_pending

    out_path = Path(output_dir) if Path(output_dir).is_absolute() else project_dir / output_dir
    try:
        directive_batches = load_directive_batches(run_id, output_dir=out_path)
    except FileNotFoundError:
        directive_batches = []

    try:
        pending_candidates = _load_pending(run_id, out_path)
    except FileNotFoundError:
        pending_candidates = []

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
        routing_context=routing_context,
        directive_batches=directive_batches,
        pending_candidates=pending_candidates,
    )
```

Note: `load_directive_batches` is the renamed function from Task 4 (`load_edit_directives` → `load_directive_batches`). If Task 4 is not yet merged, use `load_edit_directives` temporarily and update after.

- [ ] **Step 5: Run new tests to verify they pass**

Run: `uv run pytest tests/test_review_preprocessor.py::TestBuildReviewBriefingBeamWidth tests/test_review_preprocessor.py::TestBuildReviewBriefingBatchOutcomes -v`
Expected: ALL PASS

- [ ] **Step 6: Run full preprocessor test suite to check for regressions**

Run: `uv run pytest tests/test_review_preprocessor.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add odysseus/agents/review/preprocessor.py odysseus/mcp/review_tools.py tests/test_review_preprocessor.py
git commit -m "feat: add beam_width and batch_outcomes to build_review_briefing output"
```

---

## Task 9: Update pipeline status detection and instruction templates

**Files:**
- Modify: `odysseus/agents/pipeline/status.py`
- Modify: `odysseus/agents/pipeline/instructions.py`
- Modify: `odysseus/mcp/server.py`
- Test: `tests/test_pipeline_status.py`

**Context:** `_detect_stage_4_phase` in `status.py` (lines 483–530) currently returns one of `"rerun"`, `"cold_start"`, `"build_v1"`, `"review"`, `"build"`. It reads `loop_phase` from `search_state.json` (lines 514–528). The change: after confirming `loop_phase == "build"`, also read `active_evals`; if non-empty, return `"build_recovering"`. `_next_action_for_stage_4` (lines 533–594) maps phase strings to (action, tools, prompts, instruction) tuples — add `"build_recovering"` to `phase_config`. `_BUILD_TOOLS` (lines 50–58) lists `"run_eval"` — replace with `"run_batch_eval"`. `STAGE_REGISTRY["prompt_building"]` in `server.py` (lines 65–75) lists `"run_eval"` — add `"run_batch_eval"` (keep `"run_eval"` for backward compat with rerun mode, which is single-candidate). `STAGE_4_BUILD_INSTRUCTION` in `instructions.py` (lines 120–137) references `run_eval` in the sub-agent tools list — replace with `run_batch_eval`.

Steps:

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pipeline_status.py
# Add new test class (or create file if it doesn't exist):

import json
import pytest
from pathlib import Path

from odysseus.agents.pipeline.status import _detect_stage_4_phase, _next_action_for_stage_4
from odysseus.agents.pipeline.instructions import (
    STAGE_4_BUILD_INSTRUCTION,
    STAGE_4_BUILD_RECOVERING_INSTRUCTION,
)


def _write_search_state(run_dir: Path, data: dict) -> None:
    search_dir = run_dir / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    (search_dir / "search_state.json").write_text(json.dumps(data))


def _write_directive_history(run_dir: Path) -> None:
    search_dir = run_dir / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    (search_dir / "directive_history.json").write_text("[]")


def _write_v1_prompt(run_dir: Path) -> None:
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "v1.txt").write_text("prompt text")


class TestDetectStage4BuildRecovering:
    def test_detect_build_recovering_when_active_evals_non_empty(self, tmp_path):
        """loop_phase='build' + non-empty active_evals → 'build_recovering'."""
        run_dir = tmp_path / "run1"
        _write_directive_history(run_dir)
        _write_v1_prompt(run_dir)
        _write_search_state(run_dir, {
            "loop_phase": "build",
            "active_evals": ["v8", "v9"],
            "converged": False,
        })

        phase = _detect_stage_4_phase(run_dir, rerun_config=None)

        assert phase == "build_recovering"

    def test_detect_build_normal_when_active_evals_empty(self, tmp_path):
        """loop_phase='build' + empty active_evals → 'build' (not recovering)."""
        run_dir = tmp_path / "run1"
        _write_directive_history(run_dir)
        _write_v1_prompt(run_dir)
        _write_search_state(run_dir, {
            "loop_phase": "build",
            "active_evals": [],
            "converged": False,
        })

        phase = _detect_stage_4_phase(run_dir, rerun_config=None)

        assert phase == "build"

    def test_detect_build_normal_when_active_evals_field_absent(self, tmp_path):
        """Old search_state.json without active_evals field → 'build' (backward compat)."""
        run_dir = tmp_path / "run1"
        _write_directive_history(run_dir)
        _write_v1_prompt(run_dir)
        _write_search_state(run_dir, {
            "loop_phase": "build",
            "converged": False,
            # no active_evals key
        })

        phase = _detect_stage_4_phase(run_dir, rerun_config=None)

        assert phase == "build"

    def test_detect_review_unaffected_by_active_evals(self, tmp_path):
        """loop_phase='review' always returns 'review' regardless of active_evals."""
        run_dir = tmp_path / "run1"
        _write_directive_history(run_dir)
        _write_v1_prompt(run_dir)
        _write_search_state(run_dir, {
            "loop_phase": "review",
            "active_evals": ["v8"],  # should be ignored for review phase
            "converged": False,
        })

        phase = _detect_stage_4_phase(run_dir, rerun_config=None)

        assert phase == "review"


class TestNextActionBuildRecovering:
    def test_build_recovering_maps_to_recovering_instruction(self, tmp_path):
        """'build_recovering' phase returns STAGE_4_BUILD_RECOVERING_INSTRUCTION."""
        run_dir = tmp_path / "run1"
        _write_directive_history(run_dir)
        _write_v1_prompt(run_dir)
        _write_search_state(run_dir, {
            "loop_phase": "build",
            "active_evals": ["v8"],
            "converged": False,
        })

        action, tools, prompts, instruction = _next_action_for_stage_4(run_dir)

        assert "build_recovering" in action.lower() or "recovering" in action.lower()
        assert instruction == STAGE_4_BUILD_RECOVERING_INSTRUCTION
        assert "run_batch_eval" in tools

    def test_build_recovering_instruction_contains_recovery_mode_text(self):
        """STAGE_4_BUILD_RECOVERING_INSTRUCTION mentions recovery mode and run_batch_eval."""
        assert "RECOVERY MODE" in STAGE_4_BUILD_RECOVERING_INSTRUCTION
        assert "run_batch_eval" in STAGE_4_BUILD_RECOVERING_INSTRUCTION
        assert "active_evals" in STAGE_4_BUILD_RECOVERING_INSTRUCTION

    def test_build_instruction_references_run_batch_eval(self):
        """STAGE_4_BUILD_INSTRUCTION lists run_batch_eval (not run_eval) in sub-agent tools."""
        assert "run_batch_eval" in STAGE_4_BUILD_INSTRUCTION


class TestBuildToolsList:
    def test_build_tools_contains_run_batch_eval(self):
        """_BUILD_TOOLS contains run_batch_eval."""
        from odysseus.agents.pipeline.status import _BUILD_TOOLS
        assert "run_batch_eval" in _BUILD_TOOLS

    def test_build_tools_does_not_contain_run_eval(self):
        """_BUILD_TOOLS no longer contains run_eval (replaced by run_batch_eval)."""
        from odysseus.agents.pipeline.status import _BUILD_TOOLS
        assert "run_eval" not in _BUILD_TOOLS

    def test_stage_registry_prompt_building_contains_run_batch_eval(self):
        """STAGE_REGISTRY['prompt_building'] contains run_batch_eval."""
        from odysseus.mcp.server import STAGE_REGISTRY
        assert "run_batch_eval" in STAGE_REGISTRY["prompt_building"]
```

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_pipeline_status.py::TestDetectStage4BuildRecovering tests/test_pipeline_status.py::TestNextActionBuildRecovering tests/test_pipeline_status.py::TestBuildToolsList -v`
Expected: FAIL — `build_recovering` phase not detected, `STAGE_4_BUILD_RECOVERING_INSTRUCTION` does not exist, `_BUILD_TOOLS` still has `run_eval`

- [ ] **Step 3: Update `_detect_stage_4_phase` in `status.py`**

In `odysseus/agents/pipeline/status.py`, replace lines 514–530 (the normal loop / `loop_phase` reading block):

```python
    # Phase 3: Normal loop — read loop_phase from search state
    loop_phase = "review"
    if search_state_path.is_file():
        try:
            data = json.loads(search_state_path.read_text())
            raw_phase = data.get("loop_phase", "review")
            if raw_phase not in _VALID_LOOP_PHASES:
                logger.warning(
                    "Unexpected loop_phase '%s' in %s/search/search_state.json, defaulting to 'review'",
                    raw_phase,
                    run_dir,
                )
            else:
                loop_phase = raw_phase

            # Detect crash-recovery: build phase with in-flight evals
            if loop_phase == "build":
                active_evals = data.get("active_evals", [])
                if active_evals:
                    return "build_recovering"

        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("Failed to parse search_state.json in %s: %s", run_dir, exc)

    return loop_phase
```

- [ ] **Step 4: Update `_BUILD_TOOLS` in `status.py`**

Replace `"run_eval"` with `"run_batch_eval"` in `_BUILD_TOOLS`:

```python
_BUILD_TOOLS: list[str] = [
    "get_search_state",
    "get_edit_directives",
    "init_search_state",
    "register_candidate",
    "record_eval_result",
    "advance_round_tool",
    "run_batch_eval",
]
```

- [ ] **Step 5: Add `"build_recovering"` to `phase_config` in `_next_action_for_stage_4`**

In `_next_action_for_stage_4`, add the `"build_recovering"` entry to `phase_config` after the `"build"` entry (import `STAGE_4_BUILD_RECOVERING_INSTRUCTION` at the top of the file):

```python
        "build_recovering": (
            "Stage 4 — build phase (recovering): in-flight evaluations detected. "
            "Spawn the Prompt Builder in recovery mode to resume interrupted evals. "
            "REQUIRED: activate prompt 'odysseus_prompt_builder' before calling any build tools.",
            _BUILD_TOOLS,
            ["odysseus_prompt_builder"],
            STAGE_4_BUILD_RECOVERING_INSTRUCTION,
        ),
```

- [ ] **Step 6: Add `STAGE_4_BUILD_RECOVERING_INSTRUCTION` to `instructions.py`**

In `odysseus/agents/pipeline/instructions.py`, add after `STAGE_4_BUILD_INSTRUCTION` (before `STAGE_4_RERUN_INSTRUCTION`):

```python
STAGE_4_BUILD_RECOVERING_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') "
    "BEFORE spawning the sub-agent.\n\n"
    "RECOVERY MODE: active_evals is non-empty. The sub-agent must call run_batch_eval "
    "with an empty candidates list to resume in-flight evaluations before calling "
    "advance_round.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state, get_edit_directives, "
    "init_search_state, register_candidate, record_eval_result, "
    "advance_round_tool, run_batch_eval\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)
```

Also update the import in `status.py` to include `STAGE_4_BUILD_RECOVERING_INSTRUCTION`.

- [ ] **Step 7: Update `STAGE_4_BUILD_INSTRUCTION` in `instructions.py`**

Replace `run_eval` with `run_batch_eval` in the sub-agent tools list inside `STAGE_4_BUILD_INSTRUCTION`:

```python
STAGE_4_BUILD_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state, get_edit_directives, "
    "init_search_state, register_candidate, record_eval_result, "
    "advance_round_tool, run_batch_eval\n"
    "Your tools: get_pipeline_status only\n\n"
    "NOTE: optimize_routing_prompt is the pipeline entry-point tool (orchestrator-level only). "
    "Do not call it from within the sub-agent.\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)
```

- [ ] **Step 8: Add `run_batch_eval` to `STAGE_REGISTRY["prompt_building"]` in `server.py`**

In `odysseus/mcp/server.py`, update the `"prompt_building"` entry:

```python
    "prompt_building": [
        "init_search_state",
        "register_candidate",
        "run_eval",         # retained for rerun mode (single-candidate)
        "run_batch_eval",   # new — primary eval tool for normal build rounds
        "record_eval_result",
        "advance_round_tool",
        "get_search_state",
        "get_edit_directives",
        "save_prompt",
        "get_pipeline_status",
    ],
```

- [ ] **Step 9: Run all new tests to verify they pass**

Run: `uv run pytest tests/test_pipeline_status.py::TestDetectStage4BuildRecovering tests/test_pipeline_status.py::TestNextActionBuildRecovering tests/test_pipeline_status.py::TestBuildToolsList -v`
Expected: ALL PASS

- [ ] **Step 10: Run full pipeline status test suite to check for regressions**

Run: `uv run pytest tests/test_pipeline_status.py -v`
Expected: ALL PASS

- [ ] **Step 11: Commit**

```bash
git add odysseus/agents/pipeline/status.py odysseus/agents/pipeline/instructions.py odysseus/mcp/server.py tests/test_pipeline_status.py
git commit -m "feat: add build_recovering phase detection and STAGE_4_BUILD_RECOVERING_INSTRUCTION"
```

---

## Task 10: Add diversity enforcement validation to `record_directive_outcomes`

**Depends on:** Task 3 (parameter rename from `edit_directives` to `directive_batches`)

**Files:**
- Modify: `odysseus/mcp/review_tools.py`
- Test: `tests/test_review_tools.py` (create if needed, or add to existing)

**Context:** `record_directive_outcomes` currently accepts `directive_batches` (renamed from `edit_directives` in Task 3) and persists them via `save_directive_batches`. After that persistence, two new validations must run: (1) batch count must equal `beam_width` from `SearchState`; (2) when `beam_width >= 3`, at least one batch must have `mutation_strategy == "exploratory"`. The validation happens on the already-parsed `DirectiveBatch` objects, before the loop phase transition. If either check fails, return a descriptive JSON error and do NOT flip `loop_phase` to `"build"`.

Steps:

- [ ] **Step 1: Write failing test — wrong batch count**

```python
# tests/test_review_tools.py

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.server.fastmcp import Context


def _make_ctx(project_dir: Path) -> MagicMock:
    ctx = MagicMock(spec=Context)
    ctx.request_context = MagicMock()
    ctx.request_context.lifespan_context = {"project_dir": str(project_dir)}
    return ctx


def _make_batch(batch_id: str, strategy: str = "targeted") -> dict:
    return {
        "directive_batch_id": batch_id,
        "parent_version": "v3",
        "directives": [],
        "mutation_strategy": strategy,
        "priority": 1,
    }


def _write_search_state(project_dir: Path, run_id: str, beam_width: int) -> None:
    search_dir = project_dir / "outputs" / run_id / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "search_state_id": run_id,
        "backend": "anthropic",
        "round": 2,
        "beam_width": beam_width,
        "min_beam_width": 2,
        "max_beam_width": 5,
        "active_evals": [],
        "loop_phase": "review",
        "converged": False,
        "mutation_mode": "targeted",
        "stagnation_count": 0,
        "convergence_limit": 5,
        "stagnation_limit": 3,
        "max_rounds": 20,
        "epsilon": 0.001,
        "pareto_front": [],
        "round_history": [],
        "total_routing_cost": 0.0,
    }
    (search_dir / "search_state.json").write_text(json.dumps(state))


class TestRecordDirectiveOutcomesValidatesBatchCount:
    @pytest.mark.asyncio
    async def test_record_directive_outcomes_validates_batch_count(self, tmp_path):
        """3 batches when beam_width=2 → validation error, loop_phase not flipped."""
        from odysseus.mcp.review_tools import record_directive_outcomes

        run_id = "run1"
        _write_search_state(tmp_path, run_id, beam_width=2)
        ctx = _make_ctx(tmp_path)

        batches = [
            _make_batch("b1", "targeted"),
            _make_batch("b2", "targeted"),
            _make_batch("b3", "exploratory"),  # 3 batches, beam_width=2 → error
        ]

        result_str = await record_directive_outcomes(
            ctx=ctx,
            run_id=run_id,
            outcomes=[],
            loop_signal={"action": "refine", "reason": "continue"},
            directive_batches=batches,
            output_dir=str(tmp_path / "outputs"),
        )
        result = json.loads(result_str)
        assert "error" in result
        assert "beam_width" in result["error"].lower() or "batch" in result["error"].lower()

        # loop_phase must NOT have been flipped to "build"
        state_path = tmp_path / "outputs" / run_id / "search" / "search_state.json"
        state = json.loads(state_path.read_text())
        assert state.get("loop_phase") == "review"
```

- [ ] **Step 2: Write failing test — diversity not enforced for beam_width=3**

```python
    @pytest.mark.asyncio
    async def test_record_directive_outcomes_validates_diversity(self, tmp_path):
        """beam_width=3, all targeted → diversity validation error."""
        from odysseus.mcp.review_tools import record_directive_outcomes

        run_id = "run1"
        _write_search_state(tmp_path, run_id, beam_width=3)
        ctx = _make_ctx(tmp_path)

        batches = [
            _make_batch("b1", "targeted"),
            _make_batch("b2", "targeted"),
            _make_batch("b3", "targeted"),  # none exploratory → error
        ]

        result_str = await record_directive_outcomes(
            ctx=ctx,
            run_id=run_id,
            outcomes=[],
            loop_signal={"action": "refine", "reason": "continue"},
            directive_batches=batches,
            output_dir=str(tmp_path / "outputs"),
        )
        result = json.loads(result_str)
        assert "error" in result
        assert "exploratory" in result["error"].lower()

        state_path = tmp_path / "outputs" / run_id / "search" / "search_state.json"
        state = json.loads(state_path.read_text())
        assert state.get("loop_phase") == "review"
```

- [ ] **Step 3: Write failing test — diversity NOT required for beam_width=2**

```python
class TestRecordDirectiveOutcomesDiversityNotRequired:
    @pytest.mark.asyncio
    async def test_record_directive_outcomes_diversity_not_required_beam_2(self, tmp_path):
        """beam_width=2, all targeted → OK (diversity rule only applies when beam_width >= 3)."""
        from odysseus.mcp.review_tools import record_directive_outcomes

        run_id = "run1"
        _write_search_state(tmp_path, run_id, beam_width=2)
        ctx = _make_ctx(tmp_path)

        batches = [
            _make_batch("b1", "targeted"),
            _make_batch("b2", "targeted"),
        ]

        result_str = await record_directive_outcomes(
            ctx=ctx,
            run_id=run_id,
            outcomes=[],
            loop_signal={"action": "refine", "reason": "continue"},
            directive_batches=batches,
            output_dir=str(tmp_path / "outputs"),
        )
        result = json.loads(result_str)
        assert "error" not in result
        assert result.get("directive_batches_saved") == 2
```

- [ ] **Step 4: Write failing test — happy path**

```python
class TestRecordDirectiveOutcomesHappyPath:
    @pytest.mark.asyncio
    async def test_record_directive_outcomes_happy_path(self, tmp_path):
        """Correct count + required diversity → success, loop_phase flipped to 'build'."""
        from odysseus.mcp.review_tools import record_directive_outcomes

        run_id = "run1"
        _write_search_state(tmp_path, run_id, beam_width=3)
        ctx = _make_ctx(tmp_path)

        batches = [
            _make_batch("b1", "targeted"),
            _make_batch("b2", "targeted"),
            _make_batch("b3", "exploratory"),  # satisfies diversity
        ]

        result_str = await record_directive_outcomes(
            ctx=ctx,
            run_id=run_id,
            outcomes=[],
            loop_signal={"action": "refine", "reason": "continue"},
            directive_batches=batches,
            output_dir=str(tmp_path / "outputs"),
        )
        result = json.loads(result_str)
        assert "error" not in result
        assert result.get("directive_batches_saved") == 3

        state_path = tmp_path / "outputs" / run_id / "search" / "search_state.json"
        state = json.loads(state_path.read_text())
        assert state.get("loop_phase") == "build"
```

- [ ] **Step 5: Run failing tests**

Run: `uv run pytest tests/test_review_tools.py -v`
Expected: FAIL — no validation logic exists yet

- [ ] **Step 6: Implement validation in `record_directive_outcomes`**

In `odysseus/mcp/review_tools.py`, update the `record_directive_outcomes` function. After the existing directive batches persistence block (the `if directive_batches is not None:` block), add the validation before the loop phase transition:

```python
    # Persist directive batches for Prompt Builder consumption
    if directive_batches is not None:
        from odysseus.agents.review.models import DirectiveBatch
        from odysseus.agents.review.ops import save_directive_batches

        parsed_batches = [DirectiveBatch.model_validate(d) for d in directive_batches]
        save_directive_batches(run_id, parsed_batches, output_dir=out)
        result["directive_batches_saved"] = len(parsed_batches)

        # Validate batch count against beam_width
        try:
            state = _load_state(run_id, out)
            beam_width: int = getattr(state, "beam_width", 2)
        except FileNotFoundError:
            beam_width = 2

        if len(parsed_batches) != beam_width:
            return json.dumps({
                "error": (
                    f"Batch count mismatch: received {len(parsed_batches)} directive batch(es) "
                    f"but beam_width is {beam_width}. "
                    f"You must emit exactly {beam_width} directive batch(es) — one per candidate slot."
                )
            })

        # Validate diversity: beam_width >= 3 requires at least one exploratory batch
        if beam_width >= 3:
            strategies = {b.mutation_strategy for b in parsed_batches}
            if "exploratory" not in strategies:
                return json.dumps({
                    "error": (
                        f"Diversity violation: beam_width is {beam_width} (>= 3), so at least one "
                        "directive batch must have mutation_strategy == 'exploratory'. "
                        "All batches are currently 'targeted' or 'structural'. "
                        "Add at least one exploratory batch to escape local optima."
                    )
                })
```

The validation block must be placed BEFORE the loop signal handling and the `_set_loop_phase` call so that a failed validation aborts early without transitioning the loop phase.

The full updated function body ordering becomes:
1. Parse and save `DirectiveOutcome` records (existing)
2. Parse and save `directive_batches` (existing, renamed from `edit_directives`)
3. **NEW**: validate batch count against `beam_width` — return error JSON if fails
4. **NEW**: validate diversity for `beam_width >= 3` — return error JSON if fails
5. Handle `loop_signal` (existing)
6. Call `_set_loop_phase(run_id, "build", ...)` (existing)

- [ ] **Step 7: Run all new tests to verify they pass**

Run: `uv run pytest tests/test_review_tools.py -v`
Expected: ALL PASS

- [ ] **Step 8: Run full review tool test suite to check for regressions**

Run: `uv run pytest tests/ -k "review" -v`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add odysseus/mcp/review_tools.py tests/test_review_tools.py
git commit -m "feat: add beam_width batch count and diversity validation to record_directive_outcomes"
```

---

## Task 11: Update Review Agent system prompt

**Files:**
- Modify: `odysseus/agents/prompts/review_agent_system.md`

No tests — this is a system prompt markdown file.

Steps:

- [ ] **Step 1: Read the current prompt to understand structure** (already done — see context above)

- [ ] **Step 2: Make the edits**

Apply the following changes to `odysseus/agents/prompts/review_agent_system.md`:

**Change 1: Replace the `edit_directives` output schema section with `directive_batches`**

Replace the `"edit_directives": [...]` block in the Output Contract JSON example (lines 113–138) with:

```diff
-  "edit_directives": [
-    {
-      "directive_id": "<string, e.g. d1, d2>",
-      "target_version": "<version string>",
-      "block_type": "<rule | example | output_schema | vocabulary>",
-      "block_identifier": "<e.g. Rule 2 | Example 5 | Output Schema>",
-      "granularity": "<macro | micro>",
-      "directive": "<string>",
-      "priority": "<high | medium | low>",
-      "example_content": {
-        "input": "<string — required when block_type is example>",
-        "route": "<string — required when block_type is example>",
-        "reasoning": "<string — required when block_type is example>",
-        "exclusions": [{"route": "<string>", "reason": "<string>"}]
-      }
-    }
-  ],
+  "directive_batches": [
+    {
+      "directive_batch_id": "<string, e.g. b1, b2>",
+      "parent_version": "<version string — Pareto front member to branch from>",
+      "directives": [
+        {
+          "directive_id": "<string, e.g. d1, d2>",
+          "target_version": "<version string>",
+          "block_type": "<rule | example | output_schema | vocabulary>",
+          "block_identifier": "<e.g. Rule 2 | Example 5 | Output Schema>",
+          "granularity": "<macro | micro>",
+          "directive": "<string>",
+          "priority": "<high | medium | low>",
+          "example_content": {
+            "input": "<string — required when block_type is example>",
+            "route": "<string — required when block_type is example>",
+            "reasoning": "<string — required when block_type is example>",
+            "exclusions": [{"route": "<string>", "reason": "<string>"}]
+          }
+        }
+      ],
+      "mutation_strategy": "<targeted | exploratory | structural>",
+      "priority": <int — execution order hint, lower runs first>
+    }
+  ],
```

**Change 2: Update the Output Contract descriptive text**

Replace the sentence immediately after the opening of the Output Contract section:

```diff
-Every candidate in the briefing must appear in both `candidate_ranking` and `promotion_decisions`. `directive_history_update` must cover every directive from the previous round's `edit_directives` (match by `directive_id`). Omit a field only if it is genuinely empty (e.g., `edit_directives: []` when no directives are warranted).
+Every candidate in the briefing must appear in both `candidate_ranking` and `promotion_decisions`. `directive_history_update` must cover every directive from the previous round's `directive_batches` (match by `directive_id` within each batch's `directives` list). Omit a field only if it is genuinely empty (e.g., `directive_batches: []` when no directives are warranted, such as on exit).
```

**Change 3: Add "Multi-parent branching" section**

Add the following section immediately after the `## Output Contract` section (before `## Evaluation Priorities`):

```markdown
## Directive Batch Contract

### Batch count

Emit exactly `beam_width` directive batches. Each batch produces exactly one candidate. `beam_width` is provided in `ReviewBriefing.beam_width`. The tool will reject your output if the batch count does not match.

### Multi-parent branching

Each batch specifies a `parent_version` — the Pareto front member the Prompt Builder will apply that batch's `directives` to, producing one child candidate. Batches may target different Pareto front members to explore independent directions in parallel. When the front has only one member, all batches necessarily share the same `parent_version`.

Choose `parent_version` to maximize exploration coverage:
- A batch targeting a high-quality front member with targeted edits exploits that candidate's strengths.
- A batch targeting a lower-cost front member with exploratory edits may open up a new cost/quality tradeoff.
- When two batches target the same parent, give them clearly differentiated `mutation_strategy` values to avoid redundant candidates.

### `mutation_strategy` values

| Value | Use when |
|---|---|
| `targeted` | Focused edits to specific blocks — rule tweaks, example refinements. Use when the search is making progress. |
| `exploratory` | Broader changes that explore new directions — new rules, example swaps, assembly policy changes. Use to escape local optima. |
| `structural` | Fundamental reorganization — section reordering, schema overhaul, major example replacement. Reserve for when both targeted and exploratory approaches have stagnated. |

Note: `SearchState.mutation_mode` (two-valued: `targeted | exploratory`) controls the overall search posture. `DirectiveBatch.mutation_strategy` (three-valued) is a per-batch instruction. You may assign `structural` to individual batches regardless of the current `mutation_mode`.
```

**Change 4: Add diversity enforcement rule to Anti-Patterns**

Add a new anti-pattern at the top of the `## Anti-Patterns` list (before anti-pattern 1):

```markdown
0. **Do not emit only `targeted` batches when `beam_width >= 3`.** When the beam is wide enough to support exploration, at least one batch must have `mutation_strategy == "exploratory"`. Emitting only `targeted` or `structural` batches at `beam_width >= 3` is a contract violation — `record_directive_outcomes` will reject your output with a descriptive error. Include at least one exploratory batch to avoid local-optima lock-in.
```

Renumber the existing anti-patterns 1–5 to 1–5 (the new entry is numbered 0 to preserve existing numbering, but in the actual prompt it should flow as a natural list — renumber all to 1–6 for clarity):

```markdown
## Anti-Patterns

Avoid these failure modes:

1. **Do not emit only `targeted` batches when `beam_width >= 3`.** When the beam is wide enough to support exploration, at least one batch must have `mutation_strategy == "exploratory"`. Emitting only `targeted` or `structural` batches at `beam_width >= 3` is a contract violation — `record_directive_outcomes` will reject your output with a descriptive error. Include at least one exploratory batch to avoid local-optima lock-in.

2. **Do not apply regression guards to block exploration.** Guards block promotion only. A candidate with a regression flag can and should continue as "refine" if it is structurally novel.

3. **Do not suggest only micro-edits when diversity is collapsing or the oracle gap is large.** Micro-edits tune a local optimum; they cannot break out of structural plateaus. When `prompt_similarity` is low or captured ratios are below 0.60, emit at least one macro directive.

4. **Do not re-suggest mutations that are already in `mutation_history.ineffective_mutations`.** If a mutation type has been tried and failed, recommend from `untried_mutation_types` instead.

5. **Do not exit when significant headroom and untried mutations exist.** If `candidate_quality_captured < 0.75` or `candidate_cost_captured < 0.70` and `untried_mutation_types` is non-empty, signal refine, not exit.

6. **Do not prune a structurally novel candidate solely because it regressed.** Mark it "refine" with targeted fix directives. Premature pruning kills exploration.
```

**Change 5: Update the cold-start section to use `directive_batches` framing**

In `## Cold-Start Phase (Round 0)`, step 5, replace:

```diff
-5. Call `record_directive_outcomes` with:
-   - `outcomes`: empty list `[]` (no prior directives to track on cold start)
-   - `loop_signal`: `{"action": "refine", "reason": "<your reason>"}`
-   - `edit_directives`: the full list of EditDirective objects from your ReviewResult
+5. Call `record_directive_outcomes` with:
+   - `outcomes`: empty list `[]` (no prior directives to track on cold start)
+   - `loop_signal`: `{"action": "refine", "reason": "<your reason>"}`
+   - `directive_batches`: a single-element list containing one `DirectiveBatch` with `directive_batch_id: "b0"`, `parent_version: "v0"` (sentinel for cold start), `directives`: the full list of EditDirective objects from your ReviewResult, `mutation_strategy: "structural"` (initial prompt construction), `priority: 1`
```

**Change 6: Update Exit verification section**

Replace the final `Exit verification` section:

```diff
-When calling `record_directive_outcomes`, include:
-- `loop_signal`: your complete loop signal object (this is how the system receives your convergence decision)
-- `edit_directives`: your complete list of edit directive objects from the ReviewResult (this persists them for the Prompt Builder to retrieve via `get_edit_directives`)
+When calling `record_directive_outcomes`, include:
+- `loop_signal`: your complete loop signal object (this is how the system receives your convergence decision)
+- `directive_batches`: your complete list of `DirectiveBatch` objects from the ReviewResult, each with `directive_batch_id`, `parent_version`, `directives`, `mutation_strategy`, and `priority` (this persists them for the Prompt Builder to retrieve via `get_edit_directives`)
```

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/prompts/review_agent_system.md
git commit -m "feat: update Review Agent system prompt for directive_batches, multi-parent branching, and diversity rule"
```

---

## Task 12: Update Prompt Builder system prompt

**Files:**
- Modify: `odysseus/agents/prompts/prompt_builder_system.md`

No tests — system prompt.

Steps:

- [ ] **Step 1: Read the current prompt to understand structure** (already done — see context above)

- [ ] **Step 2: Make the edits**

Apply the following changes to `odysseus/agents/prompts/prompt_builder_system.md`:

**Change 1: Update the Inputs table — `review_directives` row**

```diff
-| `review_directives` | list[EditDirective] | `get_edit_directives` | Block-level edit directives with `example_content`; retrieved via tool call (round 1+) |
+| `review_directives` | list[DirectiveBatch] | `get_edit_directives` | Directive batches with `parent_version`, `directives`, and `mutation_strategy`; retrieved via tool call (round 2+) |
```

**Change 2: Replace the Tools table**

Replace the existing `## Tools` table:

```diff
 | Tool | Purpose |
 |------|---------|
 | `init_search_state` | Initialize search state for optimization run |
 | `register_candidate` | Register a new prompt candidate |
-| `record_eval_result` | Record eval results for Pareto tracking |
 | `advance_round_tool` | Close round, update front, check convergence |
 | `get_search_state` | Read current search state |
 | `save_prompt` | Save compiled prompt text to disk |
 | `get_edit_directives` | Retrieve Review Agent's edit directives (block-level edits, example content) |
-| `run_eval` | Evaluate a prompt version against the dev set |
+| `run_batch_eval` | Register, evaluate, and record results for all candidates concurrently |
```

The `record_eval_result` and `run_eval` rows are removed. `run_batch_eval` replaces both. `register_candidate` is retained for the Phase 1 (v1) flow only. The updated table:

```markdown
| Tool | Purpose |
|------|---------|
| `init_search_state` | Initialize search state for optimization run |
| `register_candidate` | Register a new prompt candidate (Phase 1 / v1 only) |
| `record_eval_result` | Record eval results for Pareto tracking (Phase 1 / v1 only) |
| `advance_round_tool` | Close round, update front, check convergence |
| `get_search_state` | Read current search state |
| `save_prompt` | Save compiled prompt text to disk |
| `get_edit_directives` | Retrieve Review Agent's directive batches (round 2+) |
| `run_eval` | Evaluate a single prompt version (Phase 1 / v1 only) |
| `run_batch_eval` | Register, evaluate concurrently, and record results for all candidates (Phase 2+) |
```

**Change 3: Add recovery mode check at the start of Phase 2**

Replace the opening of `## Phase 2 — Optimization loop`:

```diff
 ## Phase 2 — Optimization loop

 Execute on round 2 and every subsequent round.

-1. **Receive feedback.** Call `get_edit_directives(run_id=run_id)` to retrieve the Review Agent's block-level edit directives. Read the latest ScoreReport from `eval_score_report`. Apply vocabulary directives (`block_type == 'vocabulary'`) as in Phase 1 step 5: use refined descriptions when compiling Categories and Decision Logic; ignore directives referencing unrecognized route or dimension names.
-2. **Read search state.** Call `get_search_state(search_state_id)`. Note the `mutation_mode` (set by the Review Agent's loop signal) and `pareto_front`.
+1. **Check for crash recovery.** Call `get_search_state(search_state_id)`. If `active_evals` is non-empty, you are in recovery mode — skip steps 2–5 and go directly to step 6 with an empty candidates list: call `run_batch_eval(run_id=run_id, candidates=[])` to resume in-flight evaluations, then proceed to step 7.
+2. **Receive directive batches.** Call `get_edit_directives(run_id=run_id)` to retrieve the Review Agent's directive batches (a `list[DirectiveBatch]`). Each batch has a `parent_version`, a `directives` list, and a `mutation_strategy`. Sort batches by `priority` (ascending) before processing. Apply vocabulary directives (`block_type == 'vocabulary'`) within each batch's `directives` list as in Phase 1 step 5.
+3. **Read search state.** Note `beam_width`, `mutation_mode`, and `pareto_front` from the search state. `beam_width` tells you how many candidates to generate — it should match the number of directive batches returned by `get_edit_directives`.
```

**Change 4: Replace the "Select parents" and "Generate child variants" steps**

Replace steps 3–6 of Phase 2 with the new pipelined generation flow:

```diff
-3. **Select parents.** Pick 1-2 parents from the Pareto front. If the front has only one member, use it as the sole parent with two different mutation strategies.
-4. **Generate child variants.** Create 1-2 child prompts per parent.
-
-   | Mutation mode | Strategy |
-   |---------------|----------|
-   | `targeted` | Apply Review Agent directives: paraphrase sections, reorder rules, tighten precision, swap or reorder few-shot examples |
-   | `exploratory` | Make larger structural changes: add/delete sections, completely different example sets, different prompting style |
-
-5. **Write children.** Call `save_prompt(run_id=run_id, prompt_version="vN", content=<child prompt text>)` for each child (increment version number sequentially). Search state is persisted under `outputs/<run_id>/search/`.
-6. **Evaluate each child.** For each child prompt:
-   - Call `register_candidate(run_id=run_id, prompt_version="vN", parent_version="vP", example_ids=[<complete list of holdout example IDs used in this child prompt>])`. The `example_ids` list must contain every holdout example ID in the child — the full set, not just changed examples.
-   - Call `run_eval(prompt_version="vN", data_source=dev_jsonl_path, backend=backend)`.
-   - Extract `quality_score` and `cost` from the ScoreReport.
-   - Call `record_eval_result(search_state_id, "vN", quality_score, cost)`.
+4. **Generate all candidates first — no tool calls during generation.** For each directive batch (sorted by `priority`):
+   a. Identify the batch's `parent_version` — this is the Pareto front member to apply the directives to. Load its prompt text from disk (it was saved by a previous `save_prompt` call).
+   b. Apply the batch's `directives` to that parent prompt, following the strategy indicated by `mutation_strategy`:
+      - `targeted`: apply focused block-level edits (rule tweaks, example substitutions, precision improvements)
+      - `exploratory`: make broader changes (new rules, different example sets, structural variations)
+      - `structural`: fundamental reorganization (section reordering, schema changes, major example overhaul)
+   c. Assign the next sequential version number (e.g., v8, v9, v10).
+   d. Call `save_prompt(run_id=run_id, prompt_version="vN", content=<child prompt text>)`.
+   e. Note the `example_ids` from the directives in this batch for later use in `run_batch_eval`.
+
+   **Do not call `register_candidate` or any eval tool during generation.** Complete all candidates before evaluating any of them.
+
+5. **Evaluate all candidates with a single `run_batch_eval` call.** Once all candidate prompts are saved, call:
+
+   ```
+   run_batch_eval(run_id=run_id, candidates=[
+     {
+       "prompt_version": "vN",
+       "parent_version": "vP",
+       "mutation_strategy": "<strategy from batch>",
+       "source_directive_batch_id": "<batch.directive_batch_id>",
+       "example_ids": [<all holdout example IDs in this candidate>]
+     },
+     ...  # one entry per candidate
+   ])
+   ```
+
+   `run_batch_eval` handles registration, concurrent evaluation, and result recording internally. The returned `BatchEvalResult` has `succeeded` and `failed` lists — you do not need to call `register_candidate` or `record_eval_result` separately for Phase 2.
```

Renumber the remaining steps accordingly:

- Old step 7 (Advance round) → new step 6
- Old step 8 (Read round result) → new step 7

**Change 5: Update the Constraints section**

Replace the `Deterministic tool calls` constraint:

```diff
-- **Deterministic tool calls.** Always register a candidate before evaluating it. Always record eval results before advancing the round.
+- **Tool call ordering.** In Phase 2: generate all candidates (save_prompt calls) before calling run_batch_eval. Call advance_round_tool only after run_batch_eval returns. In Phase 1: register_candidate → run_eval → record_eval_result → advance_round_tool.
```

**Change 6: Update the Entry verification section**

Replace the Phase 2 loop_phase check to mention recovery mode:

```diff
 If in the optimization loop (round 2+), also confirm `loop_phase` is `"build"` in the search state (call `get_search_state`). If it is `"review"`, stop: the Review Agent should have been dispatched instead.
+
+If `loop_phase` is `"build"` but `active_evals` is non-empty, you are in recovery mode. Proceed immediately to `run_batch_eval(run_id=run_id, candidates=[])` to resume interrupted evaluations.
```

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/prompts/prompt_builder_system.md
git commit -m "feat: update Prompt Builder system prompt for run_batch_eval, directive batches, and recovery mode"
```

---

## Final Integration Verification

After all tasks are complete:

- [ ] **Run full test suite**: `uv run pytest -v`
- [ ] **Run linter**: `uv run ruff check .`
- [ ] **Run type checker**: `uv run pyright`
- [ ] **Run formatter**: `uv run ruff format .`
- [ ] **Verify no regressions in existing tests**
- [ ] **Final commit with all remaining changes**

### Recommended Testing Order

1. `tests/test_prompt_builder_search.py` — model tests
2. `tests/test_review_models.py` — new model tests
3. `tests/test_review_ops.py` — persistence tests
4. `tests/test_prompt_builder_search_ops.py` — advance_round tests
5. `tests/test_batch_eval.py` — batch eval tool tests
6. `tests/test_review_preprocessor.py` — preprocessor tests
7. `tests/test_pipeline_status.py` — pipeline detection tests
8. `tests/test_review_tools.py` — diversity validation tests
9. Full suite: `uv run pytest`
