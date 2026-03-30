# Merge Stage 4 into Refinement Loop

**Date:** 2026-03-30
**Status:** Approved

## Problem

The pipeline has a chicken-and-egg problem at the Stage 4→5 boundary:

1. Stage 4 dispatches the Prompt Builder to compile v1
2. The Prompt Builder's Phase 1 requires `review_directives` with few-shot examples from the Review Agent
3. The Review Agent has a Cold-Start Phase (Round 0) designed to select these seed examples — but it only runs in Stage 5, after v1 already exists
4. Result: the orchestrator gets confused at refinement loop entry and dispatches the Prompt Builder without the prerequisite directives

Additionally, a bug compounds the confusion:
- `orchestrator_tools.py:88` checks `current_stage == 5` for dynamic prompt lookup, but Stage 5 (the refinement loop) uses string-keyed prompt names (`"odysseus_review_agent"`, `"odysseus_prompt_builder"`). The integer `5` is not in `_STAGE_PROMPT_MAP`, so sub-agent instructions arrive with an empty `<stage_system_prompt>` tag.

A secondary plumbing gap: `record_directive_outcomes_tool` calls `_set_loop_phase(run_id, "build")` after the Review Agent finishes, but on cold-start no `search_state.json` exists yet — `_set_loop_phase` raises `FileNotFoundError`, which is suppressed by `contextlib.suppress`. In the merged design this is harmless because `_next_action_for_stage_4` uses file-existence detection (not `loop_phase`) to determine the cold-start → build-v1 transition. The silent suppression is intentional and does not need fixing.

## Solution

Merge Stage 4 (Prompt v1 Compiled) into Stage 5 (Refinement Loop) to create a single stage that owns the full lifecycle from seed example selection through convergence. Renumber downstream stages.

### New stage layout

| Stage | Name | Change |
|-------|------|--------|
| 1 | Input Report | unchanged |
| 2 | Data Validated | unchanged |
| 3 | Backend Configured | unchanged |
| 4 | Refinement Loop | **merged** — absorbs old Stage 4 + 5 |
| 5 | Holdout Validation | renumbered (was 6) |
| 6 | Final Report | renumbered (was 7) |

### Stage 4 three-phase detection

`_next_action_for_stage_4(run_dir, project_dir)` determines which sub-phase to dispatch:

```
No search/directive_history.json AND no search/search_state.json?
  → Cold-start phase: dispatch Review Agent to select seed examples

search/directive_history.json exists but no prompts/v1.*?
  → Build-v1 phase: dispatch Prompt Builder to compile initial prompt

prompts/v1.* exists (search_state.json exists)?
  → Normal loop: read loop_phase from search_state.json → dispatch Review or Prompt Builder
```

**Completion:** `search_state.json` with `converged == true`. The old Stage 4 `v1.*` check is no longer a stage-completion gate — v1 is now an intermediate artifact within the stage.

**Edge case — partial cold-start recovery:** If the cold-start Review Agent creates `directive_history.json` but crashes before `complete_stage`, the orchestrator re-dispatches and detection correctly moves to the build-v1 phase. If `search_state.json` exists but `directive_history.json` does not (aborted attempt), detection falls to the normal loop branch and reads `loop_phase` — this is correct because `search_state.json` implies the cold-start and v1 phases already completed.

**Error case — no `activate_prompt`:** If `current_stage == 4` but `activate_prompt` is `None` (an error state), `lookup_key` falls back to the integer `4`, which has no entry in `_STAGE_PROMPT_MAP`. The prompt injection silently skips — this is the intended fail-safe.

### HARD_STOP templates

Three templates, all following the existing pattern (`HARD_STOP` + `PRE-DISPATCH` + `Sub-agent tools` + `POST-EXIT` + `<stage_system_prompt>`):

| Template | Dispatches | Stage scope | Key difference |
|----------|-----------|-------------|----------------|
| `_STAGE_4_COLD_START_INSTRUCTION` | Review Agent | `review` | `next_action` text says "select initial few-shot examples from the dataset". The `"review"` scope exposes `build_review_briefing_tool` and `run_eval` which the cold-start agent won't use — this is acceptable; the Review Agent knows to enter cold-start mode when no search state exists. |
| `_STAGE_4_REVIEW_INSTRUCTION` | Review Agent | `review` | `next_action` text says "analyse eval results and emit edit directives" |
| `_STAGE_4_BUILD_INSTRUCTION` | Prompt Builder | `prompt_building` | Used for both v1 compilation and variant generation |

### Prompt lookup

`orchestrator_tools.py` dynamic lookup key: `activate_prompt if current_stage == 4 and activate_prompt else current_stage`. String-keyed entries in `_STAGE_PROMPT_MAP` (`"odysseus_review_agent"`, `"odysseus_prompt_builder"`) resolve the correct system prompt per sub-phase.

The integer `4` entry is removed from `_STAGE_PROMPT_MAP` (it pointed to `prompt_builder_system.md` statically). No replacement integer entry is added — Stage 4 always resolves by `activate_prompt` name.

### Stage scopes

No new `STAGE_REGISTRY` entries. Cold-start and normal review both use `"review"` scope. Build-v1 and optimization build both use `"prompt_building"` scope.

### Precondition guards

`check_artifacts()` calls in MCP tool modules enforce that prerequisite artifacts exist before a tool runs. Each guard has a hardcoded `stage` number and `stage_name` string. Renumbering map:

| Tool module | Guard | Old `stage` | New `stage` | New `stage_name` |
|-------------|-------|-------------|-------------|------------------|
| `prompt_building_tools.py` (`init_search_state_tool`) | `dev.jsonl` exists | 4 / "Search Init" | 4 / "Refinement Loop" |
| `prompt_building_tools.py` (`run_eval`) | `dev.jsonl` exists | 5 / "Prompt Evaluation" | 4 / "Refinement Loop" |
| `prompt_building_tools.py` (`filter_holdout_dataset_tool`) | `dev.jsonl` exists | 7 / "Holdout Validation" | 5 / "Holdout Validation" |
| `holdout_tools.py` (`run_holdout_eval`) | `search_state.json` exists | 7 / "Holdout Validation" | 5 / "Holdout Validation" |

Data validation guards (`data_validation_tools.py`, `stage=2`) are unchanged.

### Stage progression and sub-agent re-dispatch loop

Stage 4 is the only stage where the orchestrator must re-dispatch **different** sub-agents within a single stage. The POST-EXIT pattern in each HARD_STOP template ensures this:

```
1. Orchestrator calls complete_stage(run_id) → returns to orchestrator scope
2. Orchestrator calls get_pipeline_status(run_id)
3. If Stage 4 status != "complete":
   a. _next_action_for_stage_4 re-evaluates the three-phase detection
   b. Returns the appropriate HARD_STOP + system prompt for the NEXT sub-phase
   c. Orchestrator spawns the indicated sub-agent (may differ from previous)
4. If Stage 4 status == "complete" (converged):
   a. Pipeline advances to Stage 5 (Holdout Validation)
```

The key difference from Stages 1-3 (single sub-agent per stage): each `complete_stage` → `get_pipeline_status` cycle may yield a **different** sub-agent instruction. The orchestrator must not assume the same agent runs again — it reads the new `subagent_instruction` each time.

Example full progression through Stage 4:
1. `get_pipeline_status` → cold-start → HARD_STOP dispatches Review Agent
2. Review Agent selects seed examples → `record_directive_outcomes_tool` saves directives → exits
3. `complete_stage` → `get_pipeline_status` → build-v1 → HARD_STOP dispatches Prompt Builder
4. Prompt Builder compiles v1, evaluates, advances round → exits
5. `complete_stage` → `get_pipeline_status` → normal loop, `loop_phase="review"` → HARD_STOP dispatches Review Agent
6. Review Agent analyses results → `record_directive_outcomes_tool` sets `loop_phase="build"` → exits
7. `complete_stage` → `get_pipeline_status` → normal loop, `loop_phase="build"` → HARD_STOP dispatches Prompt Builder
8. ... repeat 5-7 until `converged == true` ...
9. `complete_stage` → `get_pipeline_status` → Stage 4 complete → advances to Stage 5

## Bug fix included

**`orchestrator_tools.py:88`** — currently `current_stage == 5`; changes to `current_stage == 4` to match the merged stage number. This is the only stage that uses dynamic prompt lookup by `activate_prompt` name.

## Files changed

### Core pipeline logic

| File | Changes |
|------|---------|
| `odysseus/agents/pipeline/status.py` | Remove old Stages 4-5 from `_STAGES`; add merged Stage 4 "Refinement Loop"; renumber Stages 5-6. Remove `_STAGE_5_*` templates; add `_STAGE_4_COLD_START_INSTRUCTION`, `_STAGE_4_REVIEW_INSTRUCTION`, `_STAGE_4_BUILD_INSTRUCTION`. Replace `_next_action_for_stage_5` with `_next_action_for_stage_4` (three-phase detection). Remove `_NEXT_ACTION[4]`; renumber `[6]→[5]`, `[7]→[6]`. Merge `_check_stage_4` (v1 glob) and `_check_stage_5` (convergence) into single `_check_stage_4` that checks convergence only. Renumber `_check_stage_6` → `_check_stage_5`. Remove `_check_stage_7` stub (becomes `_check_stage_6`). Update `current_stage` cap from 7 to 6. |
| `odysseus/mcp/orchestrator_tools.py` | Line 88: `current_stage == 5` → `current_stage == 4` for dynamic prompt lookup. Update comment. |
| `odysseus/mcp/server.py` | Remove `_STAGE_PROMPT_MAP[4]` integer entry. Update comment about dynamic lookup to reference Stage 4. |

### Agent prompts (entry verification)

| File | Change |
|------|--------|
| `review_agent_system.md` | `current_stage: 5` → `current_stage: 4` |
| `prompt_builder_system.md` | Stage references (old 4 and 5) both become `current_stage: 4` |

### MCP tool modules (docstrings and stage guards)

| File | Changes |
|------|---------|
| `odysseus/mcp/prompt_building_tools.py` | Update `[Stage 6: Eval Loop]` docstrings → `[Stage 4: Refinement Loop]`. Update stage guard checks (old 4/5 → 4). |
| `odysseus/mcp/holdout_tools.py` | Update `[Stage 7: Holdout Validation]` docstrings → `[Stage 5: Holdout Validation]`. Update stage guard (old 7 → 5). |
| `odysseus/mcp/review_tools.py` | Update `[Stage 5: Eval Loop -- Review]` docstrings → `[Stage 4: Refinement Loop -- Review]`. |

### Tests

| File | Changes |
|------|---------|
| `tests/test_pipeline_status.py` | Renumber all stage assertions, helper functions, test class names. Merge Stage 4/5 test coverage into Stage 4 tests. Update `_setup_through_stage*` helpers. |
| `tests/test_mcp.py` | Renumber stage references (old 7 → 6). |
| `tests/test_mcp_stage_scoping.py` | Update stage count assertion (7 → 6 stages). |

### Documentation

| File | Changes |
|------|---------|
| `docs/architecture.md` | Renumber stage references, update stage names. |
| `README.md` | Renumber stage section headers (old 4-7 → 3-6). |
| `odysseus/agents/README.md` | Update stage-to-agent mapping table. |
| `tests/scenarios/README.md` | Update any stage references in scenario descriptions. |

### Scenario files

Stage references in scenario files (`tests/scenarios/*.md`) updated mechanically where present.

## Design rationale

- **Why merge instead of two-phase Stage 4?** The distinction between "bootstrap" and "optimization loop" was artificial — same agents, same tools, same scopes. Merging gives one stage that owns the full prompt lifecycle.
- **Why renumber?** A gap in stage numbers (1-2-3-5-6-7) would be confusing. Mechanical renumbering is low-risk.
- **Why three sub-phases instead of two?** The cold-start (no search state, no directives) needs different `next_action` text than the normal review phase (which analyses eval results). Without this distinction, the orchestrator gets misleading guidance on first entry.
