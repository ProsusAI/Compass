# Routing Analysis Agent Removal — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Routing Analysis Agent from the pipeline, simplify the stratified split to route-only, and give the Review Agent ownership of example content.

**Architecture:** Delete the `odysseus/agents/routing_analysis/` subpackage and `odysseus/mcp/routing_analysis_tools.py`. Relocate `RoutingContext` models to `odysseus/agents/routing_context.py`, stratified split to `odysseus/agents/data_validation/split.py`, and `stratified_split_tool` to `odysseus/mcp/data_validation_tools.py`. Update pipeline status to remove stage 3, renumber stages, and make the Review Agent the refinement loop entry point.

**Tech Stack:** Python 3.11+, pydantic, pytest, MCP (FastMCP)

**Spec:** `docs/superpowers/specs/2026-03-30-routing-analysis-removal-design.md`

---

## Chunk 1: Model Relocation & Split Simplification

### Task 1: Relocate RoutingContext models

**Files:**
- Create: `odysseus/agents/routing_context.py`
- Source: `odysseus/agents/routing_analysis/models.py:196-283`

- [ ] **Step 1: Write the test for relocated models**

Create `tests/test_routing_context.py` with tests that verify `RoutingContext`, `RouteDefinition`, `RoutingDimension`, `RouteOrdering` can be imported from the new location and round-trip through serialization. Copy relevant tests from `tests/test_routing_rationale_models.py` that cover these four models only.

```python
# tests/test_routing_context.py
"""Tests for relocated RoutingContext models."""
import pytest
from odysseus.agents.routing_context import (
    RouteDefinition,
    RoutingContext,
    RoutingDimension,
    RouteOrdering,
)


def test_route_definition_creation():
    rd = RouteDefinition(name="simple", description="Simple queries")
    assert rd.name == "simple"
    assert rd.description == "Simple queries"


def test_routing_dimension_creation():
    dim = RoutingDimension(
        name="complexity",
        direction="higher_is_better",
        description="Query complexity",
    )
    assert dim.direction == "higher_is_better"


def test_route_ordering_creation():
    ordering = RouteOrdering(
        dimension="complexity",
        order=["simple", "moderate", "complex"],
    )
    assert len(ordering.order) == 3


def test_routing_context_without_seed_vocabulary():
    """RoutingContext no longer has seed_vocabulary field."""
    ctx = RoutingContext(
        domain="customer support",
        routes=[RouteDefinition(name="simple", description="Simple")],
        routing_dimensions=[
            RoutingDimension(
                name="complexity",
                direction="higher_is_better",
                description="Complexity",
            )
        ],
    )
    assert ctx.domain == "customer support"
    assert "seed_vocabulary" not in RoutingContext.model_fields


def test_routing_context_serialization_roundtrip():
    ctx = RoutingContext(
        domain="test",
        routes=[RouteDefinition(name="a", description="A")],
        routing_dimensions=[
            RoutingDimension(
                name="cost",
                direction="lower_is_better",
                description="Cost",
            )
        ],
        route_ordering=RouteOrdering(dimension="cost", order=["a"]),
    )
    data = ctx.model_dump()
    restored = RoutingContext.model_validate(data)
    assert restored.domain == ctx.domain
    assert restored.route_ordering is not None
    assert restored.route_ordering.order == ["a"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_routing_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'odysseus.agents.routing_context'`

- [ ] **Step 3: Create `odysseus/agents/routing_context.py`**

Copy `RouteDefinition`, `RoutingDimension`, `RouteOrdering`, `RoutingContext` from `odysseus/agents/routing_analysis/models.py`. Drop the `seed_vocabulary` field from `RoutingContext`. Do NOT copy `SeedVocabulary`, `VocabularyEntry`, `RationaleCard`, `RationaleCardSet`, `RouteExclusion`, `VocabularyRegistry`, or any regex constants.

```python
# odysseus/agents/routing_context.py
"""Domain-agnostic routing context models.

Relocated from odysseus.agents.routing_analysis.models as part of
routing analysis agent removal.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator


class RouteDefinition(BaseModel):
    """A single route target in the routing system."""

    name: str
    description: str

    @field_validator("name")
    @classmethod
    def name_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must be non-empty")
        return v.strip()

    @field_validator("description")
    @classmethod
    def description_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must be non-empty")
        return v.strip()


class RoutingDimension(BaseModel):
    """A dimension along which routes differ (e.g., cost, capability)."""

    name: str
    direction: Literal["lower_is_better", "higher_is_better"]
    description: str

    @field_validator("name")
    @classmethod
    def name_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must be non-empty")
        return v.strip()

    @field_validator("description")
    @classmethod
    def description_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must be non-empty")
        return v.strip()


class RouteOrdering(BaseModel):
    """Optional ordering of routes along a specific dimension."""

    dimension: str
    order: list[str]

    @field_validator("order")
    @classmethod
    def order_must_be_non_empty(cls, v: list[str]) -> list[str]:
        if len(v) == 0:
            raise ValueError("order must contain at least one route")
        return v


class RoutingContext(BaseModel):
    """Domain-agnostic routing configuration.

    Synthesized by the Data Validation Agent from the dataset
    and user-provided problem description.
    """

    domain: str
    routes: list[RouteDefinition]
    routing_dimensions: list[RoutingDimension]
    route_ordering: RouteOrdering | None = None

    @field_validator("routes")
    @classmethod
    def routes_must_be_non_empty(cls, v: list[RouteDefinition]) -> list[RouteDefinition]:
        if len(v) == 0:
            raise ValueError("routes must contain at least one route")
        return v

    @field_validator("routing_dimensions")
    @classmethod
    def dimensions_must_be_non_empty(
        cls, v: list[RoutingDimension]
    ) -> list[RoutingDimension]:
        if len(v) == 0:
            raise ValueError("routing_dimensions must contain at least one dimension")
        return v
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_routing_context.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/routing_context.py tests/test_routing_context.py
git commit -m "feat: relocate RoutingContext models to standalone module

Extracts RouteDefinition, RoutingDimension, RouteOrdering, RoutingContext
from routing_analysis subpackage. Drops seed_vocabulary field."
```

---

### Task 2: Simplify and relocate stratified split

**Files:**
- Create: `odysseus/agents/data_validation/split.py`
- Source: `odysseus/agents/routing_analysis/split.py`, `odysseus/agents/routing_analysis/registry.py:23-32`

- [ ] **Step 1: Check if `odysseus/agents/data_validation/` exists as a subpackage**

Run: `ls /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal/odysseus/agents/data_validation/`
If it doesn't exist, create the directory and `__init__.py`.

- [ ] **Step 2: Write tests for simplified split**

Create `tests/test_data_validation_split.py`. The simplified split uses route-only stratification, no rationale cards. Copy/adapt relevant tests from `tests/test_stratified_split.py`.

```python
# tests/test_data_validation_split.py
"""Tests for route-only stratified split."""
import json
import pytest
from odysseus.agents.data_validation.split import (
    compute_dataset_hash,
    stratified_split,
    SplitReport,
)


def _make_example(eid: str, route: str) -> dict:
    return {
        "id": eid,
        "input": f"query for {eid}",
        "expected": {"route": route},
    }


def _make_examples(route_counts: dict[str, int]) -> list[dict]:
    examples = []
    i = 0
    for route, count in route_counts.items():
        for _ in range(count):
            examples.append(_make_example(f"ex_{i}", route))
            i += 1
    return examples


class TestComputeDatasetHash:
    def test_deterministic(self):
        examples = _make_examples({"simple": 3, "complex": 2})
        h1 = compute_dataset_hash(examples)
        h2 = compute_dataset_hash(examples)
        assert h1 == h2

    def test_order_independent(self):
        examples = _make_examples({"simple": 3, "complex": 2})
        h1 = compute_dataset_hash(examples)
        h2 = compute_dataset_hash(list(reversed(examples)))
        assert h1 == h2

    def test_returns_16_hex_chars(self):
        examples = _make_examples({"simple": 3})
        h = compute_dataset_hash(examples)
        assert len(h) == 16
        int(h, 16)  # validates hex


class TestStratifiedSplit:
    def test_basic_split(self):
        examples = _make_examples({"simple": 10, "complex": 10})
        dev, holdout, report = stratified_split(examples)
        assert len(dev) + len(holdout) == 20
        assert len(dev) == 16  # 80% of 20
        assert len(holdout) == 4

    def test_preserves_route_distribution(self):
        examples = _make_examples({"simple": 10, "complex": 10})
        dev, holdout, report = stratified_split(examples)
        dev_routes = {e["expected"]["route"] for e in dev}
        holdout_routes = {e["expected"]["route"] for e in holdout}
        assert "simple" in dev_routes
        assert "complex" in dev_routes
        assert "simple" in holdout_routes or "complex" in holdout_routes

    def test_deterministic(self):
        examples = _make_examples({"simple": 10, "complex": 10})
        dev1, holdout1, _ = stratified_split(examples)
        dev2, holdout2, _ = stratified_split(examples)
        assert [e["id"] for e in dev1] == [e["id"] for e in dev2]
        assert [e["id"] for e in holdout1] == [e["id"] for e in holdout2]

    def test_singletons_go_to_dev(self):
        examples = _make_examples({"simple": 10, "rare": 1})
        dev, holdout, _ = stratified_split(examples)
        rare_in_dev = [e for e in dev if e["expected"]["route"] == "rare"]
        rare_in_holdout = [e for e in holdout if e["expected"]["route"] == "rare"]
        assert len(rare_in_dev) == 1
        assert len(rare_in_holdout) == 0

    def test_split_report_structure(self):
        examples = _make_examples({"simple": 10, "complex": 10})
        _, _, report = stratified_split(examples)
        assert isinstance(report, SplitReport)
        assert report.dev_size + report.holdout_size == 20

    def test_no_rationale_cards_in_signature(self):
        """Split function does not accept rationale card parameters."""
        import inspect
        sig = inspect.signature(stratified_split)
        param_names = set(sig.parameters.keys())
        assert "card_set" not in param_names
        assert "cards" not in param_names
        assert "rationale" not in param_names

    def test_custom_dev_ratio(self):
        examples = _make_examples({"simple": 10, "complex": 10})
        dev, holdout, _ = stratified_split(examples, dev_ratio=0.5)
        assert len(dev) == 10
        assert len(holdout) == 10
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_data_validation_split.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement simplified split**

```python
# odysseus/agents/data_validation/split.py
"""Route-only stratified split for dev/holdout partitioning.

Relocated and simplified from odysseus.agents.routing_analysis.split.
Uses only assigned_route as the stratum key (no rationale card annotations).
"""

from __future__ import annotations

import hashlib
import math
import random
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field


class SplitReport(BaseModel):
    """Report produced alongside the dev/holdout split."""

    dev_size: int
    holdout_size: int
    dev_ratio: float
    dataset_hash: str
    per_route_dev: dict[str, int] = Field(default_factory=dict)
    per_route_holdout: dict[str, int] = Field(default_factory=dict)


def compute_dataset_hash(examples: list[dict[str, Any]]) -> str:
    """Deterministic SHA-256 hash over (id, input, expected.route) tuples.

    Order-independent. Returns 16 hex chars.
    Algorithm matches the original in routing_analysis/registry.py.
    """
    tuples = sorted(
        (str(e["id"]), str(e["input"]), str(e["expected"]["route"]))
        for e in examples
    )
    payload = "\n".join(f"{id_}\t{inp}\t{route}" for id_, inp, route in tuples)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def stratified_split(
    examples: list[dict[str, Any]],
    *,
    dev_ratio: float = 0.8,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], SplitReport]:
    """Split examples into dev and holdout sets, stratified by route.

    Args:
        examples: List of example dicts with expected.route field.
        dev_ratio: Fraction allocated to dev set (default 0.8).

    Returns:
        (dev_examples, holdout_examples, split_report)
    """
    dataset_hash = compute_dataset_hash(examples)
    rng = random.Random(int(dataset_hash, 16))

    # Group by route
    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ex in examples:
        route = ex["expected"]["route"]
        strata[route].append(ex)

    dev: list[dict[str, Any]] = []
    holdout: list[dict[str, Any]] = []
    per_route_dev: dict[str, int] = {}
    per_route_holdout: dict[str, int] = {}

    for route, group in sorted(strata.items()):
        shuffled = list(group)
        rng.shuffle(shuffled)

        if len(shuffled) < 2:
            # Singletons go to dev
            dev.extend(shuffled)
            per_route_dev[route] = len(shuffled)
            per_route_holdout[route] = 0
        else:
            n_dev = max(1, math.floor(len(shuffled) * dev_ratio))
            dev.extend(shuffled[:n_dev])
            holdout.extend(shuffled[n_dev:])
            per_route_dev[route] = n_dev
            per_route_holdout[route] = len(shuffled) - n_dev

    report = SplitReport(
        dev_size=len(dev),
        holdout_size=len(holdout),
        dev_ratio=dev_ratio,
        dataset_hash=dataset_hash,
        per_route_dev=per_route_dev,
        per_route_holdout=per_route_holdout,
    )

    return dev, holdout, report
```

Also update `odysseus/agents/data_validation/__init__.py` — this file already exists with existing exports. Add these imports incrementally (do NOT replace the file):

```python
# Add to existing imports in odysseus/agents/data_validation/__init__.py
from odysseus.agents.data_validation.split import (
    SplitReport,
    compute_dataset_hash,
    stratified_split,
)
# Add to existing __all__: "SplitReport", "compute_dataset_hash", "stratified_split"
```

Also delete `tests/test_stratified_split.py` and `tests/test_stratified_split_card_set.py` — these test the old split interface and are superseded by `tests/test_data_validation_split.py`. The spec lists both under "Delete."

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_data_validation_split.py -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add odysseus/agents/data_validation/split.py odysseus/agents/data_validation/__init__.py tests/test_data_validation_split.py
git commit -m "feat: add route-only stratified split to data_validation subpackage

Simplified split uses assigned_route as sole stratum key.
No rationale card parameters or outputs."
```

---

### Task 3: Relocate stratified_split_tool to data_validation_tools

**Files:**
- Modify: `odysseus/mcp/data_validation_tools.py`
- Source: `odysseus/mcp/routing_analysis_tools.py:155-224`

- [ ] **Step 1: Write test for relocated tool**

Add to `tests/test_mcp.py` or create a focused test. The tool should now import from `data_validation.split`, have no `card_set_path` parameter, and reference Stage 2.

```python
# tests/test_stratified_split_tool_relocation.py
"""Test that stratified_split_tool is available via data_validation_tools."""
import pytest


def test_tool_importable_from_data_validation_tools():
    from odysseus.mcp.data_validation_tools import stratified_split_tool
    assert callable(stratified_split_tool)


def test_tool_has_no_card_set_parameter():
    import inspect
    from odysseus.mcp.data_validation_tools import stratified_split_tool
    sig = inspect.signature(stratified_split_tool)
    param_names = set(sig.parameters.keys())
    assert "card_set_path" not in param_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_stratified_split_tool_relocation.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Add stratified_split_tool to data_validation_tools.py**

Copy `stratified_split_tool` from `routing_analysis_tools.py:155-224` to `data_validation_tools.py`. Modify:
- Import `stratified_split`, `compute_dataset_hash` from `odysseus.agents.data_validation.split` instead of `odysseus.agents.routing_analysis`
- Remove `card_set_path` parameter
- Remove card set loading, validation, and output writes
- Remove `_load_card_set` helper if present
- Update stage reference from `stage=3, stage_name="Routing Analysis"` to `stage=2, stage_name="Data Validation"`
- Update docstring to reflect Stage 2 usage
- Keep `_load_examples`, `_write_jsonl` helpers (or import from existing)

The relocated tool should look like this (adapt imports to match the actual file):

```python
@mcp.tool()
async def stratified_split_tool(
    ctx: Context,
    run_id: str,
    dataset_path: str,
    dev_ratio: float = 0.8,
) -> str:
    """[Stage 2: Data Validation] Split a dataset into dev and holdout partitions.

    Writes dev.jsonl, holdout.jsonl, and split_report.json to
    outputs/<run_id>/analysis/.

    Args:
        run_id: Pipeline run identifier.
        dataset_path: Absolute path to the validated JSONL dataset file.
        dev_ratio: Proportion allocated to dev set. Defaults to 0.8.

    Returns:
        JSON with paths to all output files.
    """
    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    check_artifacts(
        project_dir / "outputs" / run_id / "validation" / "data_quality_report.json",
        stage=2,
        stage_name="Data Validation",
        hint="Complete data validation first.",
    )

    path = Path(dataset_path)
    if not path.is_file():
        raise ToolError(f"Dataset file not found: {dataset_path}")

    examples = _load_examples(path)

    from odysseus.agents.data_validation.split import stratified_split

    dev_examples, holdout_examples, split_report = stratified_split(
        examples, dev_ratio=dev_ratio
    )

    output_dir = project_dir / "outputs" / run_id / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    dev_path = output_dir / "dev.jsonl"
    holdout_path = output_dir / "holdout.jsonl"
    split_report_path = output_dir / "split_report.json"

    _write_jsonl(dev_path, dev_examples)
    _write_jsonl(holdout_path, holdout_examples)
    split_report_path.write_text(
        split_report.model_dump_json(indent=2), encoding="utf-8"
    )

    return json.dumps(
        {
            "dev_path": str(dev_path),
            "holdout_path": str(holdout_path),
            "split_report_path": str(split_report_path),
        },
        indent=2,
    )
```

Ensure `_load_examples` and `_write_jsonl` helpers are available in `data_validation_tools.py` — copy from `routing_analysis_tools.py` or import from a shared module if one exists.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_stratified_split_tool_relocation.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/mcp/data_validation_tools.py tests/test_stratified_split_tool_relocation.py
git commit -m "feat: relocate stratified_split_tool to data_validation_tools

Removed card_set_path parameter, updated stage label to Stage 2.
Imports from data_validation.split instead of routing_analysis."
```

---

## Chunk 2: Pipeline Status & Search State Changes

### Task 4: Update pipeline status — remove stage 3, renumber

**Files:**
- Modify: `odysseus/agents/pipeline/status.py`
- Modify: `tests/test_pipeline_status.py`

- [ ] **Step 1: Update tests for new stage numbering**

Read `tests/test_pipeline_status.py`. Update all tests:
- Remove any tests for stage 3 (Routing Analysis & Split)
- Renumber expected stage numbers: old 4→3, 5→4, 6→5, 7→6, 8→7
- Update expected stage names and artifact lists
- Remove `_check_stage_3` test coverage
- Stage 2 should now require `analysis/dev.jsonl` and `analysis/holdout.jsonl`

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_pipeline_status.py -v`
Expected: FAIL — stage numbers don't match

- [ ] **Step 3: Update `odysseus/agents/pipeline/status.py`**

Changes to make:
1. Remove stage 3 from `_STAGES` list (`"Routing Analysis & Split"` entry with `validation_report.json`, `dev.jsonl`, etc.)
2. Update stage 2 entry: add `analysis/dev.jsonl` and `analysis/holdout.jsonl` to its file checks (this may need a custom `_check_stage_2` since files span two subfolders: `validation/` and `analysis/`)
3. Renumber stages 4-8 to 3-7 in `_STAGES`
4. Delete `_check_stage_3` function entirely
5. Renumber all `_check_stage_*` functions (4→3, 5→4, 6→5, 7→6)
6. Update `_check_stage` dispatcher to match new numbering
7. Renumber `_NEXT_ACTION` keys: delete key 3, shift 4→3, 5→4, 7→6, 8→7
8. Add `stratified_split_tool` to stage 2 `_NEXT_ACTION` tools list
9. Update stage 2 HARD_STOP instruction to include `stratified_split_tool` in sub-agent tool list
10. Delete stage 3 `_NEXT_ACTION` entry and its HARD_STOP instruction
11. Remove `"routing_analysis"` references from prompts lists
12. Update cap for `current_stage` from 8 to 7

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_pipeline_status.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/pipeline/status.py tests/test_pipeline_status.py
git commit -m "refactor: remove stage 3 from pipeline, renumber stages 4-8 to 3-7

Stage 2 (Data Validation) now includes stratified split artifacts.
Routing Analysis stage deleted entirely."
```

---

### Task 5: Update search state — loop_phase defaults to "review"

**Files:**
- Modify: `odysseus/agents/prompt_builder/search.py`
- Modify: `odysseus/agents/prompt_builder/search_ops.py`
- Modify: `tests/test_prompt_builder_search.py`
- Modify: `tests/test_prompt_builder_search_ops.py`

- [ ] **Step 1: Update tests for review-first default**

In `tests/test_prompt_builder_search.py`:
- Find tests that assert `loop_phase == "build"` as default and change to `"review"`

In `tests/test_prompt_builder_search_ops.py`:
- Find tests for `init_search_state` and update expected `loop_phase` default to `"review"`

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_prompt_builder_search.py tests/test_prompt_builder_search_ops.py -v`
Expected: FAIL — loop_phase assertions don't match

- [ ] **Step 3: Update search.py and search_ops.py**

In `odysseus/agents/prompt_builder/search.py`:
- Change `loop_phase: Literal["build", "review"] = "build"` to `loop_phase: Literal["build", "review"] = "review"`

In `odysseus/agents/prompt_builder/search_ops.py`:
- If `init_search_state()` explicitly sets `loop_phase="build"`, change to `loop_phase="review"`

Also update `_next_action_for_stage_6` in `pipeline/status.py` — this function handles the refinement loop (old stage 6, now stage 5 after renumbering). Rename to `_next_action_for_stage_5` and change the default `loop_phase = "build"` fallback to `loop_phase = "review"`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_prompt_builder_search.py tests/test_prompt_builder_search_ops.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/prompt_builder/search.py odysseus/agents/prompt_builder/search_ops.py odysseus/agents/pipeline/status.py tests/test_prompt_builder_search.py tests/test_prompt_builder_search_ops.py
git commit -m "refactor: default loop_phase to 'review' for review-first entry

Review Agent now runs first in the refinement loop (cold-start)
before Prompt Builder assembles v1."
```

---

### Task 6: Update review models — concrete example directives

**Files:**
- Modify: `odysseus/agents/review/models.py`
- Modify: `tests/test_review_models.py`

- [ ] **Step 1: Update tests for example content in directives**

Read `odysseus/agents/review/models.py` and `tests/test_review_models.py`. Add tests for:
- `EditDirective` with `block_type="example"` now includes an `example_content` field (optional, used when `block_type == "example"`)
- `ExampleContent` model with fields: `input`, `route`, `reasoning`, `exclusions` (list of `{route, reason}`)
- `ExampleSummary` drops `ambiguity_tags` field

```python
# Add to tests/test_review_models.py
from odysseus.agents.review.models import ExampleContent


def test_example_content_model():
    content = ExampleContent(
        input="Build a multi-step data pipeline",
        route="complex",
        reasoning="Requires chained operations with control flow",
        exclusions=[
            {"route": "simple", "reason": "Single-step tasks only"},
            {"route": "moderate", "reason": "No error handling at this tier"},
        ],
    )
    assert content.route == "complex"
    assert len(content.exclusions) == 2


def test_edit_directive_with_example_content():
    directive = EditDirective(
        directive_id="d1",
        target_version="v2",
        block_type="example",
        block_identifier="example_0",
        granularity="macro",
        directive="Replace with boundary case example",
        priority="high",
        example_content=ExampleContent(
            input="Translate this document",
            route="moderate",
            reasoning="Requires language understanding but no multi-step logic",
            exclusions=[{"route": "simple", "reason": "Needs domain knowledge"}],
        ),
    )
    assert directive.example_content is not None
    assert directive.example_content.route == "moderate"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_review_models.py -v -k "example_content"`
Expected: FAIL

- [ ] **Step 3: Implement ExampleContent and update EditDirective**

In `odysseus/agents/review/models.py`:

```python
class ExampleContent(BaseModel):
    """Concrete content for a few-shot example."""

    input: str = Field(description="The example input/query text")
    route: str = Field(description="The assigned route for this example")
    reasoning: str = Field(description="Why this route fits")
    exclusions: list[dict[str, str]] = Field(
        description="List of {route, reason} for excluded routes"
    )
```

Add `example_content: ExampleContent | None = None` field to `EditDirective`.

Remove `ambiguity_tags` from `ExampleSummary` (make it optional with default `[]` to avoid breaking callers before they're updated — trace all callers that construct `ExampleSummary` objects, including `build_review_briefing_tool` in `odysseus/mcp/review_tools.py`).

Also add `ExampleContent` to `odysseus/agents/review/__init__.py` re-exports:
- Add `ExampleContent` to the import block from `odysseus.agents.review.models`
- Add `"ExampleContent"` to `__all__`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_review_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/review/models.py tests/test_review_models.py
git commit -m "feat: add ExampleContent model for concrete example directives

EditDirective.example_content carries full example body with reasoning
and tier exclusions when block_type is 'example'."
```

---

## Chunk 3: MCP Surface Cleanup

### Task 7: Remove routing analysis from MCP registrations

**Files:**
- Modify: `odysseus/mcp/server.py`
- Modify: `odysseus/mcp/prompts.py`
- Modify: `odysseus/mcp/resources.py`
- Modify: `odysseus/mcp/__init__.py`

- [ ] **Step 1: Update MCP tests**

Read `tests/test_mcp.py`. Remove or update tests that reference:
- `create_seed_registry_tool`, `resolve_registry_tool`, `validate_rationale_card_set_tool`, `prune_registry_tool`
- `odysseus_routing_analysis` prompt
- Routing analysis skill resources
- Stage 3 in `STAGE_REGISTRY`

Add assertions that `stratified_split_tool` is importable from `data_validation_tools`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_mcp.py -v`
Expected: FAIL — deleted tools still registered

- [ ] **Step 3: Update `odysseus/mcp/server.py`**

- Remove `"3: routing_analysis_system.md"` from `_STAGE_PROMPT_MAP`
- Remove the `"routing_analysis"` entry from `STAGE_REGISTRY`
- Add `stratified_split_tool` to the `"data_validation"` entry in `STAGE_REGISTRY`
- Remove `import odysseus.mcp.routing_analysis_tools as _routing_analysis_tools`
- Renumber remaining stage entries (4→3, 5→4, etc.)
- Update the RoutingContext import from `odysseus.agents.routing_analysis` to `odysseus.agents.routing_context`

- [ ] **Step 4: Update `odysseus/mcp/prompts.py`**

- Delete the `odysseus_routing_analysis()` prompt function

- [ ] **Step 5: Update `odysseus/mcp/resources.py`**

- Delete `classify_example_skill()`, `generate_rationale_skill()`, `check_overlap_skill()` resource functions

- [ ] **Step 6: Update `odysseus/mcp/__init__.py`**

- Remove `from odysseus.mcp.routing_analysis_tools import (...)` block entirely (all 5 imports: `create_seed_registry_tool`, `prune_registry_tool`, `resolve_registry_tool`, `stratified_split_tool`, `validate_rationale_card_set_tool`)
- Add `stratified_split_tool` to the `from odysseus.mcp.data_validation_tools import (...)` block
- Update `__all__`: remove the 4 deleted tools, keep `stratified_split_tool` (now sourced from data_validation_tools)

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_mcp.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add odysseus/mcp/server.py odysseus/mcp/prompts.py odysseus/mcp/resources.py odysseus/mcp/__init__.py tests/test_mcp.py
git commit -m "refactor: remove routing analysis from MCP registrations

Deletes 4 tools, 1 prompt, 3 resources. Moves stratified_split_tool
to data_validation stage in STAGE_REGISTRY."
```

---

**Chunk 3 checkpoint:** Run `uv run pytest --tb=short` to catch any cross-cutting breakage before proceeding to deletions.

---

## Chunk 4: Delete Routing Analysis Subpackage & Cleanup Imports

### Task 8: Update agents/__init__.py re-exports

**Files:**
- Modify: `odysseus/agents/__init__.py`

- [ ] **Step 1: Read current `odysseus/agents/__init__.py`**

Identify all re-exports from `routing_analysis` subpackage (lines ~71-106 and `__all__` entries ~143-176).

- [ ] **Step 2: Remove routing analysis re-exports**

- Remove the entire `from odysseus.agents.routing_analysis import (...)` block
- Add `from odysseus.agents.routing_context import (RoutingContext, RouteDefinition, RoutingDimension, RouteOrdering)` for backward compatibility
- Add `from odysseus.agents.data_validation.split import (stratified_split, compute_dataset_hash, SplitReport)` for backward compatibility
- Update `__all__` to remove all deleted symbols and add the relocated ones

- [ ] **Step 3: Run tests to verify imports still work**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_routing_context.py tests/test_data_validation_split.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add odysseus/agents/__init__.py
git commit -m "refactor: update agents __init__ re-exports for routing analysis removal

Removes routing_analysis imports, adds routing_context and
data_validation.split re-exports."
```

---

### Task 9: Delete routing analysis subpackage and related files

**Files:**
- Delete: `odysseus/agents/routing_analysis/` (entire directory)
- Delete: `odysseus/agents/prompts/routing_analysis_system.md`
- Delete: `odysseus/mcp/routing_analysis_tools.py`
- Delete: `odysseus/skills/classify-example/`
- Delete: `odysseus/skills/generate-routing-rationale/`
- Delete: `odysseus/skills/check-semantic-overlap/`
- Delete: `tests/test_routing_rationale_models.py`
- Delete: `tests/test_routing_rationale_registry.py`
- Delete: `tests/test_routing_rationale_checks.py`
- Delete: `tests/test_deterministic_validation.py`
- Delete: `tests/test_stratified_split_card_set.py`

- [ ] **Step 1: Delete all files**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal
rm -rf odysseus/agents/routing_analysis/
rm odysseus/agents/prompts/routing_analysis_system.md
rm odysseus/mcp/routing_analysis_tools.py
rm -rf odysseus/skills/classify-example/
rm -rf odysseus/skills/generate-routing-rationale/
rm -rf odysseus/skills/check-semantic-overlap/
rm tests/test_routing_rationale_models.py
rm tests/test_routing_rationale_registry.py
rm tests/test_routing_rationale_checks.py
rm tests/test_deterministic_validation.py
rm tests/test_stratified_split_card_set.py
```

- [ ] **Step 2: Run full test suite to check for broken imports**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest --tb=short 2>&1 | head -80`
Expected: No `ImportError` or `ModuleNotFoundError`. Some tests may fail for other reasons (stage numbers, etc.) but there should be no import failures.

- [ ] **Step 3: Fix any remaining broken imports**

Grep for any remaining references to `routing_analysis`, `routing_rationale`, `RationaleCard`, `VocabularyRegistry`, `RouteExclusion` in the codebase (excluding tests/scenarios/ and docs/). Fix each import.

```bash
cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal
grep -r "routing_analysis\|routing_rationale\|RationaleCard\|VocabularyRegistry\|RouteExclusion\|SeedVocabulary" odysseus/ --include="*.py" -l
```

- [ ] **Step 4: Run full test suite again**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest --tb=short`
Expected: No import errors. Test failures should only be from not-yet-updated test logic, not missing modules.

- [ ] **Step 5: Commit**

```bash
git add -u  # stages only tracked file deletions, not untracked files
git commit -m "refactor: delete routing analysis subpackage and related files

Removes: routing_analysis/ subpackage, routing_analysis_tools.py,
routing_analysis_system.md, 3 skill directories, 5 test files."
```

---

## Chunk 5: Agent Prompt Updates

### Task 10: Update Review Agent system prompt — cold-start & example crafting

**Files:**
- Modify: `odysseus/agents/prompts/review_agent_system.md`

- [ ] **Step 1: Read current prompt**

Read `odysseus/agents/prompts/review_agent_system.md` in full.

- [ ] **Step 2: Add cold-start phase**

Add a new section before the existing review flow. The cold-start phase:
- Triggers when no search state exists (first dispatch in refinement loop)
- Review Agent reads `holdout.jsonl` and `routing_context.json`
- Selects 3-5 diverse examples covering different routes
- Crafts each example with: input, route, reasoning, tier exclusions
- Emits as `edit_directives` with `block_type: "example"` and populated `example_content`
- Advances loop_phase to `"build"` after emitting

- [ ] **Step 3: Update edit directive section**

Update the edit directive guidelines:
- `block_type: "example"` directives MUST include `example_content` with full body
- Example content includes: `input`, `route`, `reasoning`, `exclusions` (list of `{route, reason}`)
- Review Agent selects examples based on failure modes from eval results
- Remove any references to rationale cards, vocabulary registry, annotation taxonomy

- [ ] **Step 4: Remove rationale card references**

Search the prompt for any mentions of:
- rationale cards, card sets
- vocabulary registry
- intent_pattern, complexity_structure
- ambiguity_tags (if referenced as rationale card field)
- routing analysis agent

Remove or replace these references.

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/prompts/review_agent_system.md
git commit -m "feat: add cold-start phase and example crafting to Review Agent prompt

Review Agent is now the refinement loop entry point. Crafts initial
examples from holdout data and refines based on eval failure modes."
```

---

### Task 11: Update Prompt Builder system prompt

**Files:**
- Modify: `odysseus/agents/prompts/prompt_builder_system.md`

- [ ] **Step 1: Read current prompt**

Read `odysseus/agents/prompts/prompt_builder_system.md` in full.

- [ ] **Step 2: Update prompt**

Changes:
- Remove all references to rationale cards, vocabulary registry, holdout rationale card set
- Round 1 no longer selects examples — it receives example directives from Review Agent
- Update entry verification: stage numbers shift (check `current_stage` values)
- Prompt Builder assembles examples provided by Review Agent, does NOT select them
- Structure, rules, output schema remain Prompt Builder's responsibility

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/prompts/prompt_builder_system.md
git commit -m "refactor: update Prompt Builder prompt for review-first loop

Prompt Builder receives examples from Review Agent directives.
Removes rationale card references and example selection logic."
```

---

### Task 12: Update Data Validation system prompt

**Files:**
- Modify: `odysseus/agents/prompts/data_validation_system.md`

- [ ] **Step 1: Read current prompt**

Read `odysseus/agents/prompts/data_validation_system.md` in full.

- [ ] **Step 2: Update prompt**

Changes:
- Add Phase 3 — Split: after validation passes, call `stratified_split_tool`
- Remove `seed_vocabulary` from RoutingContext synthesis section (field count drops from 5 to 4)
- Update outputs list to include `dev.jsonl` and `holdout.jsonl`
- Update exit criteria to include split artifacts

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/prompts/data_validation_system.md
git commit -m "feat: add stratified split phase to Data Validation Agent prompt

Phase 3 calls stratified_split_tool after validation.
Drops seed_vocabulary from RoutingContext."
```

---

## Chunk 6: Review Preprocessor & Remaining Cleanup

### Task 13: Update review preprocessor

**Files:**
- Modify: `odysseus/agents/review/preprocessor.py`

- [ ] **Step 1: Read current preprocessor**

Read `odysseus/agents/review/preprocessor.py` in full. Identify all rationale card references.

- [ ] **Step 2: Remove rationale card dependencies**

The preprocessor itself does not import rationale card models directly. The changes are:
- `ExampleSummary` objects are received as parameters — callers (e.g., `build_review_briefing_tool` in `odysseus/mcp/review_tools.py`) construct them. Update callers to construct `ExampleSummary` without `ambiguity_tags` (now optional/removed).
- If `compute_diversity_metrics` references rationale-card-based fields, update to use route-based diversity only.
- The briefing's `holdout_examples` field stays but carries simplified `ExampleSummary` objects.

- [ ] **Step 3: Run tests**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/ -k "review" --tb=short -v`
Expected: PASS — verify no import errors or missing field errors

- [ ] **Step 4: Commit**

```bash
git add odysseus/agents/review/preprocessor.py
git commit -m "refactor: remove rationale card references from review preprocessor

Briefing now includes raw holdout examples instead of card summaries."
```

---

### Task 14: Update existing stratified split tests

**Files:**
- Modify: `tests/test_stratified_split.py`

- [ ] **Step 1: Read and update tests**

Read `tests/test_stratified_split.py`. This file tests the OLD split and imports `SplitMismatchError`, `validate_split_inputs`, and other symbols from `routing_analysis`. Since Task 2 already created `tests/test_data_validation_split.py` with comprehensive coverage of the new route-only split, **delete this file** — it was already listed for deletion in Task 2 Step 4 but adding an explicit cleanup step here for safety.

Note: `SplitMismatchError` and `validate_split_inputs` are dropped — the simplified split has no card-set validation to mismatch against. The new split validates only that `examples` is non-empty (implicit in the route grouping logic).

- [ ] **Step 2: Run tests**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest tests/test_stratified_split.py -v`
Expected: PASS (or file deleted)

- [ ] **Step 3: Commit**

```bash
git add tests/test_stratified_split.py
git commit -m "refactor: update stratified split tests for route-only split

Tests import from data_validation.split, no rationale card references."
```

---

### Task 15: Update documentation

**Files:**
- Modify: `docs/architecture.md`
- Modify: `odysseus/agents/README.md`

- [ ] **Step 1: Update `docs/architecture.md`**

Read current file. Make these changes:
- Update pipeline flow diagram: remove stage 3 (Routing Analysis)
- Update stage table: renumber, remove routing analysis row
- Update agent table: remove routing analysis agent
- Update context dict keys: remove rationale-related keys
- Update model documentation: remove rationale card models
- Update tool table: remove 4 routing analysis tools, move stratified_split_tool to stage 2
- Update prompt table: remove routing analysis prompt
- Update resource table: remove 3 routing analysis resources
- Update artifact directory descriptions

- [ ] **Step 2: Update `odysseus/agents/README.md`**

Read current file. Remove:
- Routing analysis subpackage documentation
- Rationale card model docs
- Registry operation docs
- Validation check docs

Update:
- Split documentation to reference `data_validation/split.py`
- RoutingContext documentation to reference `routing_context.py`

- [ ] **Step 3: Commit**

```bash
git add docs/architecture.md odysseus/agents/README.md
git commit -m "docs: update architecture and agents README for routing analysis removal

Pipeline flow, stage tables, model docs, tool tables updated.
Routing analysis references removed throughout."
```

---

### Task 16: Delete or update routing analysis scenario files

**Files:**
- Delete/modify: `tests/scenarios/23_*.md` through `tests/scenarios/36_*.md` (routing-analysis-specific)
- Modify: `tests/scenarios/README.md`

- [ ] **Step 1: Identify scenario files to delete or update**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal
grep -rl "rationale\|card_set\|classify_example\|routing_analysis\|create_seed_registry\|validate_rationale\|vocabulary_registry" tests/scenarios/ --include="*.md"
```

This will match scenarios 23-36 (routing-analysis-specific) AND scenarios 37-53 (pipeline/review/prompt-builder scenarios that reference rationale cards or the old pipeline flow). Review each:
- **Delete** scenarios that purely test routing analysis agent behavior (23-36)
- **Update** pipeline/review/prompt-builder scenarios (37-53) to remove routing analysis references and adjust to the new pipeline flow

- [ ] **Step 2: Delete routing analysis scenarios**

Delete identified files.

- [ ] **Step 3: Update `tests/scenarios/README.md`**

Remove deleted scenarios from the index table. Renumber if needed.

- [ ] **Step 4: Commit**

```bash
git add -A tests/scenarios/
git commit -m "refactor: remove routing analysis scenario files

Deletes scenarios testing routing analysis agent behavior.
Updates scenario index."
```

---

### Task 17: Final verification — full test suite and lint

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pytest --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Run linter**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run ruff check .`
Expected: No errors

- [ ] **Step 3: Run formatter**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run ruff format .`

- [ ] **Step 4: Run type checker**

Run: `cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal && uv run pyright`
Expected: No errors related to routing analysis imports

- [ ] **Step 5: Grep for any remaining references**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus/.claude/worktrees/routing-analysis-removal
grep -r "routing_analysis\|routing_rationale\|RationaleCard\|VocabularyRegistry\|RouteExclusion\|SeedVocabulary\|VocabularyEntry" odysseus/ tests/ --include="*.py" --include="*.md" -l
```

Expected: No matches in Python files. Only matches in spec/plan docs.

- [ ] **Step 6: Final commit if any fixups needed**

```bash
git add -A
git commit -m "style: fix lint and formatting after routing analysis removal"
```
