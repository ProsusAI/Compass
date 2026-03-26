"""Tests for the User Input agent static context document (THP-69)."""

from pathlib import Path

CONTEXT_PATH = Path(__file__).resolve().parent.parent / "odysseus" / "agents" / "user_input_context.md"


class TestContextFileExists:
    """The context file must exist and be non-empty."""

    def test_file_exists(self) -> None:
        assert CONTEXT_PATH.exists(), f"Expected context file at {CONTEXT_PATH}"

    def test_file_is_not_empty(self) -> None:
        content = CONTEXT_PATH.read_text()
        assert len(content.strip()) > 0


class TestContextWordCount:
    """The context must stay within the target token budget (~500-800 words)."""

    def test_minimum_word_count(self) -> None:
        content = CONTEXT_PATH.read_text()
        word_count = len(content.split())
        assert word_count >= 400, f"Context too short: {word_count} words (minimum 400)"

    def test_maximum_word_count(self) -> None:
        content = CONTEXT_PATH.read_text()
        word_count = len(content.split())
        assert word_count <= 1000, f"Context too long: {word_count} words (maximum 1000)"


class TestContextStructure:
    """The context must contain required sections from the spec."""

    def _load(self) -> str:
        return CONTEXT_PATH.read_text()

    def test_contains_domain_section(self) -> None:
        content = self._load()
        assert "cost-quality routing" in content.lower()

    def test_contains_model_tier_routing(self) -> None:
        content = self._load()
        assert "model" in content.lower() and "tier" in content.lower()

    def test_contains_tool_routing(self) -> None:
        content = self._load()
        assert "tool" in content.lower()

    def test_has_three_sections(self) -> None:
        content = self._load()
        headings = [line for line in content.splitlines() if line.startswith("## ")]
        assert len(headings) >= 3, f"Expected at least 3 sections, found {len(headings)}"

    def test_contains_entry_gate_role(self) -> None:
        content = self._load()
        assert "entry gate" in content.lower()

    def test_contains_downstream_delegation(self) -> None:
        content = self._load()
        assert "downstream" in content.lower()

    def test_contains_data_validation_agent_reference(self) -> None:
        content = self._load()
        assert "data validation" in content.lower()

    def test_contains_routing_dataset_component(self) -> None:
        content = self._load()
        assert "routing dataset" in content.lower() or "routing_dataset" in content.lower()

    def test_contains_problem_description_component(self) -> None:
        content = self._load()
        assert "problem description" in content.lower() or "problem_description" in content.lower()

    def test_contains_target_metrics_component(self) -> None:
        content = self._load()
        assert "target metric" in content.lower() or "target_metrics" in content.lower()

    def test_contains_accuracy_metric(self) -> None:
        content = self._load()
        assert "accuracy" in content.lower()

    def test_contains_f1_metric(self) -> None:
        content = self._load()
        assert "f1" in content.lower()

    def test_contains_confusion_metric(self) -> None:
        content = self._load()
        assert "confusion" in content.lower()

    def test_contains_cost_quality_reduction_metric(self) -> None:
        content = self._load()
        assert "cost_quality_reduction" in content or "cost quality reduction" in content.lower()

    def test_contains_cost_reduction_output_keys(self) -> None:
        content = self._load()
        assert "cost_reduction" in content
        assert "quality_reduction" in content
