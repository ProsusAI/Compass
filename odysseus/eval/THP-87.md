# THP-87 — Develop Prompt Manager with Hot-Reloading

**Type:** Task  
**Status:** To Do  
**Epic:** [THP-75](https://prosus-thymo-thesis.atlassian.net/browse/THP-75) — Eval framework Code  
**Jira:** [THP-87](https://prosus-thymo-thesis.atlassian.net/browse/THP-87)

## Description

Create the prompt manager to manage versioned prompts, support hot-reloading from a watched directory, and provide a method to retrieve prompts by version. Ensure prompt usage is logged for traceability.

## What to build

Implement a concrete class that satisfies the `PromptManager` protocol defined in `odysseus/eval/protocols.py`:

```python
class PromptManager(Protocol):
    def load(self, version: str) -> str: ...
```

The implementation should:

- **Store versioned prompts** — read prompt files from the `prompts/` directory (project root). Files should follow a naming convention such as `{version}.yaml` or `{version}.txt`.
- **Resolve `"latest"`** — when `version="latest"` is passed, determine the most recent version automatically (e.g. by file modification time or a manifest file). The controller always calls `load(config.prompt_version)` without knowing whether `"latest"` needs resolution.
- **Hot-reloading** — watch the `prompts/` directory for file changes and reload in-memory cache without restarting. Use `watchfiles` or `watchdog` (add as a dependency in `pyproject.toml`).
- **Log usage** — log at `INFO` level every time a prompt is loaded, including the resolved version name.

Suggested file: `odysseus/prompts/manager.py`

## How it links with the rest of the codebase

| Touch point | Detail |
|---|---|
| `odysseus/eval/protocols.py` | Defines the `PromptManager` protocol this class must satisfy. |
| `odysseus/eval/controller.py` | Calls `deps.prompt_manager.load(config.prompt_version)` as step 1 of every run. The returned string is the raw prompt template passed to `backend.call()`. |
| `odysseus/eval/models.py` | `RunConfig.prompt_version` (default `"latest"`) is the version string forwarded to `load()`. |
| `prompts/` (project root) | On-disk store for versioned prompt files. Directory already created via `.gitkeep`. |
| `odysseus/mcp.py` | The MCP tool will eventually wire a concrete `PromptManager` into `RunDependencies` before calling `run()`. |

## Dependencies between tasks

- No hard blockers — can be developed and unit-tested independently using the protocol as the contract.
- THP-92 (Run Controller) consumes this via `RunDependencies.prompt_manager`.
