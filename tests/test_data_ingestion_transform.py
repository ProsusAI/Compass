"""Tests for odysseus.agents.data_ingestion_transform."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odysseus.agents.data_ingestion_transform import (
    TransformResult,
    _check_required_targets,
    _get_nested,
    _maybe_coerce_numeric,
    _set_nested,
    transform_dataset,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _minimal_mapping() -> dict[str, str]:
    """Mapping that satisfies all required targets."""
    return {
        "text": "input",
        "tier": "expected.route",
        "routes": "expected.routes",
    }


def _minimal_mapping_json() -> str:
    return json.dumps(_minimal_mapping())


# ---------------------------------------------------------------------------
# TestTransformResult — model construction
# ---------------------------------------------------------------------------


class TestTransformResult:
    def test_minimal_construction(self) -> None:
        result = TransformResult(
            output_path="/tmp/out.jsonl",
            original_dataset_path="/tmp/in.jsonl",
            rows_written=5,
            fields_mapped={"text": "input"},
        )
        assert result.output_path == "/tmp/out.jsonl"
        assert result.original_dataset_path == "/tmp/in.jsonl"
        assert result.rows_written == 5
        assert result.fields_mapped == {"text": "input"}
        assert result.fields_dropped == []

    def test_with_dropped_fields(self) -> None:
        result = TransformResult(
            output_path="/tmp/out.jsonl",
            original_dataset_path="/tmp/in.jsonl",
            rows_written=3,
            fields_mapped={"text": "input"},
            fields_dropped=["extra_col", "unused"],
        )
        assert result.fields_dropped == ["extra_col", "unused"]


# ---------------------------------------------------------------------------
# TestFlatToFlat
# ---------------------------------------------------------------------------


class TestFlatToFlat:
    def test_simple_rename(self, tmp_path: Path) -> None:
        src = tmp_path / "data.jsonl"
        _write_jsonl(
            src,
            [
                {"text": "hello", "tier": "opus", "routes": {"opus": {}, "haiku": {}}},
            ],
        )
        out = tmp_path / "out.jsonl"
        result = transform_dataset(str(src), _minimal_mapping_json(), str(out))

        assert result.rows_written == 1
        rows = _read_jsonl(out)
        assert rows[0]["input"] == "hello"
        assert rows[0]["expected"]["route"] == "opus"

    def test_id_generated_when_missing(self, tmp_path: Path) -> None:
        src = tmp_path / "data.jsonl"
        _write_jsonl(
            src,
            [
                {"text": "q1", "tier": "opus", "routes": {"opus": {}}},
                {"text": "q2", "tier": "haiku", "routes": {"haiku": {}}},
            ],
        )
        out = tmp_path / "out.jsonl"
        transform_dataset(str(src), _minimal_mapping_json(), str(out))

        rows = _read_jsonl(out)
        assert rows[0]["id"] == "row-0"
        assert rows[1]["id"] == "row-1"

    def test_existing_id_preserved(self, tmp_path: Path) -> None:
        src = tmp_path / "data.jsonl"
        _write_jsonl(
            src,
            [{"my_id": "abc-1", "text": "hello", "tier": "opus", "routes": {}}],
        )
        mapping = {**_minimal_mapping(), "my_id": "id"}
        out = tmp_path / "out.jsonl"
        transform_dataset(str(src), json.dumps(mapping), str(out))

        rows = _read_jsonl(out)
        assert rows[0]["id"] == "abc-1"
        # Should not have auto-generated id since mapping covers it
        assert rows[0]["id"] != "row-0"

    def test_unmapped_fields_dropped(self, tmp_path: Path) -> None:
        src = tmp_path / "data.jsonl"
        _write_jsonl(
            src,
            [{"text": "q", "tier": "opus", "routes": {}, "extra": "dropped_value"}],
        )
        out = tmp_path / "out.jsonl"
        result = transform_dataset(str(src), _minimal_mapping_json(), str(out))

        rows = _read_jsonl(out)
        assert "extra" not in rows[0]
        assert "extra" in result.fields_dropped

    def test_missing_required_target_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "data.jsonl"
        _write_jsonl(src, [{"text": "hello"}])
        # Mapping covers input but not expected.route or expected.routes
        partial_mapping = json.dumps({"text": "input"})
        out = tmp_path / "out.jsonl"
        with pytest.raises(ValueError, match="required target fields"):
            transform_dataset(str(src), partial_mapping, str(out))


# ---------------------------------------------------------------------------
# TestNestedMapping
# ---------------------------------------------------------------------------


class TestNestedMapping:
    def test_nested_source_to_nested_target(self, tmp_path: Path) -> None:
        """Source with nested expected.* fields maps to canonical target."""
        src = tmp_path / "data.json"
        rows = [
            {
                "query": "What is AI?",
                "label": {"route": "opus", "routes": {"opus": {"cost": 0.05, "quality_score": 0.9}}},
            }
        ]
        src.write_text(json.dumps(rows))
        mapping = json.dumps(
            {
                "query": "input",
                "label.route": "expected.route",
                "label.routes": "expected.routes",
            }
        )
        out = tmp_path / "out.jsonl"
        result = transform_dataset(str(src), mapping, str(out))

        assert result.rows_written == 1
        rows_out = _read_jsonl(out)
        assert rows_out[0]["input"] == "What is AI?"
        assert rows_out[0]["expected"]["route"] == "opus"
        assert rows_out[0]["expected"]["routes"]["opus"]["cost"] == 0.05

    def test_object_passthrough_for_routes(self, tmp_path: Path) -> None:
        """An entire routes dict value passes through unchanged."""
        src = tmp_path / "data.jsonl"
        routes = {"opus": {"cost": 0.05, "quality_score": 0.98}, "haiku": {"cost": 0.002, "quality_score": 0.72}}
        _write_jsonl(
            src,
            [{"text": "q", "tier": "opus", "routes": routes}],
        )
        out = tmp_path / "out.jsonl"
        transform_dataset(str(src), _minimal_mapping_json(), str(out))

        rows = _read_jsonl(out)
        assert rows[0]["expected"]["routes"] == routes

    def test_column_expansion_for_routes_csv(self, tmp_path: Path) -> None:
        """Flat CSV columns map to deeply nested expected.routes structure."""
        src = tmp_path / "data.csv"
        src.write_text("text,tier,opus_cost,opus_quality,haiku_cost,haiku_quality\nhello,opus,0.05,0.98,0.002,0.72\n")
        mapping = json.dumps(
            {
                "text": "input",
                "tier": "expected.route",
                "opus_cost": "expected.routes.opus.cost",
                "opus_quality": "expected.routes.opus.quality_score",
                "haiku_cost": "expected.routes.haiku.cost",
                "haiku_quality": "expected.routes.haiku.quality_score",
            }
        )
        out = tmp_path / "out.jsonl"
        transform_dataset(str(src), mapping, str(out))

        rows = _read_jsonl(out)
        row = rows[0]
        assert row["input"] == "hello"
        assert row["expected"]["route"] == "opus"
        # Numeric coercion: CSV strings become floats
        assert row["expected"]["routes"]["opus"]["cost"] == pytest.approx(0.05)
        assert row["expected"]["routes"]["opus"]["quality_score"] == pytest.approx(0.98)
        assert row["expected"]["routes"]["haiku"]["cost"] == pytest.approx(0.002)
        assert row["expected"]["routes"]["haiku"]["quality_score"] == pytest.approx(0.72)

    def test_overwrite_existing_output(self, tmp_path: Path) -> None:
        """transform_dataset overwrites an existing output file."""
        src = tmp_path / "data.jsonl"
        _write_jsonl(src, [{"text": "q", "tier": "opus", "routes": {}}])
        out = tmp_path / "out.jsonl"
        out.write_text("stale content\n")

        transform_dataset(str(src), _minimal_mapping_json(), str(out))

        rows = _read_jsonl(out)
        assert len(rows) == 1
        assert rows[0]["input"] == "q"


# ---------------------------------------------------------------------------
# TestNumericCoercion
# ---------------------------------------------------------------------------


class TestNumericCoercion:
    def test_string_float_coerced(self) -> None:
        assert _maybe_coerce_numeric("0.05") == pytest.approx(0.05)
        assert isinstance(_maybe_coerce_numeric("0.05"), float)

    def test_string_int_coerced(self) -> None:
        assert _maybe_coerce_numeric("42") == 42
        assert isinstance(_maybe_coerce_numeric("42"), int)

    def test_non_numeric_string_unchanged(self) -> None:
        assert _maybe_coerce_numeric("opus") == "opus"

    def test_non_string_unchanged(self) -> None:
        assert _maybe_coerce_numeric(3.14) == pytest.approx(3.14)
        assert _maybe_coerce_numeric({"key": "val"}) == {"key": "val"}

    def test_set_nested_coerces_from_csv(self, tmp_path: Path) -> None:
        """End-to-end: CSV cost string "0.05" becomes float 0.05 in output."""
        src = tmp_path / "data.csv"
        src.write_text("text,tier,opus_cost,opus_quality,haiku_cost,haiku_quality\nhi,opus,0.05,0.98,0.002,0.72\n")
        mapping = json.dumps(
            {
                "text": "input",
                "tier": "expected.route",
                "opus_cost": "expected.routes.opus.cost",
                "opus_quality": "expected.routes.opus.quality_score",
                "haiku_cost": "expected.routes.haiku.cost",
                "haiku_quality": "expected.routes.haiku.quality_score",
            }
        )
        out = tmp_path / "out.jsonl"
        transform_dataset(str(src), mapping, str(out))

        rows = _read_jsonl(out)
        cost = rows[0]["expected"]["routes"]["opus"]["cost"]
        assert cost == pytest.approx(0.05)
        assert isinstance(cost, float), f"Expected float, got {type(cost)}"


# ---------------------------------------------------------------------------
# TestInternalHelpers
# ---------------------------------------------------------------------------


class TestSetNestedGetNested:
    def test_set_top_level(self) -> None:
        obj: dict = {}
        _set_nested(obj, "key", "value")
        assert obj == {"key": "value"}

    def test_set_two_levels(self) -> None:
        obj: dict = {}
        _set_nested(obj, "a.b", "val")
        assert obj == {"a": {"b": "val"}}

    def test_set_three_levels(self) -> None:
        obj: dict = {}
        _set_nested(obj, "a.b.c", 42)
        assert obj["a"]["b"]["c"] == 42

    def test_get_existing_path(self) -> None:
        obj = {"a": {"b": {"c": "found"}}}
        assert _get_nested(obj, "a.b.c") == "found"

    def test_get_missing_path(self) -> None:
        obj = {"a": {"b": {}}}
        assert _get_nested(obj, "a.b.missing") is None

    def test_get_top_level(self) -> None:
        obj = {"key": "val"}
        assert _get_nested(obj, "key") == "val"


class TestCheckRequiredTargets:
    def test_all_required_covered(self) -> None:
        _check_required_targets(
            {
                "text": "input",
                "tier": "expected.route",
                "routes": "expected.routes",
            }
        )  # should not raise

    def test_child_mapping_satisfies_parent(self) -> None:
        _check_required_targets(
            {
                "text": "input",
                "tier": "expected.route",
                "opus_cost": "expected.routes.opus.cost",
            }
        )  # should not raise

    def test_missing_input_raises(self) -> None:
        with pytest.raises(ValueError, match="required target fields"):
            _check_required_targets(
                {
                    "tier": "expected.route",
                    "routes": "expected.routes",
                }
            )

    def test_missing_expected_route_raises(self) -> None:
        with pytest.raises(ValueError, match="required target fields"):
            _check_required_targets(
                {
                    "text": "input",
                    "routes": "expected.routes",
                }
            )

    def test_missing_expected_routes_raises(self) -> None:
        with pytest.raises(ValueError, match="required target fields"):
            _check_required_targets(
                {
                    "text": "input",
                    "tier": "expected.route",
                }
            )
