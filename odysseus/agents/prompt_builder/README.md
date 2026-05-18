# odysseus/agents/prompt_builder — Prompt Builder Subpackage

Manages the search-loop optimization: tracks `SearchState` and an elite set across rounds, persists all state to files, filters holdout contamination, and regenerates a live HTML visualization on each state mutation.

The subpackage is code-only; the Prompt Builder Agent (LLM-driven, system prompt in `odysseus/agents/prompts/`) calls these functions via MCP tools defined in `odysseus/mcp/prompt_building_tools.py`. Inputs are populated via the discovery sequence defined in `odysseus/agents/prompts/prompt_builder_system.md` — the agent uses MCP tools (`get_routing_context`, `get_search_state`, `get_child_variants`, `get_prompt_text`) rather than a context dict.

## Contents

| File | What it does |
|------|-------------|
| [`search.py`](search.py) | Pydantic models (`Candidate`, `RoundSummary`, `SearchState`) and search algorithm primitives: `update_pareto_front`, `compute_front_improvement`. |
| [`search_ops.py`](search_ops.py) | File-backed state operations: `init_search_state`, `get_search_state`, `register_candidate`, `record_eval_result`, `advance_round`, `set_loop_phase`. Persists to `outputs/<run_id>/search/`. Algorithm is hardcoded per branch via `_BRANCH_ALGORITHM` / `_BRANCH_ALGORITHM_STATE` module constants; leaf branches set these to a concrete algorithm. `search_state.json` is auto-created at Stage 4 entry by `_ensure_stage4_search_state` in `pipeline/status.py` — no agent action needed. `register_candidate` accepts an optional `trajectory_id: int | None` parameter for leaf-branch use. Idempotent no-op when the state file is pristine (round=0, empty history/elite_set/pending); raises `FileExistsError` (surfaced as `ToolError` by the MCP wrapper) when called on a state that already has progress. Sub-agents must use `get_search_state` on round 2+. |
| [`search_tree.py`](search_tree.py) | `collect_data()` reads search state + per-candidate eval reports and builds the DATA dict; `render_html()` injects it into the self-contained HTML template. Strategy-injectable via `_STRATEGY_LABELS` and `_algorithm_chips()`. Node coloring reflects `on_front` (Pareto elite-set) membership; leaf branches can extend for algorithm-specific overlays. |
| [`viz.py`](viz.py) | `write_viz(run_id)` — regenerates `outputs/<run_id>/search/viz.html`; called after every state mutation via `_try_write_viz` (never raises). |
| [`holdout_filter.py`](holdout_filter.py) | `filter_holdout_dataset()` — removes few-shot example IDs from the holdout JSONL before final evaluation to prevent data contamination. |
| [`best_practices.md`](best_practices.md) | MCP resource: model-agnostic routing prompt best practices (role framing, rule ordering, few-shot design). |
| [`conventions_claude.md`](conventions_claude.md) | MCP resource: Claude-specific routing prompt conventions (XML tags, extended thinking, tool use patterns). |
| [`conventions_openai.md`](conventions_openai.md) | MCP resource: OpenAI GPT routing prompt conventions. |
| [`conventions_openai_gpt-5-2.md`](conventions_openai_gpt-5-2.md) | MCP resource: GPT-5-2 specific conventions. |

## Persistence layout

```
outputs/<run_id>/search/
  search_state.json        # SearchState (elite_set, round_history, phase)
  pending_candidates.json  # Candidates registered but not yet advanced
  candidate_archive.json   # Append-only record of every scored candidate (used by search-tree viz to preserve lineage of dominated/non-elite candidates)
  viz.html                 # Live interactive visualization (regenerated after each state mutation)
```

Eval reports are written by the eval engine at:

```
outputs/<run_id>/eval/<prompt_version>/report.json
```

