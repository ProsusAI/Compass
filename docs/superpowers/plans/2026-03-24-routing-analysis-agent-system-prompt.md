# Routing Analysis Agent System Prompt — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the unified Routing Analysis Agent system prompt and supporting infrastructure (MCP tools, skill, split extension) so the agent can orchestrate the full annotation-validation-split pipeline.

**Architecture:** System prompt as orchestrator (Approach C) — the prompt defines phases and sequencing, activates existing annotation skills (`classify-example`, `generate-routing-rationale`) plus a new `check-semantic-overlap` skill, and calls MCP tools for deterministic operations. The `stratified_split` function is extended to partition card sets alongside examples.

**Tech Stack:** Python 3.11+, uv, MCP (FastMCP), Agent Skills spec, pytest, ruff, pyright

**Spec:** `docs/superpowers/specs/2026-03-24-routing-analysis-agent-system-prompt-design.md`

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `odysseus/agents/prompts/routing_analysis_system.md` | Agent system prompt |
| Create | `odysseus/skills/check-semantic-overlap/SKILL.md` | Semantic overlap skill |
| Create | `odysseus/skills/check-semantic-overlap/references/vocabulary-registry-rules.md` | Shared reference (symlink or copy from classify-example) |
| Modify | `odysseus/agents/stratified_split.py:68-125` | Extend to return split card sets |
| Modify | `odysseus/agents/stratified_split.py:128-171` | Update `_build_result` return type |
| Create | `odysseus/agents/routing_rationale_checks_deterministic.py` | Deterministic-only validation runner (no judge_fn) |
| Modify | `odysseus/mcp.py` | Register new tools + prompt + resources |
| Modify | `odysseus/agents/__init__.py` | Export new symbols |
| Modify | `docs/architecture.md` | Add context keys, update agent row |
| Create | `tests/test_stratified_split_card_set.py` | Tests for card set splitting |
| Create | `tests/test_deterministic_validation.py` | Tests for deterministic validation runner |
| Modify | `tests/test_stratified_split.py` | Update existing tests for new return type |
| Create | `tests/scenarios/29_routing_analysis_startup.md` | Integration scenario: agent reads inputs |
| Create | `tests/scenarios/30_routing_analysis_full_pipeline.md` | Integration scenario: full pipeline |

---

## Chunk 1: Extend stratified_split to partition card sets

### Task 1: Write failing test for card set splitting

**Files:**
- Create: `tests/test_stratified_split_card_set.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for stratified_split card set partitioning."""

from __future__ import annotations

from datetime import datetime

from odysseus.agents.routing_rationale_models import (
    RationaleCard,
    RationaleCardSet,
    RouteExclusion,
    VocabularyEntry,
    VocabularyRegistry,
)
from odysseus.agents.stratified_split import stratified_split
from odysseus.eval.models import Example, Expected, ModelCostQuality


def _make_example(id_: str, input_: str, route: str) -> Example:
    """Create a minimal Example for testing."""
    return Example(
        id=id_,
        input=input_,
        expected=Expected(
            route=route,
            routes={route: ModelCostQuality(cost=0.01, quality_score=0.9)},
        ),
        split="dev",
    )


def _make_card(example_id: str, route: str, intent: str, complexity: str):
    return RationaleCard(
        example_id=example_id,
        assigned_route=route,
        intent_pattern=intent,
        complexity_structure=complexity,
        route_exclusions=[
            RouteExclusion(route="other", reason="not relevant"),
        ],
        ambiguity_tags=[],
    )


def _make_registry():
    return VocabularyRegistry(
        intent_pattern=[
            VocabularyEntry(
                name="direct-question",
                definition="A straightforward question",
                example_ids=["ex1", "ex2", "ex3", "ex4"],
            ),
        ],
        complexity_structure=[
            VocabularyEntry(
                name="single-step",
                definition="One-step reasoning",
                example_ids=["ex1", "ex2", "ex3", "ex4"],
            ),
        ],
        ambiguity_tags=[],
    )


def _make_card_set(examples, cards, registry):
    return RationaleCardSet(
        cards=cards,
        dataset_hash="abc123",
        registry=registry,
        created_at=datetime(2026, 1, 1),
    )


def test_split_returns_five_elements():
    """stratified_split returns (dev, holdout, dev_cards, holdout_cards, report)."""
    examples = [
        _make_example(f"ex{i}", f"query {i}", "route-a")
        for i in range(1, 5)
    ]
    cards = {
        ex.id: _make_card(ex.id, "route-a", "direct-question", "single-step")
        for ex in examples
    }
    registry = _make_registry()
    card_set = _make_card_set(examples, cards, registry)

    result = stratified_split(examples, card_set)
    assert len(result) == 5, f"Expected 5-tuple, got {len(result)}-tuple"

    dev_ex, holdout_ex, dev_cards, holdout_cards, report = result
    assert isinstance(dev_cards, RationaleCardSet)
    assert isinstance(holdout_cards, RationaleCardSet)


def test_split_card_sets_match_examples():
    """Dev/holdout card sets contain exactly the cards for their examples."""
    examples = [
        _make_example(f"ex{i}", f"query {i}", "route-a")
        for i in range(1, 11)
    ]
    cards = {
        ex.id: _make_card(ex.id, "route-a", "direct-question", "single-step")
        for ex in examples
    }
    registry = _make_registry()
    card_set = _make_card_set(examples, cards, registry)

    dev_ex, holdout_ex, dev_cards, holdout_cards, report = stratified_split(
        examples, card_set
    )

    dev_ids = {ex.id for ex in dev_ex}
    holdout_ids = {ex.id for ex in holdout_ex}

    assert set(dev_cards.cards.keys()) == dev_ids
    assert set(holdout_cards.cards.keys()) == holdout_ids


def test_split_card_sets_share_registry():
    """Both dev and holdout card sets have the same registry."""
    examples = [
        _make_example(f"ex{i}", f"query {i}", "route-a")
        for i in range(1, 5)
    ]
    cards = {
        ex.id: _make_card(ex.id, "route-a", "direct-question", "single-step")
        for ex in examples
    }
    registry = _make_registry()
    card_set = _make_card_set(examples, cards, registry)

    _, _, dev_cards, holdout_cards, _ = stratified_split(examples, card_set)

    assert dev_cards.registry == holdout_cards.registry
    assert dev_cards.dataset_hash == holdout_cards.dataset_hash


def test_degenerate_single_example_all_to_dev():
    """Single example: all goes to dev, holdout card set is empty."""
    examples = [_make_example("ex1", "query 1", "route-a")]
    cards = {"ex1": _make_card("ex1", "route-a", "direct-question", "single-step")}
    registry = _make_registry()
    card_set = _make_card_set(examples, cards, registry)

    dev_ex, holdout_ex, dev_cards, holdout_cards, _ = stratified_split(
        examples, card_set
    )

    assert len(dev_ex) == 1
    assert len(holdout_ex) == 0
    assert set(dev_cards.cards.keys()) == {"ex1"}
    assert len(holdout_cards.cards) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stratified_split_card_set.py -v`
Expected: FAIL — `stratified_split` returns 3-tuple, not 5-tuple

- [ ] **Step 3: Commit failing test**

```bash
git add tests/test_stratified_split_card_set.py
git commit -m "test: add failing tests for card set partitioning in stratified_split"
```

### Task 2: Extend stratified_split to return split card sets

**Files:**
- Modify: `odysseus/agents/stratified_split.py:68-171`

- [ ] **Step 4: Update `_build_result` to partition card set and return 5-tuple**

In `odysseus/agents/stratified_split.py`, change `_build_result` (line 128) to:

```python
def _build_result(
    dev: list[Example],
    holdout: list[Example],
    all_examples: list[Example],
    card_set: RationaleCardSet,
    dev_ratio: float,
    singleton_strata_count: int = 0,
) -> tuple[list[Example], list[Example], RationaleCardSet, RationaleCardSet, SplitReport]:
    """Construct the split result with partitioned card sets and report."""
    dataset_hash = compute_dataset_hash(all_examples)

    dev_ids = {ex.id for ex in dev}
    holdout_ids = {ex.id for ex in holdout}

    # Partition card set
    dev_card_set = RationaleCardSet(
        cards={eid: card_set.cards[eid] for eid in dev_ids},
        dataset_hash=card_set.dataset_hash,
        registry=card_set.registry,
        created_at=card_set.created_at,
        inherited_from=card_set.inherited_from,
    )
    holdout_card_set = RationaleCardSet(
        cards={eid: card_set.cards[eid] for eid in holdout_ids},
        dataset_hash=card_set.dataset_hash,
        registry=card_set.registry,
        created_at=card_set.created_at,
        inherited_from=card_set.inherited_from,
    )

    # Build strata report
    strata_counts: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {"total": 0, "dev": 0, "holdout": 0}
    )
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
    return dev, holdout, dev_card_set, holdout_card_set, report
```

- [ ] **Step 5: Update `stratified_split` return type annotation (line 72)**

Change the return type on line 72 from:
```python
) -> tuple[list[Example], list[Example], SplitReport]:
```
to:
```python
) -> tuple[list[Example], list[Example], RationaleCardSet, RationaleCardSet, SplitReport]:
```

Also update the docstring Returns section to:
```
Returns:
    (dev_examples, holdout_examples, dev_card_set, holdout_card_set, report)
```

- [ ] **Step 6: Update existing tests in `tests/test_stratified_split.py`**

All existing tests unpack the 3-tuple. Update them to unpack the 5-tuple. The pattern is:
```python
# Before:
dev, holdout, report = stratified_split(examples, card_set)
# After:
dev, holdout, _dev_cards, _holdout_cards, report = stratified_split(examples, card_set)
```

- [ ] **Step 7: Run all split tests**

Run: `uv run pytest tests/test_stratified_split.py tests/test_stratified_split_card_set.py -v`
Expected: ALL PASS

- [ ] **Step 8: Run linting and type checks**

Run: `uv run ruff check odysseus/agents/stratified_split.py && uv run pyright odysseus/agents/stratified_split.py`
Expected: Clean

- [ ] **Step 9: Commit**

```bash
git add odysseus/agents/stratified_split.py tests/test_stratified_split.py tests/test_stratified_split_card_set.py
git commit -m "feat: extend stratified_split to partition card sets into dev/holdout"
```

---

## Chunk 2: Deterministic validation runner

### Task 3: Write failing test for deterministic validation

**Files:**
- Create: `tests/test_deterministic_validation.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for deterministic validation runner (no LLM judge)."""

from __future__ import annotations

from datetime import datetime

from odysseus.agents.routing_rationale_checks_deterministic import (
    validate_deterministic,
)
from odysseus.agents.routing_rationale_models import (
    RationaleCard,
    RationaleCardSet,
    RouteDefinition,
    RouteExclusion,
    RoutingContext,
    RoutingDimension,
    VocabularyEntry,
    VocabularyRegistry,
)


def _make_routing_context():
    return RoutingContext(
        domain="test",
        routes=[
            RouteDefinition(name="route-a", description="Route A"),
            RouteDefinition(name="route-b", description="Route B"),
        ],
        routing_dimensions=[
            RoutingDimension(
                name="complexity",
                direction="lower_is_better",
                description="test",
            ),
        ],
    )


def _make_valid_card_set():
    registry = VocabularyRegistry(
        intent_pattern=[
            VocabularyEntry(
                name="direct-question",
                definition="A straightforward question",
                example_ids=["ex1", "ex2", "ex3"],
            ),
        ],
        complexity_structure=[
            VocabularyEntry(
                name="single-step",
                definition="One-step reasoning",
                example_ids=["ex1", "ex2", "ex3"],
            ),
        ],
        ambiguity_tags=[],
    )
    cards = {
        f"ex{i}": RationaleCard(
            example_id=f"ex{i}",
            assigned_route="route-a",
            intent_pattern="direct-question",
            complexity_structure="single-step",
            route_exclusions=[
                RouteExclusion(route="route-b", reason="not relevant"),
            ],
            ambiguity_tags=[],
        )
        for i in range(1, 4)
    }
    return RationaleCardSet(
        cards=cards,
        dataset_hash="abc",
        registry=registry,
        created_at=datetime(2026, 1, 1),
    )


def test_valid_card_set_all_pass():
    """Valid card set passes all deterministic checks."""
    ctx = _make_routing_context()
    card_set = _make_valid_card_set()
    results = validate_deterministic(card_set, ctx, dataset_size=3)
    failures = [r for r in results if not r.passed]
    assert failures == [], f"Unexpected failures: {failures}"


def test_does_not_include_registry_consistency():
    """Deterministic runner excludes check_registry_consistency."""
    ctx = _make_routing_context()
    card_set = _make_valid_card_set()
    results = validate_deterministic(card_set, ctx, dataset_size=3)
    check_names = {r.check_name for r in results}
    assert "check_registry_consistency" not in check_names


def test_missing_exclusion_detected():
    """Missing route exclusion is caught."""
    ctx = _make_routing_context()
    card_set = _make_valid_card_set()
    # Remove the exclusion for route-b
    card_set.cards["ex1"].route_exclusions = []
    results = validate_deterministic(card_set, ctx, dataset_size=3)
    coverage_results = [r for r in results if r.check_name == "check_exclusion_coverage"]
    failed = [r for r in coverage_results if not r.passed]
    assert len(failed) == 1
    assert "ex1" in failed[0].affected_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_deterministic_validation.py -v`
Expected: FAIL — `routing_rationale_checks_deterministic` module not found

- [ ] **Step 3: Commit failing test**

```bash
git add tests/test_deterministic_validation.py
git commit -m "test: add failing tests for deterministic validation runner"
```

### Task 4: Implement deterministic validation runner

**Files:**
- Create: `odysseus/agents/routing_rationale_checks_deterministic.py`

- [ ] **Step 4: Write the deterministic runner**

```python
"""Deterministic validation checks for routing rationale card sets.

Wraps the individual check functions from routing_rationale_checks,
excluding the async LLM-judged check_registry_consistency. This module
is used by the MCP tool — semantic overlap is handled by the
check-semantic-overlap skill instead.
"""

from __future__ import annotations

from odysseus.agents.routing_rationale_checks import (
    RationaleCheckResult,
    check_ambiguity_tag_membership,
    check_cluster_thresholds,
    check_exclusion_coverage,
    check_exclusion_format,
    check_pruning_cleanup,
    check_required_fields,
    check_vocabulary_membership,
    find_orphaned_examples,
)
from odysseus.agents.routing_rationale_models import (
    RationaleCardSet,
    RoutingContext,
)


def validate_deterministic(
    card_set: RationaleCardSet,
    routing_context: RoutingContext,
    dataset_size: int,
) -> list[RationaleCheckResult]:
    """Run all deterministic validation checks on a RationaleCardSet.

    Same ordering as validate_rationale_card_set but without
    check_registry_consistency (the async LLM-judged check).

    Returns a flat list of RationaleCheckResult in the order:
    1. check_cluster_thresholds
    2. check_pruning_cleanup
    3. find_orphaned_examples
    4. Per-card: check_required_fields, check_vocabulary_membership,
       check_exclusion_coverage, check_exclusion_format,
       check_ambiguity_tag_membership
    """
    results: list[RationaleCheckResult] = []

    # --- Dataset-level checks ---
    results.append(check_cluster_thresholds(card_set.registry, dataset_size))
    results.append(check_pruning_cleanup(card_set))
    results.append(find_orphaned_examples(card_set))

    # --- Per-card checks ---
    available_routes = {r.name for r in routing_context.routes}
    for card in card_set.cards.values():
        results.append(check_required_fields(card, card_set.registry))
        results.append(check_vocabulary_membership(card, card_set.registry))
        results.append(check_exclusion_coverage(card, available_routes))
        results.append(check_exclusion_format(card))
        results.append(check_ambiguity_tag_membership(card, card_set.registry))

    return results
```

- [ ] **Step 5: Export from `__init__.py`**

Add `validate_deterministic` to `odysseus/agents/__init__.py` imports and `__all__`.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_deterministic_validation.py -v`
Expected: ALL PASS

- [ ] **Step 7: Lint and type check**

Run: `uv run ruff check odysseus/agents/routing_rationale_checks_deterministic.py && uv run pyright odysseus/agents/routing_rationale_checks_deterministic.py`
Expected: Clean

- [ ] **Step 8: Commit**

```bash
git add odysseus/agents/routing_rationale_checks_deterministic.py odysseus/agents/__init__.py tests/test_deterministic_validation.py
git commit -m "feat: add deterministic validation runner (no LLM judge)"
```

---

## Chunk 3: Create check-semantic-overlap skill

### Task 5: Create the skill using skill-creator

**Files:**
- Create: `odysseus/skills/check-semantic-overlap/SKILL.md`
- Create: `odysseus/skills/check-semantic-overlap/references/vocabulary-registry-rules.md`

- [ ] **Step 1: Create skill directory**

```bash
mkdir -p odysseus/skills/check-semantic-overlap/references
```

- [ ] **Step 2: Write SKILL.md**

Use the `example-skills:skill-creator` skill to create `odysseus/skills/check-semantic-overlap/SKILL.md`. The skill must follow the Agent Skills spec (https://agentskills.io/specification).

Requirements for the skill:
- **name:** `check-semantic-overlap`
- **description:** Pairwise semantic overlap detection across vocabulary registry entries. Use during validation of a RationaleCardSet to check that no two entries within the same dimension (intent_pattern, complexity_structure, ambiguity_tags) are semantically redundant.
- **Inputs:** `VocabularyRegistry` (the registry to check)
- **Procedure:** For each dimension, compare all pairs of entries by definition. Flag pairs where one definition substantially subsumes the other or both describe the same concept with different wording.
- **Output:** List of overlapping pairs with reasoning, or "no overlap detected"
- **References:** Link to `references/vocabulary-registry-rules.md`

- [ ] **Step 3: Copy vocabulary registry rules reference**

Copy or symlink `odysseus/skills/classify-example/references/vocabulary-registry-rules.md` to `odysseus/skills/check-semantic-overlap/references/vocabulary-registry-rules.md` (same rules apply to both skills).

- [ ] **Step 4: Validate skill structure**

Verify:
- Frontmatter has `name` and `description`
- `name` matches directory name (`check-semantic-overlap`)
- SKILL.md is under 500 lines
- References are one level deep

- [ ] **Step 5: Commit**

```bash
git add odysseus/skills/check-semantic-overlap/
git commit -m "feat: create check-semantic-overlap skill following Agent Skills spec"
```

---

## Chunk 4: Register MCP tools, prompt, and resources

### Task 6: Add MCP tools for routing analysis

**Files:**
- Modify: `odysseus/mcp.py`

- [ ] **Step 1: Add imports at top of `mcp.py`**

Add imports for `create_seed_registry`, `resolve_registry`, `prune_registry`, `validate_deterministic`, `stratified_split`, and the relevant models.

- [ ] **Step 2: Add `create_seed_registry` tool**

```python
@mcp.tool()
async def create_seed_registry_tool() -> str:
    """Initialize a vocabulary registry with the 4 canonical ambiguity tags.

    Returns:
        JSON-serialized VocabularyRegistry.
    """
    registry = create_seed_registry()
    return registry.model_dump_json(indent=2)
```

- [ ] **Step 3: Add `resolve_registry` tool**

```python
@mcp.tool()
async def resolve_registry_tool(dataset_hash: str, registry_dir: str = "outputs") -> str:
    """Look up an existing vocabulary registry by dataset hash.

    Args:
        dataset_hash: Content hash of the dataset.
        registry_dir: Directory to search for registries. Defaults to "outputs".

    Returns:
        JSON-serialized VocabularyRegistry if found, or error message.
    """
    from pathlib import Path
    result = resolve_registry(dataset_hash, Path(registry_dir))
    if result is None:
        return json.dumps({"found": False, "message": f"No registry found for hash {dataset_hash}"})
    return result.model_dump_json(indent=2)
```

- [ ] **Step 4: Add `validate_rationale_card_set` tool (deterministic)**

```python
@mcp.tool()
async def validate_rationale_card_set_tool(
    card_set_json: str,
    routing_context_json: str,
    dataset_size: int,
) -> str:
    """Run deterministic validation checks on a RationaleCardSet.

    Excludes LLM-judged semantic overlap (handled by check-semantic-overlap skill).

    Args:
        card_set_json: JSON-serialized RationaleCardSet.
        routing_context_json: JSON-serialized RoutingContext.
        dataset_size: Number of examples in the dataset.

    Returns:
        JSON array of RationaleCheckResult objects.
    """
    card_set = RationaleCardSet.model_validate_json(card_set_json)
    routing_context = RoutingContext.model_validate_json(routing_context_json)
    results = validate_deterministic(card_set, routing_context, dataset_size)
    return json.dumps([r.model_dump() for r in results], indent=2)
```

- [ ] **Step 5: Add `prune_registry` tool**

```python
@mcp.tool()
async def prune_registry_tool(registry_json: str, dataset_size: int) -> str:
    """Remove vocabulary entries below the cluster threshold.

    Threshold: max(3, ceil(0.05 * dataset_size)).

    Args:
        registry_json: JSON-serialized VocabularyRegistry.
        dataset_size: Number of examples in the dataset.

    Returns:
        JSON with pruned_registry and removed_entries map.
    """
    registry = VocabularyRegistry.model_validate_json(registry_json)
    pruned, removed = prune_registry(registry, dataset_size)
    return json.dumps({
        "pruned_registry": json.loads(pruned.model_dump_json()),
        "removed_entries": removed,
    }, indent=2)
```

- [ ] **Step 6: Add `stratified_split` tool**

```python
@mcp.tool()
async def stratified_split_tool(
    dataset_path: str,
    card_set_json: str,
    dev_ratio: float = 0.8,
) -> str:
    """Split dataset and card set into dev/holdout with matched pairs.

    Args:
        dataset_path: Path to JSONL dataset file.
        card_set_json: JSON-serialized RationaleCardSet.
        dev_ratio: Proportion for dev set. Default 0.8.

    Returns:
        JSON with dev_path, holdout_path, dev_card_set_path,
        holdout_card_set_path, and split_report.
    """
    path = Path(dataset_path)
    if not path.is_file():
        raise ToolError(f"Dataset file not found: {dataset_path}")

    # Parse dataset
    examples = _load_examples(path)
    card_set = RationaleCardSet.model_validate_json(card_set_json)

    dev_ex, holdout_ex, dev_cards, holdout_cards, report = stratified_split(
        examples, card_set, dev_ratio
    )

    # Write outputs to same directory as dataset
    out_dir = path.parent
    dev_path = out_dir / "dev.jsonl"
    holdout_path = out_dir / "holdout.jsonl"
    dev_cards_path = out_dir / "dev_rationale_card_set.json"
    holdout_cards_path = out_dir / "holdout_rationale_card_set.json"
    report_path = out_dir / "split_report.json"

    _write_jsonl(dev_path, dev_ex)
    _write_jsonl(holdout_path, holdout_ex)
    dev_cards_path.write_text(dev_cards.model_dump_json(indent=2))
    holdout_cards_path.write_text(holdout_cards.model_dump_json(indent=2))
    report_path.write_text(report.model_dump_json(indent=2))

    return json.dumps({
        "dev_jsonl_path": str(dev_path),
        "holdout_jsonl_path": str(holdout_path),
        "dev_rationale_card_set_path": str(dev_cards_path),
        "holdout_rationale_card_set_path": str(holdout_cards_path),
        "split_report_path": str(report_path),
    }, indent=2)
```

Note: `_load_examples` and `_write_jsonl` are helper functions to add before the tool definitions:

```python
def _load_examples(path: Path) -> list[Example]:
    """Load Example objects from a JSONL file."""
    from odysseus.eval.models import Example

    examples: list[Example] = []
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        examples.append(Example.model_validate_json(stripped))
    return examples


def _write_jsonl(path: Path, examples: list[Example]) -> None:
    """Write Example objects to a JSONL file."""
    with path.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(ex.model_dump_json() + "\n")
```

- [ ] **Step 7: Add routing analysis prompt and resources**

```python
@mcp.prompt()
async def odysseus_routing_analysis() -> list[Message]:
    """Activate the Odysseus routing analysis agent.

    Use after the data validation agent has produced a data quality report
    and routing context. Annotates, validates, and splits the dataset.
    """
    system_prompt = _load_text("odysseus/agents/prompts/routing_analysis_system.md")
    return [UserMessage(content=system_prompt)]


@mcp.resource("odysseus://agents/routing-analysis/classify-example-skill")
async def classify_example_skill() -> str:
    """Classify-example skill for the Routing Analysis Agent."""
    return _load_text("odysseus/skills/classify-example/SKILL.md")


@mcp.resource("odysseus://agents/routing-analysis/generate-rationale-skill")
async def generate_rationale_skill() -> str:
    """Generate-routing-rationale skill for the Routing Analysis Agent."""
    return _load_text("odysseus/skills/generate-routing-rationale/SKILL.md")


@mcp.resource("odysseus://agents/routing-analysis/check-overlap-skill")
async def check_overlap_skill() -> str:
    """Check-semantic-overlap skill for the Routing Analysis Agent."""
    return _load_text("odysseus/skills/check-semantic-overlap/SKILL.md")
```

- [ ] **Step 8: Run lint and type check on mcp.py**

Run: `uv run ruff check odysseus/mcp.py && uv run pyright odysseus/mcp.py`
Expected: Clean

- [ ] **Step 9: Commit**

```bash
git add odysseus/mcp.py
git commit -m "feat: register routing analysis MCP tools, prompt, and resources"
```

---

## Chunk 5: Write the system prompt

### Task 7: Write routing_analysis_system.md

**Files:**
- Create: `odysseus/agents/prompts/routing_analysis_system.md`

- [ ] **Step 1: Write the system prompt**

Follow the structure from the spec (Section "System Prompt Structure") and match the style of `user_input_system.md` and `data_validation_system.md`. The prompt must cover:

1. **Identity & Role** — "You are the Routing Analysis Agent. You receive a validated dataset with routing context and produce a fully annotated, validated, and split dataset ready for prompt construction."

2. **Inputs** — Table of context dict keys (from spec Section "Inputs"). Instruction to read and validate all inputs on startup.

3. **Tools** — Table of MCP tools with signatures and purpose. Note that `validate_rationale_card_set` runs deterministic checks only.

4. **Skills** — List the 3 skills by name. For each: when to activate, what it does, where the SKILL.md lives. Use the Agent Skills activation pattern — read the full SKILL.md when the phase requires it.

5. **Phases** — Phase 1 (Classification Pass), Phase 2 (Rationale Pass), Phase 3 (Validation & Fix Loop, max 5 retries with prune → validate → overlap check → auto-fix cycle), Phase 4 (Split & Output).

6. **Checkpointing** — Scratch directory at `scratch/<run_id>/` (run_id = dataset content hash). Checkpoint files after each phase. Incremental writes within phases. Recovery on restart. Cleanup on success.

7. **Validation & Error Handling** — Auto-fix strategy table by severity/failure type (from spec). 5-attempt retry cap. Fail to user with error report after cap.

8. **Output Contract** — Two tables: keys for Prompt Builder Agent, keys for Final Reporting Agent only. Explicit constraint: holdout artifacts never sent to Prompt Builder.

9. **Constraints** — Information leakage prevention. Deterministic split guarantees. Dataset provenance via `dataset_hash`.

- [ ] **Step 2: Verify prompt is under 500 lines**

Run: `wc -l odysseus/agents/prompts/routing_analysis_system.md`
Expected: < 500 lines

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/prompts/routing_analysis_system.md
git commit -m "feat: add routing analysis agent system prompt"
```

---

## Chunk 6: Update documentation

### Task 8: Update architecture.md

**Files:**
- Modify: `docs/architecture.md`

- [ ] **Step 1: Update Agent Registry table (line ~26)**

Update the Routing Analysis Agent row:
- Status: Done
- Reads from Context: `validated_input_report_path`, `data_quality_report`, `routing_context`, `dataset_path`
- Writes to Context: `dev_rationale_card_set_path`, `dev_jsonl_path`, `vocabulary_registry_path`, `split_report_path`, `routing_context` (passthrough), `holdout_rationale_card_set_path`, `holdout_jsonl_path`

- [ ] **Step 2: Update Data Validation Agent row (line ~25)**

Add output context keys: `data_quality_report`, `routing_context`, `dataset_path`

- [ ] **Step 3: Add new context keys to Context Dict Reference table (line ~32)**

Add all 8 new keys with types, source agents, and consumer agents.

- [ ] **Step 4: Update MCP Surface tables**

Add the new tools (`create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`) to the Tools table. Add the new prompt and resources to their respective tables.

- [ ] **Step 5: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: update architecture with routing analysis agent context keys and tools"
```

---

## Chunk 7: Integration test scenarios

### Task 9: Write integration test scenarios

**Files:**
- Create: `tests/scenarios/29_routing_analysis_startup.md`
- Create: `tests/scenarios/30_routing_analysis_full_pipeline.md`
- Modify: `tests/scenarios/README.md`

- [ ] **Step 1: Write scenario 29 — startup and input validation**

Scenario: Agent starts, reads all 4 context dict inputs, initializes registry, and confirms it's ready to proceed. Verify it fails gracefully if an input is missing.

Follow the 4-section format: Setup, Scenario Description, User Simulator, Verification Criteria.

- [ ] **Step 2: Write scenario 30 — full pipeline**

Scenario: Agent runs the complete pipeline on `rationale_test_dataset.jsonl` — classification pass, rationale pass, validation loop, and split. Verify outputs include dev/holdout card sets, registry, and split report.

- [ ] **Step 3: Update scenarios README**

Add scenarios 29-30 to the index table under a new "Routing Analysis Agent — Full Pipeline" category.

- [ ] **Step 4: Commit**

```bash
git add tests/scenarios/29_routing_analysis_startup.md tests/scenarios/30_routing_analysis_full_pipeline.md tests/scenarios/README.md
git commit -m "test: add routing analysis agent integration test scenarios"
```

---

## Chunk 8: Final verification

### Task 10: Run full test suite and lint

- [ ] **Step 1: Run all tests**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 2: Run linting**

Run: `uv run ruff check .`
Expected: Clean

- [ ] **Step 3: Run formatting**

Run: `uv run ruff format --check .`
Expected: Clean (or run `uv run ruff format .` to fix)

- [ ] **Step 4: Run type checking**

Run: `uv run pyright`
Expected: Clean

- [ ] **Step 5: Final commit if any formatting fixes**

```bash
git add -A
git commit -m "chore: fix lint and format issues"
```
