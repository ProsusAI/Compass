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


class QueryLengthDistribution(BaseModel):
    """Character length distribution of query inputs."""

    min: int
    max: int
    mean: float
    p95: float
    count: int


class DataQualityReport(BaseModel):
    """Top-level report wrapping all validation check sections."""

    summary: str
    schema_findings: list[SchemaFinding]
    label_distribution: LabelDistribution
    volume_assessment: VolumeAssessment
    query_length: QueryLengthDistribution | None = None


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
    null_field_indices: list[int] = []

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
    findings.append(
        SchemaFinding(
            field="null_fields",
            status="fail" if null_field_indices else "pass",
            violation="Null values detected in non-required fields" if null_field_indices else None,
            row_indices=null_field_indices,
        )
    )

    return findings


def check_label_distribution(
    rows: list[dict],
    min_tier_percentage: float,
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
    tier_dists: list[TierDistribution] = []
    imbalanced: list[str] = []

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


def check_query_length_distribution(
    rows: list[dict],
) -> QueryLengthDistribution:
    """Compute character length distribution of the input field.

    Skips rows where ``input`` is missing or not a string.
    """
    lengths = [len(row["input"]) for row in rows if isinstance(row.get("input"), str)]

    if not lengths:
        return QueryLengthDistribution(
            min=0,
            max=0,
            mean=0.0,
            p95=0.0,
            count=0,
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


def check_volume_adequacy(
    rows: list[dict],
    min_per_tier: int,
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

    tier_volumes: list[TierVolume] = []
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
