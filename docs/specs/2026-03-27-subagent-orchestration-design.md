# Sub-agent Orchestration via `get_pipeline_status`

**Date:** 2026-03-27
**Status:** Approved

---

## Problem

The orchestrating agent runs all pipeline stages inline, accumulating context across every stage. This grows the context window unnecessarily and means the orchestrator — not the stage agent — ends up doing work that belongs inside a focused, stage-specific context.

---

## Goal

Instruct the orchestrating agent to spawn a sub-agent for each pipeline stage, keeping each agent's context clean and bounded. The instruction must be self-contained and machine-followable, embedded in the tool the orchestrator already calls: `get_pipeline_status`.

---

## Design

### New field: `subagent_instruction`

`get_pipeline_status` gains one new field. For stages that have an agent prompt, it is a fully self-contained prose string:

```
Spawn a sub-agent for Stage N: <Stage Name>. Activate the `<prompt_name>` MCP prompt — it contains the agent's full workflow. The agent may call these tools: get_pipeline_status, <tool1>, <tool2>, .... Do not call these tools yourself. After the sub-agent exits, call get_pipeline_status to verify stage completion.
```

For stages without a prompt (stages 8–9: stubs), `subagent_instruction` is `null`. Stage 4 has the `odysseus_backend_setup` prompt but no callable tools — its instruction activates the prompt only.

For null-instruction stages (7, 8, 9), the orchestrator calls any available tools directly rather than delegating to a sub-agent.

### `get_pipeline_status` is always in tool scope

`get_pipeline_status` is included in every sub-agent's callable tool list. Some agents (e.g. Routing Analysis) have inner phases; they self-check progress via `get_pipeline_status` without needing orchestrator intervention.

### Implementation

`_NEXT_ACTION` in `pipeline_status.py` expands from a 3-tuple to a 4-tuple:

```python
(next_action_text, tools, prompts, subagent_instruction)
```

`_next_action_for_stage` renders the 4th element and includes it in the response dict as `subagent_instruction`.

The `subagent_instruction` string is composed from the existing `activate_prompt` and `available_tools` values — it is not independently maintained.

**Important:** Several existing `_NEXT_ACTION` tool lists are incomplete relative to the full set of stage-scoped tools in `mcp.py`. These must be corrected as part of this change — not just extended with the 4th tuple element:

- Stage 2: expand from `["validate_dataset", "transform_dataset"]` to `["validate_dataset", "detect_and_parse_dataset", "transform_dataset", "save_routing_context"]`
- Stage 3: expand from `["stratified_split_tool", "create_seed_registry_tool"]` to the full five-tool set in the stage mapping table
- Stage 6: expand from `["init_search_state_tool", "advance_round_tool"]` to the full eight-tool set in the stage mapping table

**Call sites:** `_next_action_for_stage` is called in two places in `get_pipeline_status`:
1. The main return path (line ~233)
2. The early-return "no runs found" path (line ~176)

Both unpack the tuple as `action, tools, prompts = ...` and must be updated to `action, tools, prompts, subagent_instruction = ...`.

### Stage mapping

| Stage | Prompt | Stage tools (excluding `get_pipeline_status`) | `subagent_instruction` |
|---|---|---|---|
| 1: Input Report | `odysseus_routing_input` | `submit_input_report` | non-null |
| 2: Data Validated | `odysseus_data_validation` | `validate_dataset`, `detect_and_parse_dataset`, `transform_dataset`, `save_routing_context` | non-null |
| 3: Routing Analysis & Split | `odysseus_routing_analysis` | `create_seed_registry_tool`, `resolve_registry_tool`, `validate_rationale_card_set_tool`, `prune_registry_tool`, `stratified_split_tool` | non-null |
| 4: Backend Configured | `odysseus_backend_setup` | _(none — manual setup, prompt only)_ | non-null |
| 5: Prompt v1 Compiled | `odysseus_prompt_builder` | `optimize_routing_prompt` | non-null |
| 6: Eval Loop Active | `odysseus_review_agent` | `init_search_state_tool`, `register_candidate_tool`, `record_eval_result_tool`, `advance_round_tool`, `get_search_state_tool`, `run_eval`, `build_review_briefing_tool`, `record_directive_outcomes_tool` | non-null |
| 7: Converged | _(none)_ | `run_holdout_eval`, `filter_holdout_dataset_tool` | null — orchestrator calls tools directly |
| 8: Holdout Validation | _(stub)_ | _(none)_ | null |
| 9: Final Report | _(stub)_ | _(none)_ | null |

Note: `get_pipeline_status` is always prepended to the tool list in every non-null instruction, regardless of stage.

**Stage numbering in `mcp.py` docstrings:** Tool docstrings in `mcp.py` use a compact 7-stage numbering that predates the current 9-stage pipeline (it does not count Backend Configured as a numbered stage). The mapping is:

| `mcp.py` docstring label | Pipeline stage (9-stage) |
|---|---|
| `[Stage 1: Input]` | Stage 1 |
| `[Stage 2: Data Validation]` | Stage 2 |
| `[Stage 3: Routing Analysis]` | Stage 3 |
| `[Stage 4: Search Init]` | Stage 6 (`init_search_state_tool`) |
| `[Stage 5: Prompt Search/Evaluation]` | Stage 6 (search + eval tools) |
| `[Stage 6: Review]` | Stage 6 (review tools) |
| `[Stage 7: Holdout Validation]` | Stage 7 |

These docstring labels should be corrected to match the 9-stage numbering as part of this change.

### Orchestrator protocol

```
1. Call get_pipeline_status
2. If subagent_instruction is non-null → spawn sub-agent with that instruction
   (orchestrator does NOT call stage tools itself)
3. Wait for sub-agent to complete
4. Call get_pipeline_status again to verify and get the next instruction
5. If subagent_instruction is null → orchestrator calls any available_tools directly
6. Repeat until pipeline complete
```

---

## What does not change

- `activate_prompt`, `available_tools`, `next_action` remain in the response.
- `subagent_instruction` is additive — it composes from the existing fields.
- No changes to any agent system prompt.
- No changes to any MCP tool signatures.

---

## Files affected

- `odysseus/agents/pipeline_status.py` — `_NEXT_ACTION` 4-tuple (with corrected tool lists for stages 2, 3, 6), `_next_action_for_stage`, both call sites in `get_pipeline_status`
- `odysseus/mcp.py` — `get_pipeline_status` tool docstring; `[Stage N:]` prefix corrections on `init_search_state_tool`, `register_candidate_tool`, `record_eval_result_tool`, `advance_round_tool`, `get_search_state_tool`, `run_eval`, `build_review_briefing_tool`, `record_directive_outcomes_tool`
