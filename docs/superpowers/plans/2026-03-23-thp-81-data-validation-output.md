# THP-81 Data Validation Output Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the data quality report structure and pre-written validation check functions for the Data Validation agent's format gate.

**Architecture:** Three pure functions in a single Python module operate on raw parsed JSONL rows (list of dicts) and return typed Pydantic models. A companion markdown document defines the report structure for embedding into the agent's system prompt (THP-106). No external dependencies — stdlib only (`collections.Counter`).

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, ruff, pyright

**Spec:** `docs/superpowers/specs/2026-03-23-thp-81-data-validation-output-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `odysseus/agents/data_validation_checks.py` | Create | Pydantic models + three validation functions |
| `tests/test_data_validation_checks.py` | Create | Unit tests for all three functions + models |
| `odysseus/agents/data_validation_output.md` | Create | Report structure reference for THP-106 |
| `odysseus/agents/__init__.py` | Modify | Export new models and functions |

---

## Chunk 1: Pydantic Models and Schema Conformance

### Task 1: Pydantic Models

**Files:**
- Create: `odysseus/agents/data_validation_checks.py`
- Create: `tests/test_data_validation_checks.py`

- [ ] **Step 1: Write tests for Pydantic models**

Create `tests/test_data_validation_checks.py`:

```python
"""Tests for data validation check models and functions."""

from pydantic import ValidationError
import pytest

from odysseus.agents.data_validation_checks import (
    DataQualityReport,
    LabelDistribution,
    SchemaFinding,
    TierDistribution,
    TierVolume,
    VolumeAssessment,
)


class TestSchemaFinding:
    def test_pass_finding(self):
        f = SchemaFinding(field="input", status="pass")
        assert f.violation is None
        assert f.row_indices == []

    def test_fail_finding(self):
        f = SchemaFinding(
            field="input",
            status="fail",
            violation="null value in 2 rows",
            row_indices=[0, 3],
        )
        assert f.status == "fail"
        assert f.row_indices == [0, 3]

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            SchemaFinding(field="input", status="unknown")


class TestTierDistribution:
    def test_construction(self):
        td = TierDistribution(
            tier="opus", count=10, percentage=0.5, imbalanced=False
        )
        assert td.tier == "opus"
        assert td.percentage == 0.5


class TestLabelDistribution:
    def test_construction(self):
        ld = LabelDistribution(
            tiers=[
                TierDistribution(
                    tier="opus", count=10, percentage=0.5, imbalanced=False
                ),
                TierDistribution(
                    tier="haiku", count=10, percentage=0.5, imbalanced=False
                ),
            ],
            total_records=20,
            num_tiers=2,
            imbalanced_tiers=[],
            min_tier_percentage=0.1,
        )
        assert ld.num_tiers == 2
        assert ld.min_tier_percentage == 0.1


class TestVolumeAssessment:
    def test_pass_verdict(self):
        va = VolumeAssessment(
            tiers=[
                TierVolume(
                    tier="opus",
                    verdict="adequate",
                    actual_count=20,
                    minimum_required=5,
                )
            ],
            overall_verdict="pass",
            min_per_tier=5,
        )
        assert va.overall_verdict == "pass"

    def test_invalid_verdict_rejected(self):
        with pytest.raises(ValidationError):
            TierVolume(
                tier="opus",
                verdict="maybe",
                actual_count=20,
                minimum_required=5,
            )


class TestDataQualityReport:
    def test_construction(self):
        report = DataQualityReport(
            summary="Dataset looks good.",
            schema_findings=[
                SchemaFinding(field="input", status="pass")
            ],
            label_distribution=LabelDistribution(
                tiers=[
                    TierDistribution(
                        tier="opus",
                        count=10,
                        percentage=1.0,
                        imbalanced=False,
                    )
                ],
                total_records=10,
                num_tiers=1,
                imbalanced_tiers=[],
                min_tier_percentage=0.1,
            ),
            volume_assessment=VolumeAssessment(
                tiers=[
                    TierVolume(
                        tier="opus",
                        verdict="adequate",
                        actual_count=10,
                        minimum_required=5,
                    )
                ],
                overall_verdict="pass",
                min_per_tier=5,
            ),
        )
        assert report.summary == "Dataset looks good."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data_validation_checks.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement Pydantic models**

Create `odysseus/agents/data_validation_checks.py`:

```python
"""Data validation checks for the Data Validation agent.

Provides three validation functions that operate on raw parsed JSONL rows
and return typed Pydantic models. Used by THP-145 (validation logic) and
referenced by THP-106 (system prompt).

See: docs/superpowers/specs/2026-03-23-thp-81-data-validation-output-design.md
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field


# --- Pydantic Models ---


class SchemaFinding(BaseModel):
    """Result of a single schema conformance check."""

    field: str
    status: Literal["pass", "fail"]
    violation: str | None = None
    row_indices: list[int] = Field(default_factory=list)


class TierDistribution(BaseModel):
    """Label distribution stats for a single routing tier."""

    tier: str
    count: int
    percentage: float
    imbalanced: bool


class LabelDistribution(BaseModel):
    """Label distribution stats across all routing tiers."""

    tiers: list[TierDistribution]
    total_records: int
    num_tiers: int
    imbalanced_tiers: list[str]
    min_tier_percentage: float


class TierVolume(BaseModel):
    """Volume adequacy verdict for a single routing tier."""

    tier: str
    verdict: Literal["adequate", "insufficient", "absent"]
    actual_count: int
    minimum_required: int


class VolumeAssessment(BaseModel):
    """Volume adequacy assessment across all routing tiers."""

    tiers: list[TierVolume]
    overall_verdict: Literal["pass", "fail"]
    min_per_tier: int


class DataQualityReport(BaseModel):
    """Top-level report wrapping all four sections."""

    summary: str
    schema_findings: list[SchemaFinding]
    label_distribution: LabelDistribution
    volume_assessment: VolumeAssessment
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_validation_checks.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/data_validation_checks.py tests/test_data_validation_checks.py
git commit -m "feat(thp-81): add Pydantic models for data validation report"
```

---

### Task 2: `check_schema_conformance` — Required Keys and Null Checks

**Files:**
- Modify: `odysseus/agents/data_validation_checks.py`
- Modify: `tests/test_data_validation_checks.py`

Test helper to add at the top of the test file (after imports):

```python
def _valid_row(**overrides) -> dict:
    """Build a valid row, overriding specific fields."""
    row = {
        "id": "ex-1",
        "input": "What is quantum entanglement?",
        "expected": {
            "route": "opus",
            "routes": {
                "opus": {"cost": 0.05, "quality_score": 0.98},
                "haiku": {"cost": 0.002, "quality_score": 0.72},
            },
        },
    }
    row.update(overrides)
    return row
```

- [ ] **Step 1: Write tests for required keys and null checks**

Add to `tests/test_data_validation_checks.py`:

```python
from odysseus.agents.data_validation_checks import check_schema_conformance


class TestCheckSchemaConformance:
    def test_valid_rows_all_pass(self):
        rows = [_valid_row(id="ex-1"), _valid_row(id="ex-2")]
        findings = check_schema_conformance(rows)
        assert all(f.status == "pass" for f in findings)

    def test_missing_required_key_input(self):
        row = _valid_row()
        del row["input"]
        findings = check_schema_conformance([row])
        input_finding = next(
            f for f in findings if f.field == "input"
        )
        assert input_finding.status == "fail"
        assert 0 in input_finding.row_indices

    def test_missing_required_key_expected(self):
        row = _valid_row()
        del row["expected"]
        findings = check_schema_conformance([row])
        expected_finding = next(
            f for f in findings if f.field == "expected"
        )
        assert expected_finding.status == "fail"

    def test_null_input_treated_as_missing(self):
        row = _valid_row(input=None)
        findings = check_schema_conformance([row])
        input_finding = next(
            f for f in findings if f.field == "input"
        )
        assert input_finding.status == "fail"
        assert 0 in input_finding.row_indices

    def test_null_id_treated_as_missing(self):
        row = _valid_row(id=None)
        findings = check_schema_conformance([row])
        id_finding = next(f for f in findings if f.field == "id")
        assert id_finding.status == "fail"

    def test_missing_expected_route(self):
        row = _valid_row()
        del row["expected"]["route"]
        findings = check_schema_conformance([row])
        route_finding = next(
            f for f in findings if f.field == "expected.route"
        )
        assert route_finding.status == "fail"

    def test_missing_expected_routes(self):
        row = _valid_row()
        del row["expected"]["routes"]
        findings = check_schema_conformance([row])
        routes_finding = next(
            f for f in findings if f.field == "expected.routes"
        )
        assert routes_finding.status == "fail"

    def test_empty_rows_all_pass(self):
        findings = check_schema_conformance([])
        assert all(f.status == "pass" for f in findings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data_validation_checks.py::TestCheckSchemaConformance -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `check_schema_conformance` — required keys and nulls**

Add to `odysseus/agents/data_validation_checks.py`:

```python
def _extract_route(row: dict) -> str | None:
    """Extract expected.route from a row, or None if missing/invalid."""
    expected = row.get("expected")
    if not isinstance(expected, dict):
        return None
    route = expected.get("route")
    if not isinstance(route, str):
        return None
    return route


def check_schema_conformance(rows: list[dict]) -> list[SchemaFinding]:
    """Check all rows against THP-80 schema constraints.

    Returns one SchemaFinding per check type. row_indices collects
    all failing row indices for that check.
    """
    findings: dict[str, SchemaFinding] = {}

    # Check 1: Required top-level keys present and non-null
    for field in ("id", "input", "expected"):
        failing = [
            i
            for i, row in enumerate(rows)
            if field not in row or row[field] is None
        ]
        findings[field] = SchemaFinding(
            field=field,
            status="fail" if failing else "pass",
            violation=(
                f"missing or null in {len(failing)} row(s)" if failing else None
            ),
            row_indices=failing,
        )

    # Check 1 (continued): Required nested keys present and non-null
    for nested_field, parent in (
        ("expected.route", "expected"),
        ("expected.routes", "expected"),
    ):
        key = nested_field.split(".")[-1]
        failing = [
            i
            for i, row in enumerate(rows)
            if isinstance(row.get(parent), dict)
            and (key not in row[parent] or row[parent][key] is None)
        ]
        findings[nested_field] = SchemaFinding(
            field=nested_field,
            status="fail" if failing else "pass",
            violation=(
                f"missing or null in {len(failing)} row(s)" if failing else None
            ),
            row_indices=failing,
        )

    # Check 2: Correct types
    type_checks: list[tuple[str, type]] = [
        ("id", str),
        ("input", str),
        ("expected", dict),
    ]
    for field, expected_type in type_checks:
        failing = [
            i
            for i, row in enumerate(rows)
            if field in row
            and row[field] is not None
            and not isinstance(row[field], expected_type)
        ]
        findings[f"{field}_type"] = SchemaFinding(
            field=field,
            status="fail" if failing else "pass",
            violation=(
                f"wrong type in {len(failing)} row(s), expected {expected_type.__name__}"
                if failing
                else None
            ),
            row_indices=failing,
        )

    # Check 2 (continued): expected.route must be str
    failing = [
        i
        for i, row in enumerate(rows)
        if isinstance(row.get("expected"), dict)
        and "route" in row["expected"]
        and row["expected"]["route"] is not None
        and not isinstance(row["expected"]["route"], str)
    ]
    findings["expected.route_type"] = SchemaFinding(
        field="expected.route",
        status="fail" if failing else "pass",
        violation=(
            f"wrong type in {len(failing)} row(s), expected str"
            if failing
            else None
        ),
        row_indices=failing,
    )

    # Check 2 (continued): expected.routes values must have numeric cost and quality_score
    failing = []
    for i, row in enumerate(rows):
        expected = row.get("expected")
        if not isinstance(expected, dict):
            continue
        routes = expected.get("routes")
        if not isinstance(routes, dict):
            continue
        for model_name, model_data in routes.items():
            if not isinstance(model_data, dict):
                failing.append(i)
                break
            cost = model_data.get("cost")
            quality = model_data.get("quality_score")
            if not isinstance(cost, (int, float)) or not isinstance(
                quality, (int, float)
            ):
                failing.append(i)
                break
    findings["expected.routes_values_type"] = SchemaFinding(
        field="expected.routes",
        status="fail" if failing else "pass",
        violation=(
            f"invalid cost/quality_score types in {len(failing)} row(s)"
            if failing
            else None
        ),
        row_indices=failing,
    )

    # Check 3: Route-in-routes
    failing = []
    for i, row in enumerate(rows):
        expected = row.get("expected")
        if not isinstance(expected, dict):
            continue
        route = expected.get("route")
        routes = expected.get("routes")
        if not isinstance(route, str) or not isinstance(routes, dict):
            continue
        if route not in routes:
            failing.append(i)
    findings["route_in_routes"] = SchemaFinding(
        field="expected.route",
        status="fail" if failing else "pass",
        violation=(
            f"route not found in routes keys in {len(failing)} row(s)"
            if failing
            else None
        ),
        row_indices=failing,
    )

    # Check 4: Non-empty routes
    failing = [
        i
        for i, row in enumerate(rows)
        if isinstance(row.get("expected"), dict)
        and isinstance(row["expected"].get("routes"), dict)
        and len(row["expected"]["routes"]) == 0
    ]
    findings["non_empty_routes"] = SchemaFinding(
        field="expected.routes",
        status="fail" if failing else "pass",
        violation=(
            f"empty routes in {len(failing)} row(s)" if failing else None
        ),
        row_indices=failing,
    )

    # Check 5: Consistent model set
    model_sets: list[tuple[int, frozenset[str]]] = []
    for i, row in enumerate(rows):
        expected = row.get("expected")
        if not isinstance(expected, dict):
            continue
        routes = expected.get("routes")
        if not isinstance(routes, dict):
            continue
        model_sets.append((i, frozenset(routes.keys())))

    if model_sets:
        reference_set = model_sets[0][1]
        inconsistent = [
            idx for idx, ms in model_sets if ms != reference_set
        ]
        findings["consistent_model_set"] = SchemaFinding(
            field="expected.routes",
            status="fail" if inconsistent else "pass",
            violation=(
                f"inconsistent model keys in {len(inconsistent)} row(s)"
                if inconsistent
                else None
            ),
            row_indices=inconsistent,
        )
    else:
        findings["consistent_model_set"] = SchemaFinding(
            field="expected.routes",
            status="pass",
        )

    # Check 6: Unique IDs
    seen_ids: dict[str, int] = {}
    duplicate_indices: list[int] = []
    for i, row in enumerate(rows):
        row_id = row.get("id")
        if not isinstance(row_id, str):
            continue
        if row_id in seen_ids:
            duplicate_indices.append(i)
            if seen_ids[row_id] not in duplicate_indices:
                duplicate_indices.append(seen_ids[row_id])
        else:
            seen_ids[row_id] = i
    findings["unique_ids"] = SchemaFinding(
        field="id",
        status="fail" if duplicate_indices else "pass",
        violation=(
            f"duplicate IDs in {len(duplicate_indices)} row(s)"
            if duplicate_indices
            else None
        ),
        row_indices=sorted(duplicate_indices),
    )

    return list(findings.values())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_validation_checks.py::TestCheckSchemaConformance -v`
Expected: All PASS

- [ ] **Step 5: Run linter and type checker**

Run: `uv run ruff check odysseus/agents/data_validation_checks.py && uv run pyright odysseus/agents/data_validation_checks.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add odysseus/agents/data_validation_checks.py tests/test_data_validation_checks.py
git commit -m "feat(thp-81): implement check_schema_conformance with tests"
```

---

### Task 3: `check_schema_conformance` — Type and Cross-Record Checks

**Files:**
- Modify: `tests/test_data_validation_checks.py`

- [ ] **Step 1: Write tests for type checks, route-in-routes, consistent model set, and unique IDs**

Add to `TestCheckSchemaConformance`:

```python
    def test_wrong_type_input_not_string(self):
        row = _valid_row(input=123)
        findings = check_schema_conformance([row])
        type_findings = [
            f for f in findings if f.field == "input" and "type" in (f.violation or "")
        ]
        assert any(f.status == "fail" for f in type_findings)

    def test_wrong_type_expected_not_dict(self):
        row = _valid_row(expected="not_a_dict")
        findings = check_schema_conformance([row])
        type_findings = [
            f
            for f in findings
            if f.field == "expected" and "type" in (f.violation or "")
        ]
        assert any(f.status == "fail" for f in type_findings)

    def test_route_not_in_routes_keys(self):
        row = _valid_row()
        row["expected"]["route"] = "gpt-4o"
        findings = check_schema_conformance([row])
        rir = next(
            f
            for f in findings
            if f.field == "expected.route"
            and f.violation
            and "not found in routes" in f.violation
        )
        assert rir.status == "fail"
        assert 0 in rir.row_indices

    def test_empty_routes_detected(self):
        row = _valid_row()
        row["expected"]["routes"] = {}
        findings = check_schema_conformance([row])
        empty = next(
            f
            for f in findings
            if f.field == "expected.routes"
            and f.violation
            and "empty" in f.violation
        )
        assert empty.status == "fail"

    def test_inconsistent_model_set(self):
        row1 = _valid_row(id="ex-1")
        row2 = _valid_row(id="ex-2")
        row2["expected"]["routes"] = {
            "sonnet": {"cost": 0.01, "quality_score": 0.88}
        }
        findings = check_schema_conformance([row1, row2])
        cons = next(
            f
            for f in findings
            if f.field == "expected.routes"
            and f.violation
            and "inconsistent" in f.violation
        )
        assert cons.status == "fail"

    def test_duplicate_ids(self):
        row1 = _valid_row(id="dup")
        row2 = _valid_row(id="dup")
        findings = check_schema_conformance([row1, row2])
        dup = next(
            f
            for f in findings
            if f.field == "id" and f.violation and "duplicate" in f.violation
        )
        assert dup.status == "fail"
        assert sorted(dup.row_indices) == [0, 1]

    def test_invalid_cost_quality_types(self):
        row = _valid_row()
        row["expected"]["routes"]["opus"]["cost"] = "expensive"
        findings = check_schema_conformance([row])
        type_finding = next(
            f
            for f in findings
            if f.field == "expected.routes"
            and f.violation
            and "cost/quality_score" in f.violation
        )
        assert type_finding.status == "fail"

    def test_multiple_rows_mixed_validity(self):
        valid = _valid_row(id="ex-1")
        invalid = _valid_row(id="ex-2", input=None)
        findings = check_schema_conformance([valid, invalid])
        input_finding = next(f for f in findings if f.field == "input" and f.status == "fail")
        assert input_finding.row_indices == [1]
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_validation_checks.py::TestCheckSchemaConformance -v`
Expected: All PASS (implementation from Task 2 covers these)

- [ ] **Step 3: Commit**

```bash
git add tests/test_data_validation_checks.py
git commit -m "test(thp-81): add type, cross-record, and edge case tests for schema conformance"
```

---

## Chunk 2: Label Distribution and Volume Adequacy

### Task 4: `check_label_distribution`

**Files:**
- Modify: `odysseus/agents/data_validation_checks.py`
- Modify: `tests/test_data_validation_checks.py`

- [ ] **Step 1: Write tests**

Add to `tests/test_data_validation_checks.py`:

```python
from odysseus.agents.data_validation_checks import check_label_distribution


class TestCheckLabelDistribution:
    def test_balanced_two_tiers(self):
        two_tier_routes = {
            "opus": {"cost": 0.05, "quality_score": 0.9},
            "haiku": {"cost": 0.002, "quality_score": 0.7},
        }
        rows = [
            _valid_row(
                id="1",
                expected={"route": "opus", "routes": two_tier_routes},
            ),
            _valid_row(
                id="2",
                expected={"route": "haiku", "routes": two_tier_routes},
            ),
        ]
        result = check_label_distribution(rows, min_tier_percentage=0.1)
        assert result.total_records == 2
        assert result.num_tiers == 2
        assert result.imbalanced_tiers == []
        assert result.min_tier_percentage == 0.1
        for td in result.tiers:
            assert td.count == 1
            assert td.percentage == 0.5
            assert td.imbalanced is False

    def test_imbalanced_tier_flagged(self):
        rows = [_valid_row(id=f"ex-{i}") for i in range(10)]
        # 9 opus, 1 haiku
        rows[-1]["expected"] = {
            "route": "haiku",
            "routes": {
                "opus": {"cost": 0.05, "quality_score": 0.9},
                "haiku": {"cost": 0.002, "quality_score": 0.7},
            },
        }
        result = check_label_distribution(rows, min_tier_percentage=0.15)
        assert "haiku" in result.imbalanced_tiers
        haiku_tier = next(t for t in result.tiers if t.tier == "haiku")
        assert haiku_tier.imbalanced is True

    def test_skips_rows_without_valid_route(self):
        rows = [
            _valid_row(id="1"),
            {"id": "2", "input": "bad row"},  # no expected
        ]
        result = check_label_distribution(rows, min_tier_percentage=0.1)
        assert result.total_records == 1

    def test_empty_rows(self):
        result = check_label_distribution([], min_tier_percentage=0.1)
        assert result.total_records == 0
        assert result.num_tiers == 0
        assert result.tiers == []

    def test_all_rows_schema_invalid(self):
        rows = [{"id": "1", "input": "hello"}, {"id": "2"}]
        result = check_label_distribution(rows, min_tier_percentage=0.1)
        assert result.total_records == 0
        assert result.tiers == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data_validation_checks.py::TestCheckLabelDistribution -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `check_label_distribution`**

Add to `odysseus/agents/data_validation_checks.py`:

```python
def check_label_distribution(
    rows: list[dict], min_tier_percentage: float
) -> LabelDistribution:
    """Compute label distribution stats per routing tier.

    Internally skips rows without a valid expected.route.
    """
    routes = [r for row in rows if (r := _extract_route(row)) is not None]
    total = len(routes)

    if total == 0:
        return LabelDistribution(
            tiers=[],
            total_records=0,
            num_tiers=0,
            imbalanced_tiers=[],
            min_tier_percentage=min_tier_percentage,
        )

    counts = Counter(routes)
    tier_dists = []
    imbalanced = []

    for tier, count in sorted(counts.items()):
        pct = count / total
        is_imbalanced = pct < min_tier_percentage
        if is_imbalanced:
            imbalanced.append(tier)
        tier_dists.append(
            TierDistribution(
                tier=tier,
                count=count,
                percentage=pct,
                imbalanced=is_imbalanced,
            )
        )

    return LabelDistribution(
        tiers=tier_dists,
        total_records=total,
        num_tiers=len(counts),
        imbalanced_tiers=imbalanced,
        min_tier_percentage=min_tier_percentage,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_validation_checks.py::TestCheckLabelDistribution -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/agents/data_validation_checks.py tests/test_data_validation_checks.py
git commit -m "feat(thp-81): implement check_label_distribution with tests"
```

---

### Task 5: `check_volume_adequacy`

**Files:**
- Modify: `odysseus/agents/data_validation_checks.py`
- Modify: `tests/test_data_validation_checks.py`

- [ ] **Step 1: Write tests**

Add to `tests/test_data_validation_checks.py`:

```python
from odysseus.agents.data_validation_checks import check_volume_adequacy


class TestCheckVolumeAdequacy:
    def test_all_tiers_adequate(self):
        rows = [_valid_row(id=f"ex-{i}") for i in range(10)]
        result = check_volume_adequacy(rows, min_per_tier=5)
        assert result.overall_verdict == "pass"
        assert result.min_per_tier == 5
        assert all(t.verdict == "adequate" for t in result.tiers)

    def test_insufficient_tier(self):
        rows = [_valid_row(id=f"ex-{i}") for i in range(3)]
        result = check_volume_adequacy(rows, min_per_tier=5)
        assert result.overall_verdict == "fail"
        opus_tier = next(t for t in result.tiers if t.tier == "opus")
        assert opus_tier.verdict == "insufficient"
        assert opus_tier.actual_count == 3
        assert opus_tier.minimum_required == 5

    def test_insufficient_tiers_from_mixed_data(self):
        rows = [
            _valid_row(id="1"),
            _valid_row(
                id="2",
                expected={
                    "route": "haiku",
                    "routes": {
                        "opus": {"cost": 0.05, "quality_score": 0.9},
                        "haiku": {"cost": 0.002, "quality_score": 0.7},
                    },
                },
            ),
        ]
        result = check_volume_adequacy(rows, min_per_tier=5)
        assert result.overall_verdict == "fail"
        for tier in result.tiers:
            assert tier.verdict == "insufficient"

    def test_skips_rows_without_valid_route(self):
        rows = [
            _valid_row(id="1"),
            {"id": "2", "input": "bad row"},
        ]
        result = check_volume_adequacy(rows, min_per_tier=1)
        assert result.overall_verdict == "pass"
        assert len(result.tiers) == 1

    def test_empty_rows(self):
        result = check_volume_adequacy([], min_per_tier=5)
        assert result.overall_verdict == "fail"
        assert result.tiers == []

    def test_all_rows_schema_invalid(self):
        rows = [{"id": "1", "input": "hello"}, {"id": "2"}]
        result = check_volume_adequacy(rows, min_per_tier=5)
        assert result.overall_verdict == "fail"
        assert result.tiers == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data_validation_checks.py::TestCheckVolumeAdequacy -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `check_volume_adequacy`**

Add to `odysseus/agents/data_validation_checks.py`:

```python
def check_volume_adequacy(
    rows: list[dict], min_per_tier: int
) -> VolumeAssessment:
    """Assess volume adequacy per routing tier.

    Internally skips rows without a valid expected.route.
    """
    routes = [r for row in rows if (r := _extract_route(row)) is not None]
    counts = Counter(routes)

    if not counts:
        return VolumeAssessment(
            tiers=[],
            overall_verdict="fail",
            min_per_tier=min_per_tier,
        )

    tier_volumes = []
    all_adequate = True

    # Note: Counter only contains tiers with count > 0, so "absent"
    # is not reachable here. It exists in the model for cases where
    # the expected tier set is known externally (e.g. from the
    # consistent model set check). Callers with that information
    # can construct TierVolume with verdict="absent" directly.
    for tier, count in sorted(counts.items()):
        if count >= min_per_tier:
            verdict: Literal["adequate", "insufficient", "absent"] = "adequate"
        else:
            verdict = "insufficient"
            all_adequate = False

        tier_volumes.append(
            TierVolume(
                tier=tier,
                verdict=verdict,
                actual_count=count,
                minimum_required=min_per_tier,
            )
        )

    return VolumeAssessment(
        tiers=tier_volumes,
        overall_verdict="pass" if all_adequate else "fail",
        min_per_tier=min_per_tier,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_validation_checks.py::TestCheckVolumeAdequacy -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite and linter**

Run: `uv run pytest tests/test_data_validation_checks.py -v && uv run ruff check odysseus/agents/data_validation_checks.py && uv run pyright odysseus/agents/data_validation_checks.py`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add odysseus/agents/data_validation_checks.py tests/test_data_validation_checks.py
git commit -m "feat(thp-81): implement check_volume_adequacy with tests"
```

---

## Chunk 3: Reference Document, Exports, and Final Verification

### Task 6: Reference Document

**Files:**
- Create: `odysseus/agents/data_validation_output.md`

- [ ] **Step 1: Write the reference document**

Create `odysseus/agents/data_validation_output.md`:

```markdown
# Data Quality Report — Output Format Reference

This document defines the structure of the data quality report produced by the Data Validation agent. It is the primary input to THP-106 (system prompt assembly).

## Report Sections

The report has four sections, produced in this order.

### 1. Dataset Summary

Two natural-language paragraphs written by the agent:

1. **Data description** — what the dataset contains: the routing problem domain, what kinds of queries are represented, and what the routing tiers correspond to.
2. **Validation summary** — total record count, tier names and distribution, any issues found, and overall verdict (ready for downstream processing or blocked).

This section is agent-written, not code-generated. The agent bases it on the outputs of the three check functions below.

### 2. Schema Consistency Findings

Produced by `check_schema_conformance()` in `data_validation_checks.py`.

One finding per check type, each containing:
- `field` — field path checked (e.g., `"expected.route"`)
- `status` — `"pass"` or `"fail"`
- `violation` — description if failed, null if passed
- `row_indices` — indices of failing rows

Checks: required keys present and non-null, correct types, route-in-routes, non-empty routes, consistent model set, unique IDs. See the spec for full details.

### 3. Label Distribution Stats

Produced by `check_label_distribution()` in `data_validation_checks.py`.

Per tier: count, percentage, imbalance flag. Dataset-level: total records, number of tiers, imbalanced tier list, threshold used.

### 4. Volume Adequacy Assessment

Produced by `check_volume_adequacy()` in `data_validation_checks.py`.

Per tier: verdict (`adequate` / `insufficient` / `absent`), actual count, minimum required. Dataset-level: overall verdict (`pass` / `fail`), threshold used.

## Implementation

All check functions and Pydantic models live in `odysseus/agents/data_validation_checks.py`. The top-level `DataQualityReport` model wraps all four sections.

## Linkages

- **THP-80** — Schema constraints that `check_schema_conformance` validates against.
- **THP-69** — Volume thresholds and imbalance minimums passed as parameters.
- **THP-145** — Imports and calls the check functions directly.
- **THP-106** — Embeds this report structure into the agent system prompt.
- **THP-74** — Consumes the data quality report; reads the dataset summary for quick context.
```

- [ ] **Step 2: Commit**

```bash
git add odysseus/agents/data_validation_output.md
git commit -m "docs(thp-81): add data quality report output format reference"
```

---

### Task 7: Update Exports and Final Verification

**Files:**
- Modify: `odysseus/agents/__init__.py`

- [ ] **Step 1: Add exports to `__init__.py`**

Add to `odysseus/agents/__init__.py`:

```python
from odysseus.agents.data_validation_checks import (
    DataQualityReport,
    LabelDistribution,
    SchemaFinding,
    TierDistribution,
    TierVolume,
    VolumeAssessment,
    check_label_distribution,
    check_schema_conformance,
    check_volume_adequacy,
)
```

And add to `__all__`:

```python
    "DataQualityReport",
    "LabelDistribution",
    "SchemaFinding",
    "TierDistribution",
    "TierVolume",
    "VolumeAssessment",
    "check_label_distribution",
    "check_schema_conformance",
    "check_volume_adequacy",
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass (both new and existing)

- [ ] **Step 3: Run linter and type checker on all changed files**

Run: `uv run ruff check odysseus/agents/data_validation_checks.py odysseus/agents/__init__.py && uv run pyright odysseus/agents/data_validation_checks.py odysseus/agents/__init__.py`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add odysseus/agents/__init__.py
git commit -m "feat(thp-81): export validation check models and functions"
```

- [ ] **Step 5: Run full project checks**

Run: `uv run ruff check . && uv run pyright && uv run pytest -v`
Expected: All green
