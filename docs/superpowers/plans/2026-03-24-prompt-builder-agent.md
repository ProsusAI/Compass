# Prompt Builder Agent Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Prompt Builder Agent — an LLM-driven agent with code-driven MCP tools for tournament-selection search optimization with Pareto tracking across quality and cost.

**Architecture:** Bottom-up implementation. Pure Pydantic models first, then stateful operations, then holdout filtering, then MCP tool wiring, then content resources, then the agent system prompt. Each layer is independently testable.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, FastMCP

**Spec:** `docs/superpowers/specs/2026-03-24-thp-77-prompt-builder-agent-design.md`

---

## Chunk 1: Search State Models + Pareto Logic

### Task 1: Candidate model

**Files:**
- Create: `odysseus/agents/prompt_builder_search.py`
- Test: `tests/test_prompt_builder_search.py`

- [ ] **Step 1: Write failing tests for Candidate**

```python
"""Tests for odysseus.agents.prompt_builder_search."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from odysseus.agents.prompt_builder_search import Candidate


class TestCandidate:
    def test_valid_construction(self) -> None:
        c = Candidate(
            prompt_version="v1",
            parent_version=None,
            quality_score=0.85,
            cost=0.12,
            round_introduced=1,
        )
        assert c.prompt_version == "v1"
        assert c.parent_version is None
        assert c.quality_score == 0.85
        assert c.cost == 0.12
        assert c.round_introduced == 1
        assert c.dominated is False  # default

    def test_with_parent(self) -> None:
        c = Candidate(
            prompt_version="v2",
            parent_version="v1",
            quality_score=0.90,
            cost=0.15,
            round_introduced=2,
        )
        assert c.parent_version == "v1"

    def test_empty_version_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Candidate(
                prompt_version="",
                parent_version=None,
                quality_score=0.5,
                cost=0.1,
                round_introduced=1,
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_builder_search.py::TestCandidate -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement Candidate**

Create `odysseus/agents/prompt_builder_search.py`:

```python
"""Search state models and Pareto dominance logic for the Prompt Builder Agent.

Pure data models (no I/O). Stateful operations live in prompt_builder_search_ops.py.

See: docs/superpowers/specs/2026-03-24-thp-77-prompt-builder-agent-design.md
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator


class Candidate(BaseModel):
    """A single prompt candidate in the search population.

    Fields:
        prompt_version: Version string (e.g., "v1"). Non-empty.
        parent_version: Version of the parent prompt, or None for initial.
        quality_score: Primary quality metric value (higher is better).
        cost: Total eval cost (lower is better).
        round_introduced: Round number when this candidate was created.
        dominated: Whether this candidate is dominated on the Pareto front.
    """

    prompt_version: str
    parent_version: str | None
    quality_score: float
    cost: float
    round_introduced: int
    dominated: bool = False

    @field_validator("prompt_version")
    @classmethod
    def version_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("prompt_version must be non-empty")
        return v.strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompt_builder_search.py::TestCandidate -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/prompt_builder_search.py tests/test_prompt_builder_search.py
git commit -m "feat: add Candidate model for prompt builder search"
```

### Task 2: RoundSummary model

**Files:**
- Modify: `odysseus/agents/prompt_builder_search.py`
- Modify: `tests/test_prompt_builder_search.py`

- [ ] **Step 1: Write failing tests for RoundSummary**

Append to `tests/test_prompt_builder_search.py`:

```python
from odysseus.agents.prompt_builder_search import RoundSummary


class TestRoundSummary:
    def test_valid_construction(self) -> None:
        rs = RoundSummary(
            round=1,
            candidates_evaluated=["v1"],
            new_pareto_points=1,
            front_size=1,
            mutation_mode="targeted",
            stagnation_count=0,
        )
        assert rs.round == 1
        assert rs.candidates_evaluated == ["v1"]
        assert rs.new_pareto_points == 1

    def test_round_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            RoundSummary(
                round=0,
                candidates_evaluated=[],
                new_pareto_points=0,
                front_size=0,
                mutation_mode="targeted",
                stagnation_count=0,
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompt_builder_search.py::TestRoundSummary -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement RoundSummary**

Add to `odysseus/agents/prompt_builder_search.py`:

```python
class RoundSummary(BaseModel):
    """Summary of a single search round.

    Fields:
        round: Round number (>= 1).
        candidates_evaluated: Prompt versions evaluated this round.
        new_pareto_points: Number of new non-dominated points added.
        front_size: Total Pareto front size after this round.
        mutation_mode: "targeted" or "exploratory".
        stagnation_count: Consecutive rounds without Pareto improvement.
    """

    round: int
    candidates_evaluated: list[str]
    new_pareto_points: int
    front_size: int
    mutation_mode: Literal["targeted", "exploratory"]
    stagnation_count: int

    @field_validator("round")
    @classmethod
    def round_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("round must be >= 1")
        return v
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompt_builder_search.py::TestRoundSummary -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/prompt_builder_search.py tests/test_prompt_builder_search.py
git commit -m "feat: add RoundSummary model for prompt builder search"
```

### Task 3: SearchState model

**Files:**
- Modify: `odysseus/agents/prompt_builder_search.py`
- Modify: `tests/test_prompt_builder_search.py`

- [ ] **Step 1: Write failing tests for SearchState**

Append to `tests/test_prompt_builder_search.py`:

```python
from odysseus.agents.prompt_builder_search import SearchState


class TestSearchState:
    def test_valid_construction_defaults(self) -> None:
        ss = SearchState(
            search_state_id="abc123",
            backend="anthropic-sonnet",
        )
        assert ss.search_state_id == "abc123"
        assert ss.backend == "anthropic-sonnet"
        assert ss.primary_metric_name is None
        assert ss.round == 0
        assert ss.pareto_front == []
        assert ss.round_history == []
        assert ss.stagnation_count == 0
        assert ss.stagnation_limit == 3
        assert ss.convergence_limit == 5
        assert ss.max_rounds == 50
        assert ss.mutation_mode == "targeted"
        assert ss.converged is False

    def test_custom_limits(self) -> None:
        ss = SearchState(
            search_state_id="xyz",
            backend="openai-gpt4",
            max_rounds=10,
            stagnation_limit=2,
            convergence_limit=4,
            primary_metric_name="accuracy",
        )
        assert ss.max_rounds == 10
        assert ss.stagnation_limit == 2
        assert ss.convergence_limit == 4
        assert ss.primary_metric_name == "accuracy"

    def test_convergence_limit_must_exceed_stagnation_limit(self) -> None:
        with pytest.raises(ValidationError):
            SearchState(
                search_state_id="bad",
                backend="test",
                stagnation_limit=5,
                convergence_limit=3,
            )

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SearchState(search_state_id="", backend="test")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_builder_search.py::TestSearchState -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement SearchState**

Add to `odysseus/agents/prompt_builder_search.py`:

```python
class SearchState(BaseModel):
    """Full search state for the Prompt Builder optimization loop.

    Fields:
        search_state_id: Unique identifier for this search run. Non-empty.
        backend: Backend label used for evaluation.
        primary_metric_name: Name of the primary quality metric from eval config.
            If None, the agent uses the first metric in the eval config.
        round: Current round number (0 = not started).
        pareto_front: Non-dominated candidates.
        round_history: Summary of each completed round.
        stagnation_count: Consecutive rounds without Pareto improvement.
        stagnation_limit: Rounds before switching to exploratory mode. Default: 3.
        convergence_limit: Rounds before declaring convergence. Default: 5.
        max_rounds: Hard round cap. Default: 50.
        mutation_mode: Current mutation strategy.
        converged: Whether the search has converged.

    Cross-field validation:
        convergence_limit must be > stagnation_limit.
    """

    search_state_id: str
    backend: str
    primary_metric_name: str | None = None
    round: int = 0
    pareto_front: list[Candidate] = []
    round_history: list[RoundSummary] = []
    stagnation_count: int = 0
    stagnation_limit: int = 3
    convergence_limit: int = 5
    max_rounds: int = 50
    mutation_mode: Literal["targeted", "exploratory"] = "targeted"
    converged: bool = False

    @field_validator("search_state_id")
    @classmethod
    def id_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("search_state_id must be non-empty")
        return v.strip()

    @model_validator(mode="after")
    def convergence_must_exceed_stagnation(self) -> SearchState:
        if self.convergence_limit <= self.stagnation_limit:
            raise ValueError(
                f"convergence_limit ({self.convergence_limit}) must be > "
                f"stagnation_limit ({self.stagnation_limit})"
            )
        return self
```

Add `model_validator` to the imports at the top of the file:

```python
from pydantic import BaseModel, field_validator, model_validator
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompt_builder_search.py::TestSearchState -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/prompt_builder_search.py tests/test_prompt_builder_search.py
git commit -m "feat: add SearchState model for prompt builder search"
```

### Task 4: Pareto dominance logic

**Files:**
- Modify: `odysseus/agents/prompt_builder_search.py`
- Modify: `tests/test_prompt_builder_search.py`

- [ ] **Step 1: Write failing tests for dominance**

Append to `tests/test_prompt_builder_search.py`:

```python
from odysseus.agents.prompt_builder_search import dominates, update_pareto_front


def _candidate(version: str, quality: float, cost: float) -> Candidate:
    return Candidate(
        prompt_version=version,
        parent_version=None,
        quality_score=quality,
        cost=cost,
        round_introduced=1,
    )


class TestDominates:
    def test_a_dominates_b_higher_quality_lower_cost(self) -> None:
        a = _candidate("a", quality=0.9, cost=0.1)
        b = _candidate("b", quality=0.8, cost=0.2)
        assert dominates(a, b) is True
        assert dominates(b, a) is False

    def test_a_dominates_b_same_quality_lower_cost(self) -> None:
        a = _candidate("a", quality=0.9, cost=0.1)
        b = _candidate("b", quality=0.9, cost=0.2)
        assert dominates(a, b) is True
        assert dominates(b, a) is False

    def test_a_dominates_b_higher_quality_same_cost(self) -> None:
        a = _candidate("a", quality=0.9, cost=0.1)
        b = _candidate("b", quality=0.8, cost=0.1)
        assert dominates(a, b) is True
        assert dominates(b, a) is False

    def test_no_dominance_tradeoff(self) -> None:
        a = _candidate("a", quality=0.9, cost=0.3)
        b = _candidate("b", quality=0.8, cost=0.1)
        assert dominates(a, b) is False
        assert dominates(b, a) is False

    def test_identical_candidates_no_dominance(self) -> None:
        a = _candidate("a", quality=0.9, cost=0.1)
        b = _candidate("b", quality=0.9, cost=0.1)
        assert dominates(a, b) is False
        assert dominates(b, a) is False


class TestUpdateParetoFront:
    def test_empty_front_adds_candidate(self) -> None:
        c = _candidate("v1", quality=0.8, cost=0.2)
        front, new_points = update_pareto_front([], [c])
        assert len(front) == 1
        assert front[0].prompt_version == "v1"
        assert front[0].dominated is False
        assert new_points == 1

    def test_dominated_candidate_not_added(self) -> None:
        existing = _candidate("v1", quality=0.9, cost=0.1)
        existing.dominated = False
        worse = _candidate("v2", quality=0.8, cost=0.2)
        front, new_points = update_pareto_front([existing], [worse])
        assert len(front) == 1
        assert front[0].prompt_version == "v1"
        assert new_points == 0

    def test_new_candidate_dominates_existing(self) -> None:
        existing = _candidate("v1", quality=0.8, cost=0.2)
        better = _candidate("v2", quality=0.9, cost=0.1)
        front, new_points = update_pareto_front([existing], [better])
        assert len(front) == 1
        assert front[0].prompt_version == "v2"
        assert new_points == 1

    def test_tradeoff_candidates_both_kept(self) -> None:
        existing = _candidate("v1", quality=0.9, cost=0.3)
        tradeoff = _candidate("v2", quality=0.8, cost=0.1)
        front, new_points = update_pareto_front([existing], [tradeoff])
        assert len(front) == 2
        versions = {c.prompt_version for c in front}
        assert versions == {"v1", "v2"}
        assert new_points == 1

    def test_duplicate_quality_cost_rejected(self) -> None:
        existing = _candidate("v1", quality=0.9, cost=0.1)
        duplicate = _candidate("v2", quality=0.9, cost=0.1)
        front, new_points = update_pareto_front([existing], [duplicate])
        assert len(front) == 1
        assert front[0].prompt_version == "v1"
        assert new_points == 0

    def test_multiple_new_candidates(self) -> None:
        c1 = _candidate("v1", quality=0.9, cost=0.3)
        c2 = _candidate("v2", quality=0.8, cost=0.1)
        c3 = _candidate("v3", quality=0.7, cost=0.5)  # dominated by both
        front, new_points = update_pareto_front([], [c1, c2, c3])
        assert len(front) == 2
        versions = {c.prompt_version for c in front}
        assert versions == {"v1", "v2"}
        assert new_points == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_builder_search.py::TestDominates -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement dominance functions**

Add to `odysseus/agents/prompt_builder_search.py`:

```python
def dominates(a: Candidate, b: Candidate) -> bool:
    """Return True if candidate a Pareto-dominates candidate b.

    a dominates b iff a.quality_score >= b.quality_score AND a.cost <= b.cost
    with at least one strict inequality.
    """
    at_least_as_good = a.quality_score >= b.quality_score and a.cost <= b.cost
    strictly_better = a.quality_score > b.quality_score or a.cost < b.cost
    return at_least_as_good and strictly_better


def update_pareto_front(
    front: list[Candidate],
    new_candidates: list[Candidate],
) -> tuple[list[Candidate], int]:
    """Add new candidates to the Pareto front, removing dominated ones.

    Deduplication: candidates with identical (quality_score, cost) are rejected
    if one already exists on the front.

    Returns:
        (updated_front, new_pareto_points) where new_pareto_points is the count
        of new candidates that were added to the front.
    """
    existing_pairs: set[tuple[float, float]] = {
        (c.quality_score, c.cost) for c in front
    }

    candidates_to_consider: list[Candidate] = []
    for c in new_candidates:
        pair = (c.quality_score, c.cost)
        if pair in existing_pairs:
            continue  # duplicate
        candidates_to_consider.append(c)
        existing_pairs.add(pair)

    # Merge existing front + new candidates, then filter
    all_candidates = list(front) + candidates_to_consider
    updated_front: list[Candidate] = []

    for candidate in all_candidates:
        is_dominated = any(
            dominates(other, candidate)
            for other in all_candidates
            if other.prompt_version != candidate.prompt_version
        )
        candidate.dominated = is_dominated
        if not is_dominated:
            updated_front.append(candidate)

    new_versions = {c.prompt_version for c in candidates_to_consider}
    new_pareto_points = sum(
        1 for c in updated_front if c.prompt_version in new_versions
    )

    return updated_front, new_pareto_points
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompt_builder_search.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/prompt_builder_search.py tests/test_prompt_builder_search.py
git commit -m "feat: add Pareto dominance logic for prompt builder search"
```

### Task 5: select_best helper

**Files:**
- Modify: `odysseus/agents/prompt_builder_search.py`
- Modify: `tests/test_prompt_builder_search.py`

- [ ] **Step 1: Write failing tests for select_best**

Append to `tests/test_prompt_builder_search.py`:

```python
from odysseus.agents.prompt_builder_search import select_best


class TestSelectBest:
    def test_selects_highest_quality(self) -> None:
        front = [
            _candidate("v1", quality=0.8, cost=0.1),
            _candidate("v2", quality=0.9, cost=0.3),
        ]
        assert select_best(front) == "v2"

    def test_ties_broken_by_lowest_cost(self) -> None:
        front = [
            _candidate("v1", quality=0.9, cost=0.3),
            _candidate("v2", quality=0.9, cost=0.1),
        ]
        assert select_best(front) == "v2"

    def test_single_candidate(self) -> None:
        front = [_candidate("v1", quality=0.8, cost=0.2)]
        assert select_best(front) == "v1"

    def test_empty_front_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            select_best([])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_builder_search.py::TestSelectBest -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement select_best**

Add to `odysseus/agents/prompt_builder_search.py`:

```python
def select_best(front: list[Candidate]) -> str:
    """Select the best candidate from the Pareto front.

    Picks the highest quality_score, breaking ties by lowest cost.

    Returns:
        The prompt_version of the best candidate.

    Raises:
        ValueError: If the front is empty.
    """
    if not front:
        raise ValueError("Cannot select from an empty Pareto front")
    best = max(front, key=lambda c: (c.quality_score, -c.cost))
    return best.prompt_version
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompt_builder_search.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/prompt_builder_search.py tests/test_prompt_builder_search.py
git commit -m "feat: add select_best helper for Pareto front"
```

---

## Chunk 2: Search State Operations

### Task 6: init_search_state and get_search_state

**Files:**
- Create: `odysseus/agents/prompt_builder_search_ops.py`
- Create: `tests/test_prompt_builder_search_ops.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for odysseus.agents.prompt_builder_search_ops."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from odysseus.agents.prompt_builder_search import SearchState
from odysseus.agents.prompt_builder_search_ops import (
    get_search_state,
    init_search_state,
)


class TestInitSearchState:
    def test_creates_state_with_defaults(self, tmp_path: Path) -> None:
        state = init_search_state(
            backend="anthropic-sonnet",
            output_dir=tmp_path,
        )
        assert state.backend == "anthropic-sonnet"
        assert state.round == 0
        assert state.max_rounds == 50
        assert state.stagnation_limit == 3
        assert state.convergence_limit == 5
        assert state.search_state_id  # non-empty

    def test_creates_state_with_custom_params(self, tmp_path: Path) -> None:
        state = init_search_state(
            backend="openai-gpt4",
            output_dir=tmp_path,
            max_rounds=10,
            stagnation_limit=2,
            convergence_limit=4,
            primary_metric_name="accuracy",
        )
        assert state.max_rounds == 10
        assert state.primary_metric_name == "accuracy"

    def test_persists_state_file(self, tmp_path: Path) -> None:
        state = init_search_state(
            backend="test",
            output_dir=tmp_path,
        )
        state_file = tmp_path / state.search_state_id / "search_state.json"
        assert state_file.exists()
        loaded = SearchState.model_validate_json(state_file.read_text())
        assert loaded.search_state_id == state.search_state_id


class TestGetSearchState:
    def test_loads_persisted_state(self, tmp_path: Path) -> None:
        state = init_search_state(backend="test", output_dir=tmp_path)
        loaded = get_search_state(state.search_state_id, output_dir=tmp_path)
        assert loaded.search_state_id == state.search_state_id
        assert loaded.backend == "test"

    def test_missing_state_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            get_search_state("nonexistent", output_dir=tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_builder_search_ops.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement init_search_state and get_search_state**

Create `odysseus/agents/prompt_builder_search_ops.py`:

```python
"""Stateful search operations for the Prompt Builder Agent.

Manages persistence of SearchState to outputs/<search_state_id>/search_state.json.
Called by MCP tools in odysseus/mcp.py.

See: docs/superpowers/specs/2026-03-24-thp-77-prompt-builder-agent-design.md
"""

from __future__ import annotations

import uuid
from pathlib import Path

from odysseus.agents.prompt_builder_search import (
    Candidate,
    RoundSummary,
    SearchState,
    select_best,
    update_pareto_front,
)

_DEFAULT_OUTPUT_DIR = Path("outputs")


def _state_path(search_state_id: str, output_dir: Path) -> Path:
    return output_dir / search_state_id / "search_state.json"


def _save_state(state: SearchState, output_dir: Path) -> None:
    path = _state_path(state.search_state_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def _load_state(search_state_id: str, output_dir: Path) -> SearchState:
    path = _state_path(search_state_id, output_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"Search state not found: {path}"
        )
    return SearchState.model_validate_json(path.read_text(encoding="utf-8"))


def init_search_state(
    backend: str,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
    max_rounds: int = 50,
    stagnation_limit: int = 3,
    convergence_limit: int = 5,
    primary_metric_name: str | None = None,
) -> SearchState:
    """Initialize a new search state and persist it.

    Returns the created SearchState.
    """
    state = SearchState(
        search_state_id=uuid.uuid4().hex[:12],
        backend=backend,
        primary_metric_name=primary_metric_name,
        max_rounds=max_rounds,
        stagnation_limit=stagnation_limit,
        convergence_limit=convergence_limit,
    )
    _save_state(state, output_dir)
    return state


def get_search_state(
    search_state_id: str,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
) -> SearchState:
    """Load and return the current search state."""
    return _load_state(search_state_id, output_dir)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompt_builder_search_ops.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/prompt_builder_search_ops.py tests/test_prompt_builder_search_ops.py
git commit -m "feat: add init and get search state operations"
```

### Task 7: register_candidate

**Files:**
- Modify: `odysseus/agents/prompt_builder_search_ops.py`
- Modify: `tests/test_prompt_builder_search_ops.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_prompt_builder_search_ops.py`:

```python
from odysseus.agents.prompt_builder_search_ops import register_candidate


class TestRegisterCandidate:
    def test_registers_initial_candidate(self, tmp_path: Path) -> None:
        state = init_search_state(backend="test", output_dir=tmp_path)
        register_candidate(
            state.search_state_id,
            prompt_version="v1",
            output_dir=tmp_path,
        )
        # Verify pending candidates file was created with the candidate
        pending_file = tmp_path / state.search_state_id / "pending_candidates.json"
        assert pending_file.exists()
        pending_data = json.loads(pending_file.read_text())
        assert len(pending_data) == 1
        assert pending_data[0]["prompt_version"] == "v1"

    def test_registers_child_candidate(self, tmp_path: Path) -> None:
        state = init_search_state(backend="test", output_dir=tmp_path)
        register_candidate(
            state.search_state_id,
            prompt_version="v1",
            output_dir=tmp_path,
        )
        updated = register_candidate(
            state.search_state_id,
            prompt_version="v2",
            parent_version="v1",
            output_dir=tmp_path,
        )
        loaded = get_search_state(state.search_state_id, output_dir=tmp_path)
        assert loaded is not None

    def test_duplicate_version_raises(self, tmp_path: Path) -> None:
        state = init_search_state(backend="test", output_dir=tmp_path)
        register_candidate(
            state.search_state_id,
            prompt_version="v1",
            output_dir=tmp_path,
        )
        with pytest.raises(ValueError, match="already registered"):
            register_candidate(
                state.search_state_id,
                prompt_version="v1",
                output_dir=tmp_path,
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_builder_search_ops.py::TestRegisterCandidate -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement register_candidate**

Add to `odysseus/agents/prompt_builder_search_ops.py`:

```python
def _pending_path(search_state_id: str, output_dir: Path) -> Path:
    return output_dir / search_state_id / "pending_candidates.json"


def _load_pending(search_state_id: str, output_dir: Path) -> list[Candidate]:
    path = _pending_path(search_state_id, output_dir)
    if not path.exists():
        return []
    import json as _json
    raw = _json.loads(path.read_text(encoding="utf-8"))
    return [Candidate.model_validate(c) for c in raw]


def _save_pending(
    search_state_id: str, pending: list[Candidate], output_dir: Path
) -> None:
    path = _pending_path(search_state_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    import json as _json
    path.write_text(
        _json.dumps([c.model_dump() for c in pending], indent=2), encoding="utf-8"
    )


def register_candidate(
    search_state_id: str,
    prompt_version: str,
    parent_version: str | None = None,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
) -> SearchState:
    """Register a new prompt candidate in the search state.

    The candidate is persisted to pending_candidates.json until
    record_eval_result is called and advance_round consumes it.
    Raises ValueError if prompt_version is already registered.

    Returns the current SearchState.
    """
    state = _load_state(search_state_id, output_dir)
    pending = _load_pending(search_state_id, output_dir)

    # Check for duplicate versions across front, history, and pending
    all_versions: set[str] = {c.prompt_version for c in state.pareto_front}
    for rs in state.round_history:
        all_versions.update(rs.candidates_evaluated)
    all_versions.update(c.prompt_version for c in pending)

    if prompt_version in all_versions:
        raise ValueError(f"Prompt version {prompt_version!r} is already registered")

    candidate = Candidate(
        prompt_version=prompt_version,
        parent_version=parent_version,
        quality_score=0.0,  # placeholder until eval
        cost=0.0,  # placeholder until eval
        round_introduced=state.round + 1,
    )

    pending.append(candidate)
    _save_pending(search_state_id, pending, output_dir)

    return state
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompt_builder_search_ops.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/prompt_builder_search_ops.py tests/test_prompt_builder_search_ops.py
git commit -m "feat: add register_candidate operation"
```

### Task 8: record_eval_result

**Files:**
- Modify: `odysseus/agents/prompt_builder_search_ops.py`
- Modify: `tests/test_prompt_builder_search_ops.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_prompt_builder_search_ops.py`:

```python
from odysseus.agents.prompt_builder_search_ops import record_eval_result


class TestRecordEvalResult:
    def test_records_quality_and_cost(self, tmp_path: Path) -> None:
        state = init_search_state(backend="test", output_dir=tmp_path)
        register_candidate(state.search_state_id, "v1", output_dir=tmp_path)
        result = record_eval_result(
            state.search_state_id,
            prompt_version="v1",
            quality_score=0.85,
            cost=0.12,
            output_dir=tmp_path,
        )
        assert result["prompt_version"] == "v1"
        assert result["quality_score"] == 0.85
        assert result["cost"] == 0.12

    def test_unknown_version_raises(self, tmp_path: Path) -> None:
        state = init_search_state(backend="test", output_dir=tmp_path)
        with pytest.raises(ValueError, match="not found"):
            record_eval_result(
                state.search_state_id,
                prompt_version="v99",
                quality_score=0.5,
                cost=0.1,
                output_dir=tmp_path,
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_builder_search_ops.py::TestRecordEvalResult -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement record_eval_result**

Add to `odysseus/agents/prompt_builder_search_ops.py`:

```python
def record_eval_result(
    search_state_id: str,
    prompt_version: str,
    quality_score: float,
    cost: float,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
) -> dict[str, object]:
    """Record eval results for a pending candidate.

    Updates the candidate's quality_score and cost on disk. The candidate
    remains pending until advance_round is called.

    Returns:
        Dict with prompt_version, quality_score, cost confirmation.

    Raises:
        ValueError: If prompt_version is not in the pending list.
    """
    pending = _load_pending(search_state_id, output_dir)
    target = None
    for c in pending:
        if c.prompt_version == prompt_version:
            target = c
            break

    if target is None:
        raise ValueError(
            f"Prompt version {prompt_version!r} not found in pending candidates "
            f"for search state {search_state_id!r}"
        )

    target.quality_score = quality_score
    target.cost = cost

    _save_pending(search_state_id, pending, output_dir)

    return {
        "prompt_version": prompt_version,
        "quality_score": quality_score,
        "cost": cost,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompt_builder_search_ops.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/prompt_builder_search_ops.py tests/test_prompt_builder_search_ops.py
git commit -m "feat: add record_eval_result operation"
```

### Task 9: advance_round

**Files:**
- Modify: `odysseus/agents/prompt_builder_search_ops.py`
- Modify: `tests/test_prompt_builder_search_ops.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_prompt_builder_search_ops.py`:

```python
from odysseus.agents.prompt_builder_search_ops import advance_round
from odysseus.agents.prompt_builder_search import RoundSummary


class TestAdvanceRound:
    def _run_round(
        self,
        tmp_path: Path,
        search_state_id: str,
        versions_with_scores: list[tuple[str, float, float]],
    ) -> RoundSummary:
        """Helper: register candidates, record results, advance."""
        for version, quality, cost in versions_with_scores:
            register_candidate(search_state_id, version, output_dir=tmp_path)
            record_eval_result(
                search_state_id, version, quality, cost, output_dir=tmp_path
            )
        return advance_round(search_state_id, output_dir=tmp_path)

    def test_first_round_adds_to_front(self, tmp_path: Path) -> None:
        state = init_search_state(backend="test", output_dir=tmp_path)
        summary = self._run_round(
            tmp_path, state.search_state_id, [("v1", 0.85, 0.12)]
        )
        assert summary.round == 1
        assert summary.new_pareto_points == 1
        assert summary.front_size == 1
        assert summary.stagnation_count == 0

    def test_stagnation_increments(self, tmp_path: Path) -> None:
        state = init_search_state(backend="test", output_dir=tmp_path)
        # Round 1: add a strong candidate
        self._run_round(tmp_path, state.search_state_id, [("v1", 0.9, 0.1)])
        # Round 2: add a dominated candidate — no new Pareto points
        summary = self._run_round(
            tmp_path, state.search_state_id, [("v2", 0.8, 0.2)]
        )
        assert summary.stagnation_count == 1

    def test_stagnation_resets_on_improvement(self, tmp_path: Path) -> None:
        state = init_search_state(backend="test", output_dir=tmp_path)
        self._run_round(tmp_path, state.search_state_id, [("v1", 0.8, 0.2)])
        # Stagnant round
        self._run_round(tmp_path, state.search_state_id, [("v2", 0.7, 0.3)])
        # Improvement — tradeoff point
        summary = self._run_round(
            tmp_path, state.search_state_id, [("v3", 0.75, 0.1)]
        )
        assert summary.stagnation_count == 0

    def test_switches_to_exploratory_at_stagnation_limit(self, tmp_path: Path) -> None:
        state = init_search_state(
            backend="test", output_dir=tmp_path, stagnation_limit=2, convergence_limit=4
        )
        self._run_round(tmp_path, state.search_state_id, [("v1", 0.9, 0.1)])
        self._run_round(tmp_path, state.search_state_id, [("v2", 0.8, 0.2)])
        summary = self._run_round(
            tmp_path, state.search_state_id, [("v3", 0.7, 0.3)]
        )
        assert summary.stagnation_count == 2
        loaded = get_search_state(state.search_state_id, output_dir=tmp_path)
        assert loaded.mutation_mode == "exploratory"

    def test_converges_at_convergence_limit(self, tmp_path: Path) -> None:
        state = init_search_state(
            backend="test",
            output_dir=tmp_path,
            stagnation_limit=2,
            convergence_limit=4,
        )
        self._run_round(tmp_path, state.search_state_id, [("v1", 0.9, 0.1)])
        # 4 stagnant rounds
        for i in range(2, 6):
            self._run_round(
                tmp_path, state.search_state_id,
                [(f"v{i}", 0.9 - i * 0.05, 0.1 + i * 0.05)]
            )
        loaded = get_search_state(state.search_state_id, output_dir=tmp_path)
        assert loaded.converged is True

    def test_max_rounds_forces_convergence(self, tmp_path: Path) -> None:
        state = init_search_state(
            backend="test", output_dir=tmp_path, max_rounds=2, convergence_limit=5
        )
        self._run_round(tmp_path, state.search_state_id, [("v1", 0.8, 0.2)])
        self._run_round(tmp_path, state.search_state_id, [("v2", 0.85, 0.15)])
        loaded = get_search_state(state.search_state_id, output_dir=tmp_path)
        assert loaded.converged is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_builder_search_ops.py::TestAdvanceRound -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement advance_round**

Add to `odysseus/agents/prompt_builder_search_ops.py`:

```python
def advance_round(
    search_state_id: str,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
) -> RoundSummary:
    """Close the current round, update Pareto front, check convergence.

    Moves all pending candidates into the Pareto front evaluation,
    updates stagnation tracking, and checks for mode switches and
    convergence.

    Returns a RoundSummary for the completed round.
    """
    state = _load_state(search_state_id, output_dir)
    pending = _load_pending(search_state_id, output_dir)

    if not pending:
        raise ValueError(f"No pending candidates for search state {search_state_id!r}")

    # Update Pareto front
    updated_front, new_pareto_points = update_pareto_front(
        state.pareto_front, pending
    )

    # Update stagnation
    if new_pareto_points > 0:
        stagnation_count = 0
        mutation_mode: Literal["targeted", "exploratory"] = "targeted"
    else:
        stagnation_count = state.stagnation_count + 1
        if stagnation_count >= state.stagnation_limit:
            mutation_mode = "exploratory"
        else:
            mutation_mode = state.mutation_mode

    new_round = state.round + 1

    # Check convergence
    converged = (
        stagnation_count >= state.convergence_limit
        or new_round >= state.max_rounds
    )

    # Build round summary
    summary = RoundSummary(
        round=new_round,
        candidates_evaluated=[c.prompt_version for c in pending],
        new_pareto_points=new_pareto_points,
        front_size=len(updated_front),
        mutation_mode=mutation_mode,
        stagnation_count=stagnation_count,
    )

    # Update and persist state
    state.round = new_round
    state.pareto_front = updated_front
    state.round_history.append(summary)
    state.stagnation_count = stagnation_count
    state.mutation_mode = mutation_mode
    state.converged = converged

    _save_state(state, output_dir)

    # Clear pending candidates file
    _save_pending(search_state_id, [], output_dir)

    return summary
```

Add `Literal` to the typing imports at the top:

```python
from typing import Literal
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompt_builder_search_ops.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/prompt_builder_search_ops.py tests/test_prompt_builder_search_ops.py
git commit -m "feat: add advance_round with stagnation and convergence logic"
```

---

## Chunk 3: Holdout Filter

### Task 10: filter_holdout_dataset

**Files:**
- Create: `odysseus/agents/prompt_builder_holdout_filter.py`
- Create: `tests/test_prompt_builder_holdout_filter.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for odysseus.agents.prompt_builder_holdout_filter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odysseus.agents.prompt_builder_holdout_filter import filter_holdout_dataset


def _write_holdout_jsonl(path: Path, examples: list[dict]) -> None:
    with open(path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")


class TestFilterHoldoutDataset:
    def test_filters_excluded_ids(self, tmp_path: Path) -> None:
        holdout_path = tmp_path / "holdout.jsonl"
        examples = [
            {"id": "ex1", "input": "query 1", "expected": {"route": "a", "routes": {"a": {"cost": 0.01, "quality_score": 0.9}}}, "split": "holdout"},
            {"id": "ex2", "input": "query 2", "expected": {"route": "b", "routes": {"b": {"cost": 0.02, "quality_score": 0.8}}}, "split": "holdout"},
            {"id": "ex3", "input": "query 3", "expected": {"route": "a", "routes": {"a": {"cost": 0.01, "quality_score": 0.9}}}, "split": "holdout"},
        ]
        _write_holdout_jsonl(holdout_path, examples)

        filtered_path = filter_holdout_dataset(
            holdout_jsonl_path=str(holdout_path),
            exclude_ids=["ex1", "ex3"],
        )

        filtered = Path(filtered_path)
        assert filtered.exists()
        lines = [json.loads(l) for l in filtered.read_text().strip().splitlines()]
        assert len(lines) == 1
        assert lines[0]["id"] == "ex2"

    def test_no_exclusions_copies_all(self, tmp_path: Path) -> None:
        holdout_path = tmp_path / "holdout.jsonl"
        examples = [
            {"id": "ex1", "input": "q1", "expected": {"route": "a", "routes": {"a": {"cost": 0.01, "quality_score": 0.9}}}, "split": "holdout"},
        ]
        _write_holdout_jsonl(holdout_path, examples)

        filtered_path = filter_holdout_dataset(
            holdout_jsonl_path=str(holdout_path),
            exclude_ids=[],
        )

        lines = Path(filtered_path).read_text().strip().splitlines()
        assert len(lines) == 1

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            filter_holdout_dataset(
                holdout_jsonl_path="/nonexistent/holdout.jsonl",
                exclude_ids=[],
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_builder_holdout_filter.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement filter_holdout_dataset**

Create `odysseus/agents/prompt_builder_holdout_filter.py`:

```python
"""Holdout dataset filtering for the Prompt Builder Agent.

Removes few-shot examples from the holdout set before final evaluation,
preventing data contamination. Used by the Final Reporting Agent.

See: docs/superpowers/specs/2026-03-24-thp-77-prompt-builder-agent-design.md
"""

from __future__ import annotations

import json
from pathlib import Path


def filter_holdout_dataset(
    holdout_jsonl_path: str,
    exclude_ids: list[str],
) -> str:
    """Remove examples with IDs in exclude_ids from the holdout JSONL.

    Writes a filtered JSONL file alongside the original with a
    '_filtered' suffix.

    Args:
        holdout_jsonl_path: Path to the holdout JSONL file.
        exclude_ids: Example IDs to exclude (few-shot examples used in prompt).

    Returns:
        Path to the filtered JSONL file.

    Raises:
        FileNotFoundError: If holdout_jsonl_path does not exist.
    """
    source = Path(holdout_jsonl_path)
    if not source.is_file():
        raise FileNotFoundError(f"Holdout dataset not found: {holdout_jsonl_path}")

    exclude_set = set(exclude_ids)
    filtered_path = source.parent / f"{source.stem}_filtered{source.suffix}"

    with open(source, encoding="utf-8") as fin, open(
        filtered_path, "w", encoding="utf-8"
    ) as fout:
        for line in fin:
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            if row.get("id") not in exclude_set:
                fout.write(stripped + "\n")

    return str(filtered_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompt_builder_holdout_filter.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/prompt_builder_holdout_filter.py tests/test_prompt_builder_holdout_filter.py
git commit -m "feat: add holdout dataset filter for data contamination prevention"
```

---

## Chunk 4: MCP Surface

### Task 11: Wire search tools into MCP

**Files:**
- Modify: `odysseus/mcp.py`
- Modify: `tests/test_mcp.py` (if MCP tool tests exist for pattern reference)

- [ ] **Step 1: Read existing MCP tool patterns**

Read `odysseus/mcp.py` to confirm current tool wiring patterns. All tools follow the pattern: parse inputs, call domain function, return JSON string.

- [ ] **Step 2: Add search state tools to mcp.py**

Add imports at the top of `odysseus/mcp.py`:

```python
from odysseus.agents.prompt_builder_search_ops import (
    advance_round,
    get_search_state,
    init_search_state,
    record_eval_result,
    register_candidate,
)
from odysseus.agents.prompt_builder_holdout_filter import filter_holdout_dataset
```

Add the following tool definitions:

```python
@mcp.tool()
async def init_search_state_tool(
    backend: str,
    max_rounds: int = 50,
    stagnation_limit: int = 3,
    convergence_limit: int = 5,
    primary_metric_name: str | None = None,
) -> str:
    """Initialize search state for a prompt optimization run.

    Args:
        backend: Backend label for evaluation.
        max_rounds: Hard round cap. Default: 50.
        stagnation_limit: Rounds before exploratory mode. Default: 3.
        convergence_limit: Rounds before convergence. Default: 5.
        primary_metric_name: Name of the primary quality metric. Optional.

    Returns:
        JSON with search_state_id and initial state.
    """
    state = init_search_state(
        backend=backend,
        max_rounds=max_rounds,
        stagnation_limit=stagnation_limit,
        convergence_limit=convergence_limit,
        primary_metric_name=primary_metric_name,
    )
    return state.model_dump_json(indent=2)


@mcp.tool()
async def register_candidate_tool(
    search_state_id: str,
    prompt_version: str,
    parent_version: str | None = None,
) -> str:
    """Register a new prompt candidate in the search state.

    Args:
        search_state_id: ID of the search state.
        prompt_version: Version string for the new candidate.
        parent_version: Version of the parent prompt. Optional.

    Returns:
        JSON confirmation with prompt_version.
    """
    try:
        register_candidate(
            search_state_id=search_state_id,
            prompt_version=prompt_version,
            parent_version=parent_version,
        )
    except (FileNotFoundError, ValueError) as e:
        raise ToolError(str(e)) from e
    return json.dumps({"registered": prompt_version})


@mcp.tool()
async def record_eval_result_tool(
    search_state_id: str,
    prompt_version: str,
    quality_score: float,
    cost: float,
) -> str:
    """Record evaluation results for Pareto tracking.

    Args:
        search_state_id: ID of the search state.
        prompt_version: Version of the evaluated candidate.
        quality_score: Primary quality metric value.
        cost: Total evaluation cost.

    Returns:
        JSON confirmation with recorded values.
    """
    try:
        result = record_eval_result(
            search_state_id=search_state_id,
            prompt_version=prompt_version,
            quality_score=quality_score,
            cost=cost,
        )
    except (FileNotFoundError, ValueError) as e:
        raise ToolError(str(e)) from e
    return json.dumps(result)


@mcp.tool()
async def advance_round_tool(
    search_state_id: str,
) -> str:
    """Close the current round, update Pareto front, check convergence.

    Args:
        search_state_id: ID of the search state.

    Returns:
        JSON round summary with new_pareto_points, stagnation_count,
        converged status, and recommended mutation_mode.
    """
    try:
        summary = advance_round(search_state_id=search_state_id)
    except (FileNotFoundError, ValueError) as e:
        raise ToolError(str(e)) from e
    return summary.model_dump_json(indent=2)


@mcp.tool()
async def get_search_state_tool(
    search_state_id: str,
) -> str:
    """Read the current search state.

    Args:
        search_state_id: ID of the search state.

    Returns:
        Full search state JSON including Pareto front, round history,
        convergence status, and mutation mode.
    """
    try:
        state = get_search_state(search_state_id=search_state_id)
    except FileNotFoundError as e:
        raise ToolError(str(e)) from e
    return state.model_dump_json(indent=2)


@mcp.tool()
async def filter_holdout_dataset_tool(
    holdout_jsonl_path: str,
    exclude_ids: list[str],
) -> str:
    """Remove few-shot examples from holdout set before final evaluation.

    Used by the Final Reporting Agent to prevent data contamination.

    Args:
        holdout_jsonl_path: Path to the holdout JSONL file.
        exclude_ids: Example IDs to exclude (few-shots used in prompt).

    Returns:
        JSON with the filtered_holdout_path.
    """
    try:
        filtered_path = filter_holdout_dataset(
            holdout_jsonl_path=holdout_jsonl_path,
            exclude_ids=exclude_ids,
        )
    except FileNotFoundError as e:
        raise ToolError(str(e)) from e
    return json.dumps({"filtered_holdout_path": filtered_path})
```

- [ ] **Step 3: Add MCP prompt for the Prompt Builder agent**

Add to `odysseus/mcp.py`:

```python
@mcp.prompt()
async def odysseus_prompt_builder() -> list[Message]:
    """Activate the Odysseus prompt builder agent.

    Use after the routing analysis agent has produced annotated and split
    datasets. Compiles and iteratively optimizes routing prompts.
    """
    system_prompt = _load_text("odysseus/agents/prompts/prompt_builder_system.md")
    return [UserMessage(content=system_prompt)]
```

- [ ] **Step 4: Add MCP resources for best practices and conventions**

Add to `odysseus/mcp.py`:

```python
@mcp.resource("odysseus://agents/prompt-builder/best-practices")
async def prompt_builder_best_practices() -> str:
    """General prompt engineering principles for routing prompts."""
    return _load_text("odysseus/agents/prompt_builder_best_practices.md")


@mcp.resource("odysseus://agents/prompt-builder/conventions-claude")
async def prompt_builder_conventions_claude() -> str:
    """Claude conventions and Anthropic cookbook patterns for routing prompts."""
    return _load_text("odysseus/agents/prompt_builder_conventions_claude.md")


@mcp.resource("odysseus://agents/prompt-builder/conventions-openai")
async def prompt_builder_conventions_openai() -> str:
    """OpenAI conventions and cookbook patterns for routing prompts."""
    return _load_text("odysseus/agents/prompt_builder_conventions_openai.md")
```

- [ ] **Step 5: Run linting and type checks**

Run: `uv run ruff check odysseus/mcp.py && uv run pyright odysseus/mcp.py`
Expected: PASS (fix any issues)

- [ ] **Step 6: Commit**

```bash
git add odysseus/mcp.py
git commit -m "feat: wire prompt builder tools, prompt, and resources into MCP"
```

---

## Chunk 5: Best Practices & Convention Resources

### Task 12: General best practices resource

**Files:**
- Create: `odysseus/agents/prompt_builder_best_practices.md`

- [ ] **Step 1: Write best practices content**

Create `odysseus/agents/prompt_builder_best_practices.md` with curated prompt engineering principles relevant to routing prompts. Content should cover:

- **Role framing:** Set the LLM's role as a routing classifier upfront
- **Chain-of-thought:** When and how to request reasoning before routing decisions
- **Ordering effects:** Place the most discriminating rules first; LLMs attend more to early instructions
- **Negative vs positive framing:** Define routes by what they handle, not what they don't; use exclusions sparingly for genuinely ambiguous cases
- **Few-shot design:** Include boundary examples that demonstrate hard decisions; balance coverage across routes
- **Output format:** Be explicit about expected format; provide a template
- **Anchoring:** Start with the most common/default route to anchor expectations
- **Precision over length:** Shorter, precise rules outperform verbose explanations

This is a reference document for the LLM agent — write it as actionable guidance, not theory.

- [ ] **Step 2: Commit**

```bash
git add odysseus/agents/prompt_builder_best_practices.md
git commit -m "feat: add general prompt engineering best practices resource"
```

### Task 13: Claude conventions resource

**Files:**
- Create: `odysseus/agents/prompt_builder_conventions_claude.md`

- [ ] **Step 1: Research and write Claude conventions**

Create `odysseus/agents/prompt_builder_conventions_claude.md`. Distill from Anthropic's prompt engineering guide and cookbook. Cover:

- **XML tags:** Use `<routes>`, `<rules>`, `<examples>`, `<example>`, `<input>`, `<output>` for structure
- **System prompt style:** Claude performs best with structured system prompts; separate instructions from context
- **Prefilled responses:** Use assistant turn prefill for structured output (`{"route":`)
- **Example formatting:** `<example>` blocks with clear input/output separation
- **Emphasis:** `<important>` tags for critical rules; avoid ALL CAPS
- **Long context:** Claude handles long prompts well; don't sacrifice clarity for brevity
- **Thinking/reasoning:** When to use `<thinking>` tags for chain-of-thought
- **Relevant cookbook patterns:** structured output, classification tasks, multi-step routing

- [ ] **Step 2: Commit**

```bash
git add odysseus/agents/prompt_builder_conventions_claude.md
git commit -m "feat: add Claude conventions and cookbook patterns resource"
```

### Task 14: OpenAI conventions resource

**Files:**
- Create: `odysseus/agents/prompt_builder_conventions_openai.md`

- [ ] **Step 1: Research and write OpenAI conventions**

Create `odysseus/agents/prompt_builder_conventions_openai.md`. Distill from OpenAI's prompt engineering guide and cookbook. Cover:

- **System vs user messages:** Put rules and role in system message; examples in user messages
- **JSON mode:** Use `response_format: { "type": "json_object" }` for structured output
- **Function calling:** Alternative to JSON mode for structured routing responses
- **Example formatting:** Use `User:` / `Assistant:` turn pairs for few-shot
- **Emphasis:** Bold and numbered lists for critical rules; avoid XML tags
- **Markdown structure:** Use headers and numbered lists for organization
- **Relevant cookbook patterns:** classification, structured output, routing

- [ ] **Step 2: Commit**

```bash
git add odysseus/agents/prompt_builder_conventions_openai.md
git commit -m "feat: add OpenAI conventions and cookbook patterns resource"
```

---

## Chunk 6: Agent System Prompt

### Task 15: Write the Prompt Builder agent system prompt

**Files:**
- Create: `odysseus/agents/prompts/prompt_builder_system.md`

- [ ] **Step 1: Write the system prompt**

Create `odysseus/agents/prompts/prompt_builder_system.md`. This is the main deliverable — it instructs the LLM agent on how to compile routing prompts and run the optimization loop. Structure:

```markdown
You are the Prompt Builder Agent in the Odysseus routing-prompt optimization pipeline.

## Your job
<high-level description: compile and optimize routing prompts>

## Inputs
<table of context dict keys, types, sources>

## Tools
<table of MCP tools with purpose descriptions>

## Resources
<table of MCP resources — best practices, conventions>

## Phase 1 — Initial Compilation
<step-by-step instructions for round 1>
<how to detect provider from backend>
<how to read best practices + conventions resources>
<how to select few-shot examples from holdout>
<prompt section convention>
<model-specific compilation guidance>

## Phase 2 — Optimization Loop
<step-by-step instructions for round 2+>
<how to interpret Review Agent directives>
<parent selection from Pareto front>
<mutation operators: targeted vs exploratory>
<how to call tools in sequence>

## Convergence
<how to interpret advance_round results>
<when to stop>
<how to select and output the final prompt>

## Output Contract
<context dict keys to write>

## Constraints
<holdout isolation note>
<data contamination prevention>
<skill adherence>
```

Follow the style of `odysseus/agents/prompts/routing_analysis_system.md` — structured, table-heavy, imperative instructions.

- [ ] **Step 2: Verify the prompt references correct tool names and resource URIs**

Cross-reference against `odysseus/mcp.py` to ensure all tool names and resource URIs match.

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/prompts/prompt_builder_system.md
git commit -m "feat: add Prompt Builder agent system prompt"
```

---

## Chunk 7: MCP Tool Tests & Integration Scenarios

### Task 16: MCP tool smoke tests

**Files:**
- Create: `tests/test_mcp_prompt_builder.py`

- [ ] **Step 1: Write MCP tool tests**

Follow the pattern in `tests/test_mcp.py` and `tests/test_mcp_data_validation.py`. Test each new tool's wiring:

```python
"""Smoke tests for Prompt Builder MCP tools."""

from __future__ import annotations

import json

import pytest

from odysseus.mcp import (
    advance_round_tool,
    filter_holdout_dataset_tool,
    get_search_state_tool,
    init_search_state_tool,
    record_eval_result_tool,
    register_candidate_tool,
)


@pytest.mark.asyncio
class TestSearchStateTools:
    async def test_init_returns_valid_json(self) -> None:
        result = await init_search_state_tool(backend="test")
        data = json.loads(result)
        assert "search_state_id" in data
        assert data["backend"] == "test"
        assert data["round"] == 0

    async def test_full_round_lifecycle(self) -> None:
        # Init
        init_result = json.loads(await init_search_state_tool(backend="test"))
        sid = init_result["search_state_id"]

        # Register
        reg_result = json.loads(await register_candidate_tool(sid, "v1"))
        assert reg_result["registered"] == "v1"

        # Record
        rec_result = json.loads(
            await record_eval_result_tool(sid, "v1", 0.85, 0.12)
        )
        assert rec_result["quality_score"] == 0.85

        # Advance
        adv_result = json.loads(await advance_round_tool(sid))
        assert adv_result["round"] == 1
        assert adv_result["new_pareto_points"] == 1

        # Get state
        state_result = json.loads(await get_search_state_tool(sid))
        assert state_result["round"] == 1
        assert len(state_result["pareto_front"]) == 1


@pytest.mark.asyncio
class TestFilterHoldoutTool:
    async def test_missing_file_raises_tool_error(self) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with pytest.raises(ToolError):
            await filter_holdout_dataset_tool("/nonexistent.jsonl", [])
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_mcp_prompt_builder.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_mcp_prompt_builder.py
git commit -m "test: add MCP tool smoke tests for prompt builder"
```

### Task 17: Integration test scenarios

**Files:**
- Create: `tests/scenarios/13_prompt_builder_initial_compilation.md`
- Create: `tests/scenarios/14_prompt_builder_optimization_loop.md`

Per CLAUDE.md convention, each scenario has four sections: Setup, Scenario Description, User Simulator, Verification Criteria.

- [ ] **Step 1: Write initial compilation scenario**

Create `tests/scenarios/13_prompt_builder_initial_compilation.md`:

The scenario should test that the Prompt Builder agent can:
- Read routing analysis artifacts from context
- Detect the provider from the backend profile
- Compile an initial prompt with the correct section structure
- Write the prompt to `prompts/v1.txt`
- Call `init_search_state`, `register_candidate`, `run_eval`, `record_eval_result`, and `advance_round` in sequence

- [ ] **Step 2: Write optimization loop scenario**

Create `tests/scenarios/14_prompt_builder_optimization_loop.md`:

The scenario should test that the Prompt Builder agent can:
- Receive review directives and ScoreReport
- Select parents from the Pareto front
- Generate child variants using targeted mutations
- Evaluate candidates and update the Pareto front
- Detect stagnation and switch to exploratory mode

- [ ] **Step 3: Update tests/scenarios/README.md with new scenarios**

Add the two new scenarios to the scenario index table.

- [ ] **Step 4: Commit**

```bash
git add tests/scenarios/13_prompt_builder_initial_compilation.md tests/scenarios/14_prompt_builder_optimization_loop.md tests/scenarios/README.md
git commit -m "test: add prompt builder integration test scenarios"
```

---

## Chunk 8: Documentation Updates

### Task 18: Update architecture.md

**Files:**
- Modify: `docs/architecture.md`

- [ ] **Step 1: Update the pipeline diagram**

Update the mermaid diagram to show Prompt Builder Agent status as "done" instead of "planned".

- [ ] **Step 2: Update agent registry table**

Update the Prompt Builder row in the agent registry table:

```markdown
| Prompt Builder | LLM-driven | [`odysseus/agents/prompts/prompt_builder_system.md`](../odysseus/agents/prompts/prompt_builder_system.md), [`odysseus/agents/prompt_builder_search.py`](../odysseus/agents/prompt_builder_search.py) | Done | `dev_rationale_card_set_path`, `dev_jsonl_path`, `vocabulary_registry_path`, `split_report_path`, `routing_context`, `holdout_jsonl_path`, `holdout_rationale_card_set_path`, `backend`, `eval_score_report` | `prompt_version`, `few_shot_example_ids` |
```

- [ ] **Step 3: Update context dict reference table**

Add `few_shot_example_ids` row. Update `holdout_jsonl_path` and `holdout_rationale_card_set_path` consumed-by columns to include "Prompt Builder Agent".

- [ ] **Step 4: Update MCP surface tables**

Add new tools (`init_search_state`, `register_candidate`, `record_eval_result`, `advance_round`, `get_search_state`, `filter_holdout_dataset`), prompt (`odysseus_prompt_builder`), and resources to the appropriate tables.

- [ ] **Step 5: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: update architecture for Prompt Builder Agent"
```

### Task 19: Run full test suite and lint

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 2: Run linter**

Run: `uv run ruff check .`
Expected: PASS

- [ ] **Step 3: Run formatter**

Run: `uv run ruff format --check .`
Expected: PASS (or run `uv run ruff format .` to fix)

- [ ] **Step 4: Run type checker**

Run: `uv run pyright`
Expected: PASS

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "chore: fix lint/type issues from prompt builder implementation"
```
