"""Data validation checks for the Data Validation agent.

Provides three validation functions that operate on raw parsed JSONL rows
and return typed Pydantic models. Used by THP-145 (validation logic) and
referenced by THP-106 (system prompt).

See: docs/superpowers/specs/2026-03-23-thp-81-data-validation-output-design.md
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_route(row: dict) -> str | None:
    """Extract expected.route from a row, or None if missing/invalid."""
    expected = row.get("expected")
    if not isinstance(expected, dict):
        return None
    route = expected.get("route")
    if not isinstance(route, str):
        return None
    return route


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def check_schema_conformance(rows: list[dict]) -> list[SchemaFinding]:
    """Check all rows against the THP-80 schema.

    Returns one SchemaFinding per check type (not per row).
    ``row_indices`` collects all failing rows for that check.
    """
    required_fail_indices: list[int] = []
    type_fail_indices: list[int] = []
    route_in_routes_fail_indices: list[int] = []
    non_empty_routes_fail_indices: list[int] = []
    duplicate_id_indices: list[int] = []

    # For consistent model set: collect (original_index, frozenset of route keys)
    route_key_sets: list[tuple[int, frozenset[str]]] = []

    seen_ids: dict[str, int] = {}  # id -> first index

    for idx, row in enumerate(rows):
        # --- Check 1: required keys present and non-null ---
        has_required = True

        for key in ("id", "input", "expected"):
            if key not in row or row[key] is None:
                has_required = False
                break

        if has_required:
            expected = row.get("expected")
            if isinstance(expected, dict):
                if "route" not in expected or expected["route"] is None:
                    has_required = False
                if "routes" not in expected or expected["routes"] is None:
                    has_required = False
            # If expected is not a dict, required keys within it are missing
            else:
                has_required = False

        if not has_required:
            required_fail_indices.append(idx)

        # --- Check 2: correct types ---
        type_ok = True
        if "id" in row and row["id"] is not None and not isinstance(row["id"], str):
            type_ok = False
        if "input" in row and row["input"] is not None and not isinstance(row["input"], str):
            type_ok = False
        expected = row.get("expected")
        if expected is not None and not isinstance(expected, dict):
            type_ok = False

        # Check expected.route type
        if isinstance(expected, dict):
            route_val = expected.get("route")
            if route_val is not None and not isinstance(route_val, str):
                type_ok = False

            # Check expected.routes values have numeric cost and quality_score
            routes_val = expected.get("routes")
            if isinstance(routes_val, dict):
                for _model_name, model_data in routes_val.items():
                    if isinstance(model_data, dict):
                        cost = model_data.get("cost")
                        quality = model_data.get("quality_score")
                        if cost is not None and not isinstance(cost, (int, float)):
                            type_ok = False
                        if quality is not None and not isinstance(quality, (int, float)):
                            type_ok = False

        if not type_ok:
            type_fail_indices.append(idx)

        # --- Checks 3-5 require expected to be a dict with routes ---
        if isinstance(expected, dict):
            route = expected.get("route")
            routes = expected.get("routes")

            # Check 3: route-in-routes
            if isinstance(route, str) and isinstance(routes, dict) and len(routes) > 0 and route not in routes:
                route_in_routes_fail_indices.append(idx)

            # Check 4: non-empty routes
            if isinstance(routes, dict) and len(routes) == 0:
                non_empty_routes_fail_indices.append(idx)

            # Collect route keys for consistency check (only valid dicts)
            if isinstance(routes, dict) and len(routes) > 0:
                route_key_sets.append((idx, frozenset(routes.keys())))

        # --- Check 6: unique IDs ---
        row_id = row.get("id")
        if isinstance(row_id, str):
            if row_id in seen_ids:
                duplicate_id_indices.append(idx)
            else:
                seen_ids[row_id] = idx

    # --- Check 5: consistent model set ---
    consistent_fail_indices: list[int] = []
    if route_key_sets:
        # Use the first valid row's key set as the reference
        _ref_idx, ref_keys = route_key_sets[0]
        for orig_idx, keys in route_key_sets[1:]:
            if keys != ref_keys:
                consistent_fail_indices.append(orig_idx)

    # Build findings
    findings: list[SchemaFinding] = []

    findings.append(
        SchemaFinding(
            field="required_keys",
            status="fail" if required_fail_indices else "pass",
            violation="Missing or null required keys" if required_fail_indices else None,
            row_indices=required_fail_indices,
        )
    )
    findings.append(
        SchemaFinding(
            field="types",
            status="fail" if type_fail_indices else "pass",
            violation="Incorrect field types" if type_fail_indices else None,
            row_indices=type_fail_indices,
        )
    )
    findings.append(
        SchemaFinding(
            field="route_in_routes",
            status="fail" if route_in_routes_fail_indices else "pass",
            violation="expected.route not found in expected.routes keys" if route_in_routes_fail_indices else None,
            row_indices=route_in_routes_fail_indices,
        )
    )
    findings.append(
        SchemaFinding(
            field="non_empty_routes",
            status="fail" if non_empty_routes_fail_indices else "pass",
            violation="expected.routes is empty" if non_empty_routes_fail_indices else None,
            row_indices=non_empty_routes_fail_indices,
        )
    )
    findings.append(
        SchemaFinding(
            field="consistent_model_set",
            status="fail" if consistent_fail_indices else "pass",
            violation="Inconsistent route keys across records" if consistent_fail_indices else None,
            row_indices=consistent_fail_indices,
        )
    )
    findings.append(
        SchemaFinding(
            field="unique_ids",
            status="fail" if duplicate_id_indices else "pass",
            violation="Duplicate id values" if duplicate_id_indices else None,
            row_indices=duplicate_id_indices,
        )
    )

    return findings
