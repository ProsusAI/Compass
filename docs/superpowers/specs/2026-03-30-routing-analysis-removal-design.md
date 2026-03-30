# Routing Analysis Agent Removal — Design Spec

**Date:** 2026-03-30
**Branch:** feat/refinement-loop-three-sub-agents
**Status:** Draft

## Motivation

The Routing Analysis Agent (stage 3) adds a heavyweight annotation phase — rationale cards, vocabulary registries, classification taxonomies — that constrains the Review Agent's freedom during the refinement loop. The annotations also create a rigid taxonomy that the pipeline must maintain but that doesn't directly improve prompt quality.

This design removes the Routing Analysis Agent, moves the stratified split into the Data Validation Agent, makes few-shot examples self-contained (with reasoning and tier exclusions inline), and gives the Review Agent full ownership of example content.

## New Pipeline Flow

```
User Input → Data Validation (+ split) → Backend Setup → Review Agent (cold-start) → Prompt Builder (v1) ⇄ Review Agent → Final Report
```

### Stages

| Stage | Agent | Responsibility |
|-------|-------|----------------|
| 1 | User Input Agent | Gather problem description, dataset path |
| 2 | Data Validation Agent | Ingest, validate, transform, route-only stratified split → `dev.jsonl` + `holdout.jsonl` |
| 3 | Backend Setup | Configure routing backend(s) |
| 4 | Review Agent (cold-start) → Prompt Builder (v1) | Review Agent crafts initial examples; Prompt Builder assembles v1, evals |
| 5 | Refinement Loop (Review ⇄ Build) | Review Agent reviews results and crafts updated examples; Prompt Builder applies directives and evals |
| 6 | Holdout Validation | Final eval on filtered holdout set |
| 7 | Final Report | Generate report |

### Agent Responsibility Split

| Concern | Owner |
|---------|-------|
| Prompt structure, rules, output schema | Prompt Builder |
| Example selection, content, reasoning, tier exclusions | Review Agent |
| Data quality, format, stratified split | Data Validation Agent |

## Design Decisions

1. **Route-only stratified split** — no annotation dimensions needed; `assigned_route` is the sole stratum key
2. **Review Agent is refinement loop entry point** — cold-start before round 1, reactive refinement after
3. **Self-contained few-shot examples** — each example carries input, assigned route, reasoning, and tier exclusions (why each other route doesn't fit)
4. **Concrete example directives** — Review Agent sends full example content to Prompt Builder, not abstract references
5. **No rationale cards, no vocabulary registry, no classification taxonomy**

## Section 1: Data Validation Agent Changes

The Data Validation Agent gains the stratified split as a third step after validation.

### New Phase 3 — Split

- After `validate_dataset` passes, call `stratified_split_tool` with route-only stratification
- Stratum key: `assigned_route` only (was `(assigned_route, intent_pattern, complexity_structure)`)
- Output: `dev.jsonl` and `holdout.jsonl` written to `outputs/<run_id>/analysis/`
- `SplitReport` simplified: per-route distribution only, no intent/complexity/ambiguity breakdowns
- No rationale card sets produced

### Unchanged

- Phase 1: ingestion, field mapping, user confirmation, transform
- Phase 2: validation checks, `RoutingContext` synthesis
- All existing MCP tools for data validation

### Context Dict Changes

Drops all rationale-related keys. Adds `dev_jsonl_path` and `holdout_jsonl_path` as stage 2 outputs.

## Section 2: Review Agent Changes

### New: Cold-Start Phase

Triggered when the pipeline reaches the refinement loop with no existing search state:

1. Review Agent reads `holdout.jsonl` and `routing_context.json`
2. Selects initial few-shot examples based on route distribution and diversity
3. Crafts each example with:
   - Input text
   - Assigned route
   - Reasoning (why this route fits)
   - Tier exclusions (why each other route doesn't fit)
4. Emits structured example directives to the Prompt Builder for v1 compilation

### Changed: Edit Directives

- `block_type: "example"` directives now carry **concrete content** — the full example body with reasoning and exclusions
- Rule/schema/assembly directives remain abstract — Prompt Builder owns structure
- Review Agent crafts new/updated examples based on eval failure modes (misrouted examples)

### Changed: Review Briefing

- `ReviewBriefing` preprocessor drops rationale card references
- Briefing includes raw holdout examples (or sampled subset) for the Review Agent to select from
- Misrouted examples from eval results drive example selection in subsequent rounds

### Unchanged

- Candidate ranking, promotion/prune decisions, loop signals, regression guards
- Oracle gap analysis, diversity metrics, diminishing returns detection
- Output JSON structure (except richer `edit_directives` for examples)

## Section 3: Refinement Loop Entry & Pipeline Guards

### Loop Entry Change

**Current:** Prompt Builder runs first (build phase), compiles v1, evals, then Review Agent.
**New:** Review Agent runs first (cold-start), crafts examples, then Prompt Builder assembles v1.

### Loop Sequence

```
Review Agent (cold-start / craft examples)
  → Prompt Builder (assemble prompt, eval)
  → Review Agent (review results, craft updated examples)
  → Prompt Builder (apply directives, eval)
  → ... repeat until exit
```

### Pipeline Status (`pipeline_status.py`)

| Change | Detail |
|--------|--------|
| Stage 3 definition | Deleted (Routing Analysis & Split) |
| `_check_stage_3` | Deleted (scratch-file in-progress detection) |
| Stage 2 files | Add `dev.jsonl`, `holdout.jsonl` (in `analysis/` subfolder) |
| Stage numbers | Stage 3 deleted; all subsequent shift down: 4→3, 5→4, 6→5, 7→6, 8→7 (8 stages → 7) |
| `_NEXT_ACTION` | Stage 3 entry deleted; stage 2 includes `stratified_split_tool`; all keys renumbered |
| Loop default phase | `loop_phase` defaults to `"review"` (was `"build"`) when no search state exists |
| Stage 5 review instruction | Updated: Review Agent is loop entry point, handles cold-start and post-eval review |
| Stage 5 build instruction | Updated: Prompt Builder dispatched only after Review Agent example directives exist |

### Search State

- `init_search_state_tool` sets initial `loop_phase` to `"review"` (was `"build"`)
- After Review Agent cold-start completes, advances to `"build"` phase
- Subsequent alternation unchanged: build → review → build → ...

### Guard Updates

- All `require_artifacts` / `check_artifacts` stage numbers shift down by one
- Routing analysis artifact checks removed from all guards
- Stage 2 guards include split outputs
- Prompt Builder gains new precondition: Review Agent example directives must exist before v1 compilation

### Sub-Agent Dispatch Instructions

- Refinement loop review-phase HARD_STOP updated: Review Agent is entry point
- Refinement loop build-phase HARD_STOP adds precondition: example directives must exist
- Stage 3 (routing analysis) HARD_STOP deleted entirely
- Stage 2 HARD_STOP updated to include `stratified_split_tool`

## Section 4: Removals

### Deleted Files

| File | Reason |
|------|--------|
| `odysseus/agents/prompts/routing_analysis_system.md` | Agent removed |
| `odysseus/agents/routing_rationale_models.py` | RationaleCard, RouteExclusion, VocabularyRegistry no longer needed. **Note:** `RoutingContext`, `RouteDefinition`, `RoutingDimension`, `RouteOrdering` must be relocated to `odysseus/agents/routing_context.py` before deletion — these models are used by `save_routing_context` and the Review Agent cold-start. `SeedVocabulary` and `VocabularyEntry` must also be relocated as `RoutingContext.seed_vocabulary` depends on them. **Decision:** drop the `seed_vocabulary` field from `RoutingContext` — it carried annotation-specific vocabulary (`intent_pattern`, `complexity_structure`, `ambiguity_tags`) that no longer exists. If `seed_vocabulary` is dropped, `SeedVocabulary` and `VocabularyEntry` do not need relocation. |
| `odysseus/agents/routing_rationale_checks.py` | LLM-judged semantic overlap checks |
| `odysseus/agents/routing_rationale_checks_deterministic.py` | Deterministic validation checks |
| `odysseus/agents/routing_rationale_registry.py` | Vocabulary registry operations (`create_seed_registry`, `resolve_registry`, `prune_registry`, etc.). **Note:** `compute_dataset_hash` must be relocated to `odysseus/agents/stratified_split.py` — it is used by the split. |
| `odysseus/skills/classify-example/` | Entire skill directory |
| `odysseus/skills/generate-routing-rationale/` | Entire skill directory |
| `odysseus/skills/check-semantic-overlap/` | Entire skill directory |

### Deleted MCP Tools

| Tool | Reason |
|------|--------|
| `create_seed_registry_tool` | Vocabulary registry removed |
| `resolve_registry_tool` | Vocabulary registry removed |
| `validate_rationale_card_set_tool` | Rationale cards removed |
| `prune_registry_tool` | Vocabulary registry removed |

### Deleted MCP Prompt

- `odysseus_routing_analysis` prompt registration

### Deleted MCP Resources

| Resource | Reason |
|----------|--------|
| `odysseus://agents/routing-analysis/classify-example-skill` | Skill removed |
| `odysseus://agents/routing-analysis/generate-rationale-skill` | Skill removed |
| `odysseus://agents/routing-analysis/check-overlap-skill` | Skill removed |

### Deleted Pipeline Artifacts

- `dev_rationale_card_set.json` / `holdout_rationale_card_set.json`
- `vocabulary_registry.json`
- `validation_report.json` (rationale validation report)
- `scratch/<dataset_hash>/` checkpoint files (phase1/2/3 classification/rationale)

### Modified (Not Deleted)

| File | Change |
|------|--------|
| `odysseus/agents/stratified_split.py` | Simplified to route-only stratification; no rationale card set partitioning. Absorb `compute_dataset_hash` from deleted registry module. |
| `stratified_split_tool` (in `mcp.py`) | Remove `card_set_path` parameter, remove card set output writes, update stage label from Stage 3 to Stage 2 |
| `SplitReport` model | Drops intent/complexity/ambiguity breakdowns |
| `odysseus/agents/pipeline_status.py` | Stage 3 removed, renumbered, loop defaults to review-first |
| `odysseus/agents/pipeline_guards.py` | Stage numbers shifted, rationale artifact checks removed |
| `odysseus/agents/review_models.py` | Example directives carry concrete content |
| `odysseus/agents/review_preprocessor.py` | Drops rationale card processing, includes holdout examples |
| `odysseus/agents/prompts/review_agent_system.md` | Cold-start phase, example crafting responsibility |
| `odysseus/agents/prompts/prompt_builder_system.md` | Drops rationale card references; receives example content from Review Agent |
| `odysseus/agents/prompt_builder_search.py` | Init defaults to review phase |
| `odysseus/agents/prompt_builder_search_ops.py` | Matching changes |
| `odysseus/mcp.py` | Remove routing analysis tool/prompt/resource registrations; remove `validate_deterministic` import; update `save_routing_context` and `RoutingContext` imports to new location |
| `odysseus/agents/prompts/data_validation_system.md` | Add Phase 3 split instructions; reference `stratified_split_tool`; update outputs list |
| `odysseus/agents/__init__.py` | Remove all re-exports of deleted rationale/registry symbols; update `RoutingContext` import path |
| `odysseus/agents/README.md` | Remove rationale card/registry documentation sections; update pipeline description |
| `docs/architecture.md` | Substantial rewrite: pipeline flow, agent table, stage definitions, context dict keys, model docs, tool/prompt/resource tables, artifact directory descriptions |

### New Files

| File | Content |
|------|---------|
| `odysseus/agents/routing_context.py` | Relocated `RoutingContext`, `RouteDefinition`, `RoutingDimension`, `RouteOrdering` models from deleted `routing_rationale_models.py` |

### Test Impact

**Delete:**

| File | Reason |
|------|--------|
| `tests/test_routing_rationale_models.py` | Models deleted |
| `tests/test_routing_rationale_registry.py` | Registry deleted |
| `tests/test_routing_rationale_checks.py` | Checks deleted |
| `tests/test_deterministic_validation.py` | Deterministic checks deleted |
| `tests/test_stratified_split_card_set.py` | Card set partitioning removed |

**Modify:**

| File | Change |
|------|--------|
| `tests/test_stratified_split.py` | Remove rationale card references; test route-only stratification |
| `tests/test_pipeline_status.py` | Stage numbers shift; stage 3 checks removed |
| `tests/test_review_models.py` | Updated example directive structure |
| `tests/test_mcp.py` | Deleted tool/prompt/resource registrations |

**Scenario files:** Routing-analysis-specific scenarios in `tests/scenarios/` (e.g. `23_classify_example_simple_queries.md` through `36_validation_to_analysis_borderline.md`) need deletion or rewrite. Exact scope determined during implementation.

### Data Contamination Note

Few-shot examples are selected from the holdout set. This is intentional — the existing `filter_holdout_dataset_tool` removes few-shot example IDs from the holdout JSONL before final evaluation, preventing contamination.
