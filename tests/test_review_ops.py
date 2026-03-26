"""Tests for odysseus.agents.review_ops — file-backed persistence operations."""

from __future__ import annotations

from pathlib import Path

from odysseus.agents.review_models import DirectiveOutcome, MutationRecord
from odysseus.agents.review_ops import (
    load_directive_history,
    load_mutation_log,
    load_round_reports,
    save_directive_history,
    save_mutation_log,
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


def _make_mutation_record(child: str, parent: str) -> MutationRecord:
    return MutationRecord(
        child_version=child,
        parent_version=parent,
        mutation_type="example_swap",
        description=f"Swap example in {child}",
        directive_ids=None,
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
# Mutation log
# ---------------------------------------------------------------------------


class TestSaveLoadMutationLog:
    def test_roundtrip(self, tmp_path: Path) -> None:
        log = [
            _make_mutation_record("v2", "v1"),
            _make_mutation_record("v3", "v1"),
        ]
        save_mutation_log("state-abc", log, output_dir=tmp_path)
        loaded = load_mutation_log("state-abc", output_dir=tmp_path)

        assert len(loaded) == 2
        assert loaded[0].child_version == "v2"
        assert loaded[0].parent_version == "v1"
        assert loaded[0].mutation_type == "example_swap"
        assert loaded[1].child_version == "v3"

    def test_load_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        result = load_mutation_log("nonexistent-state", output_dir=tmp_path)
        assert result == []

    def test_roundtrip_with_directive_ids(self, tmp_path: Path) -> None:
        record = MutationRecord(
            child_version="v4",
            parent_version="v3",
            mutation_type="rule_edit",
            description="Edit rule based on directives",
            directive_ids=["dir-001", "dir-002"],
        )
        save_mutation_log("state-dirs", [record], output_dir=tmp_path)
        loaded = load_mutation_log("state-dirs", output_dir=tmp_path)

        assert len(loaded) == 1
        assert loaded[0].directive_ids == ["dir-001", "dir-002"]

    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        log = [_make_mutation_record("v2", "v1")]
        save_mutation_log("state-new", log, output_dir=tmp_path)

        expected_path = tmp_path / "state-new" / "search" / "mutation_log.json"
        assert expected_path.exists()


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
        outcome = DirectiveOutcome(
            prior_directive_id="d1", was_attempted=True, outcome="improved"
        )
        save_directive_history("abc12345", [outcome], output_dir=tmp_path)
        assert (tmp_path / "abc12345" / "search" / "directive_history.json").is_file()
        loaded = load_directive_history("abc12345", output_dir=tmp_path)
        assert len(loaded) == 1

    def test_round_report_uses_run_id_path(self, tmp_path: Path) -> None:
        save_round_report("abc12345", 1, {"v1": {"score": 0.8}}, output_dir=tmp_path)
        assert (tmp_path / "abc12345" / "search" / "round_reports" / "round_1.json").is_file()
