"""Tests for odysseus.agents.data_ingestion_transform."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odysseus.agents.data_validation.transform import (
    TransformResult,
    _check_required_targets,
    _get_nested,
    _maybe_coerce_numeric,
    _set_nested,
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
    return {"opus": {"cost": 0.05, "quality_score": 0.9}}


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
