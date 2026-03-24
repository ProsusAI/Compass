# Documentation Overhaul Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul project documentation with a layered architecture map, module READMEs, agent prompt relocation, and a Claude Code rule for consistent maintenance.

**Architecture:** Top-level map doc (`docs/architecture.md`) for 30-second re-orientation links to module READMEs (`odysseus/agents/README.md`, `odysseus/eval/README.md`, `prompts/README.md`) that live next to the code they describe. Agent system prompts relocate from top-level `prompts/` to `odysseus/agents/prompts/`. A Claude Code rule enforces doc updates on interface changes.

**Tech Stack:** Markdown, Mermaid diagrams, Claude Code rules

**Spec:** `docs/superpowers/specs/2026-03-24-documentation-overhaul-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `odysseus/agents/prompts/user_input_system.md` | Move from `prompts/` | User Input Agent system prompt |
| `odysseus/agents/prompts/eval_runner_system.md` | Move from `prompts/` | Eval Runner Agent system prompt |
| `odysseus/agents/prompts/data_validation_system.md` | Move from `prompts/` | Data Validation Agent system prompt |
| `prompts/eval_runner_system.txt` | Delete | Duplicate of `.md` variant |
| `odysseus/mcp.py` | Modify (lines 43, 54) | Update `_load_text()` paths for relocated prompts |
| `odysseus/agents/eval_runner.py` | Modify (line 125) | Update `FilePromptManager` prompts_dir path |
| `tests/test_eval_runner_prompt.py` | Modify (lines 10, 23) | Update PROMPTS_DIR and file extension reference |
| `docs/architecture.md` | Create | Top-level architecture map |
| `docs/project-overview.md` | Modify | Review and update against current code |
| `odysseus/agents/README.md` | Create | Agents module documentation |
| `odysseus/eval/README.md` | Create | Eval engine entry-point documentation |
| `prompts/README.md` | Create | Routing prompt store documentation |
| `.claude/rules/update-docs-before-commit.md` | Create | Doc maintenance rule |
| `CLAUDE.md` | Modify | Add architecture doc pointer, update prompt paths |

---

## Chunk 1: Agent System Prompt Relocation

This chunk must go first — it changes file paths that all subsequent documentation references.

### Task 1: Move agent system prompts to new location

**Files:**
- Create dir: `odysseus/agents/prompts/`
- Move: `prompts/user_input_system.md` → `odysseus/agents/prompts/user_input_system.md`
- Move: `prompts/eval_runner_system.md` → `odysseus/agents/prompts/eval_runner_system.md`
- Move: `prompts/data_validation_system.md` → `odysseus/agents/prompts/data_validation_system.md`
- Delete: `prompts/eval_runner_system.txt`

- [ ] **Step 1: Create the target directory**

```bash
mkdir -p odysseus/agents/prompts
```

- [ ] **Step 2: Move the three agent system prompts**

```bash
git mv prompts/user_input_system.md odysseus/agents/prompts/user_input_system.md
git mv prompts/eval_runner_system.md odysseus/agents/prompts/eval_runner_system.md
git mv prompts/data_validation_system.md odysseus/agents/prompts/data_validation_system.md
```

- [ ] **Step 3: Delete the duplicate `.txt` variant**

```bash
git rm prompts/eval_runner_system.txt
```

- [ ] **Step 4: Verify the prompts directory is now empty**

```bash
ls prompts/
```

Expected: empty directory (no files).

- [ ] **Step 5: Commit the file moves**

```bash
git add -A
git commit -m "refactor: move agent system prompts to odysseus/agents/prompts/

Relocate user_input_system.md, eval_runner_system.md, and
data_validation_system.md from top-level prompts/ to
odysseus/agents/prompts/. Delete duplicate eval_runner_system.txt.

Top-level prompts/ is now reserved for routing prompts only."
```

### Task 2: Update code references to relocated prompts

**Files:**
- Modify: `odysseus/mcp.py:43,54`
- Modify: `odysseus/agents/eval_runner.py:125`
- Modify: `tests/test_eval_runner_prompt.py:10,23`

- [ ] **Step 1: Update `mcp.py` — user input prompt path**

In `odysseus/mcp.py` line 43, change:
```python
system_prompt = _load_text("prompts/user_input_system.md")
```
to:
```python
system_prompt = _load_text("odysseus/agents/prompts/user_input_system.md")
```

- [ ] **Step 2: Update `mcp.py` — data validation prompt path**

In `odysseus/mcp.py` line 54, change:
```python
system_prompt = _load_text("prompts/data_validation_system.md")
```
to:
```python
system_prompt = _load_text("odysseus/agents/prompts/data_validation_system.md")
```

- [ ] **Step 3: Update `eval_runner.py` — FilePromptManager path**

In `odysseus/agents/eval_runner.py` line 125, change:
```python
prompt_manager=FilePromptManager(prompts_dir=Path("prompts")),
```
to:
```python
prompt_manager=FilePromptManager(prompts_dir=Path("odysseus/agents/prompts")),
```

Note: `FilePromptManager` takes a `Path` and resolves it directly. The `EvalRunnerAgent` is instantiated from `mcp.py` where CWD is the project root, so this relative path will resolve correctly. If this breaks, use `Path(__file__).resolve().parent / "prompts"` instead for an absolute reference.

- [ ] **Step 4: Update `test_eval_runner_prompt.py` — PROMPTS_DIR**

In `tests/test_eval_runner_prompt.py` line 10, change:
```python
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
```
to:
```python
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "odysseus" / "agents" / "prompts"
```

- [ ] **Step 5: Update `test_eval_runner_prompt.py` — file extension**

In `tests/test_eval_runner_prompt.py` line 23, change:
```python
path = PROMPTS_DIR / "eval_runner_system.txt"
```
to:
```python
path = PROMPTS_DIR / "eval_runner_system.md"
```

- [ ] **Step 6: Run the eval runner prompt tests to verify**

```bash
uv run pytest tests/test_eval_runner_prompt.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Run the full test suite to catch any other breakage**

```bash
uv run pytest -v
```

Expected: no new failures.

- [ ] **Step 8: Commit the code reference updates**

```bash
git add odysseus/mcp.py odysseus/agents/eval_runner.py tests/test_eval_runner_prompt.py
git commit -m "fix: update code references for relocated agent prompts

Update _load_text() paths in mcp.py, FilePromptManager path in
eval_runner.py, and PROMPTS_DIR + file extension in test."
```

---

## Chunk 2: Architecture Map and Project Overview

### Task 3: Create `docs/architecture.md`

**Files:**
- Create: `docs/architecture.md`

Content must be derived from reading the current code, not from old specs. Read each source file before writing its documentation section.

- [ ] **Step 1: Read source files for accuracy**

Read these files to extract current state:
- `odysseus/mcp.py` — MCP tools, prompts, resources
- `odysseus/agents/__init__.py` — exported symbols
- `odysseus/agents/eval_runner.py` — EvalRunnerAgent interface
- `odysseus/agents/data_validation_checks.py` — DataQualityReport, check functions
- `odysseus/agents/routing_rationale_models.py` — RationaleCard, VocabularyRegistry, RoutingContext
- `odysseus/agents/routing_rationale_checks.py` — validation check functions
- `odysseus/agents/routing_rationale_registry.py` — registry operations
- `odysseus/agents/user_input_report.py` — UserInputReport contract
- `odysseus/eval/models.py` — ScoreReport, RunReport, RunConfig
- `odysseus/eval/protocols.py` — protocol definitions
- Agent system prompts in `odysseus/agents/prompts/`

- [ ] **Step 2: Write `docs/architecture.md` with six sections**

The document must contain:

**Section 1 — Pipeline Overview:** Mermaid diagram of the full pipeline. Mark agent status (done/in progress/planned). Show data flow between agents.

**Section 2 — Agent Registry Table:** One row per agent with columns: Agent, Type (LLM-driven / code-driven), Module / Prompt, Status, Reads from Context, Writes to Context.

**Section 3 — Context Dict Reference:** Table of all context keys: Key, Type, Set By, Consumed By, Description.

**Section 4 — Shared Models:** One paragraph each for DataQualityReport, RationaleCardSet/RationaleCard, VocabularyRegistry, ScoreReport/RunReport, RoutingContext. Link to source file.

**Section 5 — MCP Surface:** Three tables — tools, prompts, resources. Each with: name, status, purpose, backing agent/module.

**Section 6 — Directory Guide:** One-liner per top-level directory, linking to module READMEs where they exist.

Style: tables over prose, concise descriptions, backticks for code references, links to source files.

- [ ] **Step 3: Verify all links and file references in the doc are valid**

Check that every file path mentioned in the doc actually exists in the repo.

- [ ] **Step 4: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: add architecture map for quick project re-orientation

Layered entry point with pipeline diagram, agent registry, context
dict reference, shared models, MCP surface, and directory guide."
```

### Task 4: Update `docs/project-overview.md`

**Files:**
- Modify: `docs/project-overview.md`

- [ ] **Step 1: Read current `docs/project-overview.md` and compare against code**

Check each section for accuracy:
- Agent list and statuses (Section 4 + Section 7)
- Pipeline diagram (Section 3)
- Tech stack (Section 9)
- Repository structure (Section 10)
- Data flow (Section 5)

- [ ] **Step 2: Update stale sections**

Known updates needed:
- Section 7 (Current Status): Update agent statuses to match reality. Data Validation is done, User Input is in progress, Eval Runner has a system prompt and is partially done. Routing Analysis annotation models/checks/registry are done.
- Section 4: Update agent descriptions where work has been completed (e.g., Data Validation now has defined formats THP-80, THP-81; Eval Runner has system prompt THP-104).
- Section 10 (Repository Structure): Add `odysseus/agents/prompts/` for agent system prompts. Update `prompts/` description to "Routing prompt store". Add `odysseus/eval/docs/` for eval documentation.
- Add a link to `docs/architecture.md` near the top for technical detail.
- Remove any "Key open work" items that have been completed.

- [ ] **Step 3: Verify no references to deprecated patterns remain**

Search for: "async Python classes" as agent description, old prompt paths, completed THP items still listed as "To Do".

- [ ] **Step 4: Commit**

```bash
git add docs/project-overview.md
git commit -m "docs: update project overview with current agent statuses and structure"
```

---

## Chunk 3: Module READMEs

### Task 5: Create `odysseus/agents/README.md`

**Files:**
- Create: `odysseus/agents/README.md`

- [ ] **Step 1: Read all agent module files for current state**

Read each `.py` file in `odysseus/agents/` to extract:
- Classes and their purposes
- Key functions and their signatures
- Which context keys or models each defines
- Inter-module relationships

- [ ] **Step 2: Write `odysseus/agents/README.md`**

Structure:
1. **Intro** — Agents are LLM-driven (system prompts surfaced via MCP). Python code here provides domain models, validation logic, and registry operations. Agent prompts live in `prompts/` subdirectory.
2. **EvalRunnerAgent** — The one code-driven exception. Briefly explain its role and interface.
3. **Per-module sections** — For each `.py` file: what it contains, key classes/functions, which context keys or models it defines.
4. **Shared models** — RationaleCard, VocabularyRegistry, DataQualityReport, RoutingContext: what they are, how they relate, where defined.
5. **Agent prompts** — Note on the `prompts/` subdirectory, one prompt per agent.

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/README.md
git commit -m "docs: add agents module README

Covers LLM-driven agent architecture, domain models, validation
logic, registry operations, and EvalRunnerAgent as code-driven exception."
```

### Task 6: Create `odysseus/eval/README.md`

**Files:**
- Create: `odysseus/eval/README.md`

- [ ] **Step 1: Read eval module files and existing docs**

Read:
- `odysseus/eval/controller.py`, `models.py`, `protocols.py` — core interfaces
- `odysseus/eval/docs/README.md`, `docs/architecture.md`, `docs/backends.md` — existing documentation
- `odysseus/eval/dataset.py`, `metrics.py`, `collector.py`, `rate_limiter.py` — supporting modules

- [ ] **Step 2: Write `odysseus/eval/README.md` as entry point**

This is an orienting README that summarizes and links to `docs/` for depth. Structure:
1. **What this module does** — The evaluation engine: runs prompts against datasets, computes metrics, produces reports.
2. **How it works** — Brief: controller orchestrates backends, dataset, metrics, collector via protocol-based DI.
3. **Key concepts** — `RunDependencies`, `RunConfig`, `ScoreReport`, backend profiles.
4. **Deep dives** — Link to `docs/architecture.md` for internals, `docs/backends.md` for backend config, `docs/README.md` for the existing detailed docs.
5. **How EvalRunnerAgent wires it** — Config loading, dependency construction, report diffing.

Do NOT duplicate content from `docs/` subdirectory.

- [ ] **Step 3: Commit**

```bash
git add odysseus/eval/README.md
git commit -m "docs: add eval engine entry-point README

Orients reader and links to existing docs/ subdirectory for
detailed architecture and backend documentation."
```

### Task 7: Create `prompts/README.md`

**Files:**
- Create: `prompts/README.md`

- [ ] **Step 1: Read `odysseus/prompts/manager.py` for current behavior**

Extract: supported extensions, versioning logic, "latest" resolution, watch mechanism, `ODYSSEUS_PROMPTS_DIR` env var.

- [ ] **Step 2: Write `prompts/README.md`**

Structure:
1. **Purpose** — Routing prompt store: versioned prompts being optimized by the pipeline.
2. **Versioning** — File stem = version name, `"latest"` = most recently modified. Extension priority: `.yaml` > `.yml` > `.txt`.
3. **File formats** — YAML and TXT supported.
4. **How prompts are loaded** — `FilePromptManager` scans this directory, caches contents, supports hot-reload via `watch()`.
5. **Environment** — `ODYSSEUS_PROMPTS_DIR` env var overrides default location.
6. **Note** — Agent system prompts live in `odysseus/agents/prompts/`, not here.

- [ ] **Step 3: Commit**

```bash
git add prompts/README.md
git commit -m "docs: add routing prompt store README

Documents versioning scheme, supported formats, FilePromptManager
behavior, and ODYSSEUS_PROMPTS_DIR override."
```

---

## Chunk 4: Claude Code Rule and CLAUDE.md Update

### Task 8: Create Claude Code rule

**Files:**
- Create: `.claude/rules/update-docs-before-commit.md`

- [ ] **Step 1: Create the rules directory**

```bash
mkdir -p .claude/rules
```

- [ ] **Step 2: Write `.claude/rules/update-docs-before-commit.md`**

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

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/update-docs-before-commit.md
git commit -m "chore: add Claude Code rule for doc maintenance on interface changes"
```

### Task 9: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Read current `CLAUDE.md`**

- [ ] **Step 2: Add documentation pointers to Project Structure section**

Add after the existing structure block:
- `docs/architecture.md` as the technical architecture reference
- Note that agent system prompts live in `odysseus/agents/prompts/`
- Note that `prompts/` (top-level) is the routing prompt store for versioned routing prompts

Also update the Project Structure tree to reflect:
- `odysseus/agents/prompts/` — Agent system prompts
- `prompts/` description changed to "Routing prompt store (versioned prompts)"

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with architecture doc pointer and prompt locations"
```

### Task 10: Final verification

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass (no regressions from prompt relocation).

- [ ] **Step 2: Run linter**

```bash
uv run ruff check .
```

Expected: no new issues.

- [ ] **Step 3: Verify all doc cross-references resolve**

Check that every file path mentioned in `docs/architecture.md`, module READMEs, and `CLAUDE.md` exists in the repo.

- [ ] **Step 4: Read through `docs/architecture.md` end-to-end**

Final sanity check: does the architecture map accurately reflect the current codebase?
