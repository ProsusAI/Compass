# THP-110: Stratified Split Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a deterministic stratified split function that divides an annotated routing dataset into `dev.jsonl` and `holdout.jsonl` with proportional representation across routing-relevant dimensions.

**Architecture:** A single Python module (`odysseus/agents/stratified_split.py`) containing the split function, report model, and a mismatch error type. The function takes `list[Example]` + `RationaleCardSet`, joins them, stratifies on `(assigned_route, intent_pattern, complexity_structure)`, and returns in-memory results. File I/O (writing `dev.jsonl`, `holdout.jsonl`, `split_report.json`) is the caller's responsibility (the Routing Analysis Agent orchestrator) — this keeps the split function pure and testable. Determinism via `random.Random(dataset_hash)`.

**Tech Stack:** Python 3.11+, Pydantic (models), pytest (testing)

**Spec:** `docs/superpowers/specs/2026-03-24-thp-110-stratified-split-methodology.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `odysseus/agents/stratified_split.py` | Split algorithm, report model, `SplitMismatchError` |
| `tests/test_stratified_split.py` | All unit tests for the split module |
| `odysseus/agents/__init__.py` | Re-export public names from `stratified_split` |

---

## Chunk 1: Core Split Algorithm

### Task 1: SplitReport model and SplitMismatchError

**Files:**
- Create: `odysseus/agents/stratified_split.py`
- Create: `tests/test_stratified_split.py`

- [ ] **Step 1: Write failing test for SplitReport model**

```python
# tests/test_stratified_split.py
"""Tests for stratified split (THP-110)."""

from __future__ import annotations

from odysseus.agents.stratified_split import SplitMismatchError, SplitReport


def test_split_report_round_trip():
    """SplitReport can be constructed and serialized."""
    report = SplitReport(
        dataset_hash="abc123",
        split_ratio={"dev": 0.8, "holdout": 0.2},
        total_examples=10,
        dev_count=8,
        holdout_count=2,
        singleton_strata_count=0,
        strata=[],
        distributions={
            "assigned_route": {"dev": {}, "holdout": {}},
            "intent_pattern": {"dev": {}, "holdout": {}},
            "complexity_structure": {"dev": {}, "holdout": {}},
            "ambiguity_tags": {"dev": {}, "holdout": {}},
        },
    )
    data = report.model_dump()
    assert data["dataset_hash"] == "abc123"
    assert data["total_examples"] == 10


def test_split_mismatch_error_is_exception():
    """SplitMismatchError can be raised and caught."""
    with pytest.raises(SplitMismatchError, match="missing"):
        raise SplitMismatchError("missing cards for examples: ex-1")
```

Don't forget `import pytest` at the top of the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stratified_split.py -v`
Expected: FAIL — `ImportError: cannot import name 'SplitReport'`

- [ ] **Step 3: Write minimal implementation**

```python
# odysseus/agents/stratified_split.py
"""Deterministic stratified split for annotated routing datasets (THP-110).

Spec: docs/superpowers/specs/2026-03-24-thp-110-stratified-split-methodology.md
"""

from __future__ import annotations

from pydantic import BaseModel


class SplitMismatchError(Exception):
    """Raised when examples and rationale cards don't match by example_id."""


class StratumReport(BaseModel):
    """Distribution report for a single stratum."""

    key: list[str]
    total: int
    dev: int
    holdout: int


class SplitReport(BaseModel):
    """Report produced alongside the dev/holdout split."""

    dataset_hash: str
    split_ratio: dict[str, float]
    total_examples: int
    dev_count: int
    holdout_count: int
    singleton_strata_count: int
    strata: list[StratumReport]
    distributions: dict[str, dict[str, dict[str, float | int]]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stratified_split.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/stratified_split.py tests/test_stratified_split.py
git commit -m "feat(thp-110): add SplitReport model and SplitMismatchError"
```

---

### Task 2: Precondition validation (join + mismatch detection)

**Files:**
- Modify: `odysseus/agents/stratified_split.py`
- Modify: `tests/test_stratified_split.py`

- [ ] **Step 1: Write failing tests for precondition validation**

```python
# Add to tests/test_stratified_split.py
from odysseus.agents.stratified_split import validate_split_inputs
from odysseus.agents.routing_rationale_models import (
    RationaleCard,
    RationaleCardSet,
    RouteExclusion,
    VocabularyRegistry,
    VocabularyEntry,
)
from odysseus.eval.models import Example, Expected, ModelCostQuality
from datetime import datetime


# --- Helpers ---

def make_example(id: str, input: str, route: str) -> Example:
    return Example(
        id=id,
        input=input,
        expected=Expected(
            route=route,
            routes={route: ModelCostQuality(cost=0.01, quality_score=0.9)},
        ),
        split="dev",
    )


def make_card(example_id: str, route: str, intent: str, complexity: str) -> RationaleCard:
    return RationaleCard(
        example_id=example_id,
        assigned_route=route,
        intent_pattern=intent,
        complexity_structure=complexity,
        route_exclusions=[
            RouteExclusion(route="other", reason="Not applicable"),
        ],
        ambiguity_tags=[],
    )


def make_card_set(cards: list[RationaleCard]) -> RationaleCardSet:
    return RationaleCardSet(
        cards={c.example_id: c for c in cards},
        dataset_hash="abc123",
        registry=VocabularyRegistry(
            intent_pattern=[
                VocabularyEntry(name="data-analysis", definition="Analysis tasks", example_ids=[]),
            ],
            complexity_structure=[
                VocabularyEntry(name="single-step", definition="Simple tasks", example_ids=[]),
            ],
            ambiguity_tags=[],
        ),
        created_at=datetime(2026, 1, 1),
    )


# --- Tests ---

def test_validate_split_inputs_matching():
    """No error when examples and cards match."""
    examples = [make_example("ex-1", "query", "route-a")]
    cards = [make_card("ex-1", "route-a", "data-analysis", "single-step")]
    card_set = make_card_set(cards)
    # Should not raise
    validate_split_inputs(examples, card_set)


def test_validate_split_inputs_missing_card():
    """Raise SplitMismatchError when an example has no card."""
    examples = [
        make_example("ex-1", "query", "route-a"),
        make_example("ex-2", "query2", "route-b"),
    ]
    cards = [make_card("ex-1", "route-a", "data-analysis", "single-step")]
    card_set = make_card_set(cards)
    with pytest.raises(SplitMismatchError, match="ex-2"):
        validate_split_inputs(examples, card_set)


def test_validate_split_inputs_extra_card():
    """Raise SplitMismatchError when a card has no example."""
    examples = [make_example("ex-1", "query", "route-a")]
    cards = [
        make_card("ex-1", "route-a", "data-analysis", "single-step"),
        make_card("ex-2", "route-a", "data-analysis", "single-step"),
    ]
    card_set = make_card_set(cards)
    with pytest.raises(SplitMismatchError, match="ex-2"):
        validate_split_inputs(examples, card_set)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_stratified_split.py -v -k validate`
Expected: FAIL — `ImportError: cannot import name 'validate_split_inputs'`

- [ ] **Step 3: Write minimal implementation**

Add to `odysseus/agents/stratified_split.py`:

```python
from odysseus.agents.routing_rationale_models import RationaleCardSet
from odysseus.eval.models import Example


def validate_split_inputs(
    examples: list[Example],
    card_set: RationaleCardSet,
) -> None:
    """Validate that examples and rationale cards match by ID.

    Raises SplitMismatchError if any example lacks a card or vice versa.
    """
    example_ids = {ex.id for ex in examples}
    card_ids = set(card_set.cards.keys())

    missing_cards = example_ids - card_ids
    extra_cards = card_ids - example_ids

    messages: list[str] = []
    if missing_cards:
        messages.append(f"examples missing cards: {sorted(missing_cards)}")
    if extra_cards:
        messages.append(f"cards missing examples: {sorted(extra_cards)}")

    if messages:
        raise SplitMismatchError("; ".join(messages))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_stratified_split.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/stratified_split.py tests/test_stratified_split.py
git commit -m "feat(thp-110): add input validation for example/card mismatch"
```

---

### Task 3: Core stratified_split function

**Files:**
- Modify: `odysseus/agents/stratified_split.py`
- Modify: `tests/test_stratified_split.py`

- [ ] **Step 1: Write failing tests for stratified_split**

```python
# Add to tests/test_stratified_split.py
from odysseus.agents.stratified_split import stratified_split


def test_stratified_split_basic_80_20():
    """10 examples in one stratum: 8 dev, 2 holdout."""
    examples = [make_example(f"ex-{i}", f"query-{i}", "route-a") for i in range(10)]
    cards = [make_card(f"ex-{i}", "route-a", "data-analysis", "single-step") for i in range(10)]
    card_set = make_card_set(cards)

    dev, holdout, report = stratified_split(examples, card_set, dev_ratio=0.8)

    assert len(dev) == 8
    assert len(holdout) == 2
    assert report.dev_count == 8
    assert report.holdout_count == 2
    assert report.total_examples == 10


def test_stratified_split_singleton_goes_to_dev():
    """A stratum with 1 member goes to dev; larger strata still split."""
    examples = [
        *[make_example(f"ex-{i}", f"query-{i}", "route-a") for i in range(10)],
        make_example("ex-solo", "query-solo", "route-b"),  # singleton stratum
    ]
    cards = [
        *[make_card(f"ex-{i}", "route-a", "data-analysis", "single-step") for i in range(10)],
        make_card("ex-solo", "route-b", "code-generation", "multi-step"),
    ]
    card_set = make_card_set(cards)

    dev, holdout, report = stratified_split(examples, card_set, dev_ratio=0.8)

    # Singleton must be in dev
    dev_ids = {ex.id for ex in dev}
    assert "ex-solo" in dev_ids
    assert report.singleton_strata_count == 1
    # The 10-member stratum should have been split (holdout non-empty)
    assert len(holdout) > 0
    holdout_ids = {ex.id for ex in holdout}
    assert "ex-solo" not in holdout_ids


def test_stratified_split_deterministic():
    """Same inputs in different order produce same split."""
    examples = [make_example(f"ex-{i}", f"query-{i}", "route-a") for i in range(20)]
    cards = [make_card(f"ex-{i}", "route-a", "data-analysis", "single-step") for i in range(20)]
    card_set = make_card_set(cards)

    dev1, holdout1, _ = stratified_split(examples, card_set)

    # Reverse input order — split should be identical
    dev2, holdout2, _ = stratified_split(list(reversed(examples)), card_set)

    assert sorted(e.id for e in dev1) == sorted(e.id for e in dev2)
    assert sorted(e.id for e in holdout1) == sorted(e.id for e in holdout2)


def test_stratified_split_rounding_favors_dev():
    """When stratum size doesn't divide cleanly, dev gets the extra."""
    # 3 examples at 80/20: dev=2.4→3, holdout=0.6→0
    # But we need >= 2 for splitting, so with 3: dev=3, holdout=0? No:
    # floor(3 * 0.2) = 0 holdout, 3 dev. Actually ceil(3*0.8)=3, so all dev.
    # Let's use 7: ceil(7*0.8)=6, holdout=1
    examples = [make_example(f"ex-{i}", f"query-{i}", "route-a") for i in range(7)]
    cards = [make_card(f"ex-{i}", "route-a", "data-analysis", "single-step") for i in range(7)]
    card_set = make_card_set(cards)

    dev, holdout, report = stratified_split(examples, card_set, dev_ratio=0.8)

    assert len(dev) >= len(holdout)
    assert len(dev) + len(holdout) == 7
    # With 7 examples: holdout = floor(7 * 0.2) = 1, dev = 6
    assert report.dev_count == 6
    assert report.holdout_count == 1


def test_stratified_split_degenerate_single_example():
    """Dataset with 1 example: all to dev, empty holdout."""
    examples = [make_example("ex-0", "query-0", "route-a")]
    cards = [make_card("ex-0", "route-a", "data-analysis", "single-step")]
    card_set = make_card_set(cards)

    dev, holdout, report = stratified_split(examples, card_set)

    assert len(dev) == 1
    assert len(holdout) == 0


def test_stratified_split_preserves_route_balance():
    """Both dev and holdout have examples from each route."""
    examples = (
        [make_example(f"a-{i}", f"query-a-{i}", "route-a") for i in range(10)]
        + [make_example(f"b-{i}", f"query-b-{i}", "route-b") for i in range(10)]
    )
    cards = (
        [make_card(f"a-{i}", "route-a", "data-analysis", "single-step") for i in range(10)]
        + [make_card(f"b-{i}", "route-b", "code-generation", "multi-step") for i in range(10)]
    )
    card_set = make_card_set(cards)

    dev, holdout, report = stratified_split(examples, card_set)

    dev_routes = {ex.expected.route for ex in dev}
    holdout_routes = {ex.expected.route for ex in holdout}
    assert "route-a" in dev_routes
    assert "route-b" in dev_routes
    assert "route-a" in holdout_routes
    assert "route-b" in holdout_routes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_stratified_split.py -v -k "stratified_split"`
Expected: FAIL — `ImportError: cannot import name 'stratified_split'`

- [ ] **Step 3: Write minimal implementation**

Add to `odysseus/agents/stratified_split.py`:

```python
import random
from collections import defaultdict

from odysseus.agents.routing_rationale_registry import compute_dataset_hash


def stratified_split(
    examples: list[Example],
    card_set: RationaleCardSet,
    dev_ratio: float = 0.8,
) -> tuple[list[Example], list[Example], SplitReport]:
    """Split annotated examples into dev and holdout sets.

    Uses hierarchical priority stratification on
    (assigned_route, intent_pattern, complexity_structure).

    Args:
        examples: Full dataset examples.
        card_set: Rationale cards matching examples by ID.
        dev_ratio: Proportion allocated to dev set. Default 0.8.

    Returns:
        (dev_examples, holdout_examples, report)

    Raises:
        SplitMismatchError: If examples and cards don't match by ID.
    """
    validate_split_inputs(examples, card_set)

    # Degenerate case
    if len(examples) < 2:
        return _build_result(examples, [], examples, card_set, dev_ratio)

    # Build strata
    strata: dict[tuple[str, str, str], list[Example]] = defaultdict(list)
    for ex in examples:
        card = card_set.cards[ex.id]
        key = (card.assigned_route, card.intent_pattern, card.complexity_structure)
        strata[key].append(ex)

    # Deterministic seed
    dataset_hash = compute_dataset_hash(examples)
    rng = random.Random(dataset_hash)

    dev: list[Example] = []
    holdout: list[Example] = []
    singleton_count = 0

    for _key, members in sorted(strata.items()):
        if len(members) < 2:
            dev.extend(members)
            singleton_count += 1
            continue

        # Sort by ID before shuffling for input-order independence
        shuffled = sorted(members, key=lambda ex: ex.id)
        rng.shuffle(shuffled)

        # holdout count = floor(n * holdout_ratio), rest goes to dev
        holdout_count = int(len(shuffled) * (1.0 - dev_ratio))
        dev.extend(shuffled[holdout_count:])
        holdout.extend(shuffled[:holdout_count])

    return _build_result(dev, holdout, examples, card_set, dev_ratio, singleton_count)


def _build_result(
    dev: list[Example],
    holdout: list[Example],
    all_examples: list[Example],
    card_set: RationaleCardSet,
    dev_ratio: float,
    singleton_strata_count: int = 0,
) -> tuple[list[Example], list[Example], SplitReport]:
    """Construct the split result with report."""
    dataset_hash = compute_dataset_hash(all_examples)

    # Build strata report
    strata_counts: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {"total": 0, "dev": 0, "holdout": 0}
    )
    dev_ids = {ex.id for ex in dev}
    for ex in all_examples:
        card = card_set.cards[ex.id]
        key = (card.assigned_route, card.intent_pattern, card.complexity_structure)
        strata_counts[key]["total"] += 1
        if ex.id in dev_ids:
            strata_counts[key]["dev"] += 1
        else:
            strata_counts[key]["holdout"] += 1

    strata_report = [
        StratumReport(key=list(k), total=v["total"], dev=v["dev"], holdout=v["holdout"])
        for k, v in sorted(strata_counts.items())
    ]

    # Build distributions
    distributions = _compute_distributions(dev, holdout, card_set)

    report = SplitReport(
        dataset_hash=dataset_hash,
        split_ratio={"dev": dev_ratio, "holdout": round(1.0 - dev_ratio, 4)},
        total_examples=len(all_examples),
        dev_count=len(dev),
        holdout_count=len(holdout),
        singleton_strata_count=singleton_strata_count,
        strata=strata_report,
        distributions=distributions,
    )
    return dev, holdout, report


def _compute_distributions(
    dev: list[Example],
    holdout: list[Example],
    card_set: RationaleCardSet,
) -> dict[str, dict[str, dict[str, float | int]]]:
    """Compute per-dimension distributions for the split report."""
    result: dict[str, dict[str, dict[str, float | int]]] = {}

    # Normalized proportions for assigned_route, intent_pattern, complexity_structure
    for dim in ("assigned_route", "intent_pattern", "complexity_structure"):
        dev_counts: dict[str, int] = defaultdict(int)
        holdout_counts: dict[str, int] = defaultdict(int)
        for ex in dev:
            dev_counts[getattr(card_set.cards[ex.id], dim)] += 1
        for ex in holdout:
            holdout_counts[getattr(card_set.cards[ex.id], dim)] += 1

        dev_total = len(dev) or 1
        holdout_total = len(holdout) or 1
        result[dim] = {
            "dev": {k: round(v / dev_total, 4) for k, v in sorted(dev_counts.items())},
            "holdout": {k: round(v / holdout_total, 4) for k, v in sorted(holdout_counts.items())},
        }

    # Raw counts for ambiguity_tags (multi-label)
    dev_tags: dict[str, int] = defaultdict(int)
    holdout_tags: dict[str, int] = defaultdict(int)
    for ex in dev:
        for tag in card_set.cards[ex.id].ambiguity_tags:
            dev_tags[tag] += 1
    for ex in holdout:
        for tag in card_set.cards[ex.id].ambiguity_tags:
            holdout_tags[tag] += 1
    result["ambiguity_tags"] = {
        "dev": dict(sorted(dev_tags.items())),
        "holdout": dict(sorted(holdout_tags.items())),
    }

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_stratified_split.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/stratified_split.py tests/test_stratified_split.py
git commit -m "feat(thp-110): implement stratified_split core algorithm"
```

---

### Task 4: Report distributions with ambiguity tags

**Files:**
- Modify: `tests/test_stratified_split.py`

- [ ] **Step 1: Write failing test for ambiguity tag distribution in report**

```python
# Add to tests/test_stratified_split.py

def test_split_report_ambiguity_tag_distribution():
    """Report includes raw counts for ambiguity tags across dev/holdout."""
    examples = [make_example(f"ex-{i}", f"query-{i}", "route-a") for i in range(10)]
    cards = []
    for i in range(10):
        card = make_card(f"ex-{i}", "route-a", "data-analysis", "single-step")
        # Give first 3 examples an ambiguity tag
        if i < 3:
            card = card.model_copy(update={"ambiguity_tags": ["BOUNDARY_CASE"]})
        cards.append(card)
    card_set = make_card_set(cards)

    _, _, report = stratified_split(examples, card_set)

    # Ambiguity tags should appear in distributions with raw counts
    tags = report.distributions["ambiguity_tags"]
    total_boundary = tags["dev"].get("BOUNDARY_CASE", 0) + tags["holdout"].get("BOUNDARY_CASE", 0)
    assert total_boundary == 3
```

- [ ] **Step 2: Run test to verify it passes**

This test should already pass with the implementation from Task 3. Run to confirm:

Run: `uv run pytest tests/test_stratified_split.py::test_split_report_ambiguity_tag_distribution -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_stratified_split.py
git commit -m "test(thp-110): add ambiguity tag distribution test"
```

---

### Task 5: Wire up exports in __init__.py

**Files:**
- Modify: `odysseus/agents/__init__.py`

- [ ] **Step 1: Write failing test for import from agents package**

```python
# Add to tests/test_stratified_split.py

def test_public_api_exports():
    """Key names are importable from odysseus.agents."""
    from odysseus.agents import SplitMismatchError as _E
    from odysseus.agents import SplitReport as _R
    from odysseus.agents import stratified_split as _fn
    assert _E is not None
    assert _R is not None
    assert _fn is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stratified_split.py::test_public_api_exports -v`
Expected: FAIL — `ImportError: cannot import name 'stratified_split' from 'odysseus.agents'`

- [ ] **Step 3: Add exports to __init__.py**

Add the following import block and `__all__` entries to `odysseus/agents/__init__.py`:

```python
# Add import block after the routing_rationale_registry imports:
from odysseus.agents.stratified_split import (
    SplitMismatchError,
    SplitReport,
    stratified_split,
)

# Add to __all__ list (alphabetical):
# "SplitMismatchError",
# "SplitReport",
# "stratified_split",
```

- [ ] **Step 4: Run all tests to verify nothing broke**

Run: `uv run pytest -v`
Expected: PASS (all existing tests + new tests)

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/__init__.py tests/test_stratified_split.py
git commit -m "feat(thp-110): export stratified split from agents package"
```

---

## Chunk 2: Edge Cases and Documentation

### Task 6: Edge case tests

**Files:**
- Modify: `tests/test_stratified_split.py`

- [ ] **Step 1: Write edge case tests**

```python
# Add to tests/test_stratified_split.py

def test_stratified_split_empty_dataset():
    """Empty dataset: both outputs empty."""
    card_set = make_card_set([])

    dev, holdout, report = stratified_split([], card_set)

    assert len(dev) == 0
    assert len(holdout) == 0
    assert report.total_examples == 0


def test_stratified_split_all_singletons_empty_holdout():
    """When every stratum is a singleton, holdout is empty."""
    examples = [
        make_example("ex-0", "q0", "route-a"),
        make_example("ex-1", "q1", "route-b"),
        make_example("ex-2", "q2", "route-c"),
    ]
    cards = [
        make_card("ex-0", "route-a", "data-analysis", "single-step"),
        make_card("ex-1", "route-b", "code-generation", "multi-step"),
        make_card("ex-2", "route-c", "summarization", "sequential-dependency"),
    ]
    card_set = make_card_set(cards)

    dev, holdout, report = stratified_split(examples, card_set)

    assert len(dev) == 3
    assert len(holdout) == 0
    assert report.singleton_strata_count == 3


def test_stratified_split_custom_ratio():
    """Custom split ratio is respected."""
    examples = [make_example(f"ex-{i}", f"q-{i}", "route-a") for i in range(10)]
    cards = [make_card(f"ex-{i}", "route-a", "data-analysis", "single-step") for i in range(10)]
    card_set = make_card_set(cards)

    dev, holdout, report = stratified_split(examples, card_set, dev_ratio=0.5)

    assert len(dev) == 5
    assert len(holdout) == 5
    assert report.split_ratio == {"dev": 0.5, "holdout": 0.5}
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_stratified_split.py -v`
Expected: PASS (all tests)

- [ ] **Step 3: Commit**

```bash
git add tests/test_stratified_split.py
git commit -m "test(thp-110): add edge case tests for empty, all-singleton, and custom ratio"
```

---

### Task 7: Update docs

**Files:**
- Modify: `docs/architecture.md`

- [ ] **Step 1: Check current architecture doc for THP-74 section**

Read `docs/architecture.md` and find the Routing Analysis Agent entry. Update it to reflect that THP-74's pipeline is now: two per-example annotation skills + stratified split code step. Mention that skills 2-4 and clustering have been removed.

Add `stratified_split.py` to the module references for the Routing Analysis Agent.

- [ ] **Step 2: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: update architecture.md with stratified split module"
```

---

### Task 8: Run full test suite

- [ ] **Step 1: Run all tests**

Run: `uv run pytest -v`
Expected: PASS (all tests including new stratified split tests)

- [ ] **Step 2: Run linter and type checker**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: No errors

- [ ] **Step 3: Fix any issues found, then commit**

If linter or type checker reports issues, fix them and commit:

```bash
git commit -m "chore(thp-110): fix lint/type issues"
```
