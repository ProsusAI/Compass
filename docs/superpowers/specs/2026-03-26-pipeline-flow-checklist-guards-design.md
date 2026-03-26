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

## 0. Run Scoping & Directory Structure

### Run ID

Each pipeline execution is scoped to a **run ID** — an 8-character hex string generated when `submit_input_report` is called. The run ID is returned to the caller and must be passed to `get_pipeline_status` (optional) and is embedded in artifact paths.

This allows multiple pipeline runs on the same dataset (e.g., different configurations, re-runs after prompt strategy changes) to coexist without ambiguity.

**Generation:** `uuid.uuid4().hex[:8]` in `submit_input_report`.

### Directory layout

All pipeline artifacts for a run live under `outputs/<run_id>/` in named subfolders:

```
<project_dir>/
├── outputs/
│   └── <run_id>/                                    # Pipeline run scope
│       ├── input/                                   # Stage 1 — User Input Agent
│       │   └── input_report.md
│       ├── validation/                              # Stage 2 — Data Validation Agent
│       │   ├── transformed.jsonl                    # Canonical dataset (fixed path)
│       │   ├── data_quality_report.json
│       │   └── routing_context.json
│       ├── analysis/                                # Stage 3 — Routing Analysis Agent
│       │   ├── validation_report.json               # Written after Phase 3 — signals cards validated
│       │   ├── dev.jsonl
│       │   ├── holdout.jsonl
│       │   ├── dev_rationale_card_set.json
│       │   ├── holdout_rationale_card_set.json
│       │   ├── split_report.json
│       │   └── vocabulary_registry.json
│       ├── prompts/                                  # Stage 5 — Prompt versions (scoped to run)
│       │   ├── v1.txt
│       │   ├── v2.txt
│       │   └── ...
│       ├── search/                                  # Stage 5+ — Prompt Builder search state
│       │   ├── search_state.json
│       │   ├── pending_candidates.json
│       │   ├── round_reports/
│       │   │   ├── round_1.json
│       │   │   └── ...
│       │   ├── directive_history.json
│       │   └── mutation_log.json
│       └── eval/                                    # Stage 5+ — Eval Runner output
│           ├── results.jsonl
│           └── report.json
├── backends/                                        # Backend profiles (shared across runs)
│   └── <label>.yaml
└── scratch/                                         # Routing analysis checkpoints (temp)
    └── <dataset_hash>/
        ├── phase1_classification.json
        ├── phase2_rationale.json
        └── phase3_validated.json
```

Named subfolders (`input/`, `validation/`, `analysis/`, `search/`, `eval/`) eliminate the ambiguity between dataset hashes and search state IDs that previously shared the `outputs/` namespace.

### `run_id` propagation

The `run_id` is the pipeline-wide scoping key. It replaces `search_state_id` as the directory key and replaces `output_path`/`output_dir` parameters where applicable.

**How tools obtain `run_id`:**

All tools that read or write run-scoped artifacts gain a `run_id` parameter. The `run_id` is generated once by `submit_input_report` and passed explicitly by the orchestrating agent to every subsequent tool call.

| Tool | Parameter change |
|------|-----------------|
| `submit_input_report` | Returns `run_id` in response (generator). Optional `bootstrap_from_run_id` to copy seed prompt |
| `transform_dataset` | Remove `output_path`, add `run_id`. Writes to `outputs/<run_id>/validation/transformed.jsonl` |
| `validate_dataset` | Add `run_id`. Persists report to `outputs/<run_id>/validation/` |
| `detect_and_parse_dataset` | No change (reads source file, not run-scoped) |
| `stratified_split_tool` | Add `run_id`. Writes to `outputs/<run_id>/analysis/` instead of `outputs/<dataset_hash>/` |
| `init_search_state_tool` | Add `run_id`. Writes to `outputs/<run_id>/search/` instead of `outputs/<search_state_id>/` |
| `register_candidate_tool` | Replace `search_state_id` with `run_id`. Resolves state from `outputs/<run_id>/search/` |
| `record_eval_result_tool` | Replace `search_state_id` with `run_id`. Same path resolution |
| `advance_round_tool` | Replace `search_state_id` with `run_id`. Same path resolution |
| `get_search_state_tool` | Replace `search_state_id` with `run_id`. Same path resolution |
| `filter_holdout_dataset_tool` | Add `run_id`. Reads from `outputs/<run_id>/analysis/` |
| `run_eval` | Replace `search_state_id` with `run_id`. Reads search state from `outputs/<run_id>/search/` |
| `run_holdout_eval` | Add `run_id`. Reads search state from `outputs/<run_id>/search/` |
| `build_review_briefing_tool` | Replace `search_state_id` with `run_id`. Replace `output_dir` — all paths resolve under `outputs/<run_id>/search/` |
| `record_directive_outcomes_tool` | Replace `search_state_id` with `run_id`. Replace `output_dir` — same path resolution |
| `get_pipeline_status` | Optional `run_id`. Falls back to most recent run |
| `create_seed_registry_tool` | No change (returns JSON, not file-scoped) |
| `resolve_registry_tool` | No change (reads from `outputs/`, but could scope to `run_id` in future) |
| `validate_rationale_card_set_tool` | No change (pure validation, no file I/O) |
| `prune_registry_tool` | No change (pure transformation, no file I/O) |

**The `search_state_id` field** remains inside `SearchState` as an internal identifier but no longer determines the storage path. The path is always `outputs/<run_id>/search/search_state.json`.

### Impact on existing modules

**`prompt_builder_search_ops.py`:** Path helpers (`_state_path`, `_pending_path`) change from `output_dir / search_state_id / ...` to `output_dir / run_id / "search" / ...`. All public functions (`init_search_state`, `register_candidate`, `record_eval_result`, `advance_round`, `get_search_state`) replace `search_state_id` with `run_id` in their signatures.

**`review_ops.py`:** Same migration. Functions `load_directive_history`, `save_directive_history`, `load_mutation_log`, `save_mutation_log`, `load_round_reports`, `save_round_report` replace `search_state_id` + `output_dir` with `run_id`. Paths change from `outputs/<search_state_id>/directive_history.json` to `outputs/<run_id>/search/directive_history.json` (and similarly for `mutation_log.json` and `round_reports/`).

**`review_preprocessor.py`:** `build_review_briefing` receives `run_id` instead of `search_state_id`. Internal calls to search_ops and review_ops pass `run_id`.

**`prompts/manager.py` (`FilePromptManager`):** The prompts directory changes from a shared `prompts/` at project root to `outputs/<run_id>/prompts/`. The `FilePromptManager` constructor receives the run-scoped prompts directory. The `EvalRunnerAgent` and any tool that loads prompt text must use the run-scoped path.

### Scratch directory scoping

The `scratch/` directory continues to use `<dataset_hash>` as its key (not `run_id`), because scratch checkpoints are content-addressed — resuming annotation on the same dataset should find existing checkpoints regardless of which run initiated them. This is an intentional asymmetry: scratch is for mid-stage recovery, not run isolation.

The `stratified_split_tool` guard does **not** check scratch — it checks the run-scoped `outputs/<run_id>/analysis/validation_report.json` written after Phase 3 passes. Scratch checkpoints remain internal to the Routing Analysis Agent's resume logic.

## 1. Persistence Fixes

### Problem

Stages 1 (User Input) and 2 (Data Validation) don't persist structured artifacts to disk. The checklist can't detect completion of these stages, and downstream agents can't find their outputs without conversation context.

### Changes

| Gap | What to persist | Path | Writer | Consumers |
|-----|----------------|------|--------|-----------|
| A | Input report (Markdown) with dataset path + problem description | `outputs/<run_id>/input/input_report.md` | `submit_input_report` tool | Data Validation Agent, Routing Analysis Agent |
| B | `DataQualityReport` | `outputs/<run_id>/validation/data_quality_report.json` | `validate_dataset` tool | Routing Analysis Agent |
| C | `RoutingContext` | `outputs/<run_id>/validation/routing_context.json` | `validate_dataset` tool (or Data Validation Agent after synthesizing it) | Routing Analysis Agent, Prompt Builder Agent |
| D | `VocabularyRegistry` (standalone) | `outputs/<run_id>/analysis/vocabulary_registry.json` | Routing Analysis Agent during Phase 4 | Prompt Builder Agent |
| E | Routing analysis validation report | `outputs/<run_id>/analysis/validation_report.json` | Routing Analysis Agent after Phase 3 | `stratified_split_tool` guard, `get_pipeline_status` |

**Gap A — `submit_input_report`:**

Currently a stub that returns a string. Change to:
1. Generate an 8-char `run_id`
2. Create `outputs/<run_id>/input/` directory
3. Write the report Markdown to `outputs/<run_id>/input/input_report.md`
4. Return confirmation with the `run_id` and persisted path

**Gap B — `validate_dataset`:**

Currently returns the `DataQualityReport` as JSON in the tool response only. Change to:
1. Accept `run_id` parameter to scope the output
2. Write the report to `outputs/<run_id>/validation/data_quality_report.json`
3. Return the JSON as before (backward-compatible)

**Gap C — `routing_context`:**

The `RoutingContext` is synthesized by the Data Validation Agent (LLM-driven) as a YAML block in its conversation output. To persist it:
1. The Data Validation Agent writes it to `outputs/<run_id>/validation/routing_context.json` after synthesizing it
2. This is an agent-level change (prompt update), not a tool change

Alternative: add a `save_routing_context` tool that the Data Validation Agent calls. This is more explicit and verifiable by the guard system.

**Gap D — `vocabulary_registry.json`:**

The registry is embedded in each `RationaleCardSet`, but the Prompt Builder expects `vocabulary_registry_path` as a separate file. During Routing Analysis Phase 4:
1. Extract the registry from the validated `RationaleCardSet`
2. Write it to `outputs/<run_id>/analysis/vocabulary_registry.json`
3. This happens alongside the existing `stratified_split_tool` call — either in the tool itself or as a separate agent action

**Gap E — `validation_report.json`:**

The `stratified_split_tool` guard needs to verify that routing analysis phases 1-3 are complete within the current run. Currently, phase completion is only tracked in scratch checkpoints (`scratch/<dataset_hash>/phase3_validated.json`), which are content-addressed and not run-scoped.

Add a new artifact: after Phase 3 validation passes, the Routing Analysis Agent writes a validation report to `outputs/<run_id>/analysis/validation_report.json`. This file contains:
- `dataset_hash`: the content hash of the validated dataset
- `card_count`: number of rationale cards validated
- `validation_checks_passed`: number of checks that passed
- `validated_at`: ISO timestamp

This report is the run-scoped signal that phases 1-3 are complete and the dataset is ready for splitting. The `stratified_split_tool` guard checks for this file instead of scanning scratch directories.

## 2. Pipeline Stages & Detection Logic

The `get_pipeline_status` tool scans the project directory and checks for artifacts at known paths within a run scope.

| # | Stage | Detection | Artifacts checked |
|---|-------|-----------|-------------------|
| 1 | Input Report | `outputs/<run_id>/input/input_report.md` exists | Input report |
| 2 | Data Validated | Quality report AND routing context AND transformed dataset exist | `outputs/<run_id>/validation/data_quality_report.json`, `outputs/<run_id>/validation/routing_context.json`, `outputs/<run_id>/validation/transformed.jsonl` |
| 3 | Routing Analysis & Split | Dev split AND holdout split AND rationale cards AND vocabulary registry exist | `outputs/<run_id>/analysis/dev.jsonl`, `outputs/<run_id>/analysis/holdout.jsonl`, `outputs/<run_id>/analysis/dev_rationale_card_set.json`, `outputs/<run_id>/analysis/vocabulary_registry.json` |
| 4 | Backend Configured | At least one backend profile exists | `backends/*.yaml` |
| 5 | Prompt v1 Compiled | First prompt version written | `outputs/<run_id>/prompts/v1.*` |
| 6 | Eval Loop Active | Search state with at least 1 completed round | `outputs/<run_id>/search/search_state.json` parsed, `round >= 1` |
| 7 | Converged | Search state has `converged: true` | `outputs/<run_id>/search/search_state.json` parsed |
| 8 | Holdout Validation | Holdout eval results exist | (future — stub detection) |
| 9 | Final Report | Final report written | (future — stub detection) |

**Run discovery:** When `run_id` is not provided, the tool scans `outputs/*/input/input_report.md` and uses the most recently modified run. When `run_id` is provided, the tool checks only that run's artifacts.

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
async def get_pipeline_status(run_id: str | None = None) -> str:
    """Check pipeline progress and get guidance on the next step.

    Scans the project directory for pipeline artifacts and returns
    a checklist showing which stages are complete, what artifacts
    exist, and what to do next.

    Call this tool when starting work, when unsure what step comes
    next, or when another tool rejects your call with a precondition
    error.

    Args:
        run_id: Optional pipeline run ID. If omitted, uses the most
                recent run found in outputs/. Pass the run_id returned
                by submit_input_report for explicit scoping.

    Returns:
        JSON with run_id, stages, current_stage, next_action, and
        available_tools for the current stage.
    """
```

### Return schema

```json
{
  "run_id": "a1b2c3d4",
  "stages": [
    {
      "stage": 1,
      "name": "Input Report",
      "status": "complete",
      "artifacts": ["outputs/a1b2c3d4/input/input_report.md"]
    },
    {
      "stage": 2,
      "name": "Data Validated",
      "status": "complete",
      "artifacts": [
        "outputs/a1b2c3d4/validation/transformed.jsonl",
        "outputs/a1b2c3d4/validation/data_quality_report.json",
        "outputs/a1b2c3d4/validation/routing_context.json"
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
  "next_action": "Activate the odysseus_routing_analysis prompt to continue annotation. Phase 2 (rationale generation) is complete — resume from Phase 3 (validation). Inputs: dataset_path=outputs/a1b2c3d4/validation/transformed.jsonl, routing_context=outputs/a1b2c3d4/validation/routing_context.json",
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
| `submit_input_report` | None — entry point, generates the `run_id` |
| `get_pipeline_status` | None — always allowed |
| `optimize_routing_prompt` | None — full pipeline stub. When implemented, must internally enforce the same stage sequencing. |

#### Stage 2 tools — Data Validation

| Tool | Precondition | Checks |
|------|-------------|--------|
| `detect_and_parse_dataset` | Input report exists | `outputs/<run_id>/input/input_report.md` |
| `transform_dataset` | Input report exists | Same |
| `validate_dataset` | Input report exists | Same |

#### Stage 3 tools — Routing Analysis (Phases 1-3)

| Tool | Precondition | Checks |
|------|-------------|--------|
| `create_seed_registry_tool` | Dataset validated | `outputs/<run_id>/validation/data_quality_report.json` AND `outputs/<run_id>/validation/routing_context.json` |
| `resolve_registry_tool` | Dataset validated | Same |
| `validate_rationale_card_set_tool` | Dataset validated | Same |
| `prune_registry_tool` | Dataset validated | Same |

#### Stage 3 tools — Routing Analysis (Phase 4 only)

| Tool | Precondition | Checks |
|------|-------------|--------|
| `stratified_split_tool` | Rationale cards validated (within this run) | `outputs/<run_id>/analysis/validation_report.json` exists |

Error: *"Pipeline precondition not met: routing analysis validation report not found at outputs/<run_id>/analysis/validation_report.json. The Routing Analysis Agent must complete phases 1-3 (classify, annotate, validate) before splitting. Call get_pipeline_status for the full checklist."*

#### Stage 5 tools — Prompt Builder

| Tool | Precondition | Checks |
|------|-------------|--------|
| `init_search_state_tool` | Dataset split complete | `outputs/<run_id>/analysis/dev.jsonl` exists |
| `register_candidate_tool` | Search state initialized | `outputs/<run_id>/search/search_state.json` exists |
| `record_eval_result_tool` | Search state initialized | Same |
| `advance_round_tool` | Search state initialized | Same |
| `get_search_state_tool` | Search state initialized | Same |
| `filter_holdout_dataset_tool` | Dataset split complete | `outputs/<run_id>/analysis/holdout.jsonl` exists |

#### Stage 5-6 tools — Evaluation

| Tool | Precondition | Checks |
|------|-------------|--------|
| `run_eval` | Prompt exists AND dataset split exists AND backend exists | `outputs/<run_id>/prompts/<version>.*` exists, `outputs/<run_id>/analysis/dev.jsonl` exists, any `backends/*.yaml` exists |
| `run_holdout_eval` | Search converged | `outputs/<run_id>/search/search_state.json` with `converged: true` |

#### Stage 6 tools — Review

| Tool | Precondition | Checks |
|------|-------------|--------|
| `build_review_briefing_tool` | Current-round eval reports exist AND search not converged | Every path in `report_paths` param exists on disk AND `outputs/<run_id>/search/search_state.json` has `converged: false` |
| `record_directive_outcomes_tool` | Review briefing generated for current round | `outputs/<run_id>/search/round_reports/round_<current>.json` exists |

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
| `detect_and_parse_dataset` | `[Stage 2: Data Validation] Detect the format of a dataset file and parse its schema. Requires: input report submitted (run_id). Call get_pipeline_status if unsure.` |
| `create_seed_registry_tool` | `[Stage 3: Routing Analysis] Initialize a vocabulary registry with canonical ambiguity tags. Requires: dataset validated. Call get_pipeline_status if unsure.` |
| `stratified_split_tool` | `[Stage 3: Routing Analysis — Phase 4] Split dataset and card set into dev and holdout partitions. Requires: rationale cards validated (phases 1-3 complete). Call get_pipeline_status if unsure.` |
| `init_search_state_tool` | `[Stage 5: Prompt Builder] Initialize a new prompt-builder search state. Requires: dataset split complete. Call get_pipeline_status if unsure.` |
| `run_eval` | `[Stage 5-6: Eval Loop] Run an evaluation of a prompt version against the dev dataset. Requires: prompt version exists, dataset split complete, backend configured. Call get_pipeline_status if unsure.` |
| `build_review_briefing_tool` | `[Stage 6: Review] Build a ReviewBriefing for the Review Agent. Requires: all candidate eval reports exist for the current round, search not converged. Call get_pipeline_status if unsure.` |
| `submit_input_report` | `[Stage 1: Input] Submit a validated input report to the pipeline. No prerequisites. Returns a run_id for scoping all subsequent tools.` |
| `get_pipeline_status` | `Check pipeline progress and get guidance on the next step. Call at any time. Accepts optional run_id.` |

## 6. Agent Prompt Updates

Each agent prompt needs updates to:
1. Reference the persisted artifact paths within the `outputs/<run_id>/` structure
2. Mention `get_pipeline_status` as the orientation tool
3. Document what artifacts the agent must write to disk
4. Accept and propagate the `run_id`

### User Input Agent (`user_input_system.md`)

Add to conversation flow:
- Before collecting the problem spec, check if previous runs exist (scan `outputs/*/input/input_report.md`)
- If previous runs exist, ask the user: *"I found existing pipeline runs. Would you like to start fresh, or bootstrap from an existing run's prompt?"*
  - **Start fresh:** proceed normally, `submit_input_report` generates a new `run_id`
  - **Bootstrap:** the user picks a run, and its best prompt version is copied into the new run's `outputs/<new_run_id>/prompts/` as a starting point for the Prompt Builder

Add to Pipeline Handoff section:
- `submit_input_report` now generates a `run_id` and persists the report to `outputs/<run_id>/input/input_report.md`
- If bootstrapping, also accepts an optional `bootstrap_from_run_id` to copy the seed prompt
- The `run_id` is returned and must be communicated to all downstream agents

### Data Validation Agent (`data_validation_system.md`)

Add to Phase 1 — Ingestion & Mapping:
- `transform_dataset` no longer accepts a user-provided `output_path`. It writes to `outputs/<run_id>/validation/transformed.jsonl`
- The `run_id` is passed through from the User Input Agent

Add to Phase 2 output:
- After running `validate_dataset`, the report is persisted to `outputs/<run_id>/validation/data_quality_report.json`
- After synthesizing the Routing Context YAML block, persist it to `outputs/<run_id>/validation/routing_context.json`
- These paths are consumed by the Routing Analysis Agent and the pipeline checklist

### Routing Analysis Agent (`routing_analysis_system.md`)

Add to Phase 3 — Validation & Fix Loop:
- After all validation checks pass, write `outputs/<run_id>/analysis/validation_report.json` containing `dataset_hash`, `card_count`, `validation_checks_passed`, and `validated_at`
- This report is the run-scoped signal that phases 1-3 are complete and gates the `stratified_split_tool`

Add to Phase 4 — Split & Output:
- `stratified_split_tool` writes to `outputs/<run_id>/analysis/` instead of `outputs/<dataset_hash>/`
- After `stratified_split`, extract the `VocabularyRegistry` from the validated `RationaleCardSet` and write it to `outputs/<run_id>/analysis/vocabulary_registry.json`
- Update output contract to include `vocabulary_registry_path` pointing to this file

Add to Inputs section:
- `routing_context` is read from `outputs/<run_id>/validation/routing_context.json`
- `data_quality_report` is read from `outputs/<run_id>/validation/data_quality_report.json`
- `validated_input_report_path` is at `outputs/<run_id>/input/input_report.md`
- `dataset_path` is at `outputs/<run_id>/validation/transformed.jsonl`

### Prompt Builder Agent (`prompt_builder_system.md`)

Add to Inputs section:
- `routing_context` is read from `outputs/<run_id>/validation/routing_context.json`
- `vocabulary_registry_path` is at `outputs/<run_id>/analysis/vocabulary_registry.json`
- `dev_jsonl_path` is at `outputs/<run_id>/analysis/dev.jsonl`
- `dev_rationale_card_set_path` is at `outputs/<run_id>/analysis/dev_rationale_card_set.json`
- Search state is stored at `outputs/<run_id>/search/`
- Prompt versions are written to `outputs/<run_id>/prompts/v1.txt`, `v2.txt`, etc.
- If a bootstrap prompt exists (copied from a prior run), use it as the starting point for v1 compilation

### Review Agent (`review_agent_system.md`)

Add orientation note:
- All search state, round reports, and directive history are in `outputs/<run_id>/search/`
- Call `get_pipeline_status` if unsure about available data

### Backend Setup Agent (`backend_setup_system.md`)

Add orientation note:
- Backend profiles remain at `backends/<label>.yaml` (shared across runs)
- Call `get_pipeline_status` if unsure about pipeline state

### All agents — general addition

Add a note to each agent prompt:
> If you are unsure what pipeline stage you are in or what inputs are available, call `get_pipeline_status` with the current `run_id` before proceeding.

## 7. New Modules

| Module | Purpose |
|--------|---------|
| `odysseus/agents/pipeline_status.py` | `get_pipeline_status` logic — stage detection, artifact scanning, checklist generation |
| `odysseus/agents/pipeline_guards.py` | Guard decorators/helpers — artifact existence checks, error message formatting |

Both are pure functions with no side effects beyond reading the filesystem.

## 8. Implementation Ordering

Persistence fixes (Section 1) must be implemented before the checklist tool (Section 3), since the checklist depends on artifacts that do not yet exist on disk. Recommended order:

1. **Directory structure migration** — update `stratified_split_tool`, `submit_input_report`, `validate_dataset`, and `prompt_builder_search_ops` to use `outputs/<run_id>/<stage>/` paths
2. **Persistence fixes (Gaps A-D)** — implement artifact writing in `submit_input_report`, `validate_dataset`, and routing analysis Phase 4
3. **`transform_dataset` fixed output path** — remove user-provided `output_path`, write to `outputs/<run_id>/validation/transformed.jsonl`
4. **`pipeline_status.py`** — implement `get_pipeline_status` tool
5. **`pipeline_guards.py`** — implement guard decorators and inline checks
6. **Wire guards into `mcp.py`** — apply guards to all tools
7. **Tool description updates** — add stage prefixes and precondition notes
8. **Agent prompt updates** — update all 7 agent prompts with new paths and orientation notes
9. **Documentation** — update `docs/architecture.md` with new directory layout, add 6 missing search-loop tools to MCP surface table

## 9. Summary of All Changes

### New MCP tool
- `get_pipeline_status` — stateless checklist derived from disk artifacts, scoped by `run_id`

### Modified MCP tools (add guards + update descriptions + directory changes)
- `submit_input_report` — generate `run_id`, persist report to `outputs/<run_id>/input/input_report.md`, optional `bootstrap_from_run_id` to copy seed prompt
- `transform_dataset` — remove `output_path` param, write to `outputs/<run_id>/validation/transformed.jsonl`
- `validate_dataset` — guard: input report exists; persist `DataQualityReport` to `outputs/<run_id>/validation/`
- `detect_and_parse_dataset` — guard: input report exists
- `create_seed_registry_tool` — guard: dataset validated
- `resolve_registry_tool` — guard: dataset validated
- `validate_rationale_card_set_tool` — guard: dataset validated
- `prune_registry_tool` — guard: dataset validated
- `stratified_split_tool` — guard: `outputs/<run_id>/analysis/validation_report.json` exists; write to `outputs/<run_id>/analysis/`
- `init_search_state_tool` — guard: dataset split complete; write to `outputs/<run_id>/search/`
- `register_candidate_tool` — guard: search state exists (scoped to run)
- `record_eval_result_tool` — guard: search state exists (scoped to run)
- `advance_round_tool` — guard: search state exists (scoped to run)
- `get_search_state_tool` — guard: search state exists (scoped to run)
- `filter_holdout_dataset_tool` — guard: holdout split exists
- `run_eval` — guard: prompt + split + backend exist
- `run_holdout_eval` — guard: search converged
- `build_review_briefing_tool` — guard: report_paths exist + not converged
- `record_directive_outcomes_tool` — guard: current round briefing exists

### Modified agent prompts
- `user_input_system.md` — note `run_id` generation, persisted report path, bootstrap-from-existing-run option
- `data_validation_system.md` — persist quality report + routing context to disk; fixed transform output path
- `routing_analysis_system.md` — persist vocabulary registry; read inputs from `outputs/<run_id>/` paths
- `prompt_builder_system.md` — read all inputs from `outputs/<run_id>/` paths; prompts in `outputs/<run_id>/prompts/`; search state in `outputs/<run_id>/search/`
- `review_agent_system.md` — add `get_pipeline_status` orientation note
- `backend_setup_system.md` — add `get_pipeline_status` orientation note
- All prompts — add `get_pipeline_status` orientation note with `run_id`

### New modules
- `odysseus/agents/pipeline_status.py`
- `odysseus/agents/pipeline_guards.py`

### Documentation updates
- `docs/architecture.md` — add `get_pipeline_status` to MCP surface, update directory layout, add 6 missing search-loop tools to tools table
