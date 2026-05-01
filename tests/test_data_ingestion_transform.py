"""Tests for odysseus.agents.data_ingestion_transform."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odysseus.agents.data_validation.transform import (
    TransformResult,
    _check_required_targets,
    _get_nested,
    _get_nested_wildcard,
    _maybe_coerce_numeric,
    _set_nested,
    _set_nested_wildcard,
    transform_dataset,
)


class TestTransformResult:
    def test_minimal(self) -> None:
        r = TransformResult(
            output_path="/tmp/out.jsonl",
            original_dataset_path="/tmp/in.csv",
            rows_written=3,
            fields_mapped={"a": "input"},
            fields_dropped=["b"],
        )
        assert r.rows_written == 3
        assert r.original_dataset_path == "/tmp/in.csv"


class TestMaybeCoerceNumeric:
    def test_float_string(self) -> None:
        assert _maybe_coerce_numeric("0.05") == 0.05

    def test_int_string(self) -> None:
        assert _maybe_coerce_numeric("42") == 42

    def test_non_numeric_string(self) -> None:
        assert _maybe_coerce_numeric("hello") == "hello"

    def test_already_numeric(self) -> None:
        assert _maybe_coerce_numeric(3.14) == 3.14

    def test_none_passthrough(self) -> None:
        assert _maybe_coerce_numeric(None) is None

    def test_dict_passthrough(self) -> None:
        d = {"a": 1}
        assert _maybe_coerce_numeric(d) is d


class TestSetNestedGetNested:
    def test_set_flat(self) -> None:
        obj: dict = {}
        _set_nested(obj, "input", "hello")
        assert obj == {"input": "hello"}

    def test_set_nested_creates_intermediates(self) -> None:
        obj: dict = {}
        _set_nested(obj, "expected.route", "opus")
        assert obj == {"expected": {"route": "opus"}}

    def test_set_deeply_nested(self) -> None:
        obj: dict = {}
        _set_nested(obj, "expected.routes.opus.cost", "0.05")
        assert obj["expected"]["routes"]["opus"]["cost"] == 0.05

    def test_get_flat(self) -> None:
        assert _get_nested({"input": "hi"}, "input") == "hi"

    def test_get_nested(self) -> None:
        obj = {"expected": {"route": "opus"}}
        assert _get_nested(obj, "expected.route") == "opus"

    def test_get_missing_returns_none(self) -> None:
        assert _get_nested({"a": 1}, "b") is None

    def test_get_nested_missing_intermediate(self) -> None:
        assert _get_nested({"a": 1}, "a.b") is None


class TestCheckRequiredTargets:
    def test_all_present(self) -> None:
        _check_required_targets({"a": "input", "b": "expected.route", "c": "expected.routes"})

    def test_child_satisfies_parent(self) -> None:
        _check_required_targets(
            {
                "a": "input",
                "b": "expected.route",
                "c": "expected.routes.opus.cost",
            }
        )

    def test_missing_input(self) -> None:
        with pytest.raises(ValueError, match="input"):
            _check_required_targets({"b": "expected.route", "c": "expected.routes"})

    def test_missing_route(self) -> None:
        with pytest.raises(ValueError, match="expected.route"):
            _check_required_targets({"a": "input", "c": "expected.routes"})

    def test_missing_routes(self) -> None:
        with pytest.raises(ValueError, match="expected.routes"):
            _check_required_targets({"a": "input", "b": "expected.route"})


def _routes_obj() -> dict:
    return {
        "opus": {"cost": 0.05, "quality_score": 0.9},
        "haiku": {"cost": 0.001, "quality_score": 0.7},
    }


class TestFlatToFlat:
    def test_simple_rename(self, tmp_path: Path) -> None:
        src = tmp_path / "source.jsonl"
        src.write_text(
            json.dumps({"prompt": "hello", "tier": "opus", "routes": _routes_obj()})
            + "\n"
            + json.dumps({"prompt": "world", "tier": "haiku", "routes": _routes_obj()})
            + "\n"
        )
        out = tmp_path / "transformed.jsonl"
        mapping = {"prompt": "input", "tier": "expected.route", "routes": "expected.routes"}
        result = transform_dataset(str(src), json.dumps(mapping), str(out))
        assert result.rows_written == 2
        lines = out.read_text().strip().splitlines()
        row0 = json.loads(lines[0])
        assert row0["input"] == "hello"
        assert row0["expected"]["route"] == "opus"
        assert row0["expected"]["routes"]["opus"]["cost"] == 0.05

    def test_id_generated_when_missing(self, tmp_path: Path) -> None:
        src = tmp_path / "source.jsonl"
        src.write_text(json.dumps({"prompt": "hi", "tier": "opus", "routes": _routes_obj()}) + "\n")
        out = tmp_path / "transformed.jsonl"
        mapping = {"prompt": "input", "tier": "expected.route", "routes": "expected.routes"}
        transform_dataset(str(src), json.dumps(mapping), str(out))
        row = json.loads(out.read_text().strip().splitlines()[0])
        assert row["id"] == "row-0"

    def test_existing_id_preserved(self, tmp_path: Path) -> None:
        src = tmp_path / "source.jsonl"
        src.write_text(
            json.dumps(
                {
                    "my_id": "abc",
                    "prompt": "hi",
                    "tier": "opus",
                    "routes": _routes_obj(),
                }
            )
            + "\n"
        )
        out = tmp_path / "transformed.jsonl"
        mapping = {
            "my_id": "id",
            "prompt": "input",
            "tier": "expected.route",
            "routes": "expected.routes",
        }
        transform_dataset(str(src), json.dumps(mapping), str(out))
        row = json.loads(out.read_text().strip().splitlines()[0])
        assert row["id"] == "abc"

    def test_unmapped_fields_dropped(self, tmp_path: Path) -> None:
        src = tmp_path / "source.jsonl"
        src.write_text(
            json.dumps(
                {
                    "prompt": "hi",
                    "tier": "opus",
                    "routes": _routes_obj(),
                    "extra": "ignored",
                }
            )
            + "\n"
        )
        out = tmp_path / "transformed.jsonl"
        mapping = {"prompt": "input", "tier": "expected.route", "routes": "expected.routes"}
        result = transform_dataset(str(src), json.dumps(mapping), str(out))
        assert "extra" in result.fields_dropped
        row = json.loads(out.read_text().strip().splitlines()[0])
        assert "extra" not in row

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "source.jsonl"
        src.write_text('{"prompt": "hi"}\n')
        out = tmp_path / "transformed.jsonl"
        mapping = {"prompt": "input"}
        with pytest.raises(ValueError, match="required target fields"):
            transform_dataset(str(src), json.dumps(mapping), str(out))

    def test_auto_generate_mapping_key_still_generates_id(self, tmp_path: Path) -> None:
        """When mapping has _auto_generate -> id but source lacks that field, id is still generated."""
        src = tmp_path / "source.jsonl"
        src.write_text(json.dumps({"prompt": "hi", "tier": "opus", "routes": _routes_obj()}) + "\n")
        out = tmp_path / "transformed.jsonl"
        mapping = {
            "_auto_generate": "id",
            "prompt": "input",
            "tier": "expected.route",
            "routes": "expected.routes",
        }
        transform_dataset(str(src), json.dumps(mapping), str(out))
        row = json.loads(out.read_text().strip().splitlines()[0])
        assert row["id"] == "row-0"

    def test_missing_source_field_logs_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Mapping key not in source data logs a warning on first row."""
        import logging

        src = tmp_path / "source.jsonl"
        src.write_text(json.dumps({"prompt": "hi", "tier": "opus", "routes": _routes_obj()}) + "\n")
        out = tmp_path / "transformed.jsonl"
        mapping = {
            "_auto_generate": "id",
            "prompt": "input",
            "tier": "expected.route",
            "routes": "expected.routes",
        }
        with caplog.at_level(logging.WARNING):
            transform_dataset(str(src), json.dumps(mapping), str(out))
        assert "_auto_generate" in caplog.text


class TestNestedMapping:
    def test_nested_source_to_nested_target(self, tmp_path: Path) -> None:
        src = tmp_path / "source.jsonl"
        src.write_text(
            json.dumps(
                {
                    "result": {"tier": "opus"},
                    "text": "hi",
                    "models": {"opus": {"cost": 0.05, "quality_score": 0.9}},
                }
            )
            + "\n"
        )
        out = tmp_path / "transformed.jsonl"
        mapping = {"text": "input", "result.tier": "expected.route", "models": "expected.routes"}
        transform_dataset(str(src), json.dumps(mapping), str(out))
        row = json.loads(out.read_text().strip().splitlines()[0])
        assert row["expected"]["route"] == "opus"

    def test_object_passthrough_for_routes(self, tmp_path: Path) -> None:
        routes = {
            "opus": {"cost": 0.05, "quality_score": 0.98},
            "haiku": {"cost": 0.002, "quality_score": 0.72},
        }
        src = tmp_path / "source.jsonl"
        src.write_text(json.dumps({"text": "hi", "tier": "opus", "models": routes}) + "\n")
        out = tmp_path / "transformed.jsonl"
        mapping = {"text": "input", "tier": "expected.route", "models": "expected.routes"}
        transform_dataset(str(src), json.dumps(mapping), str(out))
        row = json.loads(out.read_text().strip().splitlines()[0])
        assert row["expected"]["routes"] == routes

    def test_column_expansion_for_routes(self, tmp_path: Path) -> None:
        src = tmp_path / "source.csv"
        src.write_text("text,tier,opus_cost,opus_quality,haiku_cost,haiku_quality\nhi,opus,0.05,0.98,0.002,0.72\n")
        out = tmp_path / "transformed.jsonl"
        mapping = {
            "text": "input",
            "tier": "expected.route",
            "opus_cost": "expected.routes.opus.cost",
            "opus_quality": "expected.routes.opus.quality_score",
            "haiku_cost": "expected.routes.haiku.cost",
            "haiku_quality": "expected.routes.haiku.quality_score",
        }
        transform_dataset(str(src), json.dumps(mapping), str(out))
        row = json.loads(out.read_text().strip().splitlines()[0])
        assert row["expected"]["routes"]["opus"]["cost"] == 0.05
        assert row["expected"]["routes"]["haiku"]["quality_score"] == 0.72

    def test_overwrite_existing_output(self, tmp_path: Path) -> None:
        out = tmp_path / "transformed.jsonl"
        out.write_text("old content\n")
        src = tmp_path / "source.jsonl"
        src.write_text(json.dumps({"text": "hi", "tier": "opus", "routes": _routes_obj()}) + "\n")
        mapping = {"text": "input", "tier": "expected.route", "routes": "expected.routes"}
        transform_dataset(str(src), json.dumps(mapping), str(out))
        assert "old content" not in out.read_text()


class TestGetNestedWildcard:
    def test_single_wildcard(self) -> None:
        obj = {"tier_details": {"simple": {"score": 0.87}, "complex": {"score": 0.94}}}
        results = _get_nested_wildcard(obj, "tier_details.*.score")
        keys_and_vals = {tuple(ks): v for ks, v in results}
        assert keys_and_vals[("simple",)] == 0.87
        assert keys_and_vals[("complex",)] == 0.94

    def test_no_wildcard_delegates(self) -> None:
        obj = {"a": {"b": 42}}
        results = _get_nested_wildcard(obj, "a.b")
        assert len(results) == 1
        assert results[0] == ([], 42)

    def test_missing_path_returns_empty(self) -> None:
        obj = {"a": 1}
        results = _get_nested_wildcard(obj, "b.*.c")
        assert results == []

    def test_multiple_wildcards(self) -> None:
        obj = {"a": {"x": {"p": 1, "q": 2}, "y": {"p": 3}}}
        results = _get_nested_wildcard(obj, "a.*.*")
        keys_and_vals = {tuple(ks): v for ks, v in results}
        assert keys_and_vals[("x", "p")] == 1
        assert keys_and_vals[("x", "q")] == 2
        assert keys_and_vals[("y", "p")] == 3


class TestSetNestedWildcard:
    def test_single_wildcard(self) -> None:
        obj: dict = {"routes": {"simple": {}, "complex": {}}}
        _set_nested_wildcard(obj, "routes.*.quality_score", ["simple"], 0.87)
        assert obj["routes"]["simple"]["quality_score"] == 0.87

    def test_creates_intermediates(self) -> None:
        obj: dict = {}
        _set_nested_wildcard(obj, "expected.routes.*.cost", ["opus"], 0.05)
        assert obj["expected"]["routes"]["opus"]["cost"] == 0.05


class TestWildcardTransform:
    def test_wildcard_mapping_resolves_fields(self, tmp_path: Path) -> None:
        """Wildcard mapping renames nested fields across all keys."""
        src = tmp_path / "source.jsonl"
        src.write_text(
            json.dumps(
                {
                    "text": "hello",
                    "tier": "simple",
                    "routes": {
                        "simple": {"score": 0.87, "cost_usd": 0.02},
                        "complex": {"score": 0.94, "cost_usd": 0.11},
                    },
                }
            )
            + "\n"
        )
        out = tmp_path / "transformed.jsonl"
        mapping = {
            "text": "input",
            "tier": "expected.route",
            "routes": "expected.routes",
            "routes.*.score": "expected.routes.*.quality_score",
            "routes.*.cost_usd": "expected.routes.*.cost",
        }
        transform_dataset(str(src), json.dumps(mapping), str(out))
        row = json.loads(out.read_text().strip().splitlines()[0])
        assert row["expected"]["routes"]["simple"]["quality_score"] == 0.87
        assert row["expected"]["routes"]["simple"]["cost"] == 0.02
        assert row["expected"]["routes"]["complex"]["quality_score"] == 0.94
        assert row["expected"]["routes"]["complex"]["cost"] == 0.11


class TestRouteInRoutesInvariant:
    """expected.route must be a key of expected.routes after the mapping is applied."""

    def test_misaligned_route_label_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "source.jsonl"
        src.write_text(
            json.dumps(
                {
                    "text": "hello",
                    "label": "simple",
                    "tier_details": {
                        "0_simple": {"score": 0.87, "cost_usd": 0.02},
                        "1_complex": {"score": 0.94, "cost_usd": 0.11},
                    },
                }
            )
            + "\n"
        )
        out = tmp_path / "transformed.jsonl"
        mapping = {
            "text": "input",
            "label": "expected.route",
            "tier_details": "expected.routes",
            "tier_details.*.score": "expected.routes.*.quality_score",
            "tier_details.*.cost_usd": "expected.routes.*.cost",
        }
        with pytest.raises(ValueError, match="expected.route is not a key of expected.routes"):
            transform_dataset(str(src), json.dumps(mapping), str(out))
        assert not out.exists()

    def test_aligned_route_label_passes(self, tmp_path: Path) -> None:
        src = tmp_path / "source.jsonl"
        src.write_text(
            json.dumps(
                {
                    "text": "hello",
                    "label": "0_simple",
                    "tier_details": {
                        "0_simple": {"score": 0.87, "cost_usd": 0.02},
                        "1_complex": {"score": 0.94, "cost_usd": 0.11},
                    },
                }
            )
            + "\n"
        )
        out = tmp_path / "transformed.jsonl"
        mapping = {
            "text": "input",
            "label": "expected.route",
            "tier_details": "expected.routes",
            "tier_details.*.score": "expected.routes.*.quality_score",
            "tier_details.*.cost_usd": "expected.routes.*.cost",
        }
        transform_dataset(str(src), json.dumps(mapping), str(out))
        row = json.loads(out.read_text().strip().splitlines()[0])
        assert row["expected"]["route"] == "0_simple"
        assert "0_simple" in row["expected"]["routes"]
