"""Tests for compass.agents.review_ops — file-backed persistence operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from compass.agents.prompt_builder.search import RoundSummary, SearchState
from compass.agents.review.models import (
    ChildVariant,
    EditDirective,
    ExampleContent,
)
from compass.agents.review.ops import (
    load_child_variants,
    load_historical_eval_reports,
    load_round_reports,
    save_child_variants,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_edit_directive(directive_id: str, version: str = "v1") -> EditDirective:
    return EditDirective(
        directive_id=directive_id,
        target_version=version,
        block_type="rule",
        block_identifier="Rule 1",
        granularity="micro",
        directive="Tighten wording",
        priority="medium",
    )


def _make_child_variant(variant_id: str | None = None) -> ChildVariant:
    return ChildVariant(
        variant_id=variant_id,
        hypothesis="Test hypothesis",
        directives=[_make_edit_directive("d1")],
    )


def _write_round_report_fixture(
    tmp_path: Path,
    run_id: str,
    round_num: int,
    reports: dict[str, dict[str, Any]],
) -> None:
    path = tmp_path / run_id / "search" / "round_reports" / f"round_{round_num}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reports, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Child variants
# ---------------------------------------------------------------------------


class TestSaveLoadChildVariants:
    def test_roundtrip(self, tmp_path: Path) -> None:
        variants = [
            _make_child_variant("cv-0-0"),
            _make_child_variant("cv-0-1"),
        ]
        save_child_variants("state-abc", variants, output_dir=tmp_path)
        loaded = load_child_variants("state-abc", output_dir=tmp_path)

        assert len(loaded) == 2
        assert loaded[0].variant_id == "cv-0-0"
        assert loaded[1].variant_id == "cv-0-1"
        assert loaded[0].hypothesis == "Test hypothesis"

    def test_load_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        result = load_child_variants("nonexistent-state", output_dir=tmp_path)
        assert result == []

    def test_variant_without_id(self, tmp_path: Path) -> None:
        """Variant with variant_id=None round-trips correctly."""
        variant = _make_child_variant(variant_id=None)
        save_child_variants("state-abc", [variant], output_dir=tmp_path)
        loaded = load_child_variants("state-abc", output_dir=tmp_path)
        assert len(loaded) == 1
        assert loaded[0].variant_id is None

    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        save_child_variants("state-new", [_make_child_variant("cv-0-0")], output_dir=tmp_path)
        assert (tmp_path / "state-new" / "search" / "child_variants.json").exists()


# ---------------------------------------------------------------------------
# Round reports
# ---------------------------------------------------------------------------


class TestLoadRoundReports:
    def test_loads_single_round(self, tmp_path: Path) -> None:
        reports = {
            "v2": {"accuracy": 0.85, "cost": 1.2},
        }
        _write_round_report_fixture(tmp_path, "state-abc", 1, reports)
        loaded = load_round_reports("state-abc", output_dir=tmp_path)

        assert 1 in loaded
        assert loaded[1]["v2"]["accuracy"] == 0.85

    def test_loads_multiple_rounds(self, tmp_path: Path) -> None:
        round1 = {"v2": {"accuracy": 0.80}}
        round2 = {"v3": {"accuracy": 0.85}, "v4": {"accuracy": 0.82}}

        _write_round_report_fixture(tmp_path, "state-abc", 1, round1)
        _write_round_report_fixture(tmp_path, "state-abc", 2, round2)

        loaded = load_round_reports("state-abc", output_dir=tmp_path)

        assert len(loaded) == 2
        assert 1 in loaded
        assert 2 in loaded
        assert loaded[2]["v3"]["accuracy"] == 0.85
        assert loaded[2]["v4"]["accuracy"] == 0.82

    def test_load_returns_empty_when_no_dir(self, tmp_path: Path) -> None:
        result = load_round_reports("nonexistent-state", output_dir=tmp_path)
        assert result == {}

    def test_round_numbers_parsed_correctly(self, tmp_path: Path) -> None:
        _write_round_report_fixture(tmp_path, "state-abc", 5, {"v10": {"score": 0.9}})
        _write_round_report_fixture(tmp_path, "state-abc", 10, {"v11": {"score": 0.91}})

        loaded = load_round_reports("state-abc", output_dir=tmp_path)

        assert 5 in loaded
        assert 10 in loaded
        assert loaded[5]["v10"]["score"] == 0.9

    def test_rounds_returned_in_sorted_order(self, tmp_path: Path) -> None:
        # Save out-of-order to ensure sorting is applied on load
        _write_round_report_fixture(tmp_path, "state-abc", 3, {"v5": {}})
        _write_round_report_fixture(tmp_path, "state-abc", 1, {"v3": {}})
        _write_round_report_fixture(tmp_path, "state-abc", 2, {"v4": {}})

        loaded = load_round_reports("state-abc", output_dir=tmp_path)
        keys = list(loaded.keys())

        assert keys == [1, 2, 3]


class TestLoadHistoricalEvalReports:
    @staticmethod
    def _state() -> SearchState:
        return SearchState(
            search_state_id="state-abc",
            backend="anthropic",
            round=3,
            round_history=[
                RoundSummary(round=1, candidates_evaluated=["v1"], new_elite_entries=1, elite_size=1),
                RoundSummary(round=2, candidates_evaluated=["v2", "v3"], new_elite_entries=1, elite_size=2),
            ],
        )

    def test_loads_reports_from_eval_artifacts(self, tmp_path: Path) -> None:
        state = self._state()
        eval_v1 = tmp_path / "state-abc" / "eval" / "v1"
        eval_v2 = tmp_path / "state-abc" / "eval" / "v2"
        eval_v3 = tmp_path / "state-abc" / "eval" / "v3"
        eval_v1.mkdir(parents=True, exist_ok=True)
        eval_v2.mkdir(parents=True, exist_ok=True)
        eval_v3.mkdir(parents=True, exist_ok=True)
        (eval_v1 / "report.json").write_text(json.dumps({"metrics": {"accuracy": 0.8}}), encoding="utf-8")
        (eval_v2 / "report.json").write_text(json.dumps({"metrics": {"accuracy": 0.9}}), encoding="utf-8")
        (eval_v3 / "report.json").write_text(json.dumps({"metrics": {"accuracy": 0.7}}), encoding="utf-8")

        loaded = load_historical_eval_reports("state-abc", state, output_dir=tmp_path)

        assert loaded[1]["v1"]["metrics"]["accuracy"] == 0.8
        assert loaded[2]["v2"]["metrics"]["accuracy"] == 0.9
        assert loaded[2]["v3"]["metrics"]["accuracy"] == 0.7

    def test_falls_back_to_legacy_round_reports_when_eval_missing(self, tmp_path: Path) -> None:
        state = self._state()
        eval_v1 = tmp_path / "state-abc" / "eval" / "v1"
        eval_v1.mkdir(parents=True, exist_ok=True)
        (eval_v1 / "report.json").write_text(json.dumps({"metrics": {"accuracy": 0.8}}), encoding="utf-8")
        _write_round_report_fixture(tmp_path, "state-abc", 2, {"v2": {"metrics": {"accuracy": 0.9}}})

        loaded = load_historical_eval_reports("state-abc", state, output_dir=tmp_path)

        assert loaded[1]["v1"]["metrics"]["accuracy"] == 0.8
        assert loaded[2]["v2"]["metrics"]["accuracy"] == 0.9


# ---------------------------------------------------------------------------
# Edit directives
# ---------------------------------------------------------------------------


class TestSaveLoadChildVariantsDirectives:
    """Round-trip tests for child variant directive persistence (replaces flat edit_directives tests)."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        variant = ChildVariant(
            hypothesis="Test hypothesis",
            directives=[
                EditDirective(
                    directive_id="d1",
                    target_version="v1",
                    block_type="rule",
                    block_identifier="Rule 1",
                    granularity="micro",
                    directive="Tighten wording",
                    priority="medium",
                ),
            ],
        )
        save_child_variants("run-abc", [variant], output_dir=tmp_path)
        loaded = load_child_variants("run-abc", output_dir=tmp_path)
        assert len(loaded) == 1
        assert loaded[0].directives[0].directive_id == "d1"
        assert loaded[0].directives[0].block_type == "rule"

    def test_load_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        assert load_child_variants("nonexistent", output_dir=tmp_path) == []

    def test_with_example_content(self, tmp_path: Path) -> None:
        variant = ChildVariant(
            hypothesis="Add boundary example",
            directives=[
                EditDirective(
                    directive_id="d2",
                    target_version="v1",
                    block_type="example",
                    block_identifier="Example 1",
                    granularity="macro",
                    directive="Add boundary example",
                    priority="high",
                    example_content=ExampleContent(
                        example_id="ex42",
                        input="test input",
                        route="route_a",
                        reasoning="test reasoning",
                        exclusions=[{"route": "route_b", "reason": "not applicable"}],
                    ),
                ),
            ],
        )
        save_child_variants("run-abc", [variant], output_dir=tmp_path)
        loaded = load_child_variants("run-abc", output_dir=tmp_path)
        assert loaded[0].directives[0].example_content is not None
        assert loaded[0].directives[0].example_content.example_id == "ex42"
        assert loaded[0].directives[0].example_content.route == "route_a"

    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        save_child_variants("run-new", [], output_dir=tmp_path)
        assert (tmp_path / "run-new" / "search" / "child_variants.json").exists()
