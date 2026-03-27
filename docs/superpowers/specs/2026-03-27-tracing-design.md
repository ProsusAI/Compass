# Tracing Design — Odysseus Dev Branch

**Date:** 2026-03-27
**Scope:** Dev-branch feature; zero impact on production installs
**Goal:** Rich tool-call tracing to verify pipeline flow correctness

---

## 1. Overview

Add structured, opt-in tracing to the Odysseus MCP server so that developers can inspect the sequence, arguments, results, and timing of every tool call within a pipeline run. Tracing is activated by an environment variable and has zero overhead when disabled.

---

## 2. Architecture

### 2.1 Module

A single `odysseus/tracing.py` module owns all tracing logic. It is the only new file introduced.

### 2.2 Tracer class

```
Tracer
  ├── __init__(project_dir: Path)
  ├── tool_start(tool: str, run_id: str | None, args: dict) -> int   # returns seq number
  ├── tool_end(seq: int, tool: str, run_id: str | None, result_summary: dict, duration_ms: int)
  ├── tool_error(seq: int, tool: str, run_id: str | None, error: str, duration_ms: int)
  ├── _get_trace_file(run_id: str | None) -> Path
  └── _write(run_id: str | None, event: dict)
```

`run_id` is passed per-call (not per-instance) so one singleton `Tracer` can serve multiple pipeline runs within the same server process. `project_dir` is injected at construction time; the singleton resolves it once via `get_project_dir()`. When `run_id` is absent or `None` the session fallback file is used. The instance holds a monotonic sequence counter (`itertools.count(1)`) and a `_session_file: Path | None` for deferred session-file path construction.

### 2.3 Output paths

All paths are resolved from the project directory using `get_project_dir()` from `odysseus/project_dir.py`. This ensures traces land alongside other run outputs regardless of how the server is launched (e.g. via `uvx` or with `ODYSSEUS_PROJECT_DIR` set).

| Condition | Trace file path |
|---|---|
| `run_id` known | `<project_dir>/outputs/<run_id>/traces/events.jsonl` |
| `run_id` unknown (early calls) | `<project_dir>/outputs/traces/session-<iso-timestamp>.jsonl` |

The session fallback filename timestamp is fixed at tracer construction time (one file per process lifetime). The `--list` command discovers session files by globbing `outputs/traces/session-*.jsonl`.

### 2.4 Activation

Controlled by the `ODYSSEUS_TRACE` environment variable:

- `ODYSSEUS_TRACE=1` — tracing enabled
- Absent or any other value — tracing disabled; `@trace_tool` is a zero-overhead passthrough

### 2.5 Integration point

The `@trace_tool` decorator is applied to each tool handler in `odysseus/mcp.py`. Decorator order must be:

```python
@mcp.tool()
@trace_tool
async def run_eval(...):
    ...
```

`@mcp.tool()` must be the outermost decorator so FastMCP's parameter introspection sees the original function signature. `@trace_tool` wraps the inner function only.

The decorator:

1. Checks `ODYSSEUS_TRACE`; if unset, calls through immediately with no overhead
2. Extracts `run_id` from tool kwargs; treats absent **or `None`** as unknown (uses session fallback file)
3. Calls `tracer.tool_start` with sanitized args and records entry time
4. Awaits the handler
5. Calls `tracer.tool_end` with duration and tool-specific result summary
6. On exception: calls `tracer.tool_error`, then re-raises unchanged

The tracer instance is constructed lazily on first traced call (one per process, shared across tool calls).

**Note on `optimize_routing_prompt`:** This tool is currently a stub and has no `run_id` parameter. When implemented it should accept `run_id` so its trace events land in the run-scoped file. Until then, its events will appear in the session fallback file.

---

## 3. Trace Event Schema

Each line in `events.jsonl` is a JSON object. Three event types:

### `tool_start`
```json
{
  "seq": 1,
  "timestamp": "2026-03-27T10:30:00.000Z",
  "event": "tool_start",
  "tool": "run_eval",
  "run_id": "abc123",
  "args": {
    "prompt_version": "v3",
    "backend": "claude-sonnet",
    "data_source": "outputs/abc123/analysis/dev.jsonl"
  }
}
```

### `tool_end`
```json
{
  "seq": 1,
  "timestamp": "2026-03-27T10:30:04.821Z",
  "event": "tool_end",
  "tool": "run_eval",
  "run_id": "abc123",
  "duration_ms": 4821,
  "status": "ok",
  "result_summary": {
    "accuracy": 0.87,
    "error_count": 3,
    "total_examples": 40
  }
}
```

### `tool_error`
```json
{
  "seq": 1,
  "timestamp": "2026-03-27T10:30:05.102Z",
  "event": "tool_error",
  "tool": "run_eval",
  "run_id": "abc123",
  "duration_ms": 5102,
  "status": "error",
  "error": "EvalError: backend timeout"
}
```

**Schema rules:**
- `seq` is monotonically increasing per process session; used to reconstruct order if timestamps collide
- `args` is captured verbatim for short string/path params; string values exceeding 500 characters are truncated to 500 characters with a `…` suffix. This prevents large payloads (e.g. `report` in `submit_input_report`, `card_set_json` in `validate_rationale_card_set_tool`) from ballooning the trace file.
- `result_summary` is tool-specific: each tool defines which scalar fields to surface; large nested objects (e.g. `ScoreReport`) are reduced to key metrics only
- No secrets or API keys appear in args (none are passed as tool params in the current schema)

---

## 4. Result Summary Definitions

Each tool defines its `result_summary` as a dict of scalars. Undefined tools emit `{}`.

Tool names match the exact function names registered with `@mcp.tool()` in `odysseus/mcp.py` — these are the keys the `tracing.py` lookup table must use.

| Tool | Result summary fields |
|---|---|
| `submit_input_report` | `run_id` |
| `detect_and_parse_dataset` | `format`, `row_count` |
| `transform_dataset` | `row_count`, `columns_mapped` |
| `validate_dataset` | `passed`, `warning_count`, `error_count` |
| `save_routing_context` | `run_id` |
| `create_seed_registry_tool` | `entry_count` |
| `resolve_registry_tool` | `found`, `entry_count` (`len(intent_pattern) + len(complexity_structure) + len(ambiguity_tags)` on hit; `0` on miss) |
| `stratified_split_tool` | `dev_count`, `holdout_count` |
| `validate_rationale_card_set_tool` | `passed`, `error_count` |
| `prune_registry_tool` | `removed_count`, `remaining_count` |
| `register_candidate_tool` | `candidate_id`, `version` |
| `run_eval` | `accuracy`, `error_count`, `total_examples`, `cost_usd` |
| `run_holdout_eval` | `accuracy`, `error_count`, `total_examples`, `cost_usd` |
| `record_eval_result_tool` | `candidate_id`, `score` |
| `advance_round_tool` | `round`, `converged`, `pareto_front_size` |
| `get_search_state_tool` | `round`, `candidate_count` |
| `build_review_briefing_tool` | `candidate_count`, `round` |
| `record_directive_outcomes_tool` | `directives_recorded` |
| `filter_holdout_dataset_tool` | `removed_count`, `remaining_count` |
| `get_pipeline_status` | `stage`, `complete` |
| `init_search_state_tool` | `run_id` |
| `optimize_routing_prompt` | `status` |

---

## 5. CLI Formatter

### Command

```
odysseus trace <run_id>
```

Reads `outputs/<run_id>/traces/events.jsonl` and prints a waterfall table.

### Default output

```
Run: abc123  ·  27 Mar 2026 10:29:44

 #   Tool                          Duration   Status
───────────────────────────────────────────────────────
  1  submit_input_report              112ms   ✓
  2  detect_and_parse_dataset         203ms   ✓
  3  run_eval                        4821ms   ✗  EvalError: backend timeout
───────────────────────────────────────────────────────
Total: 3 calls  ·  5.1s  ·  1 error
```

- Green checkmark for `ok`, red cross + inline error message for `error`
- Uses `rich` for color if available (transitive dep of `mcp[cli]`); falls back to plain text

### `--verbose` flag

Prints `args` and `result_summary` for each call, indented four spaces below the row as `key: value` pairs. Args are printed first, followed by result summary fields (on `tool_end`) or nothing (on `tool_error`):

```
  1  submit_input_report              112ms   ✓
      args:    run_id: abc123
      result:  run_id: abc123
  2  run_eval                        4821ms   ✓
      args:    prompt_version: v3
               backend: claude-sonnet
               data_source: outputs/abc123/analysis/dev.jsonl
      result:  accuracy: 0.87  error_count: 3  total_examples: 40  cost_usd: 0.012
  3  run_eval                        5102ms   ✗  EvalError: backend timeout
      args:    prompt_version: v4
               backend: claude-sonnet
               data_source: outputs/abc123/analysis/dev.jsonl
```

### `odysseus trace --list`

Lists all trace files found under `outputs/`:

- Run-scoped files: glob `outputs/*/traces/events.jsonl`
- Session fallback files: glob `outputs/traces/session-*.jsonl`

Prints one line per file with run_id (or session timestamp) and file size.

---

## 6. Dev Branch Strategy

- Feature lives on a dedicated `dev` branch
- `tracing.py` is committed to the repository; tracing is guarded at runtime by `ODYSSEUS_TRACE=1`
- No changes to `main` install path; `ODYSSEUS_TRACE` is undocumented in public docs
- No new runtime dependencies
- When the feature stabilises it can be promoted to `main` with documentation

---

## 7. Out of Scope

- LLM call tracing (prompt/response pairs from eval backends)
- MCP sampling / client-side reasoning capture
- Remote trace backends (OpenTelemetry exporters, Langfuse, etc.)
- Live/streaming trace output while a run is in progress
- Trace retention policy / cleanup
