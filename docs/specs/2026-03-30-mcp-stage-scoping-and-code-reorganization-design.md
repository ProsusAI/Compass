# MCP Stage-Scoped Tool Filtering & Code Reorganization

**Date:** 2026-03-30
**Status:** Approved
**Scope:** MCP server restructuring, agents module reorganization, documentation updates

## Problem

The Odysseus MCP server exposes 23 tools to every client connection. When the orchestrating agent reads the full tool catalog, it:

1. Consumes significant context window on tool descriptions before work begins
2. Attempts to "skip ahead" by calling later-stage tools before `pipeline_status` corrects course
3. Occasionally picks wrong tools due to the flat, undifferentiated tool surface

On the code side, the backing modules have grown organically:

- `mcp.py` is 1,212 lines — all 23 tools, 6 prompts, and 16 resources in one file
- `agents/` has 20 flat files with clear but unexpressed groupings (routing_rationale_*, review_*, prompt_builder_*, data_*)
- `pipeline_status.py` (557 lines) and `review_preprocessor.py` (490 lines) are at maintainability limits

## Solution Overview

1. **Session-scoped MCP tool filtering** — the orchestrator sees 4 tools; sub-agents see only their stage's tools
2. **Split `mcp.py`** into stage-specific tool modules under `mcp/`
3. **Reorganize `agents/`** into subdirectories matching pipeline stages
4. **Update documentation** to reflect the new structure

## Design

### 1. MCP Session & Tool Scoping

The MCP server maintains an `active_stage` per connection, stored in-memory (not on disk). `tools/list` returns only tools for the active stage.

#### Stage Registry

| Stage | Orchestrator Tools | Sub-Agent Tools |
|-------|-------------------|-----------------|
| `orchestrator` (default) | `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage` | — |
| `input_report` | — | `submit_input_report` |
| `data_validation` | — | `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context` |
| `routing_analysis` | — | `create_seed_registry_tool`, `resolve_registry_tool`, `prune_registry_tool`, `validate_rationale_card_set_tool`, `stratified_split_tool` |
| `backend_setup` | — | `get_default_pricing` |
| `prompt_building` | — | `init_search_state_tool`, `register_candidate_tool`, `run_eval`, `record_eval_result_tool`, `advance_round_tool`, `get_search_state_tool`, `filter_holdout_dataset_tool` |
| `review` | — | `build_review_briefing_tool`, `record_directive_outcomes_tool`, `get_search_state_tool`, `run_eval` |
| `holdout` | — | `filter_holdout_dataset_tool`, `run_holdout_eval` |

`get_pipeline_status` is available in **every** stage (always appended to the active tool set).

#### Session Lifecycle

1. Connection opens → `active_stage = "orchestrator"` (4 tools visible)
2. Orchestrator calls `start_stage(run_id, "data_validation")` → server sets `active_stage = "data_validation"`
3. `tools/list` now returns only data validation tools + `get_pipeline_status`
4. Sub-agent works with its scoped tools
5. Orchestrator calls `complete_stage(run_id)` → `active_stage` resets to `"orchestrator"`
6. Connection drop → defaults back to `"orchestrator"`

#### New Tools

**`start_stage`**
- Parameters: `run_id: str`, `stage: str`
- Validates stage name against registry
- Sets `active_stage` on the session
- Returns: confirmation with list of tools now available

**`complete_stage`**
- Parameters: `run_id: str`
- Resets `active_stage` to `"orchestrator"`
- Returns: confirmation

### 2. MCP Module Split

Replace `mcp.py` (1,212 lines) with:

```
odysseus/mcp/
  __init__.py                 # Package init, re-export create_app
  server.py                   # FastMCP app creation, session state, tools/list override, stage registry
  orchestrator_tools.py       # optimize_routing_prompt, get_pipeline_status, start_stage, complete_stage
  input_report_tools.py       # submit_input_report
  data_validation_tools.py    # detect_and_parse_dataset, transform_dataset, validate_dataset, save_routing_context
  routing_analysis_tools.py   # create_seed_registry_tool, resolve_registry_tool, prune_registry_tool, validate_rationale_card_set_tool, stratified_split_tool
  backend_setup_tools.py      # get_default_pricing
  prompt_building_tools.py    # init_search_state_tool, register_candidate_tool, run_eval, record_eval_result_tool, advance_round_tool, get_search_state_tool, filter_holdout_dataset_tool
  review_tools.py             # build_review_briefing_tool, record_directive_outcomes_tool
  holdout_tools.py            # filter_holdout_dataset_tool, run_holdout_eval
  resources.py                # All 16 MCP resources (no stage scoping needed)
  prompts.py                  # All 6 MCP prompt templates
```

Each `*_tools.py` file:
- Defines tool functions with `@mcp.tool()` decorators
- Imports business logic from corresponding `agents/` subdirectory
- Contains no business logic itself — pure MCP interface layer

**Shared tools across stages:** Some tools appear in multiple stages (e.g., `run_eval` in both `prompt_building` and `review`, `get_search_state_tool` in both). Each tool function is defined in exactly one `*_tools.py` file (its primary stage). The stage registry controls visibility — a tool can appear in multiple stages without being defined in multiple files. `server.py` owns the stage → tool mapping; tool files define functions, not stage membership.

`server.py` responsibilities:
- Create FastMCP app
- Maintain per-session `active_stage` state
- Override `tools/list` to filter by `active_stage`
- Register all tools from submodules
- Define the stage → tool mapping registry

### 3. Agents Module Reorganization

Restructure `agents/` from 20 flat files into stage-aligned subdirectories:

```
odysseus/agents/
  __init__.py                   # Re-exports from all subdirectories (backward compat)
  base.py                       # BaseAgent abstract interface
  user_input_report.py          # Input report constants
  eval_runner.py                # EvalRunnerAgent (cross-cutting)

  pipeline/
    __init__.py
    status.py                   # get_pipeline_status (from pipeline_status.py)
    guards.py                   # artifact pre-flight checks (from pipeline_guards.py)

  data_validation/
    __init__.py
    detect.py                   # format detection & parsing (from data_ingestion_detect.py)
    transform.py                # field mapping (from data_ingestion_transform.py)
    checks.py                   # data quality checks (from data_validation_checks.py)

  routing_analysis/
    __init__.py
    models.py                   # RationaleCard, VocabularyRegistry, RoutingContext, etc. (from routing_rationale_models.py)
    registry.py                 # registry lifecycle ops (from routing_rationale_registry.py)
    checks.py                   # deterministic rationale validation (from routing_rationale_checks_deterministic.py)
    checks_semantic.py          # LLM-driven overlap checks (from routing_rationale_checks.py)
    split.py                    # stratified split (from stratified_split.py)

  prompt_builder/
    __init__.py
    search.py                   # SearchState, Candidate models (from prompt_builder_search.py)
    search_ops.py               # init, register, record, advance, get (from prompt_builder_search_ops.py)
    holdout_filter.py           # filter holdout dataset (from prompt_builder_holdout_filter.py)

  review/
    __init__.py
    models.py                   # ReviewBriefing, DirectiveOutcome, etc. (from review_models.py)
    ops.py                      # directive history, mutation log I/O (from review_ops.py)
    preprocessor.py             # build_review_briefing (from review_preprocessor.py)
```

#### Import Compatibility

`agents/__init__.py` re-exports all public symbols from subdirectories. Any existing code doing `from odysseus.agents import SearchState` continues to work unchanged. Each subdirectory `__init__.py` must re-export all symbols that the current flat `agents/__init__.py` exports from the corresponding source files. The implementer should derive these lists from the existing `agents/__init__.py` at migration time.

#### Resource Files

Markdown resource files currently in `agents/` (e.g., `backend_setup_defaults.md`, `data_validation_format.md`, `prompt_builder_best_practices.md`) move to their corresponding subdirectory. The MCP resource loader paths in `mcp/resources.py` must be updated accordingly.

#### Backend Setup Stage

The `backend_setup` stage has no dedicated subdirectory under `agents/` because its sole tool (`get_default_pricing`) delegates directly to `eval/pricing.py`. No agent-level business logic exists for this stage.

#### Dependency Direction

```
mcp/*_tools.py  →  agents/<stage>/*  →  agents/pipeline/*  →  eval/*
                                     →  eval/*
```

The dependency is always `mcp/ → agents/`, never the reverse. Agents modules never import from `mcp/`.

**Cross-stage dependencies within `agents/`:** Some subdirectories import from others. Known cross-stage imports:

| From | To | Symbol(s) |
|------|----|-----------|
| `review/models.py` | `prompt_builder/search.py` | `Candidate` |
| `routing_analysis/checks.py` | `routing_analysis/checks_semantic.py` | validation helpers |
| `routing_analysis/split.py` | `routing_analysis/models.py`, `routing_analysis/registry.py` | domain models |
| `data_validation/transform.py` | `data_validation/detect.py` | `DetectionResult` |

These cross-stage imports are acceptable — they follow the data model dependency direction (models → consumers). The key invariant is: `mcp/` → `agents/`, never the reverse.

### 4. Documentation Updates

| Document | Action |
|----------|--------|
| `docs/architecture.md` | Update project structure diagram; add MCP session/stage scoping section; update module reference tables |
| `CLAUDE.md` | Update project structure tree to reflect `mcp/` and `agents/` subdirectories |
| `odysseus/agents/README.md` | Rewrite to reflect subdirectory organization; document which subdirectory backs which pipeline stage |
| `odysseus/mcp/README.md` | **New** — explain MCP layer: session scoping, stage registry, tool-file-to-stage mapping |
| `odysseus/eval/README.md` | Update any cross-references to moved agents modules |
| `prompts/README.md` | Check for stale references, update if needed |
| Agent system prompts (`agents/prompts/*.md`) | Update if they reference specific tool lists (sub-agents now get only their stage's tools) |

Docs describe current structure only. No migration history commentary.

## Migration Plan

Four phases, each independently committable and testable.

### Phase 1: Reorganize `agents/`

1. Create subdirectories: `pipeline/`, `data_validation/`, `routing_analysis/`, `prompt_builder/`, `review/`
2. Move `.py` files into subdirectories (renaming where clearer, e.g., `data_ingestion_detect.py` → `data_validation/detect.py`)
3. Move `.md` resource files to their corresponding subdirectory (e.g., `data_validation_format.md` → `data_validation/format.md`)
4. Create `__init__.py` for each subdirectory — re-export all symbols currently exported by `agents/__init__.py` from the corresponding source files
5. Update `agents/__init__.py` to re-export from subdirectories
6. Update all internal imports across the codebase
7. Run `uv run pytest` — all tests must pass
8. Run `uv run ruff check .` and `uv run pyright` — no regressions

### Phase 2: Split `mcp.py` into `mcp/`

1. Create `mcp/` directory structure
2. Extract tool functions into stage-specific files
3. Extract resources and prompts into their own files
4. Create `server.py` as the entrypoint (replacing `mcp.py`)
5. Update `__main__` entry (`python -m odysseus.mcp`) to use new structure
6. Remove old `mcp.py`
7. Run full test suite

### Phase 3: Add session-scoped tool filtering

1. Add `active_stage` session state to `server.py`
2. Define stage → tool mapping registry in `server.py`
3. Implement `start_stage` and `complete_stage` tools in `orchestrator_tools.py`
4. Override `tools/list` to filter by `active_stage`
5. Ensure `get_pipeline_status` appears in every stage's tool set
6. Update orchestrator system prompt to use `start_stage` / `complete_stage` flow
7. Test: verify tool listing changes per stage
8. Test: verify sub-agents can only call their stage's tools

### Phase 4: Update docs and agent prompts

1. Update `docs/architecture.md`
2. Update `CLAUDE.md`
3. Rewrite `odysseus/agents/README.md`
4. Create `odysseus/mcp/README.md`
5. Update `odysseus/eval/README.md` cross-references
6. Review and update agent system prompts in `agents/prompts/`
7. Remove any stale documentation

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Import breakage after file moves | `agents/__init__.py` re-exports maintain backward compatibility; full test suite validates |
| MCP entry point change breaks deployment | Update `pyproject.toml` entry point in Phase 2; test `python -m odysseus.mcp` and `uvx odysseus` |
| Session state lost on connection drop | Defaults to `"orchestrator"` stage — safe fallback, orchestrator can re-enter any stage |
| Sub-agent needs a tool from wrong stage | `get_pipeline_status` available everywhere; tool call to wrong-stage tool returns clear error |
| Agent prompts reference tools that moved | Phase 4 audits all prompts; tools keep their names, only visibility changes |
