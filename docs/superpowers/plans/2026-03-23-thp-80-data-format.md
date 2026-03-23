# THP-80 Data Format Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the `Example` model and all consumers to match the THP-80 data format spec — `input` becomes `str`, `expected` gets a typed sub-model with `route` and `routes`, and `split` is added to the model.

**Architecture:** Update the Pydantic `Example` model with typed sub-models (`ModelCostQuality`, `Expected`), then propagate the type changes through dataset loader, metrics, backends, and all test files/fixtures. The reference document is placed at `odysseus/agents/data_validation_format.md`.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, JSONL

---

## Chunk 1: Model Migration and Core Updates

### Task 1: Add typed sub-models for `Expected`

**Files:**
- Modify: `odysseus/eval/models.py:172-177`
- Test: `tests/test_models.py` (add new tests)

- [ ] **Step 1: Write failing tests for the new typed models**

```python
# tests/test_models.py — add these tests

class TestModelCostQuality:
    def test_valid_cost_quality(self):
        from odysseus.eval.models import ModelCostQuality
        m = ModelCostQuality(cost=0.05, quality_score=0.98)
        assert m.cost == 0.05
        assert m.quality_score == 0.98

    def test_negative_cost_allowed(self):
        """No range constraints per spec — normalization is conversational."""
        from odysseus.eval.models import ModelCostQuality
        m = ModelCostQuality(cost=-1.0, quality_score=2.0)
        assert m.cost == -1.0
        assert m.quality_score == 2.0


class TestExpected:
    def test_valid_expected(self):
        from odysseus.eval.models import Expected
        e = Expected(
            route="opus",
            routes={
                "opus": {"cost": 0.05, "quality_score": 0.98},
                "sonnet": {"cost": 0.01, "quality_score": 0.88},
            },
        )
        assert e.route == "opus"
        assert e.routes["opus"].cost == 0.05

    def test_route_must_be_in_routes(self):
        from odysseus.eval.models import Expected
        import pytest
        with pytest.raises(ValueError, match="route .* must be a key in routes"):
            Expected(
                route="gpt-4o",
                routes={"opus": {"cost": 0.05, "quality_score": 0.98}},
            )

    def test_routes_must_be_non_empty(self):
        from odysseus.eval.models import Expected
        import pytest
        with pytest.raises(ValueError, match="routes must contain at least one entry"):
            Expected(route="opus", routes={})


class TestExampleNewSchema:
    def test_valid_example_string_input(self):
        from odysseus.eval.models import Example
        ex = Example(
            id="ex-1",
            input="Explain quantum entanglement",
            expected={
                "route": "opus",
                "routes": {
                    "opus": {"cost": 0.05, "quality_score": 0.98},
                    "sonnet": {"cost": 0.01, "quality_score": 0.88},
                },
            },
            split="dev",
        )
        assert ex.input == "Explain quantum entanglement"
        assert ex.expected.route == "opus"
        assert ex.split == "dev"

    def test_split_must_be_dev_or_holdout(self):
        from odysseus.eval.models import Example
        import pytest
        with pytest.raises(ValueError):
            Example(
                id="ex-1",
                input="test",
                expected={
                    "route": "opus",
                    "routes": {"opus": {"cost": 0.05, "quality_score": 0.98}},
                },
                split="train",
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py::TestModelCostQuality tests/test_models.py::TestExpected tests/test_models.py::TestExampleNewSchema -v`
Expected: FAIL — `ModelCostQuality` and `Expected` do not exist yet, `Example` has wrong fields.

- [ ] **Step 3: Implement the new models**

In `odysseus/eval/models.py`, replace the `Example` class (lines 172-177) with:

```python
class ModelCostQuality(BaseModel):
    """Per-model cost and quality data for a routing option."""

    cost: float
    quality_score: float


class Expected(BaseModel):
    """Expected routing outcome for an evaluation example."""

    route: str
    routes: dict[str, ModelCostQuality]

    @model_validator(mode="after")
    def route_must_be_in_routes(self) -> Expected:
        if not self.routes:
            raise ValueError("routes must contain at least one entry")
        if self.route not in self.routes:
            raise ValueError(f"route {self.route!r} must be a key in routes, got keys: {list(self.routes.keys())}")
        return self


class Example(BaseModel):
    """A single evaluation example."""

    id: str
    input: str
    expected: Expected
    split: Literal["dev", "holdout"]
    metadata: dict[str, Any] | None = None
```

- [ ] **Step 4: Run tests to verify the new model tests pass**

Run: `uv run pytest tests/test_models.py::TestModelCostQuality tests/test_models.py::TestExpected tests/test_models.py::TestExampleNewSchema -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/models.py tests/test_models.py
git commit -m "feat(thp-80): add typed Expected/ModelCostQuality models, migrate Example"
```

### Task 2: Update `__init__.py` exports

**Files:**
- Modify: `odysseus/eval/__init__.py`

- [ ] **Step 1: Add new models to exports**

Add `Expected` and `ModelCostQuality` to the `__all__` list and import in `odysseus/eval/__init__.py`.

- [ ] **Step 2: Run import check**

Run: `uv run python -c "from odysseus.eval import Example, Expected, ModelCostQuality; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add odysseus/eval/__init__.py
git commit -m "feat(thp-80): export Expected and ModelCostQuality from eval package"
```

### Task 3: Update dataset loader

**Files:**
- Modify: `odysseus/eval/dataset.py:56-63`
- Modify: `tests/test_dataset.py`

- [ ] **Step 1: Update test fixtures to use new schema**

Update `SAMPLE_RECORDS` in `tests/test_dataset.py` to use string `input`, typed `expected`, and keep `split`:

```python
SAMPLE_RECORDS = [
    {
        "id": "1",
        "input": "hello",
        "expected": {
            "route": "greeting",
            "routes": {"greeting": {"cost": 0.01, "quality_score": 0.9}, "farewell": {"cost": 0.01, "quality_score": 0.5}},
        },
        "split": "dev",
    },
    {
        "id": "2",
        "input": "bye",
        "expected": {
            "route": "farewell",
            "routes": {"greeting": {"cost": 0.01, "quality_score": 0.4}, "farewell": {"cost": 0.01, "quality_score": 0.95}},
        },
        "split": "dev",
    },
    {
        "id": "3",
        "input": "secret",
        "expected": {
            "route": "hidden",
            "routes": {"hidden": {"cost": 0.02, "quality_score": 0.8}},
        },
        "split": "holdout",
    },
]
```

- [ ] **Step 2: Update test assertions**

Update `test_load_dev_parses_fields_correctly`:

```python
def test_load_dev_parses_fields_correctly(self, tmp_path: Path):
    from odysseus.eval.dataset import JsonlDatasetManager

    path = tmp_path / "data.jsonl"
    _write_jsonl(path, SAMPLE_RECORDS)

    manager = JsonlDatasetManager()
    examples = manager.load(str(path), "dev")

    assert examples[0].input == "hello"
    assert examples[0].expected.route == "greeting"
    assert examples[0].split == "dev"
```

Update inline JSONL strings in error tests to use the new schema (e.g., `test_malformed_json_line`, `test_blank_lines_are_skipped`, `test_missing_required_field`).

- [ ] **Step 3: Run dataset tests to see them fail**

Run: `uv run pytest tests/test_dataset.py -v`
Expected: FAIL — the dataset loader still constructs `Example` with the old field mapping.

- [ ] **Step 4: Update dataset loader to pass `split` to Example**

In `odysseus/eval/dataset.py`, update the Example construction (lines 57-61):

```python
example = Example(
    id=record["id"],
    input=record["input"],
    expected=record["expected"],
    split=record_split,
)
```

Note: `record_split` is already extracted at line 52. The `split` field is now passed through to the model instead of being discarded after filtering.

- [ ] **Step 5: Run dataset tests to verify they pass**

Run: `uv run pytest tests/test_dataset.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add odysseus/eval/dataset.py tests/test_dataset.py
git commit -m "feat(thp-80): update dataset loader and tests for new Example schema"
```

### Task 4: Update metrics to use typed access

**Files:**
- Modify: `odysseus/eval/metrics.py:71-197`
- Modify: `tests/test_metrics.py`

- [ ] **Step 1: Update test helper `_example()` in `tests/test_metrics.py`**

```python
def _example(id: str, route: str = "gpt-4o") -> Example:
    """Create a minimal Example with expected route."""
    return Example(
        id=id,
        input=f"q-{id}",
        expected={
            "route": route,
            "routes": {
                "gpt-4o": {"cost": 0.03, "quality_score": 0.95},
                "claude-sonnet": {"cost": 0.01, "quality_score": 0.88},
                "haiku": {"cost": 0.002, "quality_score": 0.72},
            },
        },
        split="dev",
    )
```

Also update `_cost_quality_example` (line 258) — it uses `input={"query": f"q-{id}"}` (dict) and lacks `split`. Change to `input=f"q-{id}"` and add `split="dev"`.

- [ ] **Step 2: Run metrics tests to see them fail**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: FAIL — metrics code accesses `ex.expected["route"]` but now `expected` is an `Expected` object, not a dict.

- [ ] **Step 3: Update metric functions for typed access**

In `odysseus/eval/metrics.py`:

`compute_accuracy` (line 78): change `ex.expected["route"]` → `ex.expected.route`

`compute_confusion` (line 91): change `ex.expected["route"]` → `ex.expected.route`

`compute_f1` (line 219): change `ex.expected["route"]` → `ex.expected.route`

`compute_cost_quality_reduction` (lines 146-165):
- `ex.expected["routes"]` → `ex.expected.routes`
- `ex.expected["route"]` → `ex.expected.route`
- `routes[baseline_class]["cost"]` → `routes[baseline_class].cost`
- `routes[baseline_class]["quality_score"]` → `routes[baseline_class].quality_score`
- `routes[pred_route]["cost"]` → `routes[pred_route].cost`
- `routes[pred_route]["quality_score"]` → `routes[pred_route].quality_score`
- `routes[oracle_route]["cost"]` → `routes[oracle_route].cost`
- `routes[oracle_route]["quality_score"]` → `routes[oracle_route].quality_score`

`_select_baseline_class` (lines 188-196):
- `ex.expected["routes"]` → `ex.expected.routes`
- `data["quality_score"]` → `data.quality_score`

- [ ] **Step 4: Run metrics tests to verify they pass**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/metrics.py tests/test_metrics.py
git commit -m "feat(thp-80): update metrics for typed Expected access"
```

### Task 5: Update mock echo backend

**Files:**
- Modify: `odysseus/eval/backends/mock_echo.py:31`
- Modify: `tests/test_mock_echo_backend.py`

- [ ] **Step 1: Update test Example instantiation in `tests/test_mock_echo_backend.py`**

Change the test's Example from:
```python
Example(id="ex-1", input={"question": "route me"}, expected={"route": "billing"})
```
to:
```python
Example(
    id="ex-1",
    input="route me",
    expected={
        "route": "billing",
        "routes": {"billing": {"cost": 0.01, "quality_score": 0.9}},
    },
    split="dev",
)
```

- [ ] **Step 2: Run mock echo tests to see them fail**

Run: `uv run pytest tests/test_mock_echo_backend.py -v`
Expected: FAIL — `expected.get("route")` no longer works on typed model.

- [ ] **Step 3: Update mock echo backend**

In `odysseus/eval/backends/mock_echo.py` line 31, change:
```python
route = example.expected.get("route", "unknown")
```
to:
```python
route = example.expected.route
```

- [ ] **Step 4: Run mock echo tests to verify they pass**

Run: `uv run pytest tests/test_mock_echo_backend.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/backends/mock_echo.py tests/test_mock_echo_backend.py
git commit -m "feat(thp-80): update mock echo backend for typed Expected"
```

## Chunk 2: Remaining Test Updates and Fixtures

### Task 6: Update controller tests

**Files:**
- Modify: `tests/test_controller.py`

- [ ] **Step 1: Update all Example instantiations in test_controller.py**

Find all `Example(...)` calls and update them. Key pattern — change:
```python
Example(id=f"ex-{i}", input={"question": f"q{i}"}, expected={"route": f"class-{i % 3}"})
```
to:
```python
Example(
    id=f"ex-{i}",
    input=f"q{i}",
    expected={
        "route": f"class-{i % 3}",
        "routes": {f"class-{j}": {"cost": 0.01, "quality_score": 0.8} for j in range(3)},
    },
    split="dev",
)
```

Also update mock backend methods that access `example.expected.get("route", "default")` → `example.expected.route`.

Also update `_write_jsonl` helper (line 129-134) — after migration, `ex.expected` is a Pydantic `Expected` model, not a dict. Change it to use `ex.model_dump()` for JSON serialization:

```python
def _write_jsonl(path: Path, examples: list[Example], split: str = "dev") -> None:
    """Write examples to a JSONL file."""
    with open(path, "w") as f:
        for ex in examples:
            record = ex.model_dump()
            f.write(json.dumps(record) + "\n")
```

Note: `split` is now part of the `Example` model, so the `split` parameter is no longer needed. Update callers accordingly.

- [ ] **Step 2: Run controller tests**

Run: `uv run pytest tests/test_controller.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_controller.py
git commit -m "feat(thp-80): update controller tests for new Example schema"
```

### Task 7: Update backend tests

**Files:**
- Modify: `tests/test_backends.py`

- [ ] **Step 1: Update EXAMPLE constant and any Example instantiations**

Change:
```python
EXAMPLE = Example(id="ex1", input={"text": "hello"}, expected={"label": "greeting"})
```
to:
```python
EXAMPLE = Example(
    id="ex1",
    input="hello",
    expected={
        "route": "greeting",
        "routes": {"greeting": {"cost": 0.01, "quality_score": 0.9}},
    },
    split="dev",
)
```

Also update any mock backend method signatures accessing Example fields.

- [ ] **Step 2: Run backend tests**

Run: `uv run pytest tests/test_backends.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_backends.py
git commit -m "feat(thp-80): update backend tests for new Example schema"
```

### Task 8: Update protocol tests

**Files:**
- Modify: `tests/test_protocols.py`

- [ ] **Step 1: Update any Example instantiations in protocol tests**

Ensure any mock DatasetManager returns Examples with the new schema (string input, typed expected, split).

- [ ] **Step 2: Run protocol tests**

Run: `uv run pytest tests/test_protocols.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_protocols.py
git commit -m "feat(thp-80): update protocol tests for new Example schema"
```

### Task 9: Update JSONL test fixtures

**Files:**
- Modify: `tests/fixtures/integration/dataset.jsonl`
- Modify: `tests/scenarios/data/valid_dataset.jsonl`
- Modify: `tests/scenarios/data/no_expected_field.jsonl`

- [ ] **Step 1: Update integration dataset fixture**

Replace `tests/fixtures/integration/dataset.jsonl` with new-schema records:

```jsonl
{"id": "ex-1", "input": "I need help with my bill", "expected": {"route": "billing", "routes": {"billing": {"cost": 0.01, "quality_score": 0.92}, "balance": {"cost": 0.01, "quality_score": 0.5}}}, "split": "dev"}
{"id": "ex-2", "input": "What is my account balance?", "expected": {"route": "balance", "routes": {"billing": {"cost": 0.01, "quality_score": 0.4}, "balance": {"cost": 0.01, "quality_score": 0.95}}}, "split": "dev"}
{"id": "ex-3", "input": "Cancel my subscription", "expected": {"route": "billing", "routes": {"billing": {"cost": 0.01, "quality_score": 0.88}, "balance": {"cost": 0.01, "quality_score": 0.3}}}, "split": "holdout"}
```

- [ ] **Step 2: Update valid_dataset.jsonl**

Replace `tests/scenarios/data/valid_dataset.jsonl` with new-schema records:

Keep all 5 records (integration scenarios reference "5 labeled routing examples"). Update each to use string `input` and include `routes` + `split`:

```jsonl
{"id": "1", "input": "What is 2+2?", "expected": {"route": "haiku", "routes": {"haiku": {"cost": 0.002, "quality_score": 0.95}, "sonnet": {"cost": 0.01, "quality_score": 0.95}, "opus": {"cost": 0.05, "quality_score": 0.95}}}, "split": "dev"}
{"id": "2", "input": "Explain quantum entanglement in detail with examples", "expected": {"route": "opus", "routes": {"haiku": {"cost": 0.002, "quality_score": 0.55}, "sonnet": {"cost": 0.01, "quality_score": 0.78}, "opus": {"cost": 0.05, "quality_score": 0.98}}}, "split": "dev"}
{"id": "3", "input": "Translate 'hello' to French", "expected": {"route": "haiku", "routes": {"haiku": {"cost": 0.002, "quality_score": 0.92}, "sonnet": {"cost": 0.01, "quality_score": 0.90}, "opus": {"cost": 0.05, "quality_score": 0.88}}}, "split": "dev"}
{"id": "4", "input": "Write a nuanced essay on the ethics of AI regulation", "expected": {"route": "opus", "routes": {"haiku": {"cost": 0.002, "quality_score": 0.45}, "sonnet": {"cost": 0.01, "quality_score": 0.72}, "opus": {"cost": 0.05, "quality_score": 0.96}}}, "split": "dev"}
{"id": "5", "input": "Summarize this paragraph in one sentence", "expected": {"route": "sonnet", "routes": {"haiku": {"cost": 0.002, "quality_score": 0.65}, "sonnet": {"cost": 0.01, "quality_score": 0.92}, "opus": {"cost": 0.05, "quality_score": 0.94}}}, "split": "dev"}
```

- [ ] **Step 3: Update no_expected_field.jsonl**

Update `tests/scenarios/data/no_expected_field.jsonl` to use string `input` (it intentionally lacks `expected` — this is a negative test case):

```jsonl
{"id": "1", "input": "What is 2+2?"}
{"id": "2", "input": "Explain quantum entanglement in detail with examples"}
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/integration/dataset.jsonl tests/scenarios/data/valid_dataset.jsonl tests/scenarios/data/no_expected_field.jsonl
git commit -m "feat(thp-80): update JSONL test fixtures to new schema"
```

## Chunk 3: Reference Document

### Task 10: Write the data validation format reference document

**Files:**
- Create: `odysseus/agents/data_validation_format.md`

- [ ] **Step 1: Write the reference document**

Create `odysseus/agents/data_validation_format.md` with the canonical schema definition from the spec. This file is consumed by THP-106 (system prompt) and THP-145 (validation logic). It should contain:

1. The target schema (required/optional fields with types)
2. Schema constraints (all 9 from the spec)
3. The informative alias table
4. Valid and invalid examples

This is a copy of the relevant sections from the design spec, formatted as a standalone reference for the agent.

- [ ] **Step 2: Commit**

```bash
git add odysseus/agents/data_validation_format.md
git commit -m "docs(thp-80): add data validation format reference document"
```

### Task 11: Run full test suite and type check

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 2: Run type checker**

Run: `uv run pyright`
Expected: No new errors related to Example/Expected/ModelCostQuality.

- [ ] **Step 3: Run linter**

Run: `uv run ruff check .`
Expected: Clean

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix(thp-80): address lint/type issues from schema migration"
```
