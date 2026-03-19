# THP-115 — Holdout Set Access Control Design

**Date:** 2026-03-19
**Status:** Draft
**Ticket:** [THP-115](https://prosus-thymo-thesis.atlassian.net/browse/THP-115)
**Epic:** [THP-76](https://prosus-thymo-thesis.atlassian.net/browse/THP-76) — Eval runner agent

## Problem

During the optimization loop the Eval Runner agent must only evaluate against the dev split. The holdout set is reserved for a single final evaluation after convergence. This spec defines where and how that constraint is enforced.

## Decisions

### Approach: Tool-Only Enforcement

Enforcement lives exclusively in the MCP tool layer (`odysseus/mcp.py`). No changes to `RunConfig`, `DatasetManager`, or `RunDependencies` — these remain split-agnostic internal components.

The threat model is an agentic LLM calling MCP tools. It can only use the parameters we expose, making the tool boundary the right and sufficient enforcement point.

## Design

### 1. Enforcement Point

**`run_eval` tool** (THP-129):
- Parameters: `prompt_version: str`, `data_source: str` — no `data_split` parameter.
- Internally constructs `RunConfig` with `data_split="dev"` hardcoded.
- Available to: Eval Runner agent.

**`run_holdout_eval` tool** (future task):
- Parameters: `prompt_version: str`, `data_source: str` — same interface.
- Internally constructs `RunConfig` with `data_split="holdout"` hardcoded.
- Available to: Final Evaluation agent only — must be absent from the Eval Runner agent's tool list.

### 2. Agent-Visible Error

Since `data_split` is never exposed as a tool parameter, the primary error path does not exist in normal operation. Three scenarios are addressed:

**Schema violation:** If the agent tries to pass `data_split` as a tool argument, MCP schema validation rejects the unknown parameter before our code runs. The agent sees a standard MCP schema error. No custom handling needed.

**Internal misuse:** A developer constructing a holdout `RunConfig` in the wrong context is a programming error, not an agent error. No runtime guard — caught by code review and tests.

**System prompt reinforcement:** THP-104 (Eval Runner agent system prompt) must explicitly state: *"You do not have access to holdout data. Holdout evaluation is performed by the Final Evaluation agent after convergence."*

**Canonical error message** (for any future guard that may need it):
> `"Error: data_split='holdout' is not permitted during the optimization loop. Holdout evaluation is performed by the Final Evaluation agent after convergence."`

### 3. Legitimate Holdout Access

A dedicated **Final Evaluation agent** runs after the optimization loop exits (the Review agent signals convergence).

**`run_holdout_eval` tool:**
- Registered in `odysseus/mcp.py` alongside `run_eval`.
- Same signature: `prompt_version: str`, `data_source: str`.
- Hardcodes `data_split="holdout"`.
- Reuses the same `RunDependencies` wiring and `controller.run()` — the only difference is the split value.
- Returns the same score report format (THP-116).

**Tool isolation:**
- The Eval Runner agent's tool list includes `run_eval` but **not** `run_holdout_eval`.
- The Final Evaluation agent's tool list includes `run_holdout_eval` but **not** `run_eval`.
- Enforced by how each agent class declares its tools — no shared "all tools" list.

**Trigger condition:**
- The pipeline orchestrator dispatches the Final Evaluation agent only after the Review agent outputs a convergence signal.
- The Final Evaluation agent receives the winning `prompt_version` and `data_source` from the pipeline context and calls `run_holdout_eval` exactly once.

## What Changes

| File | Change |
|---|---|
| `odysseus/mcp.py` | `run_eval` hardcodes `data_split="dev"` (THP-129). `run_holdout_eval` hardcodes `data_split="holdout"` (future task). |
| `prompts/eval_runner_system.md` | System prompt reinforces no-holdout constraint (THP-104). |
| Eval Runner agent | Tool list includes `run_eval` only (THP-130). |
| Final Evaluation agent | Tool list includes `run_holdout_eval` only (future task). |

## What Does NOT Change

| Component | Reason |
|---|---|
| `RunConfig` | Remains a plain data model accepting both `"dev"` and `"holdout"`. |
| `DatasetManager` | Remains split-agnostic; loads whatever split it is given. |
| `RunDependencies` | No access-control concerns added. |
| `controller.run()` | Executes whatever config it receives; enforcement is upstream. |

## Out of Scope

- Final Evaluation agent implementation (separate task, not yet filed).
- `run_holdout_eval` tool implementation (depends on this design being settled).
- Score report format (THP-116).
