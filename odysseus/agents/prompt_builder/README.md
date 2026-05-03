# odysseus/agents/prompt_builder — Prompt Builder Subpackage

Manages the search-loop optimization: tracks `SearchState` and an elite set across rounds, persists all state to files, filters holdout contamination, and regenerates a live HTML visualization on each state mutation.

The subpackage is code-only; the Prompt Builder Agent (LLM-driven, system prompt in `odysseus/agents/prompts/`) calls these functions via MCP tools defined in `odysseus/mcp/prompt_building_tools.py`.

## Contents

| File | What it does |
|------|-------------|
| [`search.py`](search.py) | Pydantic models (`Candidate`, `RoundSummary`, `SearchState`) and search algorithm primitives: `update_pareto_front`, `compute_front_improvement`. |
| [`annealing.py`](annealing.py) | EMOSA pure functions and Pydantic models: `TrajectoryState`, `TrajectorySnapshot` (per-round snapshot of each trajectory's `current_solution`, appended to `AnnealingState.trajectory_history`), `AnnealingState`. |
| [`search_ops.py`](search_ops.py) | File-backed state operations: `init_search_state`, `get_search_state`, `register_candidate`, `record_eval_result`, `advance_round`, `set_loop_phase`. Persists to `outputs/<run_id>/search/`. Algorithm is hardcoded per branch via `_BRANCH_ALGORITHM` / `_BRANCH_ALGORITHM_STATE` module constants; strategy branches flip only those two lines. `search_state.json` is auto-created at Stage 4 entry by `_ensure_stage4_search_state` in `pipeline/status.py` — no agent action needed. `register_candidate` accepts an optional `trajectory_id: int | None` parameter; when supplied it is stored directly on the `Candidate` (EMOSA only), bypassing the filename-based `_derive_trajectory_id` fallback. |
| [`search_tree.py`](search_tree.py) | `collect_data()` reads search state + per-candidate eval reports and builds the DATA dict; `render_html()` injects it into the self-contained HTML template. Strategy-injectable via `_STRATEGY_LABELS` and `_algorithm_chips()`. For EMOSA runs, `collect_data` also reads `algorithm_state.trajectory_history` and emits `iteration_currents` (per-round live trajectory points), `use_trajectory_highlight`, `trajectory_colors` (`TRAJECTORY_COLORS` constant — 5 distinct hues), and per-candidate `trajectory_id`; the JS tints each node and edge in its originating trajectory's color (T0 cyan, T1 violet, T2 emerald, T3 amber, T4 rose) and renders a data-driven legend with weight vectors. Candidates lacking `trajectory_id` (old runs, non-EMOSA) fall back to legacy elite/dominated coloring. |
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

## EMOSA trace logging

Set the environment variable `ODYSSEUS_EMOSA_TRACE=1` (or flip `EMOSA_TRACE_ENABLED = True` in `emosa_trace.py`) to enable two diagnostic outputs in `<run>/search/`:

| File | Content |
|------|---------|
| `emosa_trace.log` | Human-readable text: round boundaries, per-trajectory Metropolis decisions, neighborhood-replacement events. Written via a dedicated `logging.FileHandler` with `propagate=False` — never leaks to MCP stdout. |
| `emosa_trace.jsonl` | One JSON record per Metropolis decision — append-only, line-buffered. Use this for downstream analysis of stagnation and acceptance rates. |

### JSONL record fields

| Field | Type | Notes |
|-------|------|-------|
| `round` | `int` | Search round number |
| `trajectory_id` | `int` | EMOSA trajectory index |
| `parent_version` | `str \| null` | Parent prompt version (`null` on calibration step) |
| `child_version` | `str` | Candidate prompt version |
| `parent_energy` | `float \| null` | Tchebycheff energy of parent (`null` on calibration step) |
| `child_energy` | `float` | Tchebycheff energy of candidate |
| `delta_e` | `float \| null` | `child_energy - parent_energy` (`null` on calibration step) |
| `temperature` | `float` | Trajectory temperature at time of decision |
| `p_accept` | `float \| null` | Acceptance probability: `1.0` if `delta_e ≤ 0`, `exp(-delta_e/T)` if `delta_e > 0`, `null` on calibration step |
| `accepted` | `bool` | Whether the candidate was accepted by Metropolis |

Both outputs are off by default. `search_state.json` is not affected.
