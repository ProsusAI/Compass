# Design: `optimize_routing_prompt` as Pipeline Entry Point

**Date:** 2026-03-27
**Status:** Approved

## Problem

Using `odysseus_routing_input` (an MCP prompt) as the starting point requires the model to first explore all available tools and prompts, reason about the right starting point, and only then invoke the prompt. This adds unnecessary latency and fragile discovery at the start of every session.

## Goal

Make `optimize_routing_prompt` the natural, self-contained entry point. A user saying "optimize my routing prompt" triggers a single tool call that immediately activates the User Input Agent with full context — no exploration required.

## Design

### What changes

| Component | Change |
|---|---|
| `optimize_routing_prompt` tool in `odysseus/mcp.py` | Implement: drop the three stub parameters, accept `ctx: Context` only, call `_get_pipeline_status` server-side, return activation package |
| `odysseus/agents/prompts/user_input_system.md` | In the "Pipeline Discovery" section: remove only the sentence instructing the agent to call `get_pipeline_status`. The bootstrap decision flow (ask fresh vs bootstrap, call `submit_input_report` with `bootstrap_from_run_id`) stays unchanged. The removed sentence is replaced with: "Pipeline status has already been retrieved and is pre-injected above — use it directly." |
| `odysseus_routing_input` MCP prompt | No change — kept for direct/manual invocation |
| All other tools, prompts, and resources | No change |

### New function signature

The three existing stub parameters (`data_path`, `problem_description`, `target_metrics`) are dropped. The tool becomes a zero-argument entry point — all inputs are collected by the User Input Agent during the conversation, not upfront.

```python
@mcp.tool()
async def optimize_routing_prompt(ctx: Context) -> str:
    """Start the Odysseus routing prompt optimization pipeline.

    Call this to begin. Activates the User Input Agent, which will guide
    you through providing a problem description and dataset before the
    pipeline runs.
    """
```

The docstring is the primary model-facing discovery signal — it must be direct about being the entry point.

### Activation package

`optimize_routing_prompt` returns a single string:

```
<pipeline_status>
{JSON output of _get_pipeline_status — existing runs, current stage, next action}
</pipeline_status>

<instructions>
You are now operating as the User Input Agent for the Odysseus pipeline.
The pipeline status above has already been checked — use it to decide whether
to greet the user for a fresh run or surface existing runs and offer to bootstrap.
Follow your system prompt below exactly.
</instructions>

<system_prompt>
{full content of user_input_system.md, with the get_pipeline_status call sentence replaced as described above}
</system_prompt>
```

**Why a tool rather than the existing MCP prompt mechanism:** The `odysseus_routing_input` MCP prompt returns a `UserMessage` — it requires the model to first identify and explicitly invoke the prompt, which is the discovery step this design eliminates. A tool result is returned inline in response to the triggering tool call, requiring no additional model discovery step. The XML envelope is intentionally novel in this codebase; all other tools return data. This tool returns an activation context — a deliberate trade-off to eliminate the exploration overhead at session start.

### Server-side pipeline status

The tool resolves `project_dir` via `await resolve_project_dir(ctx)` (the standard pattern across `mcp.py`), derives `outputs_dir = project_dir / "outputs"`, then calls `_get_pipeline_status(outputs_dir=outputs_dir, run_id=None, project_dir=project_dir)` directly.

`_get_pipeline_status` is a synchronous function called inside `async def` without an executor — matching the established pattern at line 1128 of `mcp.py` where the `get_pipeline_status` MCP tool does the same thing.

### Error handling

Two separate `try/except` blocks — the failure modes are distinct:

```python
try:
    system_prompt = _load_text("odysseus/agents/prompts/user_input_system.md")
except FileNotFoundError as e:
    raise ToolError(f"User Input Agent system prompt not found — MCP server installation may be broken: {e}")

try:
    status = _get_pipeline_status(outputs_dir=outputs_dir, run_id=None, project_dir=project_dir)
except Exception as e:
    raise ToolError(f"Failed to read pipeline status from {outputs_dir}: {e}")
```

`_load_text` failure is a server installation error; `_get_pipeline_status` failure is a runtime I/O error. Keeping them separate produces actionable error messages.

| Case | Behavior |
|---|---|
| `outputs/` does not exist | `_get_pipeline_status` returns "no runs found, stage 1" — passed through normally |
| `user_input_system.md` missing | `FileNotFoundError` → `ToolError` with server installation message |
| `_get_pipeline_status` raises | Caught separately → `ToolError` with `outputs_dir` path in message |

## Testing

Follow the pattern of `TestGetPipelineStatus` in `tests/test_mcp.py` — separate tests for happy path, error paths, and schema shape.

**Happy path:**
- Call `optimize_routing_prompt` and assert the return string contains all three XML sections: `<pipeline_status>`, `<instructions>`, `<system_prompt>`

**Schema shape:**
- Assert the tool's `inputSchema` has no parameters (empty `properties`, no `required` array) — confirming the three stub params were removed

**Error paths:**
- Mock `_load_text` to raise `FileNotFoundError` — assert `ToolError` is raised with "installation" in the message
- Mock `_get_pipeline_status` to raise an `OSError` — assert `ToolError` is raised with `outputs_dir` path in the message

**Scenarios:**
- No existing scenario files reference the `get_pipeline_status` call in `user_input_system.md` — no scenario updates required
- New scenarios for the `optimize_routing_prompt` entry point are out of scope for this change

## What stays the same

- `odysseus_routing_input` MCP prompt — kept for power users and direct invocation
- `get_pipeline_status` MCP tool — unchanged, still usable independently
- All downstream agent prompts and tools — unaffected
- The User Input Agent's behavior after activation — identical; only the startup sequence changes
- The bootstrap flow — still owned by the User Input Agent via `user_input_system.md`
