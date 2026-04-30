"""Tests for odysseus.agents.review_ops — file-backed persistence operations."""

from __future__ import annotations

from pathlib import Path

from odysseus.agents.review.models import (
    ChildVariant,
    DirectiveOutcome,
    EditDirective,
    ExampleContent,
)
from odysseus.agents.review.ops import (
    load_child_variants,
    load_directive_history,
    load_round_reports,
    save_child_variants,
    save_directive_history,
    save_round_report,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_directive_outcome(directive_id: str, outcome: str = "improved") -> DirectiveOutcome:
    return DirectiveOutcome(
        prior_directive_id=directive_id,
        was_attempted=True,
        outcome=outcome,
    )


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


# ---------------------------------------------------------------------------
# Directive history
# ---------------------------------------------------------------------------


class TestSaveLoadDirectiveHistory:
    def test_roundtrip(self, tmp_path: Path) -> None:
        history = [
            _make_directive_outcome("dir-001", "improved"),
            _make_directive_outcome("dir-002", "no_effect"),
        ]
        save_directive_history("state-abc", history, output_dir=tmp_path)
        loaded = load_directive_history("state-abc", output_dir=tmp_path)

        assert len(loaded) == 2
        assert loaded[0].prior_directive_id == "dir-001"
        assert loaded[0].was_attempted is True
        assert loaded[0].outcome == "improved"
        assert loaded[1].prior_directive_id == "dir-002"
        assert loaded[1].outcome == "no_effect"

    def test_load_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        result = load_directive_history("nonexistent-state", output_dir=tmp_path)
        assert result == []

    def test_overwrite_existing(self, tmp_path: Path) -> None:
        initial = [_make_directive_outcome("dir-001", "improved")]
        save_directive_history("state-xyz", initial, output_dir=tmp_path)

        updated = [
            _make_directive_outcome("dir-001", "regressed"),
            _make_directive_outcome("dir-003", "no_effect"),
        ]
        save_directive_history("state-xyz", updated, output_dir=tmp_path)
        loaded = load_directive_history("state-xyz", output_dir=tmp_path)

        assert len(loaded) == 2
        assert loaded[0].outcome == "regressed"
        assert loaded[1].prior_directive_id == "dir-003"

    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        history = [_make_directive_outcome("dir-001")]
        save_directive_history("state-new", history, output_dir=tmp_path)

        expected_path = tmp_path / "state-new" / "search" / "directive_history.json"
        assert expected_path.exists()

    def test_empty_history_roundtrip(self, tmp_path: Path) -> None:
        save_directive_history("state-empty", [], output_dir=tmp_path)
        loaded = load_directive_history("state-empty", output_dir=tmp_path)
        assert loaded == []


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


class TestSaveLoadRoundReports:
    def test_save_single_round(self, tmp_path: Path) -> None:
        reports = {
            "v2": {"accuracy": 0.85, "cost": 1.2},
        }
        save_round_report("state-abc", 1, reports, output_dir=tmp_path)
        loaded = load_round_reports("state-abc", output_dir=tmp_path)

        assert 1 in loaded
        assert loaded[1]["v2"]["accuracy"] == 0.85

    def test_save_multiple_rounds(self, tmp_path: Path) -> None:
        round1 = {"v2": {"accuracy": 0.80}}
        round2 = {"v3": {"accuracy": 0.85}, "v4": {"accuracy": 0.82}}

        save_round_report("state-abc", 1, round1, output_dir=tmp_path)
        save_round_report("state-abc", 2, round2, output_dir=tmp_path)

        loaded = load_round_reports("state-abc", output_dir=tmp_path)

        assert len(loaded) == 2
        assert 1 in loaded
        assert 2 in loaded
        assert loaded[2]["v3"]["accuracy"] == 0.85
        assert loaded[2]["v4"]["accuracy"] == 0.82

    def test_load_returns_empty_when_no_dir(self, tmp_path: Path) -> None:
        result = load_round_reports("nonexistent-state", output_dir=tmp_path)
        assert result == {}

    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        save_round_report("state-new", 1, {"v2": {}}, output_dir=tmp_path)

        expected_path = tmp_path / "state-new" / "search" / "round_reports" / "round_1.json"
        assert expected_path.exists()

    def test_round_numbers_parsed_correctly(self, tmp_path: Path) -> None:
        save_round_report("state-abc", 5, {"v10": {"score": 0.9}}, output_dir=tmp_path)
        save_round_report("state-abc", 10, {"v11": {"score": 0.91}}, output_dir=tmp_path)

        loaded = load_round_reports("state-abc", output_dir=tmp_path)

        assert 5 in loaded
        assert 10 in loaded
        assert loaded[5]["v10"]["score"] == 0.9

    def test_rounds_returned_in_sorted_order(self, tmp_path: Path) -> None:
        # Save out-of-order to ensure sorting is applied on load
        save_round_report("state-abc", 3, {"v5": {}}, output_dir=tmp_path)
        save_round_report("state-abc", 1, {"v3": {}}, output_dir=tmp_path)
        save_round_report("state-abc", 2, {"v4": {}}, output_dir=tmp_path)

        loaded = load_round_reports("state-abc", output_dir=tmp_path)
        keys = list(loaded.keys())

        assert keys == [1, 2, 3]


# ---------------------------------------------------------------------------
# run_id path tests
# ---------------------------------------------------------------------------


class TestRunIdPaths:
    def test_directive_history_uses_run_id_path(self, tmp_path: Path) -> None:
        outcome = DirectiveOutcome(prior_directive_id="d1", was_attempted=True, outcome="improved")
        save_directive_history("abc12345", [outcome], output_dir=tmp_path)
        assert (tmp_path / "abc12345" / "search" / "directive_history.json").is_file()
        loaded = load_directive_history("abc12345", output_dir=tmp_path)
        assert len(loaded) == 1

    def test_round_report_uses_run_id_path(self, tmp_path: Path) -> None:
        save_round_report("abc12345", 1, {"v1": {"score": 0.8}}, output_dir=tmp_path)
        assert (tmp_path / "abc12345" / "search" / "round_reports" / "round_1.json").is_file()


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
