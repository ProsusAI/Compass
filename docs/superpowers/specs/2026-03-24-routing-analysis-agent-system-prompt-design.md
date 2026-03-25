# Routing Analysis Agent — System Prompt Design

**Date:** 2026-03-24
**Status:** Draft
**Branch:** `routing-analysis-agent`

## Summary

Design for the Routing Analysis Agent system prompt that unifies the annotation skills (`classify-example`, `generate-routing-rationale`), a new `check-semantic-overlap` skill, and code-driven operations (validation, registry management, stratified split) into a single orchestrating agent. The agent receives upstream inputs from the User Input Agent and Data Validation Agent, processes the full dataset autonomously, and produces split dev/holdout artifacts with matched rationale card sets.

## Inputs

The agent reads all inputs from context dict keys at startup:

| Key | Type | Source | Description |
|-----|------|--------|-------------|
| `validated_input_report_path` | `str` (file path) | Input Agent | Markdown report with confirmed problem description, metrics, thresholds, split ratio |
| `data_quality_report` | `DataQualityReport` | Data Validation Agent | Schema findings, label distribution, volume assessment (returned via tool, not a file path) |
| `routing_context` | `RoutingContext` | Data Validation Agent | Domain, routes, dimensions, ordering, seed vocabulary |
| `dataset_path` | `str` (file path) | Data Validation Agent | Path to the validated JSONL dataset |

Key naming follows the existing architecture doc convention: objects are passed directly (no `_path` suffix), file references use `_path`. If any input is missing or unreadable, the agent fails immediately with a clear message — no partial processing.

## MCP Tools

Code-driven, deterministic operations exposed as MCP tools:

| Tool | Purpose | Phase |
|------|---------|-------|
| `create_seed_registry()` | Initialize vocabulary registry with 4 canonical ambiguity tags | Phase 1 |
| `resolve_registry(dataset_hash)` | Check if a prior registry exists for this dataset | Phase 1 |
| `validate_rationale_card_set(card_set, routing_context, dataset_size)` | Run deterministic per-card + dataset-level checks (no LLM judge) | Phase 3 |
| `prune_registry(registry, dataset_size)` | Remove entries below cluster threshold; returns `(pruned_registry, removed_entries_map)` | Phase 3 |
| `stratified_split(examples, card_set, dev_ratio)` | Split examples + card set into dev/holdout matched pairs | Phase 4 |

**Implementation notes:**

- **`validate_rationale_card_set`**: The existing Python function requires a `judge_fn` parameter for the async LLM-judged `check_registry_consistency` call. The MCP tool wrapper calls the deterministic sub-checks directly (skipping `check_registry_consistency`), rather than invoking the top-level function with a no-op judge. Semantic overlap is handled separately by the `check-semantic-overlap` skill.
- **`resolve_registry`**: The underlying function takes `(dataset_hash, registry_dir, inherit_from)`. The MCP tool supplies a default `registry_dir` based on the run's output path.
- **`stratified_split`** (to be extended): Currently returns `tuple[list[Example], list[Example], SplitReport]`. Must be extended to also partition the `RationaleCardSet` by `example_id`, returning `tuple[list[Example], list[Example], RationaleCardSet, RationaleCardSet, SplitReport]` (dev examples, holdout examples, dev card set, holdout card set, split report).

## Skills

LLM-reasoning operations following the [Agent Skills spec](https://agentskills.io/specification):

| Skill | Purpose | Phase | Status |
|-------|---------|-------|--------|
| `classify-example` | Determine `intent_pattern` + `complexity_structure` per example | Phase 1 | Exists |
| `generate-routing-rationale` | Determine `route_exclusions` + `ambiguity_tags` per example | Phase 2 | Exists |
| `check-semantic-overlap` | LLM-judged pairwise overlap check across vocabulary entries | Phase 3 | New |

### New skill: `check-semantic-overlap`

Located at `odysseus/skills/check-semantic-overlap/SKILL.md`. Created following the Agent Skills spec using the `skill-creator` skill. Replaces the async `check_registry_consistency` LLM judge function — the agent itself performs the semantic comparison by activating this skill during Phase 3 validation.

## Execution Phases

### Phase 1 — Classification Pass

1. Read all context dict inputs and validate they exist
2. Initialize vocabulary registry (`create_seed_registry()` or `resolve_registry()`)
3. Activate `classify-example` skill
4. Process all examples — assign `intent_pattern` + `complexity_structure` to each
5. Write checkpoint: partial card set + registry snapshot to scratch directory

### Phase 2 — Rationale Pass

1. Activate `generate-routing-rationale` skill
2. Process all examples — assign `route_exclusions` + `ambiguity_tags` to each
3. Build complete `RationaleCardSet` with `VocabularyRegistry`
4. Write checkpoint: complete card set to scratch directory

### Phase 3 — Validation & Fix Loop (max 5 retries)

1. Prune registry entries below cluster threshold (`prune_registry`)
2. Call `validate_rationale_card_set()` tool (deterministic checks on post-pruning state)
3. Activate `check-semantic-overlap` skill (LLM-judged overlap)
4. If all checks pass → proceed to Phase 4
5. If failures → auto-fix affected cards/registry, write checkpoint, retry
6. If still failing after 5 retries → surface to user with detailed error report

### Phase 4 — Split & Output

1. Call `stratified_split()` — produces dev/holdout examples + matched card sets
2. Write final artifacts to `outputs/`
3. Clean up scratch directory
4. Set context dict keys (see Output Contract)

## Execution Model

The agent processes all examples autonomously in each phase. No human-in-the-loop per example. This is by design:

- **Vocabulary coherence** — seeing all examples before finalizing vocabulary entries avoids poorly calibrated early entries
- **Cluster thresholds** — pruning entries below `max(3, ceil(0.05 * dataset_size))` only makes sense after seeing everything
- **Pattern recognition** — the agent spots clusters and patterns across the full dataset

For large datasets, the agent may use a two-pass internal strategy (survey first, then commit) but this is managed internally, not exposed to the user.

## Checkpointing & Scratch Space

**Scratch directory:** `scratch/<run_id>/` (where `run_id` = dataset content hash, deterministic for a given dataset)

| Checkpoint | Written after | Contents |
|------------|--------------|----------|
| `scratch/<run_id>/phase1_classification.json` | Phase 1 | Partial card set (intent_pattern + complexity_structure only) + registry snapshot |
| `scratch/<run_id>/phase2_rationale.json` | Phase 2 | Complete card set with all fields + full registry |
| `scratch/<run_id>/phase3_validated.json` | Phase 3 | Validated card set + validation results |

**Incremental writes:** Within Phase 1 and Phase 2, the agent appends to the current checkpoint file periodically so progress isn't lost on interruption.

**Cleanup:** On successful Phase 4 completion, the entire `scratch/<run_id>/` directory is deleted. Final artifacts live in `outputs/` only.

**Recovery:** If an existing `scratch/<run_id>/` directory is detected on startup (same dataset hash), the agent reads the latest checkpoint and resumes from that phase. Recovery only applies when the dataset hash matches. A changed dataset produces a new `run_id` and starts fresh.

## Error Handling

### Validation failure auto-fix strategies

| Severity | Failure type | Auto-fix strategy |
|----------|-------------|-------------------|
| Critical | Missing required fields | Re-annotate affected cards through the relevant skill |
| Critical | Vocabulary not in registry | Add entry to registry or re-classify the example |
| Critical | Missing route exclusions | Re-run `generate-routing-rationale` for affected cards |
| Critical | Stale vocabulary references (post-pruning) | Re-annotate affected cards with updated registry |
| Warning | Cluster threshold not met | Merge thin entries into semantically closest entry, reassign affected cards |
| Warning | Orphaned examples | Add example IDs to appropriate registry entries |
| Warning | Semantic overlap detected | Merge overlapping entries, pick the more descriptive name, reassign cards |

### Retry cap

5 attempts. After 5 failed validation loops, the agent writes all current state to scratch, outputs a detailed error report listing all unresolved checks with `affected_ids`, and surfaces to the user.

## Output Contract

Outputs are partitioned to prevent information leakage between dev and holdout sets.

### To Prompt Builder Agent

| Context key | Description |
|-------------|-------------|
| `dev_rationale_card_set_path` | Rationale cards for dev examples only |
| `dev_jsonl_path` | Dev split examples |
| `vocabulary_registry_path` | Full vocabulary registry |
| `split_report_path` | Split statistics and distribution report |
| `routing_context` | `RoutingContext` object (passed through from input) |

### To Final Reporting Agent only

| Context key | Description |
|-------------|-------------|
| `holdout_rationale_card_set_path` | Rationale cards for holdout examples only |
| `holdout_jsonl_path` | Holdout split examples |

The holdout card set and examples are never sent to the Prompt Builder Agent.

Dataset provenance (`dataset_hash`) is embedded in the `RationaleCardSet` and `SplitReport` artifacts, allowing downstream agents to verify they're operating on the correct dataset.

## System Prompt Structure

The system prompt file (`odysseus/agents/prompts/routing_analysis_system.md`) follows these sections:

1. **Identity & Role** — Agent description and purpose
2. **Inputs** — Context dict keys table, startup validation
3. **Tools** — MCP tool descriptions and signatures
4. **Skills** — Skill names + when to activate each
5. **Phases** — Phase 1-4 with sequencing rules
6. **Checkpointing** — Scratch directory conventions, incremental writes, recovery
7. **Validation & Error Handling** — Fix strategies by check type, 5-attempt retry cap
8. **Output Contract** — Context dict keys split by downstream consumer
9. **Constraints** — Information leakage prevention, deterministic split guarantees

## Required Documentation Updates

The following changes to `docs/architecture.md` must accompany implementation (per project rules):

- Add `data_quality_report` and `dataset_path` to the Context Dict Reference table (set by Data Validation Agent)
- Update the Data Validation Agent's "Writes to Context" column to include `data_quality_report` and `dataset_path` as named context keys
- Add all output context keys (`dev_rationale_card_set_path`, `dev_jsonl_path`, `vocabulary_registry_path`, `split_report_path`, `holdout_rationale_card_set_path`, `holdout_jsonl_path`) to the Context Dict Reference
- Update the Routing Analysis Agent row with input/output keys and status

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Process all examples at once (no batching/human-in-the-loop) | Vocabulary coherence, cluster threshold accuracy, pattern recognition |
| System prompt as orchestrator, skills as workers (Approach C) | Matches existing project pattern, avoids unnecessary indirection |
| Skills follow Agent Skills spec (agentskills.io) | Standard format, progressive disclosure, portable |
| Semantic overlap as skill, not tool | LLM-judged operations belong in skills, not code-driven tools |
| Scratch directory for checkpoints, cleaned on success | Recovery without output pollution |
| Card set split alongside example split | Prevents information leakage — holdout cards never reach Prompt Builder |
| 5-attempt retry cap on validation | Allows autonomous fix loop while preventing infinite loops |
| Context dict keys for input/output | Consistent with existing pipeline conventions |
