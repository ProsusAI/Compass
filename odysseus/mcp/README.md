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
| [`prompt_building_tools.py`](prompt_building_tools.py) | `init_search_state_tool`, `register_candidate_tool`, `run_eval`, `run_batch_eval`, `record_eval_result_tool`, `advance_step_tool`, `get_search_state_tool`, `save_prompt_tool` |
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

| Stage name | Tools |
|---|---|
| `orchestrator` | `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage` |
| `input_report` | `submit_input_report`, `get_pipeline_status` |
| `data_validation` | `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `get_pipeline_status` |
| `backend_setup` | `get_default_pricing`, `get_pipeline_status` |
| `prompt_building` | `init_search_state_tool`, `register_candidate_tool`, `run_eval`, `run_batch_eval`, `record_eval_result_tool`, `advance_step_tool`, `get_search_state_tool`, `save_prompt_tool`, `get_pipeline_status` |
| `review` | `build_review_briefing_tool`, `record_directive_outcomes_tool`, `get_search_state_tool`, `run_eval`, `get_pipeline_status` |
| `final_report` | `filter_holdout_dataset_tool`, `run_holdout_eval`, `build_final_report_briefing_tool`, `save_final_report`, `get_pipeline_status` |

## How to add a new tool to a stage

1. Implement the tool function in the appropriate `*_tools.py` module, decorated with `@mcp.tool()`.
2. Add the tool name to the relevant entry in `STAGE_REGISTRY` in `server.py`.
3. If the tool belongs to a new stage, add a new key to `STAGE_REGISTRY` and update `odysseus/agents/pipeline/status.py` to reference the new stage name in the relevant `subagent_instruction`.
