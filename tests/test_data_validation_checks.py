"""Tests for odysseus.agents.data_validation_checks."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from odysseus.agents.data_validation_checks import (
    DataQualityReport,
    LabelDistribution,
    QueryLengthDistribution,
    SchemaFinding,
    TierDistribution,
    TierVolume,
    VolumeAssessment,
    check_label_distribution,
    check_query_length_distribution,
    check_schema_conformance,
    check_volume_adequacy,
)


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


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestSchemaFinding:
    def test_pass_finding(self) -> None:
        f = SchemaFinding(field="input", status="pass")
        assert f.status == "pass"
        assert f.violation is None
        assert f.row_indices == []

    def test_fail_finding(self) -> None:
        f = SchemaFinding(field="input", status="fail", violation="missing key", row_indices=[0, 2])
        assert f.status == "fail"
        assert f.violation == "missing key"
        assert f.row_indices == [0, 2]

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SchemaFinding(field="input", status="warning")  # type: ignore[arg-type]


class TestTierDistribution:
    def test_construction(self) -> None:
        td = TierDistribution(tier="opus", count=10, percentage=0.5, imbalanced=False)
        assert td.tier == "opus"
        assert td.count == 10
        assert td.percentage == 0.5
        assert td.imbalanced is False


class TestLabelDistribution:
    def test_construction_with_min_tier_percentage(self) -> None:
        ld = LabelDistribution(
            tiers=[TierDistribution(tier="opus", count=10, percentage=1.0, imbalanced=False)],
            total_records=10,
            num_tiers=1,
            imbalanced_tiers=[],
            min_tier_percentage=0.1,
        )
        assert ld.min_tier_percentage == 0.1
        assert ld.num_tiers == 1


class TestVolumeAssessment:
    def test_pass_verdict(self) -> None:
        va = VolumeAssessment(
            tiers=[TierVolume(tier="opus", verdict="adequate", actual_count=20, minimum_required=5)],
            overall_verdict="pass",
            min_per_tier=5,
        )
        assert va.overall_verdict == "pass"

    def test_invalid_verdict_rejected(self) -> None:
        with pytest.raises(ValidationError):
            VolumeAssessment(
                tiers=[],
                overall_verdict="maybe",  # type: ignore[arg-type]
                min_per_tier=5,
            )


class TestDataQualityReport:
    def test_full_construction(self) -> None:
        report = DataQualityReport(
            summary="All checks passed.",
            schema_findings=[SchemaFinding(field="input", status="pass")],
            label_distribution=LabelDistribution(
                tiers=[TierDistribution(tier="opus", count=10, percentage=1.0, imbalanced=False)],
                total_records=10,
                num_tiers=1,
                imbalanced_tiers=[],
                min_tier_percentage=0.1,
            ),
            volume_assessment=VolumeAssessment(
                tiers=[TierVolume(tier="opus", verdict="adequate", actual_count=10, minimum_required=5)],
                overall_verdict="pass",
                min_per_tier=5,
            ),
        )
        assert report.summary == "All checks passed."
        assert len(report.schema_findings) == 1


# ---------------------------------------------------------------------------
# check_schema_conformance tests
# ---------------------------------------------------------------------------


class TestCheckSchemaConformance:
    def test_valid_rows_all_pass(self) -> None:
        rows = [_valid_row(id="ex-1"), _valid_row(id="ex-2")]
        findings = check_schema_conformance(rows)
        assert all(f.status == "pass" for f in findings)

    def test_missing_required_key_input(self) -> None:
        row = _valid_row()
        del row["input"]
        findings = check_schema_conformance([row])
        required_finding = next(f for f in findings if f.field == "required_keys")
        assert required_finding.status == "fail"
        assert 0 in required_finding.row_indices

    def test_missing_required_key_expected(self) -> None:
        row = _valid_row()
        del row["expected"]
        findings = check_schema_conformance([row])
        required_finding = next(f for f in findings if f.field == "required_keys")
        assert required_finding.status == "fail"
        assert 0 in required_finding.row_indices

    def test_null_input_treated_as_missing(self) -> None:
        row = _valid_row(input=None)
        findings = check_schema_conformance([row])
        required_finding = next(f for f in findings if f.field == "required_keys")
        assert required_finding.status == "fail"
        assert 0 in required_finding.row_indices

    def test_null_id_treated_as_missing(self) -> None:
        row = _valid_row(id=None)
        findings = check_schema_conformance([row])
        required_finding = next(f for f in findings if f.field == "required_keys")
        assert required_finding.status == "fail"
        assert 0 in required_finding.row_indices

    def test_missing_expected_route(self) -> None:
        row = _valid_row()
        del row["expected"]["route"]
        findings = check_schema_conformance([row])
        required_finding = next(f for f in findings if f.field == "required_keys")
        assert required_finding.status == "fail"
        assert 0 in required_finding.row_indices

    def test_missing_expected_routes(self) -> None:
        row = _valid_row()
        del row["expected"]["routes"]
        findings = check_schema_conformance([row])
        required_finding = next(f for f in findings if f.field == "required_keys")
        assert required_finding.status == "fail"
        assert 0 in required_finding.row_indices

    def test_empty_rows_all_pass(self) -> None:
        findings = check_schema_conformance([])
        assert all(f.status == "pass" for f in findings)

    def test_wrong_type_input_not_string(self) -> None:
        row = _valid_row(input=42)
        findings = check_schema_conformance([row])
        type_finding = next(f for f in findings if f.field == "types")
        assert type_finding.status == "fail"
        assert 0 in type_finding.row_indices

    def test_wrong_type_expected_not_dict(self) -> None:
        row = _valid_row(expected="not a dict")
        findings = check_schema_conformance([row])
        type_finding = next(f for f in findings if f.field == "types")
        assert type_finding.status == "fail"
        assert 0 in type_finding.row_indices

    def test_route_not_in_routes_keys(self) -> None:
        row = _valid_row()
        row["expected"]["route"] = "sonnet"  # not in routes
        findings = check_schema_conformance([row])
        rir_finding = next(f for f in findings if f.field == "route_in_routes")
        assert rir_finding.status == "fail"
        assert 0 in rir_finding.row_indices

    def test_empty_routes_detected(self) -> None:
        row = _valid_row()
        row["expected"]["routes"] = {}
        findings = check_schema_conformance([row])
        nonempty_finding = next(f for f in findings if f.field == "non_empty_routes")
        assert nonempty_finding.status == "fail"
        assert 0 in nonempty_finding.row_indices

    def test_inconsistent_model_set(self) -> None:
        row_a = _valid_row(id="ex-1")
        row_b = _valid_row(id="ex-2")
        row_b["expected"]["routes"] = {
            "opus": {"cost": 0.05, "quality_score": 0.98},
            "sonnet": {"cost": 0.01, "quality_score": 0.85},
        }
        findings = check_schema_conformance([row_a, row_b])
        cons_finding = next(f for f in findings if f.field == "consistent_model_set")
        assert cons_finding.status == "fail"
        assert 1 in cons_finding.row_indices

    def test_duplicate_ids(self) -> None:
        rows = [_valid_row(id="ex-1"), _valid_row(id="ex-1")]
        findings = check_schema_conformance(rows)
        dup_finding = next(f for f in findings if f.field == "unique_ids")
        assert dup_finding.status == "fail"
        assert 1 in dup_finding.row_indices

    def test_invalid_cost_quality_types(self) -> None:
        row = _valid_row()
        row["expected"]["routes"]["opus"]["cost"] = "expensive"
        row["expected"]["routes"]["opus"]["quality_score"] = "high"
        findings = check_schema_conformance([row])
        type_finding = next(f for f in findings if f.field == "types")
        assert type_finding.status == "fail"
        assert 0 in type_finding.row_indices

    def test_multiple_rows_mixed_validity(self) -> None:
        good = _valid_row(id="ex-1")
        bad_input = _valid_row(id="ex-2", input=123)
        bad_route = _valid_row(id="ex-3")
        bad_route["expected"]["route"] = "sonnet"
        findings = check_schema_conformance([good, bad_input, bad_route])
        type_finding = next(f for f in findings if f.field == "types")
        assert type_finding.status == "fail"
        assert 1 in type_finding.row_indices
        assert 0 not in type_finding.row_indices
        rir_finding = next(f for f in findings if f.field == "route_in_routes")
        assert rir_finding.status == "fail"
        assert 2 in rir_finding.row_indices

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


# ---------------------------------------------------------------------------
# check_label_distribution tests
# ---------------------------------------------------------------------------


class TestCheckLabelDistribution:
    def test_balanced_two_tiers(self) -> None:
        rows = [
            _valid_row(id="ex-1", expected={"route": "opus", "routes": {"opus": {}, "haiku": {}}}),
            _valid_row(id="ex-2", expected={"route": "haiku", "routes": {"opus": {}, "haiku": {}}}),
        ]
        result = check_label_distribution(rows, min_tier_percentage=0.1)
        assert result.total_records == 2
        assert result.num_tiers == 2
        assert result.imbalanced_tiers == []
        for td in result.tiers:
            assert td.percentage == pytest.approx(0.5)
            assert td.imbalanced is False

    def test_imbalanced_tier_flagged(self) -> None:
        rows = [_valid_row(id=f"ex-{i}", expected={"route": "opus", "routes": {}}) for i in range(9)]
        rows.append(_valid_row(id="ex-9", expected={"route": "haiku", "routes": {}}))
        result = check_label_distribution(rows, min_tier_percentage=0.15)
        assert result.num_tiers == 2
        assert "haiku" in result.imbalanced_tiers
        assert "opus" not in result.imbalanced_tiers
        haiku_tier = next(t for t in result.tiers if t.tier == "haiku")
        assert haiku_tier.percentage == pytest.approx(0.1)
        assert haiku_tier.imbalanced is True

    def test_skips_rows_without_valid_route(self) -> None:
        rows = [
            _valid_row(id="ex-1"),
            {"id": "ex-2", "input": "no expected field"},
        ]
        result = check_label_distribution(rows, min_tier_percentage=0.1)
        assert result.total_records == 1

    def test_empty_rows(self) -> None:
        result = check_label_distribution([], min_tier_percentage=0.1)
        assert result.total_records == 0
        assert result.tiers == []
        assert result.num_tiers == 0

    def test_all_rows_schema_invalid(self) -> None:
        rows = [{"id": "ex-1", "input": "hello"}, {"id": "ex-2", "input": "world"}]
        result = check_label_distribution(rows, min_tier_percentage=0.1)
        assert result.total_records == 0
        assert result.tiers == []


# ---------------------------------------------------------------------------
# check_volume_adequacy tests
# ---------------------------------------------------------------------------


class TestCheckVolumeAdequacy:
    def test_all_tiers_adequate(self) -> None:
        rows = [_valid_row(id=f"ex-o{i}", expected={"route": "opus", "routes": {}}) for i in range(5)]
        rows += [_valid_row(id=f"ex-h{i}", expected={"route": "haiku", "routes": {}}) for i in range(5)]
        result = check_volume_adequacy(rows, min_per_tier=5)
        assert result.overall_verdict == "pass"
        assert all(tv.verdict == "adequate" for tv in result.tiers)

    def test_insufficient_tier(self) -> None:
        rows = [_valid_row(id=f"ex-{i}", expected={"route": "opus", "routes": {}}) for i in range(3)]
        result = check_volume_adequacy(rows, min_per_tier=5)
        assert result.overall_verdict == "fail"
        opus_tier = next(tv for tv in result.tiers if tv.tier == "opus")
        assert opus_tier.verdict == "insufficient"
        assert opus_tier.actual_count == 3

    def test_insufficient_tiers_from_mixed_data(self) -> None:
        rows = [
            _valid_row(id="ex-1", expected={"route": "opus", "routes": {}}),
            _valid_row(id="ex-2", expected={"route": "haiku", "routes": {}}),
        ]
        result = check_volume_adequacy(rows, min_per_tier=5)
        assert result.overall_verdict == "fail"
        assert all(tv.verdict == "insufficient" for tv in result.tiers)

    def test_skips_rows_without_valid_route(self) -> None:
        rows = [
            _valid_row(id="ex-1"),
            {"id": "ex-2", "input": "no expected field"},
        ]
        result = check_volume_adequacy(rows, min_per_tier=1)
        assert result.overall_verdict == "pass"
        assert len(result.tiers) == 1

    def test_empty_rows(self) -> None:
        result = check_volume_adequacy([], min_per_tier=5)
        assert result.overall_verdict == "fail"
        assert result.tiers == []

    def test_all_rows_schema_invalid(self) -> None:
        rows = [{"id": "ex-1", "input": "hello"}, {"id": "ex-2", "input": "world"}]
        result = check_volume_adequacy(rows, min_per_tier=5)
        assert result.overall_verdict == "fail"
        assert result.tiers == []


# ---------------------------------------------------------------------------
# QueryLengthDistribution model tests
# ---------------------------------------------------------------------------


class TestQueryLengthDistribution:
    def test_model_construction(self) -> None:
        qld = QueryLengthDistribution(min=5, max=100, mean=42.5, p95=90.0, count=10)
        assert qld.min == 5
        assert qld.max == 100
        assert qld.mean == 42.5
        assert qld.p95 == 90.0
        assert qld.count == 10


# ---------------------------------------------------------------------------
# check_query_length_distribution tests
# ---------------------------------------------------------------------------


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
        # p95 of [10, 20, 30, 40, 50] with linear interpolation:
        # rank = 0.95 * (5-1) = 3.8, lower=3, upper=4, frac=0.8
        # p95 = 40 + 0.8 * (50 - 40) = 48.0
        assert result.p95 == pytest.approx(48.0)

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
