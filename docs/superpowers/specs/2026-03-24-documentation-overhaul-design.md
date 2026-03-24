# Documentation Overhaul Design

**Date:** 2026-03-24
**Status:** Draft
**Scope:** Complete overhaul of project documentation — layered architecture map + module READMEs + enforced consistency via Claude Code rule.

## Problem

Current documentation is scattered and incomplete. There's no centralized reference that maps how agents connect, what context they share, or how data flows through the pipeline. Re-orientation after time away requires reading code to piece together the architecture. Existing docs (`project-overview.md`) may contain stale information, and design specs in `docs/superpowers/specs/` are historical artifacts with no guarantee of completeness or currency.

## Approach

Layered documentation: a top-level architecture map for 30-second re-entry, module READMEs for detailed reference next to the code they describe, and a Claude Code rule to enforce consistent maintenance. Source of truth is always the code — docs reference it, never the reverse.

## Design

### 1. Document Inventory

| File | Action | Purpose |
|------|--------|---------|
| `docs/architecture.md` | New | Top-level map: pipeline diagram, agent table, context dict reference, shared models, MCP surface, directory guide |
| `docs/project-overview.md` | Update | Review against current code, remove stale/outdated info, link to `architecture.md` for technical detail |
| `odysseus/agents/README.md` | New | Domain models, validation logic, registry operations, agent prompts, EvalRunnerAgent |
| `odysseus/agents/prompts/` | New dir | Relocate agent system prompts from top-level `prompts/` |
| `odysseus/eval/README.md` | New | Eval engine internals: controller, protocols, backends, metrics, collector, rate limiting |
| `prompts/README.md` | New | Routing prompt store: versioning scheme, PromptManager, file formats |
| `.claude/rules/update-docs-before-commit.md` | New | Doc maintenance rule with style guidance |
| `CLAUDE.md` | Update | Add pointer to `docs/architecture.md` |

**Not touched:** `docs/implementation-flow.md` (dev planning artifact), `docs/superpowers/specs/*` (historical design records).

### 2. Architecture Map (`docs/architecture.md`)

The 30-second re-entry doc. Six sections, all favoring tables and diagrams over prose:

**2.1 Pipeline Overview**
Mermaid diagram showing the full pipeline from user input to final report. Marks each agent's status (done / in progress / planned) and the data flow between them. Mermaid is preferred over ASCII because it renders natively in GitHub and most Markdown viewers.

**2.2 Agent Registry Table**
One row per agent:

| Agent | Type | Module / Prompt | Status | Reads from Context | Writes to Context |
|-------|------|-----------------|--------|--------------------|-------------------|

- **Type** distinguishes LLM-driven agents (system prompts surfaced via MCP) from code-driven agents (Python classes).
- Context keys are the shared memory map — answering "what does agent X need?" and "what does it produce?"

**2.3 Context Dict Reference**
All known context keys in one table:

| Key | Type | Set By | Consumed By | Description |
|-----|------|--------|-------------|-------------|

This is the canonical reference for the shared context that flows through the pipeline.

**2.4 Shared Models**
Brief description of cross-agent models with pointers to definitions:
- `DataQualityReport` — output of data validation checks
- `RationaleCardSet` / `RationaleCard` — structured annotation output
- `VocabularyRegistry` — dynamic vocabulary for annotation
- `ScoreReport` / `RunReport` — eval results
- `RoutingContext` — domain context for annotation skills

One paragraph each, linking to the source file.

**2.5 MCP Surface**
Three tables: exposed tools, exposed prompts, exposed resources. Each with name, status, purpose, and which agent/module backs it.

**2.6 Directory Guide**
One-liner per top-level directory, linking to its README where one exists.

### 3. Module READMEs

#### `odysseus/agents/README.md`

- **Intro:** Agents in Odysseus are primarily LLM-driven — they're system prompts (in `prompts/`) surfaced via the MCP server's prompt mechanism. Claude acts as the agent by following those instructions. The Python code in this directory provides domain models, validation logic, and registry operations that MCP tools call into.
- **EvalRunnerAgent:** The one code-driven exception — a Python class that orchestrates eval runs.
- **Per-module section:** For each `.py` file — what it contains, key classes/functions, which context keys or models it defines.
- **Shared models section:** RationaleCard, VocabularyRegistry, DataQualityReport, RoutingContext — what they are, relationships between them.
- **Agent prompts:** Note that agent system prompts live in `prompts/` subdirectory, one per agent.

Length: as long as the module warrants. The agents directory has significant complexity (models, checks, registry, one code-driven agent) so this README will likely be the longest.

#### `odysseus/eval/README.md`

**Note:** `odysseus/eval/docs/` already contains `README.md`, `architecture.md`, and `backends.md` with substantial coverage. The approach: create a new root-level `odysseus/eval/README.md` (distinct from `odysseus/eval/docs/README.md`) as the entry point that summarizes the eval engine and links to the existing `docs/` subdirectory for deep dives. The root README orients; `docs/` details. Do not duplicate content between them.

- **How the eval engine works:** Controller orchestrates backends, dataset, metrics, collector.
- **Protocol-based DI:** How `RunDependencies` wires implementations to protocols, enabling test doubles.
- **Links to deep dives:** Point to `docs/architecture.md` for internals and `docs/backends.md` for backend config.
- **How EvalRunnerAgent wires it:** Config loading, dependency construction, report diffing.

#### `prompts/README.md`

- **Purpose:** This is the routing prompt store — versioned prompts being optimized by the pipeline.
- **Versioning:** File stem = version name, `"latest"` resolves to most recently modified file.
- **File formats:** YAML and TXT supported.
- **PromptManager:** How `FilePromptManager` loads, caches, and watches for changes.
- **Environment:** `ODYSSEUS_PROMPTS_DIR` env var override.
- **Not here:** Agent system prompts live in `odysseus/agents/prompts/`.

### 4. Agent System Prompt Relocation

Move from top-level `prompts/` to `odysseus/agents/prompts/`:
- `user_input_system.md`
- `eval_runner_system.md`
- `eval_runner_system.txt` (duplicate variant — keep `.md`, delete `.txt`, update test to use `.md`)
- `data_validation_system.md`

Update live code references:
- `odysseus/mcp.py` — loads `prompts/user_input_system.md` and `prompts/data_validation_system.md` via `_load_text()`. Update paths to `odysseus/agents/prompts/`.
- `odysseus/agents/eval_runner.py` — constructs `FilePromptManager(prompts_dir=Path("prompts"))` to load `eval_runner_system`. After relocation, this must point to `odysseus/agents/prompts/` instead. Note: `FilePromptManager` resolves paths relative to `_PROJECT_ROOT` — verify this during implementation, as a bare `Path("prompts")` resolved from CWD could break. `FilePromptManager` is designed for the routing prompt store; using it to load agent prompts is a convenience, not a semantic fit. For now, update the path. If this becomes awkward later, agent prompt loading can be simplified to direct file reads.
- `tests/test_eval_runner_prompt.py` — resolves `PROMPTS_DIR` as project root `prompts/` and also uses `FilePromptManager`. Update both.
- `CLAUDE.md` — if it references prompt locations.

Note: `eval_runner_system.md` is not loaded by `mcp.py` (only referenced in historical planning docs). It still moves for consistency.

The top-level `prompts/` becomes the routing prompt store. It will initially be empty after relocation — routing prompts are created during pipeline runs, not checked in. This is expected.

### 5. `project-overview.md` Update

Review against current codebase state:
- Verify agent list and statuses match reality
- Remove any references to deprecated patterns (e.g., if it still describes agents as async Python classes)
- Ensure tech stack section is current
- Add link to `docs/architecture.md` for technical detail
- Keep it as the "what is this project" entry point — high-level purpose, not implementation detail

### 6. Claude Code Rule (`.claude/rules/update-docs-before-commit.md`)

```markdown
When changes affect agent prompts, MCP surface (tools/prompts/resources), shared models,
context dict keys, or cross-module interfaces, update the relevant documentation
(docs/architecture.md and module READMEs) in the same commit.

Style guidance:
- Prefer tables over prose for structured information (agent lists, context keys, model fields)
- Match the heading structure and formatting of the doc you're updating
- Keep descriptions concise — one sentence where one sentence suffices
- Use consistent formatting: backticks for code references, links to source files
- No padding — length should match complexity, not fill a template

Do not commit interface changes with stale docs.
```

### 7. `CLAUDE.md` Update

Add under the existing Project Structure section:

- Pointer to `docs/architecture.md` as the technical architecture reference
- Note that agent system prompts now live in `odysseus/agents/prompts/`
- Note that `prompts/` (top-level) is the routing prompt store

### 8. What Does NOT Change

- `docs/implementation-flow.md` — stays as dev planning artifact
- `docs/superpowers/specs/*` — stay as historical design records
- `docs/superpowers/plans/*` — stay as feature planning docs
- `THP-*.md` files scattered in `odysseus/agents/` and `odysseus/eval/` — historical design tickets, left in place
- Code, tests, or agent behavior — this is a documentation-only change (except the prompt file relocation and path updates)
- Integration test scenarios — no changes unless prompt paths are hardcoded in them

### 9. Content Sourcing

Documentation content is derived from reading the current code, not from design specs. The specs in `docs/superpowers/specs/` may be used as background context but are not authoritative — the code is the source of truth. Any discrepancy between spec and code should be resolved in favor of what the code actually does.
