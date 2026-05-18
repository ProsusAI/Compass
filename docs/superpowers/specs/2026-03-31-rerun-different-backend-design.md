# Rerun with Different Backend — Design Spec

## Problem

When the orchestrator detects previous pipeline runs, users currently have two options: start fresh or bootstrap from an existing run's prompt. There's no way to take a converged prompt from a completed run and re-evaluate it against a different backend (e.g., switching from Anthropic to OpenAI) without re-running the entire optimization loop.

## Solution

Add a third pipeline mode — "rerun with different backend" — that reuses the existing run, re-enters Stage 3 for backend configuration, restructures the prompt format for the new backend's conventions (without changing content), runs a single evaluation, and proceeds to Stage 5 for the final report.

## User-Facing Flow

When `optimize_routing_prompt` is called and previous runs exist, the orchestrator presents three options:

1. **Continue** — resume the most recent run at its current stage (existing behavior, made explicit)
2. **Rerun with different backend** — only shown for runs where Stage 4 has converged (a final prompt version exists). Same run ID, re-enter Stage 3 → restructure prompt → single eval → Stage 5
3. **Start again** — new run from scratch (existing behavior)

Option 2 is gated: it only appears for runs that have a converged prompt (Stage 4 complete).

`optimize_routing_prompt` extends its response with a `discovered_runs` array — each entry contains `run_id`, `current_stage`, and `has_converged_prompt: bool`. The User Input Agent uses `has_converged_prompt` to decide whether to show the rerun option for each run.

## Pipeline Mode: Rerun

### Rerun Config File

When the user picks "rerun with different backend," the orchestrator calls a new `initiate_rerun` tool which:
- Validates Stage 4 is complete for the given run
- Finds the best prompt version from `search_state.json` (the converged winner)
- Writes `outputs/<run_id>/rerun_config.json`

```json
{
  "mode": "rerun",
  "source_prompt_version": "v3",
  "original_backend": "anthropic",
  "new_backend": null
}
```

`new_backend` starts null — set once Stage 3 completes with the newly configured backend. Existing backend YAML files are untouched; the user adds a new one during Stage 3.

`initiate_rerun` also renames the existing `search/search_state.json` to `search/search_state_original.json` (preserving it for reference). This is required so that `_check_stage_4` sees Stage 4 as incomplete — without it, `converged: true` in the existing search state makes Stage 4 appear complete and the rerun is unreachable.

### Stage Behavior in Rerun Mode

| Stage | Behavior |
|---|---|
| 1 (Input Report) | Skipped — existing artifacts marked complete |
| 2 (Data Validated) | Skipped — existing artifacts marked complete |
| 3 (Backend Configured) | Re-entered. User configures a new backend. Completion: `rerun_config.json.new_backend` is non-null and that backend YAML exists with pricing |
| 4 (Refinement Loop) | Restructure-only. Prompt Builder Rerun agent reads the source prompt, applies new backend conventions (format only, no content changes), runs a single eval. Uses `max_rounds=1`, `convergence_limit=1` so `advance_round_tool` forces convergence after one round. Existing `_check_stage_4` completion logic works unchanged (checks `converged == true` in `search_state.json`) |
| 5 (Final Report) | Normal — no changes. Reads converged prompt version and new backend from search state |

**Note on `get_pipeline_status` during an in-progress rerun:** When `rerun_config.json` exists with `new_backend: null`, `get_pipeline_status` reports Stage 3 as the current stage. When `new_backend` is set but Stage 4 is incomplete, it reports Stage 4. This ensures the "continue" option resumes correctly even during an in-progress rerun.

### Stage 3 Guard Change

`_check_stage_3` currently checks for any backend YAML with non-null `pricing`. In rerun mode:
- Reads `rerun_config.json` if present
- If `new_backend` is null → Stage 3 incomplete
- If `new_backend` is set → checks that specific backend YAML exists with pricing

### Stage 4 Rerun Instruction

`_next_action_for_stage_4` detects `rerun_config.json` and returns a rerun-specific `subagent_instruction` that:
- Points to `prompt_builder_rerun_system.md` (the "b" version)
- Uses `start_stage(stage='prompt_building')` — same stage scope, same tools
- Passes source prompt version and new backend label from `rerun_config.json`

### Stage 4 Exit

No special exit logic needed. The rerun Prompt Builder initializes search state with `max_rounds=1` and `convergence_limit=1`, so `advance_round_tool` naturally sets `converged: true` after the single eval. The existing `_check_stage_4` guard (`converged == true` in `search_state.json`) triggers Stage 5 progression.

## New Components

### `initiate_rerun` Tool

- Scope: `orchestrator` (added to `STAGE_REGISTRY["orchestrator"]`)
- Parameters: `run_id: str, source_prompt_version: str | None = None`
- Validates Stage 4 is complete for the run
- Reads `search_state.json` to find the converged best prompt version. Uses the same `select_best` logic as Stage 5 (highest quality, ties broken by lowest cost). The user can override the source version by passing `source_prompt_version` explicitly.
- Renames `search/search_state.json` to `search/search_state_original.json` so `_check_stage_4` sees Stage 4 as incomplete
- Writes `rerun_config.json` to `outputs/<run_id>/`
- Returns JSON confirmation with source prompt version and instructions to proceed to Stage 3

### `prompt_builder_rerun_system.md`

A dedicated "b" version of the Prompt Builder system prompt. Same tools, same resources, but with hard constraints:

**What it does:**
- Reads the source prompt from `outputs/<run_id>/prompts/<source_prompt_version>.txt`
- Reads the new backend profile resource to detect provider
- Reads provider-specific conventions (same resources as the normal builder)
- Restructures prompt formatting to match the new backend's conventions (XML tags ↔ markdown headers, example block formatting, emphasis style)
- Saves restructured prompt as the next version
- Registers candidate, runs single eval, records result. The single candidate must be registered via `register_candidate` and scored via `record_eval_result` so it lands on the Pareto front. Stage 5's `list_pareto_candidates` auto-selects from a single-candidate front.
- Calls `init_search_state` with `max_rounds=1`, `stagnation_limit=0`, `convergence_limit=1` (note: the `SearchState` validator enforces `convergence_limit > stagnation_limit`, so `stagnation_limit` must be set to `0`)
- Calls `advance_round_tool` which converges immediately

**Hard constraint:** Content must not change — same routing objective, same decision rules, same examples, same output format. Only structural/formatting changes allowed.

**Not included:** No review cycle, no optimization loop, no mutation strategies.

### `_STAGE_PROMPT_MAP` Entry

```python
"odysseus_prompt_builder_rerun": "odysseus/agents/prompts/prompt_builder_rerun_system.md"
```

## Changes to Existing Components

### `status.py`

| Function | Change |
|---|---|
| `get_pipeline_status` | When `rerun_config.json` exists in run dir: apply rerun-mode logic for Stage 3 and Stage 4 |
| `_check_stage_3` | In rerun mode: check specific `new_backend` from `rerun_config.json` instead of "any backend with pricing". Signature changes to `_check_stage_3(project_dir, run_dir)` to access `rerun_config.json`; the parent `_check_stage` function must pass `run_dir` through |
| `_next_action_for_stage_4` | Detect `rerun_config.json` → return rerun-specific instruction pointing to `prompt_builder_rerun_system.md` |

### `orchestrator_tools.py`

| Function | Change |
|---|---|
| `optimize_routing_prompt` | Updated instructions block describing three options and which runs qualify for rerun. Response now includes `discovered_runs` array with per-run stage summaries (`run_id`, `current_stage`, `has_converged_prompt`) |
| New: `initiate_rerun` | New tool in orchestrator scope |

### `server.py`

| Location | Change |
|---|---|
| `STAGE_REGISTRY["orchestrator"]` | Add `initiate_rerun` |
| `_STAGE_PROMPT_MAP` | Add `"odysseus_prompt_builder_rerun"` entry |

### `user_input_system.md`

Pipeline Discovery section updated from two options (start fresh / bootstrap) to three options (continue / rerun with different backend / start again). The rerun option is only presented for runs with a converged prompt.

### `guards.py`

No changes needed. Guards are artifact-existence checks only — Stages 1 and 2 artifacts already exist in the run directory, so Stage 3 tools pass their guards naturally in rerun mode.

## Documentation Updates

The following docs must be updated to reflect the rerun mode:

### `docs/architecture.md`

1. **Section 1 (Pipeline Overview):** Add note about the rerun mode branching after Stage 4 convergence, or add a second mermaid diagram showing the rerun flow
2. **Section 2 (Agent Registry):** Add Prompt Builder Rerun agent row
3. **Section 5 (MCP Surface) — Tools table:** Add `initiate_rerun` tool entry
4. **Section 5 — Stage-Scoped Tool Filtering table:** Add `initiate_rerun` to the orchestrator row
5. **Section 5 — Prompts table:** Add `odysseus_prompt_builder_rerun` entry
6. **Section 6 (Directory Guide):** Document `outputs/<run_id>/rerun_config.json`

### `odysseus/agents/README.md`

Add Prompt Builder Rerun agent to the agent listing.

### `odysseus/agents/pipeline/` README or inline docs

Document the rerun mode detection logic and how `rerun_config.json` drives conditional stage behavior.

## Files Touched (Implementation Summary)

| File | Action |
|---|---|
| `odysseus/agents/prompts/prompt_builder_rerun_system.md` | **New** — rerun Prompt Builder system prompt |
| `odysseus/agents/prompts/user_input_system.md` | **Edit** — three-option discovery flow |
| `odysseus/agents/pipeline/status.py` | **Edit** — rerun-aware Stage 3 check, rerun Stage 4 instruction |
| `odysseus/mcp/orchestrator_tools.py` | **Edit** — `initiate_rerun` tool, updated `optimize_routing_prompt` instructions |
| `odysseus/mcp/server.py` | **Edit** — `_STAGE_PROMPT_MAP` entry, `STAGE_REGISTRY` update |
| `docs/architecture.md` | **Edit** — rerun mode in pipeline overview, agent registry, tool tables, directory guide |
