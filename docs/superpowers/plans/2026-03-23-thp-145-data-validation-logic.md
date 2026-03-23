# THP-145 Data Validation Logic Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add remaining validation checks (null detection, query length distribution), an orchestration function, and MCP wiring for the Data Validation agent.

**Architecture:** Extend existing `data_validation_checks.py` with two additions (null detection in schema conformance, new query length check) and a `run_all_checks` orchestrator. Wire into MCP as a prompt + tool + resources, following the existing input agent pattern.

**Tech Stack:** Python 3.11+, Pydantic, FastMCP, pytest

**Spec:** `docs/superpowers/specs/2026-03-23-thp-145-data-validation-logic-design.md`

---

## File Structure

| Action | File | Responsibility |
|---|---|---|
| Modify | `odysseus/agents/data_validation_checks.py` | Add `QueryLengthDistribution` model, `check_query_length_distribution()`, null detection in `check_schema_conformance()`, update `DataQualityReport`, add `run_all_checks()` |
| Modify | `odysseus/agents/__init__.py` | Export new symbols |
| Modify | `odysseus/mcp.py` | Add `odysseus_data_validation` prompt, `validate_dataset` tool, two resources |
| Create | `prompts/data_validation_system.md` | System prompt for the data validation agent |
| Modify | `tests/test_data_validation_checks.py` | Tests for null detection, query length, `run_all_checks` |
| Create | `tests/test_mcp_data_validation.py` | Integration tests for `validate_dataset` MCP tool |

---

## Chunk 1: Null detection in schema conformance

### Task 1: Add null field detection to `check_schema_conformance`

**Files:**
- Modify: `odysseus/agents/data_validation_checks.py:97-254`
- Test: `tests/test_data_validation_checks.py`

- [ ] **Step 1: Write failing tests for null detection**

Add to `TestCheckSchemaConformance` in `tests/test_data_validation_checks.py`:

```python
def test_null_optional_field_detected(self) -> None:
    """Null in a non-required field (metadata) is detected."""
    row = _valid_row(metadata=None)
    findings = check_schema_conformance([row])
    null_finding = next(f for f in findings if f.field == "null_fields")
    assert null_finding.status == "fail"
    assert 0 in null_finding.row_indices

def test_null_in_expected_subfield_detected(self) -> None:
    """Null in expected.routes.*.cost is detected."""
    row = _valid_row()
    row["expected"]["routes"]["opus"]["cost"] = None
    findings = check_schema_conformance([row])
    null_finding = next(f for f in findings if f.field == "null_fields")
    assert null_finding.status == "fail"
    assert 0 in null_finding.row_indices

def test_no_nulls_in_valid_rows(self) -> None:
    """Valid rows produce a passing null_fields finding."""
    rows = [_valid_row(id="ex-1"), _valid_row(id="ex-2")]
    findings = check_schema_conformance(rows)
    null_finding = next(f for f in findings if f.field == "null_fields")
    assert null_finding.status == "pass"
    assert null_finding.row_indices == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data_validation_checks.py::TestCheckSchemaConformance::test_null_optional_field_detected tests/test_data_validation_checks.py::TestCheckSchemaConformance::test_null_in_expected_subfield_detected tests/test_data_validation_checks.py::TestCheckSchemaConformance::test_no_nulls_in_valid_rows -v`

Expected: FAIL — no `null_fields` finding exists yet.

- [ ] **Step 3: Implement null detection in `check_schema_conformance`**

In `odysseus/agents/data_validation_checks.py`, add a new check inside the `for idx, row in enumerate(rows):` loop and a corresponding finding. Add a `null_field_indices` accumulator alongside the existing ones (line ~103):

```python
null_field_indices: list[int] = []
```

Inside the loop, after the existing checks (before `# --- Check 6: unique IDs ---`), add:

```python
# --- Check: null field detection (optional fields + expected.*) ---
has_null = False
# Optional top-level fields only — required fields (id, input)
# are already covered by the required_keys check above.
for key in ("metadata",):
    if key in row and row[key] is None:
        has_null = True
        break

# expected.* fields
if not has_null and isinstance(row.get("expected"), dict):
    exp = row["expected"]
    for key in ("route", "routes"):
        if key in exp and exp[key] is None:
            has_null = True
            break
    # expected.routes.*.* fields
    if not has_null and isinstance(exp.get("routes"), dict):
        for _model_name, model_data in exp["routes"].items():
            if isinstance(model_data, dict):
                for val in model_data.values():
                    if val is None:
                        has_null = True
                        break
            if has_null:
                break

if has_null:
    null_field_indices.append(idx)
```

After the existing findings list (before `return findings`), append:

```python
findings.append(
    SchemaFinding(
        field="null_fields",
        status="fail" if null_field_indices else "pass",
        violation="Null values detected in non-required fields" if null_field_indices else None,
        row_indices=null_field_indices,
    )
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_validation_checks.py::TestCheckSchemaConformance -v`

Expected: ALL PASS (including existing tests — no regressions).

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/data_validation_checks.py tests/test_data_validation_checks.py
git commit -m "feat(thp-145): add null field detection to check_schema_conformance"
```

---

## Chunk 2: Query length distribution

### Task 2: Add `QueryLengthDistribution` model and `check_query_length_distribution` function

**Files:**
- Modify: `odysseus/agents/data_validation_checks.py`
- Test: `tests/test_data_validation_checks.py`

- [ ] **Step 1: Write failing tests for query length distribution**

Add new imports and test class to `tests/test_data_validation_checks.py`:

Update the import block to include `QueryLengthDistribution` and `check_query_length_distribution`.

```python
class TestQueryLengthDistribution:
    def test_model_construction(self) -> None:
        qld = QueryLengthDistribution(min=5, max=100, mean=42.5, p95=90.0, count=10)
        assert qld.min == 5
        assert qld.max == 100
        assert qld.mean == 42.5
        assert qld.p95 == 90.0
        assert qld.count == 10


class TestCheckQueryLengthDistribution:
    def test_known_distribution(self) -> None:
        """Verify stats against hand-calculated values."""
        rows = [
            _valid_row(id="ex-1", input="a" * 10),
            _valid_row(id="ex-2", input="b" * 20),
            _valid_row(id="ex-3", input="c" * 30),
            _valid_row(id="ex-4", input="d" * 40),
            _valid_row(id="ex-5", input="e" * 50),
        ]
        result = check_query_length_distribution(rows)
        assert result.count == 5
        assert result.min == 10
        assert result.max == 50
        assert result.mean == pytest.approx(30.0)
        # p95 of [10, 20, 30, 40, 50]: 95th percentile
        # Using nearest-rank: rank = ceil(0.95 * 5) = 5 -> value = 50
        # But with linear interpolation (numpy default): 46.0
        # We'll verify the implementation matches
        assert result.p95 == pytest.approx(46.0)

    def test_skips_missing_input(self) -> None:
        rows = [
            _valid_row(id="ex-1", input="hello"),
            {"id": "ex-2", "expected": {}},  # no input field
        ]
        result = check_query_length_distribution(rows)
        assert result.count == 1
        assert result.min == 5
        assert result.max == 5

    def test_skips_non_string_input(self) -> None:
        rows = [
            _valid_row(id="ex-1", input="hello"),
            _valid_row(id="ex-2", input=42),
        ]
        result = check_query_length_distribution(rows)
        assert result.count == 1

    def test_empty_rows(self) -> None:
        result = check_query_length_distribution([])
        assert result.count == 0
        assert result.min == 0
        assert result.max == 0
        assert result.mean == 0.0
        assert result.p95 == 0.0

    def test_single_row(self) -> None:
        rows = [_valid_row(id="ex-1", input="hello world")]
        result = check_query_length_distribution(rows)
        assert result.count == 1
        assert result.min == 11
        assert result.max == 11
        assert result.mean == pytest.approx(11.0)
        assert result.p95 == pytest.approx(11.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data_validation_checks.py::TestQueryLengthDistribution tests/test_data_validation_checks.py::TestCheckQueryLengthDistribution -v`

Expected: FAIL — `QueryLengthDistribution` and `check_query_length_distribution` don't exist yet.

- [ ] **Step 3: Implement `QueryLengthDistribution` model**

Add to `odysseus/agents/data_validation_checks.py` after the `VolumeAssessment` model (before `DataQualityReport`):

```python
class QueryLengthDistribution(BaseModel):
    """Character length distribution of query inputs."""

    min: int
    max: int
    mean: float
    p95: float
    count: int
```

- [ ] **Step 4: Update `DataQualityReport` model**

Add `query_length` field:

```python
class DataQualityReport(BaseModel):
    """Top-level report wrapping all validation check sections."""

    summary: str
    schema_findings: list[SchemaFinding]
    label_distribution: LabelDistribution
    volume_assessment: VolumeAssessment
    query_length: QueryLengthDistribution | None = None
```

- [ ] **Step 5: Implement `check_query_length_distribution`**

Add to `odysseus/agents/data_validation_checks.py` after `check_volume_adequacy`:

```python
def check_query_length_distribution(
    rows: list[dict],
) -> QueryLengthDistribution:
    """Compute character length distribution of the input field.

    Skips rows where ``input`` is missing or not a string.
    """
    lengths = [
        len(row["input"])
        for row in rows
        if isinstance(row.get("input"), str)
    ]

    if not lengths:
        return QueryLengthDistribution(
            min=0, max=0, mean=0.0, p95=0.0, count=0,
        )

    lengths_sorted = sorted(lengths)
    count = len(lengths_sorted)
    total = sum(lengths_sorted)

    # p95 via linear interpolation (matches numpy default)
    rank = 0.95 * (count - 1)
    lower = int(rank)
    upper = min(lower + 1, count - 1)
    fraction = rank - lower
    p95 = lengths_sorted[lower] + fraction * (lengths_sorted[upper] - lengths_sorted[lower])

    return QueryLengthDistribution(
        min=lengths_sorted[0],
        max=lengths_sorted[-1],
        mean=total / count,
        p95=p95,
        count=count,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_validation_checks.py::TestQueryLengthDistribution tests/test_data_validation_checks.py::TestCheckQueryLengthDistribution tests/test_data_validation_checks.py::TestDataQualityReport -v`

Expected: ALL PASS.

- [ ] **Step 7: Commit**

```bash
git add odysseus/agents/data_validation_checks.py tests/test_data_validation_checks.py
git commit -m "feat(thp-145): add QueryLengthDistribution model and check function"
```

---

## Chunk 3: Orchestration function

### Task 3: Add `run_all_checks` function

**Files:**
- Modify: `odysseus/agents/data_validation_checks.py`
- Test: `tests/test_data_validation_checks.py`

- [ ] **Step 1: Write failing tests for `run_all_checks`**

Add to `tests/test_data_validation_checks.py`:

Update imports to include `run_all_checks`.

```python
class TestRunAllChecks:
    def test_returns_complete_report(self) -> None:
        """All four check sections are populated."""
        rows = [
            _valid_row(id="ex-1"),
            _valid_row(id="ex-2", expected={"route": "haiku", "routes": {"opus": {}, "haiku": {}}}),
        ]
        report = run_all_checks(rows)
        assert isinstance(report, DataQualityReport)
        assert report.summary == ""
        assert len(report.schema_findings) > 0
        assert report.label_distribution.total_records > 0
        assert report.volume_assessment.min_per_tier == 5
        assert report.query_length is not None
        assert report.query_length.count == 2

    def test_empty_rows(self) -> None:
        report = run_all_checks([])
        assert isinstance(report, DataQualityReport)
        assert report.label_distribution.total_records == 0
        assert report.volume_assessment.overall_verdict == "fail"
        assert report.query_length is not None
        assert report.query_length.count == 0

    def test_default_thresholds(self) -> None:
        """Verify the intentional default thresholds are applied."""
        rows = [_valid_row(id=f"ex-{i}") for i in range(10)]
        report = run_all_checks(rows)
        # Intentional defaults
        assert report.label_distribution.min_tier_percentage == 0.10
        assert report.volume_assessment.min_per_tier == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data_validation_checks.py::TestRunAllChecks -v`

Expected: FAIL — `run_all_checks` not defined.

- [ ] **Step 3: Implement `run_all_checks`**

Add to the end of `odysseus/agents/data_validation_checks.py`:

```python
# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

# Intentional defaults — not magic numbers. These are reasonable starting
# thresholds; downstream agents may override via pipeline config.
_DEFAULT_MIN_TIER_PERCENTAGE = 0.10
_DEFAULT_MIN_PER_TIER = 5


def run_all_checks(rows: list[dict]) -> DataQualityReport:
    """Run all validation checks and assemble a DataQualityReport.

    The ``summary`` field is set to an empty string — the calling LLM
    writes the narrative summary using the structured results.
    """
    return DataQualityReport(
        summary="",
        schema_findings=check_schema_conformance(rows),
        label_distribution=check_label_distribution(rows, _DEFAULT_MIN_TIER_PERCENTAGE),
        volume_assessment=check_volume_adequacy(rows, _DEFAULT_MIN_PER_TIER),
        query_length=check_query_length_distribution(rows),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_validation_checks.py::TestRunAllChecks -v`

Expected: ALL PASS.

- [ ] **Step 5: Run full test suite for regressions**

Run: `uv run pytest tests/test_data_validation_checks.py -v`

Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add odysseus/agents/data_validation_checks.py tests/test_data_validation_checks.py
git commit -m "feat(thp-145): add run_all_checks orchestration function"
```

---

## Chunk 4: MCP wiring

### Task 4: Add exports to `__init__.py`

**Files:**
- Modify: `odysseus/agents/__init__.py`

- [ ] **Step 1: Update exports**

Add `QueryLengthDistribution`, `check_query_length_distribution`, and `run_all_checks` to the imports and `__all__` in `odysseus/agents/__init__.py`.

- [ ] **Step 2: Verify imports work**

Run: `uv run python -c "from odysseus.agents import QueryLengthDistribution, check_query_length_distribution, run_all_checks; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/__init__.py
git commit -m "feat(thp-145): export new validation symbols from agents package"
```

### Task 5: Create system prompt

**Files:**
- Create: `prompts/data_validation_system.md`

- [ ] **Step 1: Write the system prompt**

Create `prompts/data_validation_system.md`:

```markdown
You are the Data Validation agent in the Odysseus routing-prompt optimization pipeline.

## Your job

You validate the user's routing dataset and produce a data quality report. You run after the User Input agent has collected and confirmed the problem specification.

Your workflow:
1. Call the `validate_dataset` tool with the dataset path from the validated input report.
2. Interpret the structured results returned by the tool.
3. Write a data quality report following the output format below.

## Output format

Your report has four sections:

### 1. Dataset Summary

Write two paragraphs:

1. **Data description** — what the dataset contains: the routing problem domain, what kinds of queries are represented, and what the routing tiers correspond to. Base this on the user's problem description and the data you observed.
2. **Validation summary** — total record count, tier names and distribution, any issues found, and overall verdict (ready for downstream processing or blocked by critical issues).

### 2. Schema Consistency Findings

Present the `schema_findings` from the tool output. For each finding with status `"fail"`, explain the violation and list the affected row indices. Group passing checks into a single summary line.

### 3. Label Distribution Stats

Present the `label_distribution` from the tool output. Show per-tier counts and percentages. Flag any imbalanced tiers.

### 4. Volume Adequacy Assessment

Present the `volume_assessment` from the tool output. Show per-tier verdicts. State the overall verdict.

### 5. Query Length Distribution

Present the `query_length` stats from the tool output: min, max, mean, and p95 character lengths.

## Decision rules

- If any schema finding has status `"fail"` with violation on required keys or types: the dataset is **blocked** — report the issues and ask the user to fix them.
- If volume adequacy overall verdict is `"fail"`: flag this as a **warning** — the dataset can proceed but results may be unreliable for under-covered tiers.
- If label distribution has imbalanced tiers: flag as **informational** — note which tiers are underrepresented.
- If all checks pass: the dataset is **ready** for downstream processing.

## Available tools

- `validate_dataset` — runs all validation checks against a JSONL dataset file. Returns a structured JSON report.

## Available resources

- `odysseus://agents/data-validation/format-spec` — the data format specification (THP-80).
- `odysseus://agents/data-validation/output-spec` — the output format specification (THP-81).
```

- [ ] **Step 2: Commit**

```bash
git add prompts/data_validation_system.md
git commit -m "feat(thp-145): add data validation agent system prompt"
```

### Task 6: Add MCP prompt, tool, and resources

**Files:**
- Modify: `odysseus/mcp.py`

- [ ] **Step 1: Add the prompt**

Add to `odysseus/mcp.py` after the `odysseus_routing_input` prompt:

```python
@mcp.prompt()
async def odysseus_data_validation() -> list[Message]:
    """Activate the Odysseus data validation agent.

    Use after the input agent has produced a validated input report.
    Validates the routing dataset and produces a data quality report.
    """
    system_prompt = _load_text("prompts/data_validation_system.md")
    return [UserMessage(content=system_prompt)]
```

- [ ] **Step 2: Add the resources**

Add after the existing input agent resources:

```python
@mcp.resource("odysseus://agents/data-validation/format-spec")
async def data_validation_format_spec() -> str:
    """Data format specification (THP-80) for the data validation agent."""
    return _load_text("odysseus/agents/data_validation_format.md")


@mcp.resource("odysseus://agents/data-validation/output-spec")
async def data_validation_output_spec() -> str:
    """Output format specification (THP-81) for the data validation agent."""
    return _load_text("odysseus/agents/data_validation_output.md")
```

- [ ] **Step 3: Add the tool**

Add the `validate_dataset` tool. Add `import json` (already imported) at top. Add the import for `run_all_checks`:

```python
from odysseus.agents.data_validation_checks import run_all_checks
```

Then the tool:

```python
@mcp.tool()
async def validate_dataset(dataset_path: str) -> str:
    """Run all validation checks against a JSONL routing dataset.

    Args:
        dataset_path: Absolute path to the JSONL dataset file.

    Returns:
        JSON-serialized DataQualityReport with schema findings,
        label distribution, volume adequacy, and query length stats.
    """
    path = Path(dataset_path)
    if not path.is_file():
        raise ToolError(f"Dataset file not found: {dataset_path}")

    rows: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
        for line_num, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
    except json.JSONDecodeError as exc:
        raise ToolError(f"Malformed JSONL at line {line_num}: {exc}") from exc

    report = run_all_checks(rows)
    return report.model_dump_json(indent=2)
```

- [ ] **Step 4: Verify MCP server starts**

Run: `uv run python -c "from odysseus.mcp import mcp; print('MCP OK')"`

Expected: `MCP OK`

- [ ] **Step 5: Commit**

```bash
git add odysseus/mcp.py
git commit -m "feat(thp-145): add MCP prompt, tool, and resources for data validation"
```

---

## Chunk 5: Integration tests

### Task 7: Add integration tests for `validate_dataset`

**Files:**
- Create: `tests/test_mcp_data_validation.py`

- [ ] **Step 1: Write integration tests**

Create `tests/test_mcp_data_validation.py`:

```python
"""Integration tests for the data validation MCP tool."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.mcp import validate_dataset


def _write_jsonl(rows: list[dict], path: Path) -> None:
    """Write rows as JSONL to a file."""
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _valid_row(id: str = "ex-1") -> dict:
    return {
        "id": id,
        "input": "What is quantum entanglement?",
        "expected": {
            "route": "opus",
            "routes": {
                "opus": {"cost": 0.05, "quality_score": 0.98},
                "haiku": {"cost": 0.002, "quality_score": 0.72},
            },
        },
    }


class TestValidateDataset:
    @pytest.mark.asyncio
    async def test_valid_dataset_returns_report(self, tmp_path: Path) -> None:
        dataset = tmp_path / "data.jsonl"
        _write_jsonl([_valid_row("ex-1"), _valid_row("ex-2")], dataset)

        result = await validate_dataset(str(dataset))
        report = json.loads(result)

        assert "schema_findings" in report
        assert "label_distribution" in report
        assert "volume_assessment" in report
        assert "query_length" in report
        assert report["query_length"]["count"] == 2

    @pytest.mark.asyncio
    async def test_nonexistent_file_raises_tool_error(self) -> None:
        with pytest.raises(ToolError, match="Dataset file not found"):
            await validate_dataset("/nonexistent/path/data.jsonl")

    @pytest.mark.asyncio
    async def test_malformed_jsonl_raises_tool_error(self, tmp_path: Path) -> None:
        dataset = tmp_path / "bad.jsonl"
        dataset.write_text("not valid json\n", encoding="utf-8")

        with pytest.raises(ToolError, match="Malformed JSONL"):
            await validate_dataset(str(dataset))

    @pytest.mark.asyncio
    async def test_empty_file_returns_empty_report(self, tmp_path: Path) -> None:
        dataset = tmp_path / "empty.jsonl"
        dataset.write_text("", encoding="utf-8")

        result = await validate_dataset(str(dataset))
        report = json.loads(result)

        assert report["label_distribution"]["total_records"] == 0
        assert report["query_length"]["count"] == 0

    @pytest.mark.asyncio
    async def test_blank_lines_tolerated(self, tmp_path: Path) -> None:
        dataset = tmp_path / "data.jsonl"
        row_json = json.dumps(_valid_row("ex-1"))
        dataset.write_text(f"\n{row_json}\n\n", encoding="utf-8")

        result = await validate_dataset(str(dataset))
        report = json.loads(result)

        assert report["query_length"]["count"] == 1
```

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/test_mcp_data_validation.py -v`

Expected: ALL PASS.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`

Expected: ALL PASS.

- [ ] **Step 4: Run linting and type checking**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pyright`

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add tests/test_mcp_data_validation.py
git commit -m "test(thp-145): add integration tests for validate_dataset MCP tool"
```
