# `odysseus/mcp/`

MCP server package. Thin adapter layer — each tool delegates to an agent module that owns all business logic. The MCP layer only translates between tool parameters/return values and agent context dicts.

## Package structure

| Module | Description |
|--------|-------------|
| [`server.py`](server.py) | FastMCP app instance, `STAGE_REGISTRY`, `_active_stage`, `_filtered_list_tools`, shared helpers (`_load_text`, `_load_examples`, `_write_jsonl`) |
| [`orchestrator_tools.py`](orchestrator_tools.py) | `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage` |
| [`input_report_tools.py`](input_report_tools.py) | `submit_input_report` |
| [`data_validation_tools.py`](data_validation_tools.py) | `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context` |
| [`backend_setup_tools.py`](backend_setup_tools.py) | `get_default_pricing` |
| [`prompt_building_tools.py`](prompt_building_tools.py) | `init_search_state_tool` (no `algorithm`/`algorithm_state` — hardcoded per branch), `register_candidate_tool`, `run_eval`, `run_batch_eval`, `record_eval_result_tool`, `advance_step_tool`, `get_search_state_tool`, `save_prompt_tool`, `get_child_variants_tool`, `get_edit_directives_tool` |
| [`review_tools.py`](review_tools.py) | `build_review_briefing_tool`, `record_directive_outcomes_tool` |
| [`final_report_tools.py`](final_report_tools.py) | `filter_holdout_dataset_tool`, `run_holdout_eval`, `build_final_report_briefing_tool`, `save_final_report` |
| [`resources.py`](resources.py) | MCP resource definitions (`odysseus://agents/...`, `odysseus://backends/...`) |
| [`prompts.py`](prompts.py) | MCP prompt definitions (`odysseus_routing_input`, `odysseus_data_validation`, etc.) |

## Stage registry and tool filtering

`STAGE_REGISTRY` in `server.py` maps each stage name to the list of tools visible to the sub-agent operating in that stage. The module-level `_active_stage` variable starts as `"orchestrator"` at server startup.

`list_tools` is patched at import time to filter by `STAGE_REGISTRY[_active_stage]`. When `_active_stage` is `None`, all tools are returned (filtering disabled).

The orchestrator controls scoping via two tools:

1. **`start_stage(run_id, stage)`** — sets `_active_stage` to `stage` before spawning a sub-agent.
2. **`complete_stage(run_id)`** — resets `_active_stage` to `"orchestrator"` after the sub-agent finishes.

| Stage name | Tools | Notes |
|---|---|---|
| `orchestrator` | `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage` | |
| `input_report` | `submit_input_report`, `get_pipeline_status` | |
| `data_validation` | `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `get_pipeline_status` | |
| `backend_setup` | `get_default_pricing`, `get_pipeline_status` | |
| `prompt_building` | `init_search_state_tool`, `register_candidate_tool`, `run_eval`, `run_batch_eval`, `record_eval_result_tool`, `advance_step_tool`, `get_search_state_tool`, `get_edit_directives_tool`, `get_child_variants_tool`, `save_prompt_tool`, `get_pipeline_status` | |
| `review_cold` | `build_review_briefing_tool`, `record_directive_outcomes_tool`, `get_search_state_tool`, `get_pipeline_status` | No `get_prompt_text_tool` / `query_holdout_examples_tool` — cold sub-agents have no candidate to inspect |
| `review` | `build_review_briefing_tool`, `record_directive_outcomes_tool`, `query_holdout_examples_tool`, `get_prompt_text_tool`, `get_search_state_tool`, `run_eval`, `get_pipeline_status` | Steady-review toolbelt; sub-agents call `record_directive_outcomes_tool` (single-slot for hill-climb; pass `trajectory_id=<N>` for EMOSA K-way fanout) |
| `calibration` | `build_review_briefing_tool`, `record_directive_outcomes_tool`, `get_search_state_tool`, `init_search_state_tool`, `register_candidate_tool`, `run_batch_eval`, `record_eval_result_tool`, `advance_step_tool`, `save_prompt_tool`, `get_child_variants_tool`, `get_edit_directives_tool`, `signal_eval_complete_tool`, `get_pipeline_status` | EMOSA-only — K-seed calibration phase; no `get_prompt_text_tool` / `query_holdout_examples_tool` |
| `final_report` | `filter_holdout_dataset_tool`, `run_holdout_eval`, `build_final_report_briefing_tool`, `save_final_report`, `get_pipeline_status` | |

### `record_directive_outcomes_tool` — recording review result (variants, loop signal, ranking, promotions, regression guards)

Records the Review Agent's output fields (`loop_signal`, `child_variants`, `candidate_ranking`, `promotion_decisions`, `regression_guards`). Directive outcomes (`directive_history_update`) are no longer passed here — they are synthesized wholly in code from `batch_outcomes` by `build_review_briefing_tool`. No `directive_history.json` file is persisted.

When `trajectory_id: int` is passed (EMOSA K-way fanout), the tool writes per-trajectory child variant files (`child_variants_t<N>.json`) instead of the single-slot `child_variants.json` sentinel, and calls `record_trajectory_dispatched` to mark the slot as complete. Variant ids use the format `cv-{round}-t{trajectory_id}-{i}`. Passing `trajectory_id=None` (default) keeps the original single-slot behaviour for all other strategies.

### `get_child_variants_tool` / `get_edit_directives_tool` — per-trajectory source resolution (EMOSA)

Both readers prefer per-trajectory files when present: if any `child_variants_t<N>.json` exist under `outputs/<run_id>/search/`, they call `load_all_trajectory_child_variants` and return variants sorted by `trajectory_id`. Otherwise they fall back to the single-slot `child_variants.json` written during calibration and non-EMOSA strategies.

## Model routing hints (Claude Code orchestrators)

`optimize_routing_prompt` embeds a `MODEL ROUTING` block in its briefing, and each `get_pipeline_status` response prepends a per-stage `MODEL HINT` line to `subagent_instruction`. Both hints are advisory text for Claude Code's `Agent({model: ...})` parameter.

Source of truth: `_REVIEW_AGENT_PROMPT_NAMES` in `server.py`. Resolver: `recommended_model_for(activate_prompt)` in `orchestrator_tools.py`.

| Stage category | Model |
|---|---|
| `odysseus_review_agent_iterative`, `odysseus_review_agent_cold_start` | `sonnet` |
| All other stages | `haiku` |

Non-Claude-Code consumers see these as plain text and may ignore them. No Odysseus model defaults are changed.

## How to add a new tool to a stage

1. Implement the tool function in the appropriate `*_tools.py` module, decorated with `@mcp.tool()`.
2. Add the tool name to the relevant entry in `STAGE_REGISTRY` in `server.py`.
3. If the tool belongs to a new stage, add a new key to `STAGE_REGISTRY` and update `odysseus/agents/pipeline/status.py` to reference the new stage name in the relevant `subagent_instruction`.
