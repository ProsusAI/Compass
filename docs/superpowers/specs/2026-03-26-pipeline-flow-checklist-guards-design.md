# Pipeline Flow: Checklist Tool & Precondition Guards

**Date:** 2026-03-26
**Status:** Proposed

## Problem

External LLM agents (Claude Code, Cursor) using the Odysseus MCP server see a flat list of 16+ tools, 7 prompts, and 10+ resources with no built-in guidance on ordering. They frequently:

- Call tools in the wrong order within a stage (e.g., `stratified_split` before rationale cards are generated)
- Look ahead and do work that belongs to downstream agents (e.g., trying to compile prompts during data validation)

The pipeline flow is documented in agent prompts and architecture docs, but LLM orchestrators don't reliably follow sequencing instructions in descriptions alone.

## Solution

Two complementary mechanisms:

1. **`get_pipeline_status` tool** — a checklist derived from artifacts on disk that tells the agent exactly where it is, what's done, what's next, and which tools are relevant.
2. **Precondition guards** — every tool checks that its prerequisite artifacts exist before running. On failure, returns an actionable error pointing to the checklist.

Plus two supporting changes:

3. **Persistence fixes** — stages that currently pass data only through conversation context now also persist artifacts to disk, so the checklist can detect them.
4. **Tool description updates** — each tool's docstring gets a stage prefix and precondition note.

## Design Principle

**LLM agents are unreliable instruction followers but reliable error handlers.** Guards are the enforcement mechanism (prevent wrong-order execution). The checklist is the recovery mechanism (tell the agent what to do instead). Together they create rails that prevent agents from going off-track and nudge them back when they try.

The checklist is **stateless** — it derives pipeline progress entirely from file existence checks. No state file to maintain or sync.

## 1. Persistence Fixes

### Problem

Stages 1 (User Input) and 2 (Data Validation) don't persist structured artifacts to disk. The checklist can't detect completion of these stages, and downstream agents can't find their outputs without conversation context.

### Changes

| Gap | What to persist | Path | Writer | Consumers |
|-----|----------------|------|--------|-----------|
| A | Input report (Markdown) with dataset path + problem description | `outputs/input_report.md` | `submit_input_report` tool | Data Validation Agent, Routing Analysis Agent |
| B | `DataQualityReport` | `outputs/data_quality_report.json` | `validate_dataset` tool | Routing Analysis Agent |
| C | `RoutingContext` | `outputs/routing_context.json` | `validate_dataset` tool (or Data Validation Agent after synthesizing it) | Routing Analysis Agent, Prompt Builder Agent |
| D | `VocabularyRegistry` (standalone) | `outputs/<hash>/vocabulary_registry.json` | Routing Analysis Agent during Phase 4 | Prompt Builder Agent |

**Gap A — `submit_input_report`:**

Currently a stub that returns a string. Change to:
1. Write the report Markdown to `outputs/input_report.md`
2. Return confirmation with the persisted path

**Gap B — `validate_dataset`:**

Currently returns the `DataQualityReport` as JSON in the tool response only. Change to:
1. Also write the report to `outputs/data_quality_report.json`
2. Return the JSON as before (backward-compatible)

**Gap C — `routing_context`:**

The `RoutingContext` is synthesized by the Data Validation Agent (LLM-driven) as a YAML block in its conversation output. To persist it:
1. The Data Validation Agent writes it to `outputs/routing_context.json` after synthesizing it
2. This is an agent-level change (prompt update), not a tool change

Alternative: add a `save_routing_context` tool that the Data Validation Agent calls. This is more explicit and verifiable by the guard system.

**Gap D — `vocabulary_registry.json`:**

The registry is embedded in each `RationaleCardSet`, but the Prompt Builder expects `vocabulary_registry_path` as a separate file. During Routing Analysis Phase 4:
1. Extract the registry from the validated `RationaleCardSet`
2. Write it to `outputs/<hash>/vocabulary_registry.json`
3. This happens alongside the existing `stratified_split_tool` call — either in the tool itself or as a separate agent action

## 2. Pipeline Stages & Detection Logic

The `get_pipeline_status` tool scans the project directory and checks for artifacts at known paths.

| # | Stage | Detection | Artifacts checked |
|---|-------|-----------|-------------------|
| 1 | Input Report | `outputs/input_report.md` exists | `outputs/input_report.md` |
| 2 | Data Validated | Quality report AND routing context AND transformed dataset exist | `outputs/data_quality_report.json`, `outputs/routing_context.json`, `data/transformed_*.jsonl` |
| 3 | Routing Analysis & Split | Dev split AND holdout split AND rationale cards AND vocabulary registry exist | `outputs/*/dev.jsonl`, `outputs/*/holdout.jsonl`, `outputs/*/dev_rationale_card_set.json`, `outputs/*/vocabulary_registry.json` |
| 4 | Backend Configured | At least one backend profile exists | `backends/*.yaml` |
| 5 | Prompt v1 Compiled | First prompt version written | `prompts/v1.*` |
| 6 | Eval Loop Active | Search state with at least 1 completed round | `outputs/*/search_state.json` parsed, `round >= 1` |
| 7 | Converged | Search state has `converged: true` | `outputs/*/search_state.json` parsed |
| 8 | Holdout Validation | Holdout eval results exist | (future — stub detection) |
| 9 | Final Report | Final report written | (future — stub detection) |

**In-progress detection:** If `scratch/*/phase1_classification.json` or later checkpoints exist but stage 3 is not complete, the checklist reports stage 3 as "in progress" with the checkpoint phase noted.

**Stage status values:**
- `complete` — all artifacts detected
- `in_progress` — partial artifacts detected (e.g., scratch checkpoints)
- `incomplete` — the current actionable stage
- `blocked` — prerequisites not met

The tool returns the **first incomplete stage** as "current" and provides:
- Concrete artifact paths for completed stages (so agents can reference them)
- The exact next action to take
- Which tools and prompts are relevant for the current stage

## 3. `get_pipeline_status` Tool Specification

```python
@mcp.tool()
async def get_pipeline_status() -> str:
    """Check pipeline progress and get guidance on the next step.

    Scans the project directory for pipeline artifacts and returns
    a checklist showing which stages are complete, what artifacts
    exist, and what to do next.

    Call this tool when starting work, when unsure what step comes
    next, or when another tool rejects your call with a precondition
    error.

    Returns:
        JSON with stages, current_stage, next_action, and
        available_tools for the current stage.
    """
```

### Return schema

```json
{
  "stages": [
    {
      "stage": 1,
      "name": "Input Report",
      "status": "complete",
      "artifacts": ["outputs/input_report.md"]
    },
    {
      "stage": 2,
      "name": "Data Validated",
      "status": "complete",
      "artifacts": [
        "data/transformed_routing.jsonl",
        "outputs/data_quality_report.json",
        "outputs/routing_context.json"
      ]
    },
    {
      "stage": 3,
      "name": "Routing Analysis & Split",
      "status": "in_progress",
      "artifacts": [],
      "detail": "Phase 2 checkpoint found at scratch/cda6a91a/phase2_rationale.json"
    }
  ],
  "current_stage": 3,
  "current_stage_name": "Routing Analysis & Split",
  "next_action": "Activate the odysseus_routing_analysis prompt to continue annotation. Phase 2 (rationale generation) is complete — resume from Phase 3 (validation). Inputs: dataset_path=data/transformed_routing.jsonl, routing_context=outputs/routing_context.json",
  "available_tools": [
    "validate_rationale_card_set_tool",
    "prune_registry_tool",
    "stratified_split_tool",
    "create_seed_registry_tool",
    "resolve_registry_tool"
  ],
  "available_prompts": ["odysseus_routing_analysis"]
}
```

### Implementation approach

The tool is a pure function: scan files, check existence, parse minimal JSON where needed (search state for round/converged). No side effects. Located in a new module `odysseus/agents/pipeline_status.py` to keep `mcp.py` thin.

## 4. Precondition Guards

### Error format

All guard errors follow this template:

```
Pipeline precondition not met: <what is missing>.
You are at stage <N> (<name>). <what to do instead>.
Call get_pipeline_status for the full checklist.
```

### Guard table

#### Stage 1 tools (always allowed)

| Tool | Guard |
|------|-------|
| `submit_input_report` | None — entry point |
| `get_pipeline_status` | None — always allowed |
| `optimize_routing_prompt` | None — full pipeline stub |

#### Stage 2 tools — Data Validation

| Tool | Precondition | Checks |
|------|-------------|--------|
| `detect_and_parse_dataset` | Input report exists | `outputs/input_report.md` |
| `transform_dataset` | Input report exists | `outputs/input_report.md` |
| `validate_dataset` | Input report exists | `outputs/input_report.md` |

#### Stage 3 tools — Routing Analysis (Phases 1-3)

| Tool | Precondition | Checks |
|------|-------------|--------|
| `create_seed_registry_tool` | Dataset validated | `outputs/data_quality_report.json` AND `outputs/routing_context.json` |
| `resolve_registry_tool` | Dataset validated | Same |
| `validate_rationale_card_set_tool` | Dataset validated | Same |
| `prune_registry_tool` | Dataset validated | Same |

#### Stage 3 tools — Routing Analysis (Phase 4 only)

| Tool | Precondition | Checks |
|------|-------------|--------|
| `stratified_split_tool` | Rationale cards validated | `scratch/*/phase3_validated.json` exists |

Error: *"Pipeline precondition not met: validated rationale cards not found. The Routing Analysis Agent must complete phases 1-3 (classify, annotate, validate) before splitting. Call get_pipeline_status for the full checklist."*

#### Stage 4-5 tools — Prompt Builder

| Tool | Precondition | Checks |
|------|-------------|--------|
| `init_search_state_tool` | Dataset split complete | Any `outputs/*/dev.jsonl` exists |
| `register_candidate_tool` | Search state initialized | `search_state_id` param resolves to `outputs/<sid>/search_state.json` |
| `record_eval_result_tool` | Search state initialized | Same |
| `advance_round_tool` | Search state initialized | Same |
| `get_search_state_tool` | Search state initialized | Same |
| `filter_holdout_dataset_tool` | Dataset split complete | Any `outputs/*/holdout.jsonl` exists |

#### Stage 5-6 tools — Evaluation

| Tool | Precondition | Checks |
|------|-------------|--------|
| `run_eval` | Prompt exists AND dataset split exists AND backend exists | `prompts/<version>.*` exists, any `outputs/*/dev.jsonl` exists, any `backends/*.yaml` exists |
| `run_holdout_eval` | Search converged | Any `outputs/*/search_state.json` with `converged: true` |

#### Stage 6 tools — Review

| Tool | Precondition | Checks |
|------|-------------|--------|
| `build_review_briefing_tool` | Current-round eval reports exist AND search not converged | Every path in `report_paths` param exists on disk AND `outputs/<sid>/search_state.json` has `converged: false` |
| `record_directive_outcomes_tool` | Review briefing generated for current round | `outputs/<sid>/round_reports/round_<current>.json` exists |

Error for `build_review_briefing_tool`: *"Pipeline precondition not met: not all report files exist for the specified candidates, or the search has already converged. Ensure run_eval has completed for all candidates in this round. Call get_pipeline_status for the full checklist."*

Error for `record_directive_outcomes_tool`: *"Pipeline precondition not met: no review briefing found for the current round. Run build_review_briefing_tool first. Call get_pipeline_status for the full checklist."*

### Implementation approach

A decorator or helper function in `odysseus/agents/pipeline_guards.py`:

```python
def require_artifacts(*paths: str, error_msg: str) -> Callable:
    """Decorator that checks file existence before tool execution."""
    ...
```

For dynamic checks (parsing search state JSON, checking `report_paths` params), the guard logic is inlined in the tool function before delegating to business logic.

## 5. Tool Description Updates

Every tool's docstring gets a stage prefix and precondition note. Format:

```
[Stage N: <stage name>] <existing description>. Requires: <precondition>. Call get_pipeline_status if unsure.
```

Examples:

| Tool | Updated description |
|------|-------------------|
| `detect_and_parse_dataset` | `[Stage 2: Data Validation] Detect the format of a dataset file and parse its schema. Requires: input report submitted. Call get_pipeline_status if unsure.` |
| `create_seed_registry_tool` | `[Stage 3: Routing Analysis] Initialize a vocabulary registry with canonical ambiguity tags. Requires: dataset validated. Call get_pipeline_status if unsure.` |
| `stratified_split_tool` | `[Stage 3: Routing Analysis — Phase 4] Split dataset and card set into dev and holdout partitions. Requires: rationale cards validated (phases 1-3 complete). Call get_pipeline_status if unsure.` |
| `init_search_state_tool` | `[Stage 5: Prompt Builder] Initialize a new prompt-builder search state. Requires: dataset split complete. Call get_pipeline_status if unsure.` |
| `run_eval` | `[Stage 5-6: Eval Loop] Run an evaluation of a prompt version against the dev dataset. Requires: prompt version exists, dataset split complete, backend configured. Call get_pipeline_status if unsure.` |
| `build_review_briefing_tool` | `[Stage 6: Review] Build a ReviewBriefing for the Review Agent. Requires: all candidate eval reports exist for the current round, search not converged. Call get_pipeline_status if unsure.` |
| `submit_input_report` | `[Stage 1: Input] Submit a validated input report to the pipeline. No prerequisites.` |
| `get_pipeline_status` | `Check pipeline progress and get guidance on the next step. Call at any time.` |

## 6. Agent Prompt Updates

Each agent prompt needs updates to:
1. Reference the persisted artifact paths (not just context keys)
2. Mention `get_pipeline_status` as the orientation tool
3. Document what artifacts the agent must write to disk

### User Input Agent (`user_input_system.md`)

Add to Pipeline Handoff section:
- `submit_input_report` now persists the report to `outputs/input_report.md`
- No change to agent behavior — just awareness that the report is persisted

### Data Validation Agent (`data_validation_system.md`)

Add to Phase 2 output:
- After running `validate_dataset`, persist the `DataQualityReport` to `outputs/data_quality_report.json`
- After synthesizing the Routing Context YAML block, persist it to `outputs/routing_context.json`
- These paths are consumed by the Routing Analysis Agent and the pipeline checklist

### Routing Analysis Agent (`routing_analysis_system.md`)

Add to Phase 4 — Split & Output:
- After `stratified_split`, extract the `VocabularyRegistry` from the validated `RationaleCardSet` and write it to `outputs/<hash>/vocabulary_registry.json`
- Update output contract to include `vocabulary_registry_path` pointing to this file

Add to Inputs section:
- `routing_context` can now be read from `outputs/routing_context.json`
- `data_quality_report` can now be read from `outputs/data_quality_report.json`
- `validated_input_report_path` is now at `outputs/input_report.md`

### Prompt Builder Agent (`prompt_builder_system.md`)

Add to Inputs section:
- `routing_context` can be read from `outputs/routing_context.json`
- `vocabulary_registry_path` is at `outputs/<hash>/vocabulary_registry.json`

### All agents — general addition

Add a note to each agent prompt:
> If you are unsure what pipeline stage you are in or what inputs are available, call `get_pipeline_status` before proceeding.

## 7. New Modules

| Module | Purpose |
|--------|---------|
| `odysseus/agents/pipeline_status.py` | `get_pipeline_status` logic — stage detection, artifact scanning, checklist generation |
| `odysseus/agents/pipeline_guards.py` | Guard decorators/helpers — artifact existence checks, error message formatting |

Both are pure functions with no side effects beyond reading the filesystem.

## 8. Summary of All Changes

### New MCP tool
- `get_pipeline_status` — stateless checklist derived from disk artifacts

### Modified MCP tools (add guards + update descriptions)
- `detect_and_parse_dataset` — guard: input report exists
- `transform_dataset` — guard: input report exists
- `validate_dataset` — guard: input report exists; also persist `DataQualityReport` to disk
- `create_seed_registry_tool` — guard: dataset validated
- `resolve_registry_tool` — guard: dataset validated
- `validate_rationale_card_set_tool` — guard: dataset validated
- `prune_registry_tool` — guard: dataset validated
- `stratified_split_tool` — guard: phase3_validated checkpoint exists
- `init_search_state_tool` — guard: dataset split complete
- `register_candidate_tool` — guard: search state exists
- `record_eval_result_tool` — guard: search state exists
- `advance_round_tool` — guard: search state exists
- `get_search_state_tool` — guard: search state exists
- `filter_holdout_dataset_tool` — guard: holdout split exists
- `run_eval` — guard: prompt + split + backend exist
- `run_holdout_eval` — guard: search converged
- `build_review_briefing_tool` — guard: report_paths exist + not converged
- `record_directive_outcomes_tool` — guard: current round briefing exists
- `submit_input_report` — persist report to `outputs/input_report.md`

### Modified agent prompts
- `user_input_system.md` — note persisted report path
- `data_validation_system.md` — persist quality report + routing context to disk
- `routing_analysis_system.md` — persist vocabulary registry; read inputs from disk paths
- `prompt_builder_system.md` — read routing context + registry from disk paths
- All prompts — add `get_pipeline_status` orientation note

### New modules
- `odysseus/agents/pipeline_status.py`
- `odysseus/agents/pipeline_guards.py`

### Documentation updates
- `docs/architecture.md` — add `get_pipeline_status` to MCP surface, update artifact layout
