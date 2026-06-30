"""Tests for the User Input agent defaults table (THP-71)."""

from pathlib import Path

DEFAULTS_PATH = Path(__file__).resolve().parent.parent / "odysseus" / "agents" / "user_input" / "defaults.md"
TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "odysseus" / "agents" / "user_input" / "taxonomy.md"


class TestDefaultsFileExists:
    """The defaults file must exist and be non-empty."""

    def test_file_exists(self) -> None:
        assert DEFAULTS_PATH.exists(), f"Expected defaults file at {DEFAULTS_PATH}"

    def test_file_is_not_empty(self) -> None:
        content = DEFAULTS_PATH.read_text()
        assert len(content.strip()) > 0


class TestDefaultsCoversNonBlockingFields:
    """Every non-blocking field from the taxonomy must appear in the defaults table."""

    def _get_non_blocking_fields(self) -> list[str]:
        """Extract non-blocking field names from the taxonomy file."""
        content = TAXONOMY_PATH.read_text()
        fields = []
        for line in content.splitlines():
            if "| Non-blocking |" in line or "| non-blocking |" in line.lower():
                # Field name is in the first column: | `field_name` | ...
                parts = line.split("|")
                if len(parts) >= 2:
                    field = parts[1].strip().strip("`")
                    if field:
                        fields.append(field)
        return fields

    def test_all_non_blocking_fields_present(self) -> None:
        fields = self._get_non_blocking_fields()
        assert len(fields) > 0, "Could not parse non-blocking fields from taxonomy"
        content = DEFAULTS_PATH.read_text()
        for field in fields:
            assert f"`{field}`" in content, f"Non-blocking field '{field}' not found in defaults table"


class TestDefaultsStructure:
    """The defaults file must contain the required structural elements."""

    def test_has_defaults_table(self) -> None:
        content = DEFAULTS_PATH.read_text()
        assert "Default value" in content or "Default Value" in content, "Missing defaults table header"

    def test_has_rationale_column(self) -> None:
        content = DEFAULTS_PATH.read_text()
        assert "Rationale" in content, "Missing Rationale column"

    def test_has_user_facing_note_column(self) -> None:
        content = DEFAULTS_PATH.read_text()
        assert "User-facing note" in content or "User-Facing Note" in content, "Missing User-facing note column"

    def test_has_override_mechanism(self) -> None:
        content = DEFAULTS_PATH.read_text()
        assert "override" in content.lower(), "Missing override mechanism documentation"

    def test_has_propagation_section(self) -> None:
        content = DEFAULTS_PATH.read_text()
        assert "propagation" in content.lower() or "downstream" in content.lower(), "Missing propagation documentation"


class TestDefaultValues:
    """Verify the specific default values match the taxonomy."""

    def test_target_metrics_defaults_to_f1(self) -> None:
        content = DEFAULTS_PATH.read_text()
        # Must mention f1 as the default for target_metrics (not accuracy — per THP-108 design decision)
        assert "f1" in content.lower(), "target_metrics should default to F1 (per THP-108 design decision)"

    def test_evaluation_threshold_is_080(self) -> None:
        content = DEFAULTS_PATH.read_text()
        assert "0.80" in content, "evaluation_threshold should default to 0.80"

    def test_data_split_ratio_is_080(self) -> None:
        content = DEFAULTS_PATH.read_text()
        assert "0.80" in content, "data_split_ratio should default to 0.80"

    def test_max_iterations_is_10(self) -> None:
        content = DEFAULTS_PATH.read_text()
        # Check for "10" appearing near max_iterations context
        assert "`10`" in content or "| 10 |" in content or "10 refinement" in content, (
            "max_iterations should default to 10"
        )
