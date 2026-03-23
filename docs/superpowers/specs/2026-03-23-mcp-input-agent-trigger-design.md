# MCP Input Agent Trigger Design

## Summary

Add an MCP prompt, two MCP resources, and a stub handoff tool so that agentic assistants (like Claude Code) can activate the User Input Agent on demand when a user asks for help with a routing problem.

## Motivation

The User Input Agent exists as a fully designed system prompt but has no entry point from the MCP server. When Odysseus is configured as an MCP server in an agentic assistant, the assistant needs a way to load the input agent's behavior contextually — not always-on, but when the user asks things like "help me with this routing problem."

## Approach

**MCP Prompt + Resources + Stub Tool** (Approach A from brainstorming)

- MCP prompt for behavior injection (the system prompt)
- MCP resources for on-demand reference material
- Stub tool for handoff to the next pipeline stage

This uses each MCP primitive as intended: prompts for system-level behavior, resources for reference data, tools for actions.

## Design

### Imports

All new code is added to `odysseus/mcp.py`. Required new imports:

```python
from pathlib import Path

from mcp.server.fastmcp.prompts.base import Message, UserMessage
from mcp.server.fastmcp.exceptions import ToolError  # already imported
```

### 1. MCP Prompt: `odysseus_routing_input`

Registered via `@mcp.prompt()` in `odysseus/mcp.py`. Takes no arguments. Returns the content of `prompts/user_input_system.md` as a user message.

```python
@mcp.prompt()
async def odysseus_routing_input() -> list[Message]:
    """Activate the Odysseus routing input agent.

    Use when a user wants help with a routing optimization problem.
    Guides the user through providing a complete problem specification.
    """
    system_prompt = _load_text("prompts/user_input_system.md")
    return [UserMessage(content=system_prompt)]
```

- No arguments — the agent's conversational flow handles gathering inputs
- Loaded from disk at call time so prompt edits take effect immediately
- In Claude Code, this appears as a slash command or is suggested based on user intent

**Why `UserMessage` and not system role?** MCP prompts support `user` and `assistant` roles only (no `system` role in the protocol). Using `UserMessage` is the standard way to inject behavioral instructions via MCP prompts. The assistant treats the injected content as instructions regardless of role.

### 2. MCP Resources

Two resources exposing supporting documents with content not already in the main system prompt.

**Clarification guide** — per-field questioning strategy, sufficient answer criteria, example prompts:

```python
@mcp.resource("odysseus://agents/input/clarification-guide")
async def input_clarification_guide() -> str:
    """Per-field clarification guidance for the input agent."""
    return _load_text("odysseus/agents/user_input_clarification_guide.md")
```

**Defaults reference** — override mechanism, propagation rules:

```python
@mcp.resource("odysseus://agents/input/defaults")
async def input_defaults() -> str:
    """Default values and override mechanism for optional fields."""
    return _load_text("odysseus/agents/user_input_defaults.md")
```

URI scheme: `odysseus://agents/input/...` — organized for future agent resources. The prefix allows logical grouping if more agents expose resources later.

**Why only these two?** Analysis of the supporting documents showed:
- `user_input_taxonomy.md` — 100% redundant with main prompt
- `user_input_context.md` — ~90% redundant with main prompt
- `user_input_report_template.md` — ~90% redundant with main prompt
- `user_input_clarification_guide.md` — ~30% unique (per-field guidance)
- `user_input_defaults.md` — ~40% unique (override mechanism, propagation)

### 3. Stub Tool: `submit_input_report`

Called by the assistant after the validated input report is produced. This is the hook point for wiring in the next pipeline stage.

```python
@mcp.tool()
async def submit_input_report(
    report: str,
    dataset_path: str,
    problem_description: str,
) -> str:
    """Submit a validated input report to the pipeline.

    Called after the input agent conversation completes and
    the validated input report has been produced. Triggers
    the next pipeline stage.

    Args:
        report: The full validated input report (Markdown).
        dataset_path: Absolute filesystem path to the JSONL routing dataset.
        problem_description: The validated problem description.

    Returns:
        Confirmation or next-stage result.
    """
    # TODO: Wire to next pipeline agent.
    # Expected: save report to disk, build pipeline context,
    # and dispatch the next agent (e.g. Data Validation or Analysis).
    if not report.strip():
        raise ToolError("submit_input_report failed: report is empty")
    if not dataset_path.strip():
        raise ToolError("submit_input_report failed: dataset_path is empty")
    if not problem_description.strip():
        raise ToolError("submit_input_report failed: problem_description is empty")
    return "Input report received. Next pipeline stage not yet implemented."
```

Accepts report content plus key inputs so the next agent has everything without parsing Markdown. `dataset_path` is an absolute filesystem path to the JSONL file.

### 4. File Loader Helper

Separate from the existing `FilePromptManager` which is scoped to versioned prompt files (`.yaml`, `.yml`, `.txt`) with caching. The MCP prompt and resources load Markdown files and should always read from disk (no caching) to support hot-reload during development.

```python
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_text(relative_path: str) -> str:
    """Load a text file relative to the project root.

    Raises FileNotFoundError with a clear message if the file is missing.
    """
    path = _PROJECT_ROOT / relative_path
    if not path.is_file():
        raise FileNotFoundError(
            f"Required prompt file not found: {path} "
            f"(resolved from project root {_PROJECT_ROOT})"
        )
    return path.read_text()
```

`_PROJECT_ROOT` is resolved once at import time from `mcp.py`'s known location (`odysseus/mcp.py` → two levels up). This is stable because `mcp.py` is the server entrypoint and will not move.

### 5. Handoff Instruction in System Prompt

Append to `prompts/user_input_system.md`:

```markdown
## Handoff

Once you have produced the validated input report and the user has confirmed it,
call the `submit_input_report` tool with:
- `report`: the full report Markdown
- `dataset_path`: the absolute filesystem path to the routing dataset
- `problem_description`: the validated problem description

This triggers the next pipeline stage. Do not proceed manually — the tool handles dispatch.
```

## Files Changed

| File | Change |
|---|---|
| `odysseus/mcp.py` | Add `_PROJECT_ROOT`, `_load_text` helper, `odysseus_routing_input` prompt, two resources, `submit_input_report` stub tool, new imports |
| `prompts/user_input_system.md` | Append handoff section |

## Test Plan

| Test | Description |
|---|---|
| `test_prompt_registration` | `odysseus_routing_input` is registered and returns a non-empty list of `Message` objects |
| `test_prompt_content` | Returned message content matches `prompts/user_input_system.md` file content |
| `test_resource_clarification_guide` | Resource `odysseus://agents/input/clarification-guide` returns non-empty string |
| `test_resource_defaults` | Resource `odysseus://agents/input/defaults` returns non-empty string |
| `test_submit_input_report_stub` | Returns confirmation string when given valid inputs |
| `test_submit_input_report_empty_report` | Raises `ToolError` when report is empty |
| `test_submit_input_report_empty_path` | Raises `ToolError` when dataset_path is empty |
| `test_submit_input_report_empty_description` | Raises `ToolError` when problem_description is empty |
| `test_load_text_missing_file` | `_load_text` raises `FileNotFoundError` with clear message for missing files |

## Not In Scope

- Python class implementation of the User Input Agent (it runs as prompt-injected behavior in the assistant)
- Implementation of the next pipeline stage (stub only)
- Changes to existing tools (`run_eval`, `run_holdout_eval`, `optimize_routing_prompt`)
