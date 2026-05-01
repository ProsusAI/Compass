# `odysseus/agents/`

Agent implementations, domain models, validation logic, registry operations, and pipeline guards.

Two layers:

1. **LLM-driven agents** — system prompts in [`prompts/`](prompts/) surfaced via the MCP server. Claude acts as the agent by following those instructions.
2. **Python support code** — domain models, validation functions, and registry operations that MCP tool modules call into.

---

## Subdirectory map

| Subdirectory | Pipeline stage | Contents |
|---|---|---|
| [`pipeline/`](pipeline/) | Cross-stage | `status.py` — artifact-based stage detection, subagent instructions; `guards.py` — entry/exit guard helpers |
| [`user_input/`](user_input/) | Stage 1 — User Input | `report.py` — `CONTEXT_KEY`, status constants, `read_status()`; plus `context.md`, `defaults.md`, `taxonomy.md`, `report_template.md` resources |
| [`data_validation/`](data_validation/) | Stage 2 — Data Validation | `checks.py` (schema/volume validation), `detect.py` (format detection), `transform.py` (column mapping), `split.py` (stratified split) |
| [`prompt_builder/`](prompt_builder/) | Stage 4 build phase — Prompt Building | `search_ops.py` (search state, Pareto ops, round management), `search.py` (SearchState model), `holdout_filter.py`; plus `best_practices.md`, `conventions_*.md` resources |
| [`review/`](review/) | Stage 4 review phase — Review Agent | `models.py` (ReviewBriefing, ReviewResult), `preprocessor.py` (pre-processing), `ops.py` (persistence) |
| [`final_report/`](final_report/) | Stage 6 — Final Report | `models.py` (FinalReportBriefing, charts), `preprocessor.py` (briefing builder + chart generation) |

### Cross-stage dependency direction

```
data_validation → prompt_builder ↔ review
```

`prompt_builder` reads `RoutingContext` and dev split from data validation. `prompt_builder` and `review` share `SearchState` and exchange control via `loop_phase`.

---

## Root-level modules (flat, not in a subdirectory)

| Module | Description |
|--------|-------------|
| [`base.py`](base.py) | `BaseAgent` abstract base class (`name` property, `run(context)` async method) |
| [`eval_runner.py`](eval_runner.py) | `EvalRunnerAgent` — the one code-driven agent; orchestrates a full eval run and returns `ScoreReport` |
| [`routing_context.py`](routing_context.py) | `RoutingContext` and related models (`RouteDefinition`, `RoutingDimension`, `RouteOrdering`, `SeedVocabulary`) — shared across data validation and prompt builder |

---

## Agent Prompts (`prompts/`)

One system prompt per LLM-driven agent:

| File | Agent |
|------|-------|
| [`prompts/user_input_system.md`](prompts/user_input_system.md) | User Input Agent (Stage 1) |
| [`prompts/data_validation_system.md`](prompts/data_validation_system.md) | Data Validation Agent (Stage 2) |
| [`prompts/backend_setup_system.md`](prompts/backend_setup_system.md) | Backend Setup Agent (Stage 3) |
| [`prompts/prompt_builder_system.md`](prompts/prompt_builder_system.md) | Prompt Builder Agent (Stage 4 build) |
| [`prompts/prompt_builder_rerun_system.md`](prompts/prompt_builder_rerun_system.md) | Prompt Builder Rerun Agent (Stage 4 rerun — format restructure for a different backend) |
| [`prompts/review_agent_base_system.md`](prompts/review_agent_base_system.md) | Review Agent — shared base (Stage 4 review, all strategies) |
| [`prompts/review_agent_iterative_base_system.md`](prompts/review_agent_iterative_base_system.md) | Review Agent — iterative phase base ("identify failure mode" flow) |
| [`prompts/review_agent_cold_start_base_system.md`](prompts/review_agent_cold_start_base_system.md) | Review Agent — cold-start phase base ("formulate diverse strategies" flow) |
| [`prompts/review_agent_iterative_overlay_hillclimb.md`](prompts/review_agent_iterative_overlay_hillclimb.md) | Review Agent — iterative overlay for hill_climb |
| [`prompts/review_agent_cold_start_overlay_hillclimb.md`](prompts/review_agent_cold_start_overlay_hillclimb.md) | Review Agent — cold-start overlay for hill_climb |
| [`prompts/eval_runner_system.md`](prompts/eval_runner_system.md) | Eval Runner Agent context |
| [`prompts/final_report_system.md`](prompts/final_report_system.md) | Final Report Agent (Stage 6) |

---

## `EvalRunnerAgent` — [`eval_runner.py`](eval_runner.py)

The one code-driven agent. Orchestrates a full evaluation run against the dev split without requiring an internal LLM call.

**Role:** Extracts parameters from the pipeline context, loads a run config, wires dependencies, delegates to `odysseus.eval.controller`, and returns a structured `ScoreReport`.

### Context keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `prompt_version` | `str` | `"latest"` | Prompt version to evaluate |
| `data_source` | `str` | `""` | Path to the JSONL dataset |
| `backend` | `str` | `"default"` | Backend label matching a profile in `backends/` |
| `config_path` | `str` | `"outputs/run_config.yaml"` | Path to the YAML run config |

### Outputs

On success: `{ScoreReport.CONTEXT_KEY: ScoreReport}`.

On failure: `{"error": {"category": str, "detail": str}}` where `category` is one of `not_found`, `validation_error`, `permission_denied`, `run_error`.

The data split is always `"dev"` — holdout evaluation is a separate MCP tool.
