"""Tests for the EvalRunnerAgent system prompt."""

from pathlib import Path

import pytest

from odysseus.eval.models import ScoreReport
from odysseus.prompts.manager import FilePromptManager

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@pytest.fixture
def prompt_manager() -> FilePromptManager:
    """Create a FilePromptManager pointing at the real prompts directory."""
    return FilePromptManager(PROMPTS_DIR)


class TestEvalRunnerPromptExists:
    """The prompt file must exist and be loadable."""

    def test_prompt_file_exists(self) -> None:
        path = PROMPTS_DIR / "eval_runner_system.txt"
        assert path.exists(), f"Expected prompt file at {path}"

    def test_prompt_loads_via_manager(self, prompt_manager: FilePromptManager) -> None:
        prompt = prompt_manager.load("eval_runner_system")
        assert isinstance(prompt, str)
        assert len(prompt) > 0


class TestEvalRunnerPromptContent:
    """The prompt must contain required structural elements from the spec."""

    @pytest.fixture(autouse=True)
    def _load_prompt(self, prompt_manager: FilePromptManager) -> None:
        self.prompt = prompt_manager.load("eval_runner_system")

    def test_contains_role_definition(self) -> None:
        assert "Eval Runner" in self.prompt

    def test_contains_no_interpret_guideline(self) -> None:
        assert "do not interpret" in self.prompt.lower()

    def test_contains_run_eval_tool_reference(self) -> None:
        assert "run_eval" in self.prompt

    def test_contains_prompt_version_param(self) -> None:
        assert "prompt_version" in self.prompt

    def test_contains_data_source_param(self) -> None:
        assert "data_source" in self.prompt

    def test_forbids_holdout(self) -> None:
        assert "holdout" in self.prompt.lower()

    def test_contains_eval_status_field(self) -> None:
        assert "eval_status" in self.prompt

    def test_contains_success_status(self) -> None:
        assert '"success"' in self.prompt or "'success'" in self.prompt

    def test_contains_error_status(self) -> None:
        assert '"error"' in self.prompt or "'error'" in self.prompt

    def test_contains_score_report_context_key(self) -> None:
        assert ScoreReport.CONTEXT_KEY in self.prompt

    def test_contains_eval_error_key(self) -> None:
        assert "eval_error" in self.prompt

    def test_contains_error_types(self) -> None:
        for error_type in ["missing_input", "tool_failure", "timeout"]:
            assert error_type in self.prompt, f"Missing error type: {error_type}"

    def test_contains_retry_guidance(self) -> None:
        assert "retry" in self.prompt.lower()

    def test_contains_retry_cap(self) -> None:
        assert "2 additional attempts" in self.prompt
