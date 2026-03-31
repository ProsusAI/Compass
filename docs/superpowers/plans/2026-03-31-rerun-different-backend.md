# Rerun with Different Backend — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "rerun with different backend" pipeline mode that re-evaluates a converged prompt against a new backend without re-running the full optimization loop.

**Architecture:** A new `rerun_config.json` file in `outputs/<run_id>/` drives conditional stage behavior throughout `status.py`. `_check_stage_3` becomes rerun-aware (checks a specific backend instead of any-with-pricing). `_next_action_for_stage_4` short-circuits the three-phase logic when a rerun config is present. A new `initiate_rerun` MCP tool writes the config and resets Stage 4's search state. A new `prompt_builder_rerun_system.md` system prompt guides a restructure-only Prompt Builder sub-agent that runs exactly one eval round.

**Tech Stack:** Python 3.11+, `pydantic`, `pytest`, `ruff`

---

## Chunk 1: Rerun config helpers and Stage 4 rerun instruction template

### Task 1: `_read_rerun_config` helper and `_STAGE_4_RERUN_INSTRUCTION` template

**Files:**
- Modify: `odysseus/agents/pipeline/status.py:31-64` (add constant after `_STAGE_4_BUILD_INSTRUCTION`)
- Modify: `odysseus/agents/pipeline/status.py:322-356` (add `_read_rerun_config` helper)
- Test: `tests/test_pipeline_status.py`

- [ ] **Step 1: Write failing tests for `_read_rerun_config`**

Add this class to `tests/test_pipeline_status.py` (after the existing imports, before `class TestDiscoverRuns`):

```python
from odysseus.agents.pipeline.status import _read_rerun_config


class TestReadRerunConfig:
    def test_returns_none_when_no_file(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        assert _read_rerun_config(run_dir) is None

    def test_returns_dict_when_file_exists(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        config = {
            "mode": "rerun",
            "source_prompt_version": "v3",
            "original_backend": "anthropic",
            "new_backend": None,
        }
        (run_dir / "rerun_config.json").write_text(json.dumps(config))
        result = _read_rerun_config(run_dir)
        assert result is not None
        assert result["source_prompt_version"] == "v3"
        assert result["new_backend"] is None

    def test_returns_none_on_malformed_json(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        (run_dir / "rerun_config.json").write_text("not valid json {")
        assert _read_rerun_config(run_dir) is None
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_pipeline_status.py::TestReadRerunConfig -v
```

Expected: `ImportError` or `AttributeError` — `_read_rerun_config` does not exist yet.

- [ ] **Step 3: Add `_STAGE_4_RERUN_INSTRUCTION` constant and `_read_rerun_config` helper to `status.py`**

In `odysseus/agents/pipeline/status.py`, add after `_STAGE_4_BUILD_INSTRUCTION` (after line 64):

```python
_STAGE_4_RERUN_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, "
    "init_search_state_tool, register_candidate_tool, record_eval_result_tool, "
    "advance_round_tool, run_eval\n"
    "Your tools: get_pipeline_status only\n\n"
    "NOTE: This is a rerun — the Prompt Builder Rerun agent will restructure the existing prompt "
    "for the new backend. Source prompt version: '{source_prompt_version}'. "
    "New backend: '{new_backend}'.\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)
```

Then add this helper at the end of the module (after `_next_action_for_stage`, before the final blank line):

```python
def _read_rerun_config(run_dir: Path) -> dict | None:
    """Read rerun_config.json from run_dir, returning None if absent or malformed."""
    config_path = run_dir / "rerun_config.json"
    if not config_path.is_file():
        return None
    try:
        return json.loads(config_path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return None
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_pipeline_status.py::TestReadRerunConfig -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Run full test suite and linter to confirm no regressions**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_pipeline_status.py -v && uv run ruff check odysseus/agents/pipeline/status.py
```

Expected: all existing tests PASS, no lint errors.

- [ ] **Step 6: Commit**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && git add odysseus/agents/pipeline/status.py tests/test_pipeline_status.py && git commit -m "feat: add _read_rerun_config helper and _STAGE_4_RERUN_INSTRUCTION template"
```

---

## Chunk 2: Rerun-aware Stage 3 guard

### Task 2: `_check_stage_3` signature change and rerun-mode logic

**Files:**
- Modify: `odysseus/agents/pipeline/status.py:326-356` (`_check_stage` dispatcher, line 339)
- Modify: `odysseus/agents/pipeline/status.py:378-407` (`_check_stage_3` implementation)
- Test: `tests/test_pipeline_status.py`

- [ ] **Step 1: Write failing tests for rerun-aware Stage 3**

Add this class to `tests/test_pipeline_status.py` (after `TestStage3PricingValidation`):

```python
class TestStage3RerunMode:
    """Stage 3 in rerun mode: checks specific new_backend instead of any-with-pricing."""

    def _write_rerun_config(self, run_dir: Path, new_backend: str | None) -> None:
        config = {
            "mode": "rerun",
            "source_prompt_version": "v3",
            "original_backend": "anthropic",
            "new_backend": new_backend,
        }
        (run_dir / "rerun_config.json").write_text(json.dumps(config))

    def test_stage3_incomplete_when_new_backend_is_null(self, tmp_path: Path) -> None:
        """rerun_config.json present but new_backend is null → Stage 3 incomplete."""
        _setup_through_stage2(tmp_path, "r1")
        # Add an existing (priced) backend that would satisfy normal Stage 3
        (tmp_path / "backends").mkdir(parents=True, exist_ok=True)
        (tmp_path / "backends" / "anthropic.yaml").write_text(
            "model: claude-haiku-4-5\nprovider: anthropic\n"
            "requests_per_minute: 100\ntokens_per_minute: 100000\n"
            "pricing:\n"
            "  input_cost_per_million_tokens: 0.80\n"
            "  cached_cost_per_million_tokens: 0.08\n"
            "  output_cost_per_million_tokens: 4.00\n"
        )
        self._write_rerun_config(tmp_path / "r1", new_backend=None)
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][2]["status"] == "incomplete"

    def test_stage3_complete_when_new_backend_yaml_has_pricing(self, tmp_path: Path) -> None:
        """rerun_config.json with new_backend set, that YAML has pricing → Stage 3 complete."""
        _setup_through_stage2(tmp_path, "r1")
        (tmp_path / "backends").mkdir(parents=True, exist_ok=True)
        (tmp_path / "backends" / "openai.yaml").write_text(
            "model: gpt-4o\nprovider: openai\n"
            "requests_per_minute: 100\ntokens_per_minute: 100000\n"
            "pricing:\n"
            "  input_cost_per_million_tokens: 2.50\n"
            "  cached_cost_per_million_tokens: 1.25\n"
            "  output_cost_per_million_tokens: 10.00\n"
        )
        self._write_rerun_config(tmp_path / "r1", new_backend="openai")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][2]["status"] == "complete"

    def test_stage3_incomplete_when_new_backend_yaml_missing_pricing(self, tmp_path: Path) -> None:
        """rerun_config.json with new_backend set but that YAML lacks pricing → incomplete."""
        _setup_through_stage2(tmp_path, "r1")
        (tmp_path / "backends").mkdir(parents=True, exist_ok=True)
        (tmp_path / "backends" / "openai.yaml").write_text(
            "model: gpt-4o\nprovider: openai\n"
            "requests_per_minute: 100\ntokens_per_minute: 100000\n"
        )
        self._write_rerun_config(tmp_path / "r1", new_backend="openai")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][2]["status"] == "incomplete"
        assert result["stages"][2]["detail"] == "pricing_missing"

    def test_stage3_incomplete_when_new_backend_yaml_does_not_exist(self, tmp_path: Path) -> None:
        """rerun_config.json references a backend YAML that doesn't exist → incomplete."""
        _setup_through_stage2(tmp_path, "r1")
        (tmp_path / "backends").mkdir(parents=True, exist_ok=True)
        self._write_rerun_config(tmp_path / "r1", new_backend="openai")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][2]["status"] == "incomplete"
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_pipeline_status.py::TestStage3RerunMode -v
```

Expected: 4 tests FAIL — rerun config is not yet read by `_check_stage_3`.

- [ ] **Step 3: Update `_check_stage_3` signature and logic**

In `odysseus/agents/pipeline/status.py`, replace the existing `_check_stage_3` function (lines 378-407):

```python
def _check_stage_3(project_dir: Path, run_dir: Path) -> tuple[str, list[str], str]:
    """Stage 3: Backend Configured.

    In normal mode: at least one backends/*.yaml must have valid pricing.
    In rerun mode (rerun_config.json present): the specific new_backend named in
    the config must have a YAML with valid pricing, and new_backend must be non-null.
    """
    from odysseus.eval.backends.profile import BackendProfile

    rerun_config = _read_rerun_config(run_dir)

    if rerun_config is not None:
        # Rerun mode: new_backend must be explicitly set
        new_backend = rerun_config.get("new_backend")
        if not new_backend:
            return "incomplete", [], ""

        backends_dir = project_dir / "backends"
        yaml_path = backends_dir / f"{new_backend}.yaml"
        if not yaml_path.is_file():
            return "incomplete", [str(yaml_path)], ""

        try:
            profile = BackendProfile.from_yaml(yaml_path)
            if profile.pricing is not None:
                return "complete", [str(yaml_path)], ""
        except Exception:
            pass
        return "incomplete", [str(yaml_path)], "pricing_missing"

    # Normal mode: any backend with pricing
    backends_dir = project_dir / "backends"
    if not backends_dir.is_dir():
        return "incomplete", [], ""
    yaml_files = list(backends_dir.glob("*.yaml"))
    if not yaml_files:
        return "incomplete", [], ""

    artifacts = [str(f) for f in sorted(yaml_files)]
    has_priced_backend = False

    for yf in yaml_files:
        try:
            profile = BackendProfile.from_yaml(yf)
            if profile.pricing is not None:
                has_priced_backend = True
                break
        except Exception:
            continue

    if not has_priced_backend:
        return "incomplete", artifacts, "pricing_missing"
    return "complete", artifacts, ""
```

- [ ] **Step 4: Update the `_check_stage` dispatcher to pass `run_dir` to `_check_stage_3`**

In `odysseus/agents/pipeline/status.py`, in `_check_stage` (around line 339), change:

```python
    if stage_num == 3:
        return _check_stage_3(project_dir)
```

to:

```python
    if stage_num == 3:
        return _check_stage_3(project_dir, run_dir)
```

- [ ] **Step 5: Run the new tests to confirm they pass**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_pipeline_status.py::TestStage3RerunMode -v
```

Expected: 4 tests PASS.

- [ ] **Step 6: Run full test suite and linter**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_pipeline_status.py -v && uv run ruff check odysseus/agents/pipeline/status.py
```

Expected: all tests PASS, no lint errors.

- [ ] **Step 7: Commit**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && git add odysseus/agents/pipeline/status.py tests/test_pipeline_status.py && git commit -m "feat: make _check_stage_3 rerun-aware (checks specific new_backend)"
```

---

## Chunk 3: Rerun detection in `_next_action_for_stage_4`

### Task 3: Rerun short-circuit in Stage 4 next-action

**Files:**
- Modify: `odysseus/agents/pipeline/status.py:445-531` (`_next_action_for_stage_4`)
- Test: `tests/test_pipeline_status.py`

- [ ] **Step 1: Write failing tests**

Add this class to `tests/test_pipeline_status.py` (after `TestStage3RerunMode`):

```python
class TestStage4RerunMode:
    """Stage 4 in rerun mode: skips three-phase logic, returns rerun instruction."""

    def _setup_rerun_ready(self, base: Path, run_id: str, new_backend: str = "openai") -> None:
        """Stages 1-3 complete in rerun mode: rerun_config set with new_backend."""
        _setup_through_stage2(base, run_id)
        (base / "backends").mkdir(parents=True, exist_ok=True)
        (base / "backends" / f"{new_backend}.yaml").write_text(
            f"model: gpt-4o\nprovider: openai\n"
            "requests_per_minute: 100\ntokens_per_minute: 100000\n"
            "pricing:\n"
            "  input_cost_per_million_tokens: 2.50\n"
            "  cached_cost_per_million_tokens: 1.25\n"
            "  output_cost_per_million_tokens: 10.00\n"
        )
        rerun_config = {
            "mode": "rerun",
            "source_prompt_version": "v3",
            "original_backend": "anthropic",
            "new_backend": new_backend,
        }
        (base / run_id / "rerun_config.json").write_text(json.dumps(rerun_config))

    def test_rerun_mode_returns_rerun_instruction(self, tmp_path: Path) -> None:
        """Stage 4 with rerun_config.json returns odysseus_prompt_builder_rerun prompt."""
        self._setup_rerun_ready(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 4
        assert result["activate_prompt"] == "odysseus_prompt_builder_rerun"

    def test_rerun_mode_subagent_instruction_mentions_rerun(self, tmp_path: Path) -> None:
        """Rerun subagent instruction contains source_prompt_version and new_backend."""
        self._setup_rerun_ready(tmp_path, "r1", new_backend="openai")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "v3" in instr
        assert "openai" in instr
        assert "<HARD_STOP>" in instr

    def test_rerun_mode_available_tools_are_build_tools(self, tmp_path: Path) -> None:
        """Rerun mode exposes the same tools as the normal build phase."""
        self._setup_rerun_ready(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        tools = result["available_tools"]
        assert "init_search_state_tool" in tools
        assert "register_candidate_tool" in tools
        assert "run_eval" in tools
        assert "advance_round_tool" in tools
        assert "build_review_briefing_tool" not in tools

    def test_normal_stage4_unaffected_without_rerun_config(self, tmp_path: Path) -> None:
        """Without rerun_config.json, Stage 4 still uses the three-phase detection."""
        _setup_through_stage3(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["activate_prompt"] == "odysseus_review_agent"
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_pipeline_status.py::TestStage4RerunMode -v
```

Expected: 4 tests FAIL — no rerun short-circuit exists yet.

- [ ] **Step 3: Add rerun detection to `_next_action_for_stage_4`**

In `odysseus/agents/pipeline/status.py`, at the top of `_next_action_for_stage_4` (after the docstring, before `search_dir = ...`), add:

```python
    # Rerun mode: skip three-phase logic
    rerun_config = _read_rerun_config(run_dir)
    if rerun_config is not None:
        source_version = rerun_config.get("source_prompt_version", "unknown")
        new_backend = rerun_config.get("new_backend", "unknown")
        rerun_instr = _STAGE_4_RERUN_INSTRUCTION.format(
            run_id=run_dir.name,
            source_prompt_version=source_version,
            new_backend=new_backend,
        )
        return (
            "Stage 4 — rerun mode: spawn the Prompt Builder Rerun agent to restructure "
            f"the source prompt (version {source_version}) for the new backend ({new_backend}). "
            "REQUIRED: activate prompt 'odysseus_prompt_builder_rerun' before calling any build tools.",
            [
                "get_search_state_tool",
                "init_search_state_tool",
                "register_candidate_tool",
                "record_eval_result_tool",
                "advance_round_tool",
                "run_eval",
            ],
            ["odysseus_prompt_builder_rerun"],
            rerun_instr,
        )
```

Note: `_STAGE_4_RERUN_INSTRUCTION` already has `{run_id}`, `{source_prompt_version}`, and `{new_backend}` placeholders. The `.format()` call above fills them directly. The `subagent_instruction.format(run_id=run_id)` call in `get_pipeline_status` (line 307) would double-format — guard against this by pre-formatting in `_next_action_for_stage_4`. After adding the above block, the instruction returned is already fully rendered, so the generic `run_id` format in `get_pipeline_status` must not overwrite it. The cleanest fix: format all three placeholders in `_next_action_for_stage_4` as shown, and in `get_pipeline_status` the `.format(run_id=run_id)` call is safe because `{run_id}` no longer appears in the returned string.

- [ ] **Step 4: Run the new tests to confirm they pass**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_pipeline_status.py::TestStage4RerunMode -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_pipeline_status.py -v && uv run ruff check odysseus/agents/pipeline/status.py
```

Expected: all tests PASS, no lint errors.

- [ ] **Step 6: Commit**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && git add odysseus/agents/pipeline/status.py tests/test_pipeline_status.py && git commit -m "feat: add rerun short-circuit to _next_action_for_stage_4"
```

---

## Chunk 4: `initiate_rerun` tool

### Task 4: New `initiate_rerun` MCP tool + server registration

**Files:**
- Modify: `odysseus/mcp/orchestrator_tools.py` (add `initiate_rerun` tool after `complete_stage`)
- Modify: `odysseus/mcp/server.py:35-83` (`STAGE_REGISTRY["orchestrator"]`)
- Modify: `odysseus/mcp/server.py:19-27` (`_STAGE_PROMPT_MAP`)
- Test: `tests/test_initiate_rerun.py` (new file)

- [ ] **Step 1: Write failing tests**

Create `tests/test_initiate_rerun.py`:

```python
"""Tests for initiate_rerun tool logic (direct function tests, no MCP)."""

import json
from pathlib import Path

import pytest

from odysseus.agents.pipeline.status import get_pipeline_status


def _setup_stage4_converged_with_pareto(base: Path, run_id: str) -> None:
    """Stage 4 complete: converged=True, pareto_front has one candidate."""
    (base / run_id / "input").mkdir(parents=True, exist_ok=True)
    (base / run_id / "input" / "input_report.md").write_text("# Report")
    (base / run_id / "validation").mkdir(parents=True, exist_ok=True)
    for f in ["transformed.jsonl", "data_quality_report.json", "routing_context.json"]:
        (base / run_id / "validation" / f).write_text("{}")
    (base / run_id / "analysis").mkdir(parents=True, exist_ok=True)
    for f in ["dev.jsonl", "holdout.jsonl"]:
        (base / run_id / "analysis" / f).write_text("{}")
    (base / "backends").mkdir(parents=True, exist_ok=True)
    (base / "backends" / "mock.yaml").write_text(
        "model: mock-model\nprovider: mock_echo\n"
        "requests_per_minute: 100\ntokens_per_minute: 100000\n"
        "pricing:\n"
        "  input_cost_per_million_tokens: 0.0\n"
        "  cached_cost_per_million_tokens: 0.0\n"
        "  output_cost_per_million_tokens: 0.0\n"
    )
    (base / run_id / "search").mkdir(parents=True, exist_ok=True)
    (base / run_id / "search" / "directive_history.json").write_text("[]")
    (base / run_id / "prompts").mkdir(parents=True, exist_ok=True)
    (base / run_id / "prompts" / "v1.txt").write_text("prompt text")
    (base / run_id / "prompts" / "v3.txt").write_text("best prompt text")
    pareto_front = [
        {
            "prompt_version": "v1",
            "parent_version": None,
            "quality_score": 0.80,
            "cost": 0.05,
            "round_introduced": 1,
            "dominated": True,
            "example_ids": [],
        },
        {
            "prompt_version": "v3",
            "parent_version": "v1",
            "quality_score": 0.92,
            "cost": 0.04,
            "round_introduced": 3,
            "dominated": False,
            "example_ids": [],
        },
    ]
    search_state = {
        "search_state_id": "ss-001",
        "backend": "mock",
        "primary_metric_name": None,
        "round": 5,
        "pareto_front": pareto_front,
        "round_history": [],
        "stagnation_count": 5,
        "stagnation_limit": 3,
        "convergence_limit": 5,
        "max_rounds": 50,
        "mutation_mode": "targeted",
        "converged": True,
        "loop_phase": "build",
    }
    (base / run_id / "search" / "search_state.json").write_text(json.dumps(search_state))


def _run_initiate_rerun(
    outputs_dir: Path,
    run_id: str,
    source_prompt_version: str | None = None,
) -> dict:
    """Call the initiate_rerun business logic directly (no MCP layer)."""
    from odysseus.mcp._initiate_rerun import initiate_rerun_logic
    return initiate_rerun_logic(
        outputs_dir=outputs_dir,
        run_id=run_id,
        source_prompt_version=source_prompt_version,
    )


class TestInitiateRerun:
    def test_writes_rerun_config_json(self, tmp_path: Path) -> None:
        _setup_stage4_converged_with_pareto(tmp_path, "r1")
        _run_initiate_rerun(tmp_path, "r1")
        config_path = tmp_path / "r1" / "rerun_config.json"
        assert config_path.is_file()
        config = json.loads(config_path.read_text())
        assert config["mode"] == "rerun"
        assert config["new_backend"] is None
        assert config["source_prompt_version"] == "v3"  # highest quality on front
        assert config["original_backend"] == "mock"

    def test_renames_search_state(self, tmp_path: Path) -> None:
        _setup_stage4_converged_with_pareto(tmp_path, "r1")
        _run_initiate_rerun(tmp_path, "r1")
        assert not (tmp_path / "r1" / "search" / "search_state.json").is_file()
        assert (tmp_path / "r1" / "search" / "search_state_original.json").is_file()

    def test_stage4_becomes_incomplete_after_rename(self, tmp_path: Path) -> None:
        _setup_stage4_converged_with_pareto(tmp_path, "r1")
        _run_initiate_rerun(tmp_path, "r1")
        # Stage 3 will now be incomplete (new_backend is null) so we check that Stage 4
        # would be incomplete if we could reach it; verify by checking search state gone
        assert not (tmp_path / "r1" / "search" / "search_state.json").is_file()

    def test_explicit_source_version_override(self, tmp_path: Path) -> None:
        _setup_stage4_converged_with_pareto(tmp_path, "r1")
        _run_initiate_rerun(tmp_path, "r1", source_prompt_version="v1")
        config = json.loads((tmp_path / "r1" / "rerun_config.json").read_text())
        assert config["source_prompt_version"] == "v1"

    def test_raises_when_stage4_not_complete(self, tmp_path: Path) -> None:
        # Stage 4 not converged
        (tmp_path / "r1" / "input").mkdir(parents=True, exist_ok=True)
        (tmp_path / "r1" / "input" / "input_report.md").write_text("# Report")
        (tmp_path / "r1" / "search").mkdir(parents=True, exist_ok=True)
        (tmp_path / "r1" / "search" / "search_state.json").write_text(
            json.dumps({"converged": False, "round": 1})
        )
        with pytest.raises(ValueError, match="Stage 4 is not complete"):
            _run_initiate_rerun(tmp_path, "r1")

    def test_raises_when_search_state_missing(self, tmp_path: Path) -> None:
        (tmp_path / "r1" / "input").mkdir(parents=True, exist_ok=True)
        (tmp_path / "r1" / "input" / "input_report.md").write_text("# Report")
        with pytest.raises(ValueError, match="Stage 4 is not complete"):
            _run_initiate_rerun(tmp_path, "r1")
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_initiate_rerun.py -v
```

Expected: `ModuleNotFoundError` — `odysseus.mcp._initiate_rerun` does not exist.

- [ ] **Step 3: Create `odysseus/mcp/_initiate_rerun.py` with business logic**

Create new file `odysseus/mcp/_initiate_rerun.py`:

```python
"""Business logic for the initiate_rerun MCP tool.

Separated from the MCP decorator layer so it can be tested without an async context.
"""

from __future__ import annotations

import json
from pathlib import Path

from odysseus.agents.prompt_builder.search import Candidate, select_best


def initiate_rerun_logic(
    outputs_dir: Path,
    run_id: str,
    source_prompt_version: str | None = None,
) -> dict:
    """Validate Stage 4 is complete, select the best prompt, and write rerun_config.json.

    Args:
        outputs_dir: Path to the outputs directory (project_dir/outputs).
        run_id: Pipeline run identifier.
        source_prompt_version: Override the source prompt version. If None, the best
            candidate on the Pareto front is selected automatically.

    Returns:
        Dict with keys: source_prompt_version, original_backend, message.

    Raises:
        ValueError: If Stage 4 is not complete (search_state.json missing or not converged).
        FileNotFoundError: If the run directory does not exist.
    """
    run_dir = outputs_dir / run_id
    search_state_path = run_dir / "search" / "search_state.json"

    if not search_state_path.is_file():
        raise ValueError(
            f"Stage 4 is not complete for run '{run_id}': "
            f"search_state.json not found at {search_state_path}"
        )

    try:
        data = json.loads(search_state_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"Could not read search_state.json for run '{run_id}': {e}") from e

    if not data.get("converged"):
        raise ValueError(
            f"Stage 4 is not complete for run '{run_id}': "
            f"search_state.json exists but converged is not true"
        )

    original_backend: str = data.get("backend", "unknown")

    # Select source prompt version
    if source_prompt_version is None:
        pareto_front_data: list[dict] = data.get("pareto_front", [])
        if not pareto_front_data:
            raise ValueError(
                f"No candidates on Pareto front for run '{run_id}'. "
                f"Cannot select best prompt version automatically."
            )
        front = [Candidate.model_validate(c) for c in pareto_front_data]
        source_prompt_version = select_best(front)

    # Rename search_state.json to search_state_original.json so _check_stage_4
    # sees Stage 4 as incomplete (required for rerun to proceed through Stage 4)
    original_path = run_dir / "search" / "search_state_original.json"
    search_state_path.rename(original_path)

    # Write rerun_config.json
    rerun_config = {
        "mode": "rerun",
        "source_prompt_version": source_prompt_version,
        "original_backend": original_backend,
        "new_backend": None,
    }
    (run_dir / "rerun_config.json").write_text(json.dumps(rerun_config, indent=2))

    return {
        "source_prompt_version": source_prompt_version,
        "original_backend": original_backend,
        "message": (
            f"Rerun initiated for run '{run_id}'. "
            f"Source prompt: {source_prompt_version}. "
            f"Original backend: {original_backend}. "
            f"Next step: proceed to Stage 3 to configure the new backend. "
            f"Once Stage 3 is complete, call get_pipeline_status to continue."
        ),
    }
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_initiate_rerun.py -v
```

Expected: 6 tests PASS.

- [ ] **Step 5: Add the `initiate_rerun` MCP tool to `orchestrator_tools.py`**

Add this at the end of `odysseus/mcp/orchestrator_tools.py` (after `complete_stage`):

```python
@mcp.tool()
async def initiate_rerun(
    ctx: Context,
    run_id: str,
    source_prompt_version: str | None = None,
) -> str:
    """Initiate a rerun of a completed pipeline run with a different backend.

    Only valid when Stage 4 has converged for the given run_id (a final prompt
    version exists). This tool:
    - Finds the best prompt version from the Pareto front (or uses source_prompt_version if provided)
    - Renames search/search_state.json to search/search_state_original.json
    - Writes outputs/<run_id>/rerun_config.json with mode="rerun" and new_backend=null

    After this tool returns, proceed to Stage 3 to configure the new backend. The
    pipeline will then route through a restructure-only Stage 4 (single eval round)
    followed by Stage 5 for the final report.

    Args:
        run_id: Pipeline run identifier. Must have a converged Stage 4.
        source_prompt_version: Optional override for which prompt version to rerun.
            If None, the best candidate on the Pareto front is selected automatically
            (highest quality, ties broken by lowest cost).

    Returns:
        JSON confirmation with source_prompt_version, original_backend, and instructions.
    """
    from odysseus.mcp._initiate_rerun import initiate_rerun_logic
    from mcp.server.fastmcp.exceptions import ToolError

    project_dir = await _project_dir_mod.resolve_project_dir(ctx)
    outputs_dir = project_dir / "outputs"

    try:
        result = initiate_rerun_logic(
            outputs_dir=outputs_dir,
            run_id=run_id,
            source_prompt_version=source_prompt_version,
        )
    except (ValueError, FileNotFoundError) as e:
        raise ToolError(str(e)) from e

    return json.dumps(result, indent=2)
```

- [ ] **Step 6: Register `initiate_rerun` in `STAGE_REGISTRY["orchestrator"]` and add `_STAGE_PROMPT_MAP` entry**

In `odysseus/mcp/server.py`, update `STAGE_REGISTRY["orchestrator"]` (lines 36-41):

```python
    "orchestrator": [
        "optimize_routing_prompt",
        "get_pipeline_status",
        "start_stage",
        "complete_stage",
        "initiate_rerun",
    ],
```

In `odysseus/mcp/server.py`, update `_STAGE_PROMPT_MAP` (lines 19-27):

```python
_STAGE_PROMPT_MAP: dict[int | str, str] = {
    1: "odysseus/agents/prompts/user_input_system.md",
    2: "odysseus/agents/prompts/data_validation_system.md",
    3: "odysseus/agents/prompts/backend_setup_system.md",
    # Stage 4 is dynamic — looked up by activate_prompt name:
    "odysseus_prompt_builder": "odysseus/agents/prompts/prompt_builder_system.md",
    "odysseus_prompt_builder_rerun": "odysseus/agents/prompts/prompt_builder_rerun_system.md",
    "odysseus_review_agent": "odysseus/agents/prompts/review_agent_system.md",
    5: "odysseus/agents/prompts/final_report_system.md",
}
```

- [ ] **Step 7: Run full test suite and linter**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_initiate_rerun.py tests/test_pipeline_status.py -v && uv run ruff check odysseus/mcp/
```

Expected: all tests PASS, no lint errors.

- [ ] **Step 8: Commit**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && git add odysseus/mcp/_initiate_rerun.py odysseus/mcp/orchestrator_tools.py odysseus/mcp/server.py tests/test_initiate_rerun.py && git commit -m "feat: add initiate_rerun tool with business logic and server registration"
```

---

## Chunk 5: `optimize_routing_prompt` discovered_runs extension

### Task 5: Extend `optimize_routing_prompt` response with `discovered_runs`

**Files:**
- Modify: `odysseus/mcp/orchestrator_tools.py:22-54` (`optimize_routing_prompt`)
- Modify: `odysseus/agents/pipeline/status.py:220-318` (`get_pipeline_status`)
- Test: `tests/test_pipeline_status.py`

The `discovered_runs` array must be computed by `get_pipeline_status` (which already has `outputs_dir` and `project_dir` in scope) and surfaced in its response dict. `optimize_routing_prompt` already calls `_get_pipeline_status` and uses its JSON output — it will include `discovered_runs` automatically once `get_pipeline_status` adds it.

- [ ] **Step 1: Write failing tests for `discovered_runs` in `get_pipeline_status`**

Add this class to `tests/test_pipeline_status.py` (after `TestStage5FinalReport`):

```python
class TestDiscoveredRuns:
    """get_pipeline_status includes discovered_runs with per-run summaries."""

    def test_discovered_runs_empty_when_no_outputs(self, tmp_path: Path) -> None:
        result = get_pipeline_status(tmp_path, run_id=None)
        assert result.get("discovered_runs") == []

    def test_discovered_runs_lists_all_runs(self, tmp_path: Path) -> None:
        _setup_stage1(tmp_path, "run_a")
        _setup_stage1(tmp_path, "run_b")
        result = get_pipeline_status(tmp_path, run_id=None)
        run_ids = [r["run_id"] for r in result["discovered_runs"]]
        assert "run_a" in run_ids
        assert "run_b" in run_ids

    def test_discovered_runs_has_converged_prompt_false_for_incomplete_stage4(
        self, tmp_path: Path
    ) -> None:
        _setup_stage4_v1_done(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        entry = next(r for r in result["discovered_runs"] if r["run_id"] == "r1")
        assert entry["has_converged_prompt"] is False

    def test_discovered_runs_has_converged_prompt_true_for_converged(
        self, tmp_path: Path
    ) -> None:
        _setup_stage4_converged(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        entry = next(r for r in result["discovered_runs"] if r["run_id"] == "r1")
        assert entry["has_converged_prompt"] is True

    def test_discovered_runs_includes_current_stage(self, tmp_path: Path) -> None:
        _setup_stage1(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1")
        entry = next(r for r in result["discovered_runs"] if r["run_id"] == "r1")
        assert entry["current_stage"] == 2
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_pipeline_status.py::TestDiscoveredRuns -v
```

Expected: 5 tests FAIL — `discovered_runs` key not present in response.

- [ ] **Step 3: Add `_run_summary_for` helper and `discovered_runs` to `get_pipeline_status`**

In `odysseus/agents/pipeline/status.py`, add this private helper after `discover_runs` (after line 217):

```python
def _run_summary_for(run_id: str, outputs_dir: Path, project_dir: Path) -> dict:
    """Return a minimal summary dict for a single run_id.

    Used to populate the discovered_runs array in get_pipeline_status responses.
    Calls the existing per-stage check functions to reuse their logic exactly.
    """
    run_dir = outputs_dir / run_id

    # Use existing stage check functions for accuracy
    # Stage 1: file-existence check
    s1_status, _, _ = _check_stage(
        {"stage": 1, "name": "Input Report", "subfolder": "input", "files": ["input_report.md"]},
        run_dir,
        project_dir,
    )
    if s1_status != "complete":
        return {"run_id": run_id, "current_stage": 1, "has_converged_prompt": False}

    s2_status, _, _ = _check_stage_2(run_dir)
    if s2_status != "complete":
        return {"run_id": run_id, "current_stage": 2, "has_converged_prompt": False}

    s3_status, _, _ = _check_stage_3(project_dir, run_dir)
    if s3_status != "complete":
        return {"run_id": run_id, "current_stage": 3, "has_converged_prompt": False}

    s4_status, _, _ = _check_stage_4(run_dir)
    has_converged = s4_status == "complete"
    if not has_converged:
        return {"run_id": run_id, "current_stage": 4, "has_converged_prompt": False}

    s5_status, _, _ = _check_stage_5(run_dir)
    if s5_status != "complete":
        return {"run_id": run_id, "current_stage": 5, "has_converged_prompt": True}

    return {"run_id": run_id, "current_stage": 6, "has_converged_prompt": True}
```

Then, in `get_pipeline_status`, add these lines just before the `return {` statement (around line 309):

```python
    # Populate discovered_runs for all known runs
    all_run_ids = discover_runs(outputs_dir)
    discovered_runs = [_run_summary_for(rid, outputs_dir, project_dir) for rid in all_run_ids]
```

And add `"discovered_runs": discovered_runs,` to the return dict:

```python
    return {
        "run_id": run_id,
        "stages": stage_results,
        "current_stage": current_stage,
        "current_stage_name": current_stage_name,
        "next_action": action,
        "available_tools": tools,
        "activate_prompt": prompts[0] if prompts else None,
        "subagent_instruction": subagent_instruction,
        "discovered_runs": discovered_runs,
    }
```

Also update the early-return branch (no runs found, around line 238) to include `"discovered_runs": []`:

```python
            return {
                "run_id": None,
                "stages": [],
                "current_stage": 1,
                "current_stage_name": _STAGES[0]["name"],
                "next_action": "No pipeline runs found. Call submit_input_report to start.",
                "available_tools": tools,
                "activate_prompt": prompts[0] if prompts else None,
                "subagent_instruction": subagent_instruction,
                "discovered_runs": [],
            }
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_pipeline_status.py::TestDiscoveredRuns -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Update `optimize_routing_prompt` instructions block to describe three options**

In `odysseus/mcp/orchestrator_tools.py`, update the `optimize_routing_prompt` return statement to mention `discovered_runs` and the three options:

```python
    return (
        f"<pipeline_status>\n{status_json}\n</pipeline_status>\n\n"
        f"<instructions>\n"
        f"You are now operating as the User Input Agent for the Odysseus pipeline.\n"
        f"The pipeline status above has already been checked — use it to decide how to greet the user.\n\n"
        f"The `discovered_runs` array in pipeline_status lists all known runs with:\n"
        f"  - run_id: the run identifier\n"
        f"  - current_stage: the stage the run is currently at\n"
        f"  - has_converged_prompt: true if Stage 4 has converged (a final prompt exists)\n\n"
        f"If discovered_runs is non-empty, surface the three options below.\n"
        f"Only show option 2 (rerun) for runs where has_converged_prompt is true.\n\n"
        f"Follow your system prompt below exactly.\n"
        f"</instructions>\n\n"
        f"<system_prompt>\n{system_prompt}\n</system_prompt>"
    )
```

- [ ] **Step 6: Run full test suite**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest tests/test_pipeline_status.py -v && uv run ruff check odysseus/
```

Expected: all tests PASS, no lint errors.

- [ ] **Step 7: Commit**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && git add odysseus/agents/pipeline/status.py odysseus/mcp/orchestrator_tools.py tests/test_pipeline_status.py && git commit -m "feat: add discovered_runs to get_pipeline_status response and update optimize_routing_prompt"
```

---

## Chunk 6: Prompt Builder Rerun system prompt

### Task 6: `prompt_builder_rerun_system.md`

**Files:**
- Create: `odysseus/agents/prompts/prompt_builder_rerun_system.md`

No tests needed for the system prompt file itself — correct routing is verified by the `_STAGE_PROMPT_MAP` entry added in Task 4, and end-to-end behavior is verified in integration scenarios.

- [ ] **Step 1: Create `prompt_builder_rerun_system.md`**

Create `odysseus/agents/prompts/prompt_builder_rerun_system.md`:

```markdown
## Entry verification

Your first action — before anything else — is to call `get_pipeline_status`.

- **All rounds:** confirm `current_stage: 4`
- Also confirm `activate_prompt` is `"odysseus_prompt_builder_rerun"` in the subagent instruction

If the stage does not match, stop immediately and report:
"This sub-agent was spawned for the Prompt Builder Rerun role but the pipeline is at stage N. Aborting."
Do not call any tools. Do not proceed.

---

You are the Prompt Builder Rerun Agent in the Odysseus routing-prompt optimization pipeline.

## Your job

Restructure an existing routing prompt to match a new backend's formatting conventions.
You do **not** optimize, mutate, or review the prompt — you apply a single structural transformation
and record one eval result so the pipeline can continue to Stage 5.

## Inputs

Read all inputs from the subagent instruction context.

| Key | Source | Description |
|-----|--------|-------------|
| `run_id` | Subagent instruction | Pipeline run identifier; all paths are under `outputs/<run_id>/` |
| `source_prompt_version` | Subagent instruction | Version string of the prompt to restructure (e.g. `"v3"`) |
| `new_backend` | Subagent instruction | Backend label for the new backend (e.g. `"openai"`) |

## Tools

| Tool | Purpose |
|------|---------|
| `init_search_state_tool` | Initialize search state for this single-round rerun |
| `register_candidate_tool` | Register the restructured prompt as a candidate |
| `record_eval_result_tool` | Record the eval result for Pareto tracking |
| `advance_round_tool` | Close the round and force convergence |
| `get_search_state_tool` | Read current search state |
| `save_prompt_tool` | Save the restructured prompt to disk |
| `run_eval` | Evaluate the restructured prompt against the dev set |

> Note: `optimize_routing_prompt` is the pipeline entry-point tool for orchestrators. Do not call it.

## Resources

| Resource | When to read |
|----------|-------------|
| `odysseus://backends/{new_backend}` | Read first — detect provider for the new backend |
| `odysseus://agents/prompt-builder/best-practices` | Read at start |
| `odysseus://agents/prompt-builder/conventions-claude` | When provider is Anthropic or Bedrock |
| `odysseus://agents/prompt-builder/conventions-openai` | When provider is OpenAI |
| `odysseus://agents/prompt-builder/conventions-{provider}/{model}` | After provider conventions — skip if empty |

## Workflow

Execute these steps exactly in order.

1. **Read source prompt.** Read the file at `outputs/<run_id>/prompts/<source_prompt_version>.txt`.
   This is the prompt you will restructure.

2. **Detect provider.** Read `odysseus://backends/{new_backend}` and extract the `provider` and `model` fields.

3. **Read resources.** Read the best-practices resource and the provider-specific conventions resource.
   Then attempt to read the model-specific conventions resource. If it returns empty, proceed without it.

4. **Initialize search state.** Call:
   ```
   init_search_state_tool(run_id=run_id, backend=new_backend, max_rounds=1, stagnation_limit=0, convergence_limit=1)
   ```
   Store the returned `search_state_id`.
   Note: `convergence_limit=1` and `stagnation_limit=0` are required — `advance_round_tool` will
   converge after a single round.

5. **Determine the next version number.** Scan `outputs/<run_id>/prompts/` for the highest existing
   version number (e.g. if `v3.txt` is the source, the new version is `v4`).

6. **Restructure the prompt.** Apply the new backend's formatting conventions to the source prompt.

   **Hard constraint: content must not change.**
   - Do **not** alter the routing objective, routes, decision rules, or examples.
   - Do **not** add, remove, or rephrase any semantic content.
   - Apply only structural/formatting changes:
     - XML tags (`<example>`, `<important>`) ↔ Markdown headers and `**bold**`
     - `User:`/`Assistant:` example turns ↔ `<example>` XML blocks
     - Section structure adjustments matching the target provider's conventions

   | Source provider | Target provider | Change |
   |----------------|-----------------|--------|
   | Anthropic/Bedrock | OpenAI | Replace XML structure with Markdown headers and `User:`/`Assistant:` example turns; replace `<important>` with `**bold**` |
   | OpenAI | Anthropic/Bedrock | Replace Markdown headers with XML tags; replace `User:`/`Assistant:` turns with `<example>` blocks; replace `**bold**` with `<important>` tags |

7. **Save the restructured prompt.** Call `save_prompt_tool(run_id=run_id, prompt_version="v<N>", content=<restructured text>)`.

8. **Register candidate.** Call `register_candidate_tool(run_id=run_id, prompt_version="v<N>", example_ids=[])`.
   (Example IDs are not tracked for rerun — pass an empty list.)

9. **Evaluate.** Call `run_eval(prompt_version="v<N>", data_source=outputs/<run_id>/analysis/dev.jsonl, backend=new_backend)`.

10. **Extract scores.** From the ScoreReport: extract `quality_score` from `metrics` (use `primary_metric_name` if set, otherwise the first metric) and `cost` from `summary.total_cost`.

11. **Record result.** Call `record_eval_result_tool(search_state_id, "v<N>", quality_score, cost)`.

12. **Advance round.** Call `advance_round_tool(search_state_id)`.
    The returned `RoundSummary` will have `converged: true` (because `convergence_limit=1`).

## Constraints

- **Format only, never content.** You are a formatter, not an optimizer. Any change to routing logic,
  decision rules, examples, or output format instructions is a bug.
- **Single round.** Do not loop. Call `advance_round_tool` exactly once.
- **Holdout isolation.** Never evaluate against holdout. Use only the dev split.
- **Versioning.** Increment the version number from the source (e.g. source `v3` → new `v4`).

---

## Exit verification

After calling `advance_round_tool`, check the returned `RoundSummary`:

- **`converged: true` is required.** If it is not true, something went wrong with search state
  initialization — report the error and abort.
- Call `get_pipeline_status` and confirm Stage 4 shows `status: complete`. Exit.

Do not attempt review-phase work. Do not spawn any sub-agents. Exit when Stage 4 is complete.
```

- [ ] **Step 2: Verify the file loads correctly via `_load_text`**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && python -c "
from odysseus.mcp.server import _load_text
text = _load_text('odysseus/agents/prompts/prompt_builder_rerun_system.md')
print('OK, length:', len(text))
"
```

Expected: `OK, length: <N>` (any positive integer).

- [ ] **Step 3: Commit**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && git add odysseus/agents/prompts/prompt_builder_rerun_system.md && git commit -m "feat: add prompt_builder_rerun_system.md for restructure-only Stage 4 rerun"
```

---

## Chunk 7: User Input Agent update and documentation

### Task 7: Update `user_input_system.md` Pipeline Discovery section

**Files:**
- Modify: `odysseus/agents/prompts/user_input_system.md:76-83`

- [ ] **Step 1: Update the Pipeline Discovery section**

In `odysseus/agents/prompts/user_input_system.md`, replace the Pipeline Discovery section (lines 76-83):

Old text:
```
Pipeline status has already been retrieved and is pre-injected above — use it directly. If previous runs exist, ask the user:

> "I found existing pipeline runs. Would you like to start fresh, or bootstrap from an existing run's prompt?"

- **Start fresh:** proceed normally with problem specification
- **Bootstrap:** the user picks a run, and `submit_input_report` is called with `bootstrap_from_run_id` to copy the seed prompt into the new run
```

New text:
```
Pipeline status has already been retrieved and is pre-injected above — use it directly. The status includes a `discovered_runs` array listing all known runs with `run_id`, `current_stage`, and `has_converged_prompt`.

If `discovered_runs` is non-empty, ask the user which option they want:

> "I found existing pipeline runs. How would you like to proceed?"

Present the options that apply:

1. **Continue** — resume the most recent run at its current stage. Always available.
2. **Rerun with different backend** — take an existing run's converged prompt and re-evaluate it against a new backend (format restructure only, no re-optimization). Only show this option for runs where `has_converged_prompt` is `true`. When the user picks this: ask which run to rerun (if multiple qualify), then call `initiate_rerun(run_id=<run_id>)`. After the tool returns, proceed to Stage 3 guidance so the user can configure the new backend.
3. **Start again** — new run from scratch. Always available.

- **Continue:** proceed with `get_pipeline_status` for the selected run to find the next step
- **Rerun:** call `initiate_rerun(run_id=<selected_run_id>)`, then guide through Stage 3 backend setup
- **Start again:** proceed normally with problem specification (same as fresh run)
```

- [ ] **Step 2: Run the full test suite to confirm no regressions**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest -v && uv run ruff check odysseus/
```

Expected: all tests PASS, no lint errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && git add odysseus/agents/prompts/user_input_system.md && git commit -m "feat: update user_input_system.md with three-option pipeline discovery (rerun support)"
```

---

### Task 8: Documentation updates

**Files:**
- Modify: `docs/architecture.md`
- Modify: `odysseus/agents/README.md` (if it exists; skip if not)

- [ ] **Step 1: Check whether `odysseus/agents/README.md` exists**

```bash
ls /Users/thymo.fieten/Documents/project-odysseus/odysseus/agents/README.md 2>/dev/null && echo "exists" || echo "not found"
```

- [ ] **Step 2: Update `docs/architecture.md` — Pipeline Overview section**

In `docs/architecture.md`, after the existing mermaid diagram, add a note about rerun mode. Insert after the closing triple-backtick of the mermaid block:

```markdown

**Rerun mode:** When Stage 4 has converged, the orchestrator can call `initiate_rerun` to re-enter the pipeline at Stage 3 for a different backend. The rerun flow is: Stage 3 (new backend) → Stage 4 (Prompt Builder Rerun: format restructure + single eval) → Stage 5 (final report). The original search state is preserved as `search_state_original.json`; `rerun_config.json` drives rerun-mode behavior throughout `status.py`.
```

- [ ] **Step 3: Update `docs/architecture.md` — Agent Registry table**

In the Agent Registry table (Section 2), add a row after the Prompt Builder row:

```
| Prompt Builder Rerun | LLM-driven | [`odysseus/agents/prompts/prompt_builder_rerun_system.md`](../odysseus/agents/prompts/prompt_builder_rerun_system.md) | Done | `run_id`, `source_prompt_version`, `new_backend` (from subagent instruction) | `prompt_version` (restructured) |
```

- [ ] **Step 4: Update `docs/architecture.md` — Tools table (Section 5)**

Add `initiate_rerun` to the Tools table after `complete_stage`:

```
| `initiate_rerun` | Implemented | Validate Stage 4 is complete, select best prompt version, rename search state, write `rerun_config.json` | [`odysseus/mcp/orchestrator_tools.py`](../odysseus/mcp/orchestrator_tools.py) |
```

- [ ] **Step 5: Update `docs/architecture.md` — Stage-Scoped Tool Filtering table**

In the Stage-Scoped Tool Filtering table, update the `orchestrator` row to add `initiate_rerun`:

```
| `orchestrator` | `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage`, `initiate_rerun` |
```

- [ ] **Step 6: Update `docs/architecture.md` — Prompts table**

Add `odysseus_prompt_builder_rerun` to the Prompts table:

```
| `odysseus_prompt_builder_rerun` | Prompt Builder Rerun agent — format-only restructure for a different backend (single eval round) | [`odysseus/agents/prompts/prompt_builder_rerun_system.md`](../odysseus/agents/prompts/prompt_builder_rerun_system.md) |
```

- [ ] **Step 7: Update `docs/architecture.md` — Directory Guide (Section 6)**

Add two rows to the Directory Guide after `outputs/<run_id>/search/`:

```
| `outputs/<run_id>/rerun_config.json` | Rerun mode marker: `mode`, `source_prompt_version`, `original_backend`, `new_backend` (null until Stage 3 completes) |
| `outputs/<run_id>/search/search_state_original.json` | Preserved original search state from before rerun initiation |
```

- [ ] **Step 8: Update `odysseus/agents/README.md` if it exists**

If the file exists (from Step 1), add the Prompt Builder Rerun agent to its agent listing in the same format as the existing entries.

If it does not exist, skip this step.

- [ ] **Step 9: Run full test suite and type check**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest -v && uv run ruff check odysseus/ && uv run pyright
```

Expected: all tests PASS, no lint errors, no type errors (or only pre-existing type errors).

- [ ] **Step 10: Commit**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && git add docs/architecture.md odysseus/agents/README.md && git commit -m "docs: update architecture.md for rerun mode (pipeline overview, agent registry, tool tables, directory guide)"
```

---

## Final verification

- [ ] **Run the complete test suite one final time**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Run linter and type checker**

```bash
cd /Users/thymo.fieten/Documents/project-odysseus && uv run ruff check . && uv run pyright
```

Expected: no new errors beyond any pre-existing baseline.
