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
| [`prompt_building_tools.py`](prompt_building_tools.py) | `init_search_state` (no `algorithm`/`algorithm_state` — hardcoded per branch), `register_candidate`, `run_eval`, `run_batch_eval`, `record_eval_result`, `advance_step`, `get_search_state`, `save_prompt`, `get_child_variants`, `get_edit_directives` |
| [`review_tools.py`](review_tools.py) | `build_review_briefing`, `record_directive_outcomes` |
| [`final_report_tools.py`](final_report_tools.py) | `filter_holdout_dataset`, `run_holdout_eval`, `build_final_report_briefing`, `save_final_report` |
| [`resources.py`](resources.py) | MCP resource definitions (`odysseus://agents/...`, `odysseus://backends/...`) |
| [`prompts.py`](prompts.py) | MCP prompt definitions (`odysseus_routing_input`, `odysseus_data_validation`, etc.) |

## Stage registry and tool filtering

`STAGE_REGISTRY` in `server.py` maps each stage name to the list of tools visible to the sub-agent operating in that stage. The module-level `_active_stage` variable starts as `"orchestrator"` at server startup.

`list_tools` is patched at import time to filter by `STAGE_REGISTRY[_active_stage]`. When `_active_stage` is `None`, all tools are returned (filtering disabled).

The orchestrator controls scoping via two tools:

1. **`start_stage(run_id)`** — inspects pipeline artifacts to pick the next stage, sets `_active_stage` accordingly, and returns the sub-agent prompt, dispatch checklist, and recommended model in one payload. No `stage` argument — the server decides.
2. **`complete_stage(run_id)`** — resets `_active_stage` to `"orchestrator"` after the sub-agent finishes.

| Stage name | Tools | Notes |
|---|---|---|
| `orchestrator` | `optimize_routing_prompt`, `get_pipeline_status`, `start_stage`, `complete_stage` | |
| `input_report` | `submit_input_report`, `get_pipeline_status` | |
| `data_validation` | `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context`, `get_pipeline_status` | |
| `backend_setup` | `get_default_pricing`, `get_pipeline_status` | |
| `prompt_building` | `init_search_state`, `register_candidate`, `run_eval`, `run_batch_eval`, `record_eval_result`, `advance_step`, `get_search_state`, `get_edit_directives`, `get_child_variants`, `save_prompt`, `get_pipeline_status` | |
<<<<<<< HEAD
| `review_cold` | `build_review_briefing`, `record_directive_outcomes`, `query_dev_examples`, `get_search_state`, `get_pipeline_status` | Cold sub-agents may page dev rows, but still have no `get_prompt_text` / `query_holdout_examples` |
| `review` | `build_review_briefing`, `record_directive_outcomes`, `query_dev_examples`, `query_holdout_examples`, `get_prompt_text`, `get_search_state`, `run_eval`, `get_pipeline_status` | Steady-review toolbelt; sub-agents call `record_directive_outcomes` (single-slot for hill-climb; pass `trajectory_id=<N>` for EMOSA K-way fanout). Dataset rows remain query-only and paginated. |
| `calibration` | `build_review_briefing`, `record_directive_outcomes`, `get_search_state`, `init_search_state`, `register_candidate`, `run_batch_eval`, `record_eval_result`, `advance_step`, `save_prompt`, `get_child_variants`, `get_edit_directives`, `signal_eval_complete`, `get_pipeline_status` | EMOSA-only — K-seed calibration phase; no `get_prompt_text` / dataset row-query tools |
| `final_report` | `filter_holdout_dataset`, `run_holdout_eval`, `build_final_report_briefing`, `save_final_report`, `get_pipeline_status` | |

### `record_directive_outcomes` — recording review result (variants, loop signal, ranking, promotions, regression guards)

Records the Review Agent's output fields (`loop_signal`, `child_variants`, `candidate_ranking`, `promotion_decisions`, `regression_guards`). Directive outcomes (`directive_history_update`) are no longer passed here — they are synthesized wholly in code from `batch_outcomes` by `build_review_briefing`. No `directive_history.json` file is persisted.

When `trajectory_id: int` is passed (EMOSA K-way fanout), the tool writes per-trajectory child variant files (`child_variants_t<N>.json`) instead of the single-slot `child_variants.json` sentinel, and calls `record_trajectory_dispatched` to mark the slot as complete. Variant ids use the format `cv-{round}-t{trajectory_id}-{i}`. Passing `trajectory_id=None` (default) keeps the original single-slot behaviour for all other strategies.

### `get_child_variants` / `get_edit_directives`

Both readers prefer per-trajectory files when present: if any `child_variants_t<N>.json` exist under `outputs/<run_id>/search/`, they call `load_all_trajectory_child_variants` and return variants sorted by `trajectory_id`. Otherwise they fall back to the single-slot `child_variants.json` written during calibration and non-EMOSA strategies.

## Model routing hints

`optimize_routing_prompt` and `get_pipeline_status` embed two-layer routing hints. Source of truth: `_REVIEW_AGENT_PROMPT_NAMES` in `server.py`. Resolver: `recommended_model_for(activate_prompt)` in `orchestrator_tools.py`.

**Layer 1 — Universal capability claim (all consumers):**

| Stage category | Tier | Note |
|---|---|---|
| `odysseus_review_agent_iterative`, `odysseus_review_agent_cold_start` | strong | High-stakes synthesis |
| All other stages | fast | Tool-driven / rote tasks |

**Layer 2 — Claude Code binding (Claude Code only — ignore otherwise):**

Every `Agent({...})` call MUST include a literal `model` parameter (`model: "sonnet"` for review/review_cold, `model: "haiku"` for all other stages). Omitting it inherits the orchestrator's model. Each `get_pipeline_status` response states the correct value for the current dispatch. If the aliases are unavailable, fall back to the closest tier.

Other runtimes should map the tier to their equivalent backend model. No Odysseus model defaults are changed.

## How to add a new tool to a stage

1. Implement the tool function in the appropriate `*_tools.py` module, decorated with `@mcp.tool()`.
2. Add the tool name to the relevant entry in `STAGE_REGISTRY` in `server.py`.
3. If the tool belongs to a new stage, add a new key to `STAGE_REGISTRY` and update `odysseus/agents/pipeline/status.py` to reference the new stage name in the relevant `subagent_instruction`.
