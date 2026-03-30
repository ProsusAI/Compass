# Stage 4 Refinement Loop Merge — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge old Stage 4 (Prompt v1 Compiled) and Stage 5 (Refinement Loop) into a single Stage 4 with three-phase detection (cold-start → build-v1 → normal loop), renumber downstream stages.

**Architecture:** Old Stages 4+5 become new Stage 4 "Refinement Loop" with `_next_action_for_stage_4()` dispatching Review Agent (cold-start or normal review) or Prompt Builder based on file-existence detection. Old Stage 6→5, old Stage 7→6. All guards, tests, docs, and agent prompts renumbered.

**Tech Stack:** Python, pytest, MCP (FastMCP)

**Spec:** `docs/superpowers/specs/2026-03-30-stage4-refinement-loop-merge-design.md`

---

## Chunk 1: Core Pipeline Logic

### Task 1: Rewrite `_STAGES` and stage check functions in `status.py`

**Files:**
- Modify: `odysseus/agents/pipeline/status.py:19-62` (stage definitions)
- Modify: `odysseus/agents/pipeline/status.py:364-465` (check functions)
- Modify: `odysseus/agents/pipeline/status.py:329-330` (stage cap)
- Test: `tests/test_pipeline_status.py`

- [ ] **Step 1: Write failing tests for the new stage layout**

In `tests/test_pipeline_status.py`, replace the existing `_setup_through_stage4` and `_setup_through_stage5` helpers and add new tests for Stage 4 three-phase detection. The new helpers:

```python
def _setup_through_stage3(base: Path, run_id: str) -> None:
    """Set up stages 1-3 complete: validation + split + backend."""
    _setup_through_stage2(base, run_id)
    (base / "backends").mkdir(parents=True, exist_ok=True)
    (base / "backends" / "mock.yaml").write_text("label: mock")


def _setup_stage4_cold_start_done(base: Path, run_id: str) -> None:
    """Stage 4 after cold-start: directive_history exists, no v1, no search_state."""
    _setup_through_stage3(base, run_id)
    search = base / run_id / "search"
    search.mkdir(parents=True, exist_ok=True)
    (search / "directive_history.json").write_text("[]")


def _setup_stage4_v1_done(base: Path, run_id: str) -> None:
    """Stage 4 after v1: v1 exists, search_state exists, not converged."""
    _setup_stage4_cold_start_done(base, run_id)
    (base / run_id / "prompts").mkdir(parents=True, exist_ok=True)
    (base / run_id / "prompts" / "v1.txt").write_text("prompt: test")
    search = base / run_id / "search"
    (search / "search_state.json").write_text(
        json.dumps({"round": 1, "converged": False, "loop_phase": "review"})
    )


def _setup_stage4_converged(base: Path, run_id: str) -> None:
    """Stage 4 complete: converged=True."""
    _setup_stage4_v1_done(base, run_id)
    search = base / run_id / "search"
    (search / "search_state.json").write_text(
        json.dumps({"round": 5, "converged": True, "loop_phase": "build"})
    )
```

New test classes:

```python
class TestStage4ThreePhaseDetection:
    """Stage 4 three-phase detection: cold-start → build-v1 → normal loop."""

    def test_cold_start_when_no_files(self, tmp_path: Path) -> None:
        """No directive_history, no search_state → cold-start → Review Agent."""
        _setup_through_stage3(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 4
        instr = result["subagent_instruction"]
        assert "odysseus_review_agent" in instr
        assert "cold-start" in result["next_action"].lower() or "seed" in result["next_action"].lower()

    def test_build_v1_after_cold_start(self, tmp_path: Path) -> None:
        """directive_history exists, no v1 → build-v1 → Prompt Builder."""
        _setup_stage4_cold_start_done(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 4
        instr = result["subagent_instruction"]
        assert "odysseus_prompt_builder" in instr

    def test_normal_loop_review_phase(self, tmp_path: Path) -> None:
        """v1 exists, search_state loop_phase=review → Review Agent."""
        _setup_stage4_v1_done(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 4
        assert "odysseus_review_agent" in result["subagent_instruction"]

    def test_normal_loop_build_phase(self, tmp_path: Path) -> None:
        """v1 exists, search_state loop_phase=build → Prompt Builder."""
        _setup_stage4_v1_done(tmp_path, "r1")
        search = tmp_path / "r1" / "search"
        (search / "search_state.json").write_text(
            json.dumps({"round": 1, "converged": False, "loop_phase": "build"})
        )
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 4
        assert "odysseus_prompt_builder" in result["subagent_instruction"]

    def test_stage4_complete_when_converged(self, tmp_path: Path) -> None:
        """converged=True → Stage 4 complete, advances to Stage 5."""
        _setup_stage4_converged(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][3]["status"] == "complete"  # Stage 4 index 3
        assert result["current_stage"] == 5  # Holdout Validation

    def test_stage4_incomplete_when_not_converged(self, tmp_path: Path) -> None:
        """converged=False → Stage 4 incomplete."""
        _setup_stage4_v1_done(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][3]["status"] == "incomplete"
        assert result["current_stage"] == 4


class TestStage5Holdout:
    """Stage 5 (was 6) — holdout validation."""

    def test_holdout_has_subagent_instruction(self, tmp_path: Path) -> None:
        _setup_stage4_converged(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 5
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "HARD_STOP" in instr
        assert "holdout" in instr
        assert "filter_holdout_dataset_tool" in instr
        assert "run_holdout_eval" in instr
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline_status.py::TestStage4ThreePhaseDetection -v`
Expected: FAIL — old code still has 7 stages and old Stage 4/5 logic.

- [ ] **Step 3: Rewrite `_STAGES` in `status.py`**

Replace lines 19-62 with:

```python
_STAGES: list[dict[str, Any]] = [
    {
        "stage": 1,
        "name": "Input Report",
        "subfolder": "input",
        "files": ["input_report.md"],
    },
    {
        "stage": 2,
        "name": "Data Validated",
        "subfolder": None,
        "files": [],
    },
    {
        "stage": 3,
        "name": "Backend Configured",
        "subfolder": None,
        "files": [],
    },
    {
        "stage": 4,
        "name": "Refinement Loop",
        "subfolder": "search",
        "files": [],  # special: parses search_state.json for converged == true
    },
    {
        "stage": 5,
        "name": "Holdout Validation",
        "subfolder": "reports",
        "files": [],  # special: holdout_report.json
    },
    {
        "stage": 6,
        "name": "Final Report",
        "subfolder": None,
        "files": [],  # future stub
    },
]
```

- [ ] **Step 4: Rewrite HARD_STOP templates**

Replace old `_STAGE_5_BUILD_INSTRUCTION` and `_STAGE_5_REVIEW_INSTRUCTION` with three Stage 4 templates:

```python
_STAGE_4_COLD_START_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='review') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, "
    "build_review_briefing_tool, record_directive_outcomes_tool\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

_STAGE_4_BUILD_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, "
    "init_search_state_tool, register_candidate_tool, record_eval_result_tool, "
    "advance_round_tool, run_eval, filter_holdout_dataset_tool\n"
    "Your tools: get_pipeline_status only\n\n"
    "NOTE: optimize_routing_prompt is the pipeline entry-point tool (orchestrator-level only). "
    "Do not call it from within the sub-agent.\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)

_STAGE_4_REVIEW_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 review-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='review') BEFORE spawning the sub-agent.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state_tool, "
    "build_review_briefing_tool, record_directive_outcomes_tool\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)
```

- [ ] **Step 5: Rewrite `_NEXT_ACTION` — remove old Stage 4, renumber 6→5, 7→6**

Remove the `4: (...)` entry. Change `6: (...)` key to `5` and update the HARD_STOP text to say "Stage 5" instead of "Stage 6". Change `7: (...)` key to `6`.

- [ ] **Step 6: Rewrite `_next_action_for_stage_5` → `_next_action_for_stage_4`**

Replace the entire `_next_action_for_stage_5` function with:

```python
def _next_action_for_stage_4(
    run_dir: Path,
) -> tuple[str, list[str], list[str], str]:
    """Return (action, tools, prompts, subagent_instruction) for Stage 4.

    Three-phase detection:
    1. No directive_history.json and no search_state.json → cold-start (Review Agent)
    2. directive_history.json exists but no v1.* → build-v1 (Prompt Builder)
    3. v1.* exists and search_state.json exists → normal loop (read loop_phase)
    """
    search_dir = run_dir / "search"
    directive_history = search_dir / "directive_history.json"
    search_state_path = search_dir / "search_state.json"
    prompts_dir = run_dir / "prompts"
    has_v1 = prompts_dir.is_dir() and bool(list(prompts_dir.glob("v1.*")))

    # Phase 1: Cold-start — no directives and no search state
    if not directive_history.is_file() and not search_state_path.is_file():
        return (
            "Stage 4 — cold-start: spawn the Review Agent to select initial "
            "few-shot seed examples from the dataset. "
            "REQUIRED: activate prompt 'odysseus_review_agent' before calling any review tools.",
            [
                "get_search_state_tool",
                "build_review_briefing_tool",
                "record_directive_outcomes_tool",
            ],
            ["odysseus_review_agent"],
            _STAGE_4_COLD_START_INSTRUCTION,
        )

    # Phase 2: Build v1 — directives exist but no compiled prompt yet
    if not has_v1:
        return (
            "Stage 4 — build phase: spawn the Prompt Builder to compile the "
            "initial routing prompt (v1) using seed examples from the Review Agent. "
            "REQUIRED: activate prompt 'odysseus_prompt_builder' before calling any build tools.",
            [
                "get_search_state_tool",
                "init_search_state_tool",
                "register_candidate_tool",
                "record_eval_result_tool",
                "advance_round_tool",
                "run_eval",
                "filter_holdout_dataset_tool",
            ],
            ["odysseus_prompt_builder"],
            _STAGE_4_BUILD_INSTRUCTION,
        )

    # Phase 3: Normal loop — read loop_phase from search state
    loop_phase = "review"
    if search_state_path.is_file():
        try:
            data = json.loads(search_state_path.read_text())
            loop_phase = data.get("loop_phase", "review")
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    if loop_phase == "review":
        return (
            "Stage 4 — review phase: spawn the Review Agent to analyse "
            "eval results and emit edit directives. "
            "REQUIRED: activate prompt 'odysseus_review_agent' before calling any review tools.",
            [
                "get_search_state_tool",
                "build_review_briefing_tool",
                "record_directive_outcomes_tool",
            ],
            ["odysseus_review_agent"],
            _STAGE_4_REVIEW_INSTRUCTION,
        )
    else:
        return (
            "Stage 4 — build phase: spawn the Prompt Builder to generate "
            "prompt variants and evaluate them. "
            "REQUIRED: activate prompt 'odysseus_prompt_builder' before calling any build tools.",
            [
                "get_search_state_tool",
                "init_search_state_tool",
                "register_candidate_tool",
                "record_eval_result_tool",
                "advance_round_tool",
                "run_eval",
                "filter_holdout_dataset_tool",
            ],
            ["odysseus_prompt_builder"],
            _STAGE_4_BUILD_INSTRUCTION,
        )
```

- [ ] **Step 7: Rewrite check functions and stage cap**

Replace `_check_stage_4` (v1 glob) with convergence check (old `_check_stage_5` logic). Rename old `_check_stage_6` → `_check_stage_5`. Remove old `_check_stage_5`. Update `_check_stage` dispatcher to match new numbering. Change `_check_stage_7` stub to `_check_stage_6`.

In `_check_stage`:
```python
if stage_num == 4:
    return _check_stage_4(run_dir)   # convergence check
if stage_num == 5:
    return _check_stage_5(run_dir)   # holdout report
if stage_num in (6,):
    return "incomplete", [], ""      # future stub
```

New `_check_stage_4`:
```python
def _check_stage_4(run_dir: Path) -> tuple[str, list[str], str]:
    """Stage 4: Refinement Loop — search_state.json with converged == true."""
    search_state = run_dir / "search" / "search_state.json"
    if not search_state.is_file():
        return "incomplete", [], ""
    try:
        data = json.loads(search_state.read_text())
        if data.get("converged") is True:
            return "complete", [str(search_state)], ""
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return "incomplete", [str(search_state)], ""
```

New `_check_stage_5`:
```python
def _check_stage_5(run_dir: Path) -> tuple[str, list[str], str]:
    """Stage 5: Holdout Validation — reports/holdout/holdout_report.json exists."""
    report = run_dir / "reports" / "holdout" / "holdout_report.json"
    if report.is_file():
        return "complete", [str(report)], ""
    return "incomplete", [], ""
```

Update stage cap: `current_stage = min(current_stage, 6)`.

Update `get_pipeline_status` to call `_next_action_for_stage_4` when `current_stage == 4`:
```python
if current_stage == 4:
    action, tools, prompts, subagent_instruction = _next_action_for_stage_4(run_dir)
else:
    action, tools, prompts, subagent_instruction = _next_action_for_stage(current_stage)
```

- [ ] **Step 8: Update `_NEXT_ACTION[5]` HARD_STOP to say Stage 5**

In the renumbered `5: (...)` entry (was `6`), update all text references from "Stage 6" to "Stage 5".

- [ ] **Step 9: Run tests**

Run: `uv run pytest tests/test_pipeline_status.py -v`
Expected: new tests PASS. Some old tests that reference Stage 5/6/7 will FAIL — those are updated in Task 2.

- [ ] **Step 10: Commit**

```bash
git add odysseus/agents/pipeline/status.py tests/test_pipeline_status.py
git commit -m "refactor: merge Stage 4+5 into single Refinement Loop stage

Three-phase detection: cold-start → build-v1 → normal loop.
Renumber old Stage 6→5, old Stage 7→6."
```

---

### Task 2: Fix remaining tests in `test_pipeline_status.py`

**Files:**
- Modify: `tests/test_pipeline_status.py`

- [ ] **Step 1: Remove old helpers and tests, update all references**

Remove:
- `_setup_through_stage4` (replaced by `_setup_stage4_cold_start_done` etc.)
- `_setup_through_stage5` (was an alias)
- `_setup_through_stage6_converged` (replaced by `_setup_stage4_converged`)
- `TestStage5NewBehavior` class (merged into `TestStage4ThreePhaseDetection`)
- `TestStage5DynamicHardStop` class (merged into `TestStage4ThreePhaseDetection`)

Update:
- `test_blocked_stages`: stage 4 comment → "refinement loop (stage 4)", remove old stage 5 reference. Only 3 blocked stages now (indices 3, 4, 5 for stages 4, 5, 6).
- `test_prompt_v1_glob`: remove entirely — v1 existence is no longer a stage-completion gate.
- `test_stage4_has_subagent_instruction`: becomes cold-start test (already covered by new tests — remove this one).
- `test_stage4_available_tools_correct`: update to check cold-start tools (review tools, not build tools).
- `test_stage5_*` tests: remove — replaced by `TestStage4ThreePhaseDetection`.
- `test_stage6_has_subagent_instruction`: renumber to test Stage 5 (holdout).

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/test_pipeline_status.py -v`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pipeline_status.py
git commit -m "test: update pipeline status tests for merged Stage 4"
```

---

### Task 3: Update `orchestrator_tools.py` and `server.py`

**Files:**
- Modify: `odysseus/mcp/orchestrator_tools.py:86-88`
- Modify: `odysseus/mcp/server.py:19-27`

- [ ] **Step 1: Fix prompt lookup in `orchestrator_tools.py`**

Change line 86-88 from:
```python
    # Stage 5 has dynamic prompt lookup by activate_prompt name (review vs build phase).
    # All other stages look up by stage number.
    lookup_key: int | str | None = activate_prompt if current_stage == 5 and activate_prompt else current_stage
```
to:
```python
    # Stage 4 has dynamic prompt lookup by activate_prompt name (cold-start/review/build phase).
    # All other stages look up by stage number.
    lookup_key: int | str | None = activate_prompt if current_stage == 4 and activate_prompt else current_stage
```

- [ ] **Step 2: Update `_STAGE_PROMPT_MAP` in `server.py`**

Change from:
```python
_STAGE_PROMPT_MAP: dict[int | str, str] = {
    1: "odysseus/agents/prompts/user_input_system.md",
    2: "odysseus/agents/prompts/data_validation_system.md",
    3: "odysseus/agents/prompts/backend_setup_system.md",
    4: "odysseus/agents/prompts/prompt_builder_system.md",
    # Stage 5 is dynamic — looked up by activate_prompt name:
    "odysseus_prompt_builder": "odysseus/agents/prompts/prompt_builder_system.md",
    "odysseus_review_agent": "odysseus/agents/prompts/review_agent_system.md",
}
```
to:
```python
_STAGE_PROMPT_MAP: dict[int | str, str] = {
    1: "odysseus/agents/prompts/user_input_system.md",
    2: "odysseus/agents/prompts/data_validation_system.md",
    3: "odysseus/agents/prompts/backend_setup_system.md",
    # Stage 4 is dynamic — looked up by activate_prompt name:
    "odysseus_prompt_builder": "odysseus/agents/prompts/prompt_builder_system.md",
    "odysseus_review_agent": "odysseus/agents/prompts/review_agent_system.md",
}
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_mcp.py tests/test_mcp_stage_scoping.py -v`
Expected: PASS (or stage-count failures addressed in Task 4).

- [ ] **Step 4: Commit**

```bash
git add odysseus/mcp/orchestrator_tools.py odysseus/mcp/server.py
git commit -m "fix: Stage 4 dynamic prompt lookup and remove static prompt map entry"
```

---

### Task 4: Update `test_mcp.py` and `test_mcp_stage_scoping.py`

**Files:**
- Modify: `tests/test_mcp.py:474-496`
- Modify: `tests/test_mcp_stage_scoping.py:25-36`

- [ ] **Step 1: Update `test_mcp.py` stage 7 references**

In `test_get_pipeline_status_stage7_not_enriched`: change all `7` references to `6`, update `stage_name` to `"Final Report"`.

- [ ] **Step 2: Update `test_mcp_stage_scoping.py` stage count**

Change the docstring from "All 7 stages" to "All 7 stage scopes" (the STAGE_REGISTRY has 7 entries: orchestrator + 6 stage scopes). The registry itself doesn't change — `prompt_building`, `review`, `holdout` etc. are scope names, not stage numbers.

Actually, verify: the STAGE_REGISTRY has entries for `orchestrator`, `input_report`, `data_validation`, `backend_setup`, `prompt_building`, `review`, `holdout` — that's 7. This is unchanged. Only update the docstring for clarity.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_mcp.py tests/test_mcp_stage_scoping.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_mcp.py tests/test_mcp_stage_scoping.py
git commit -m "test: renumber stage references in MCP tests"
```

---

## Chunk 2: Guards, Tool Docstrings, Agent Prompts

### Task 5: Update precondition guards and tool docstrings

**Files:**
- Modify: `odysseus/mcp/prompt_building_tools.py`
- Modify: `odysseus/mcp/holdout_tools.py`
- Modify: `odysseus/mcp/review_tools.py`

- [ ] **Step 1: Update `prompt_building_tools.py` guards and docstrings**

Replace all 6 occurrences of `[Stage 6: Eval Loop]` → `[Stage 4: Refinement Loop]` in docstrings for: `init_search_state_tool`, `register_candidate_tool`, `run_eval`, `record_eval_result_tool`, `advance_round_tool`, `get_search_state_tool`.

`init_search_state_tool` guard: `stage=4, stage_name="Search Init"` → `stage=4, stage_name="Refinement Loop"`.

`run_eval` guard: `stage=5, stage_name="Prompt Evaluation"` → `stage=4, stage_name="Refinement Loop"`.

`filter_holdout_dataset_tool` docstring: `[Stage 7: Holdout Validation]` → `[Stage 5: Holdout Validation]`.

`filter_holdout_dataset_tool` guard: `stage=7, stage_name="Holdout Validation"` → `stage=5, stage_name="Holdout Validation"`.

- [ ] **Step 2: Update `holdout_tools.py` guards and docstrings**

Line 12: `[Stage 7: Holdout Validation]` → `[Stage 5: Holdout Validation]`.

Line 26-30: `stage=7, stage_name="Holdout Validation"` → `stage=5, stage_name="Holdout Validation"`.

- [ ] **Step 3: Update `review_tools.py` docstrings**

Line 26: `[Stage 5: Eval Loop -- Review]` → `[Stage 4: Refinement Loop -- Review]`.

Line 138: `[Stage 5: Eval Loop -- Review]` → `[Stage 4: Refinement Loop -- Review]`.

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add odysseus/mcp/prompt_building_tools.py odysseus/mcp/holdout_tools.py odysseus/mcp/review_tools.py
git commit -m "refactor: renumber stage guards and docstrings for merged pipeline"
```

---

### Task 6: Update agent prompts (entry verification)

**Files:**
- Modify: `odysseus/agents/prompts/review_agent_system.md:4`
- Modify: `odysseus/agents/prompts/prompt_builder_system.md:1-12`

- [ ] **Step 1: Update Review Agent entry verification**

Change line 4 from `current_stage: 5` to `current_stage: 4`.

- [ ] **Step 2: Update Prompt Builder entry verification**

Lines 5-6 currently say:
```markdown
- **Round 1 (initial compilation):** confirm `current_stage: 4`
- **Rounds 2+ (optimization):** confirm `current_stage: 5`
```

Change to:
```markdown
- **All rounds:** confirm `current_stage: 4`
```

Line 8: Update the abort message from "stage N" to match:
```markdown
If the stage does not match, stop immediately and report:
"This sub-agent was spawned for the Prompt Builder role but the pipeline is at stage N. Aborting."
```

Line 12: `If `current_stage: 5`, also confirm...` — change to `If in the optimization loop (round 2+), also confirm...` and remove the stage 5 reference since it's all stage 4 now.

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/prompts/review_agent_system.md odysseus/agents/prompts/prompt_builder_system.md
git commit -m "docs: update agent prompts for merged Stage 4 entry verification"
```

---

### Task 7: Update documentation

**Files:**
- Modify: `README.md:174-210`
- Modify: `odysseus/agents/README.md:19-20,51-52`
- Modify: `odysseus/mcp/README.md` (if stage references exist)

- [ ] **Step 1: Update README.md stage sections**

Renumber stage headers:
- `### Stage 4: Backend Setup` → `### Stage 3: Backend Configured` (verify — may already be correct)
- `### Stage 5: Prompt Building + Eval Loop` → `### Stage 4: Refinement Loop`
- `### Stage 6: Holdout Validation` → `### Stage 5: Holdout Validation`
- `### Stage 7: Final Report` → `### Stage 6: Final Report`

Update the Stage 4 description to mention the three-phase flow: cold-start → build-v1 → review/build loop.

- [ ] **Step 2: Update `odysseus/agents/README.md`**

Lines 19-20: `Stage 4 build phase` → `Stage 4 build phase`, `Stage 5 review phase` → `Stage 4 review phase`.

Lines 51-52: `Stage 4 build` → `Stage 4 build`, `Stage 5 review` → `Stage 4 review`.

- [ ] **Step 3: Update `docs/architecture.md`**

Update "stages 1–7" references to "stages 1–6" (line 100 and line 136). No individual stage-number changes needed — architecture.md uses stage scope names, not numbers.

- [ ] **Step 4: Commit**

```bash
git add README.md odysseus/agents/README.md docs/architecture.md
git commit -m "docs: renumber stage references in README and architecture docs"
```

---

## Chunk 3: Verification

### Task 8: Full verification pass

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: all PASS.

- [ ] **Step 2: Run linter**

Run: `uv run ruff check .`
Expected: no errors.

- [ ] **Step 3: Run type checker**

Run: `uv run pyright`
Expected: no new errors.

- [ ] **Step 4: Grep for stale stage references**

Run: `grep -rn "Stage 5.*Refinement\|Stage 5.*review\|Stage 5.*build\|Stage 6.*Holdout\|Stage 7\|stage_num == 5\|stage_num == 7\|current_stage.*==.*5\|current_stage.*==.*7\|stage=5\|stage=7" odysseus/ tests/ --include="*.py" --include="*.md"`

Expected: no matches in Python/MD files (only in the spec document and plan).

- [ ] **Step 5: Final commit if any fixups needed**

```bash
git add -A && git commit -m "fix: clean up stale stage references"
```
