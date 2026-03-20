# THP-69: User Input Agent Static Context — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the static domain knowledge document that the User Input agent loads as part of its system prompt — covering cost-quality routing domain, agent role, problem specification, and available metrics.

**Architecture:** A single markdown file at `odysseus/agents/user_input_context.md` containing ~500–800 words of structured prose. This is not loaded via `FilePromptManager` (which only handles `.yaml`/`.yml`/`.txt` in `prompts/`); instead, THP-107 will embed it directly into the system prompt. Tested via a dedicated test module that validates the file exists, stays within word count, and contains required structural elements.

**Tech Stack:** Python, pytest

**Spec:** `docs/superpowers/specs/2026-03-20-thp69-user-input-static-context-design.md`

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `odysseus/agents/user_input_context.md` | Static domain knowledge context for User Input agent |
| Create | `tests/test_user_input_context.py` | Tests that the context file exists, is within bounds, and contains required sections |

---

## Chunk 1: Tests and Context Document

### Task 1: Write failing tests for the context file

**Files:**
- Create: `tests/test_user_input_context.py`

- [ ] **Step 1: Write the failing tests**

```python
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

    def test_contains_orchestrator_role(self) -> None:
        content = self._load()
        assert "orchestrat" in content.lower()

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_user_input_context.py -v`
Expected: FAIL — `user_input_context.md` does not exist yet

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_user_input_context.py
git commit -m "test(thp-69): add failing tests for user input static context"
```

---

### Task 2: Write the static context document

**Files:**
- Create: `odysseus/agents/user_input_context.md`

- [ ] **Step 4: Write the context document**

Write the markdown file following the spec's 3-section structure. Start with an H1 title (e.g. `# User Input Agent — Domain Context`) followed by 3 sections using H2 headings. The content must:

**Section 1 — Domain & Role (~150-250 words):**
- Define cost-quality routing: routing requests to LLM model tiers (e.g. Haiku/Sonnet/Opus) or tools (e.g. different websearch tools, image models) that produce the same type of output but differ in cost and quality
- Goal: route each request to the cheapest option that meets quality requirements
- Agent role: pipeline entry gate AND orchestrator
- Dispatches the Data Validation agent for dataset quality assessment; incorporates its findings into the gap report and may surface data issues as blocking gaps requiring user action
- Works iteratively with the user until problem definition and data are sufficient

**Section 2 — Complete Problem Specification (~100-150 words):**
- Required: routing dataset (JSONL with input + expected routing decision), problem description (free-text), target metrics (at least one)
- Optional: evaluation threshold, data split ratio, max iterations (defaults exist via THP-71 if omitted)
- Descriptive only — do not specify validation rules

**Section 3 — Available Metrics (~250-400 words):**
- **accuracy** — fraction of correct route predictions. Simple, interpretable. Doesn't distinguish misrouting types. Optimization target: yes (e.g. `accuracy >= 0.85`).
- **f1** — per-class precision/recall/F1 + macro F1. Use when classes are imbalanced. Optimization target: yes, typically `f1/macro` (e.g. `f1/macro >= 0.80`).
- **confusion** — full confusion matrix. Diagnostic only, not an optimization target. Shows which classes get misrouted where.
- **cost_quality_reduction** — % change in cost and quality vs. baseline tier. 4 output keys: `cost_reduction`, `quality_reduction`, `oracle_cost_reduction`, `oracle_quality_reduction`. Negative values = savings/loss. Explain sign convention clearly. Optional `baseline_class` parameter (auto-selects highest-quality class). Optimization target: yes (e.g. `cost_reduction <= -0.30`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_user_input_context.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit the context document**

```bash
git add odysseus/agents/user_input_context.md
git commit -m "feat(thp-69): add user input agent static context document"
```

---

### Task 3: Final verification

- [ ] **Step 7: Run the full test suite**

Run: `uv run pytest -v`
Expected: All existing tests + new context tests PASS

- [ ] **Step 8: Run linter and type checker**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: No errors

- [ ] **Step 9: Final commit (if any lint fixes needed)**

```bash
git add -u
git commit -m "style(thp-69): fix lint issues"
```
