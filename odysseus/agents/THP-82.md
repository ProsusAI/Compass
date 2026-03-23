# THP-82 — Expand analysis dimensions into routing rationale schema

**Type:** Task
**Status:** To Do
**Epic:** [THP-74](https://prosus-thymo-thesis.atlassian.net/browse/THP-74) — Routing Analysis Agent
**Jira:** [THP-82](https://prosus-thymo-thesis.atlassian.net/browse/THP-82)
**Design spec:** `docs/superpowers/specs/2026-03-23-thp-82-routing-rationale-schema.md`

## Description

Define the structured routing rationale schema that powers clustering, retrieval, and decision-boundary analysis. Each routing example in a dataset is annotated as a rationale card with 4 fields, supported by a dynamic vocabulary registry and a 2-skill annotation pipeline.

## What to build

Produce a reference document covering:

1. **Routing rationale schema** — 4 fields per routing example:
   - `intent_pattern` — the task type the query represents (e.g. factual-lookup, data-filtering, generation-analysis). Dynamic vocabulary with seed values.
   - `complexity_structure` — the reasoning topology required to answer (e.g. single-hop, multi-hop-chain, sequential-dependency). Dynamic vocabulary with seed values.
   - `tier_disqualifiers` — why specific tiers are ruled out, as a list of `{tier: int, reason: string}`. Every non-assigned tier must have at least one entry.
   - `ambiguity_tags` — controlled vocabulary labels for examples near routing boundaries. Dynamic with seed values.

2. **Vocabulary registry** — unified expansion mechanism for all 3 dynamic vocabularies:
   - Seed values are suggestions evaluated against the same threshold as new entries.
   - Minimum cluster size: `max(3, ceil(0.05 * dataset_size))`.
   - Append-only across runs on the same dataset for consistency.
   - New entries require name, definition, example IDs, and justification.

3. **Annotation guidance** — 2 sequential agent skills:
   - `classify_example`: jointly determines `intent_pattern` + `complexity_structure`.
   - `generate_routing_rationale`: produces `tier_disqualifiers` + proposes `ambiguity_tags`.
   - Post-loop validation prunes below-threshold entries and flags orphaned examples.

4. **Validation checks** — per-card and dataset-level:
   - Per-card: required fields, vocabulary membership, disqualifier coverage and format.
   - Dataset-level: cluster thresholds, pruning cleanup, orphaned example flagging, registry consistency.

**Fields considered and dropped:** `required_capability` (absorbed by intent + complexity), `tool_dependency` (no signal in current data), `risk_level` (replaced by ambiguity_tags), `tie_breaker` (redundant or over-specifying). See design spec for full rationale.

**Success criteria:** each routing example can be represented as a structured rationale card, the schema adapts to arbitrary datasets via vocabulary registry expansion, and the annotation pipeline produces consistent results across runs.

## How it links with the rest of the codebase

| Touch point | Detail |
|---|---|
| THP-80 | Each annotated record begins with the base fields defined in the data format spec. The rationale card is an annotation layer on top. |
| THP-81 | Missing signal detection in the output report uses the rationale schema to identify what is absent. |
| THP-86 | Serialization format builds on this logical schema. The vocabulary registry is persisted as part of THP-86's output artifact. |
| THP-106 | Final system prompt embeds the 2 annotation skills so the agent can produce structured rationale cards. |
| THP-74 | Rationale cards feed into Phase 1 (clustering, boundary analysis) and Phase 2 (stratified splitting via ambiguity tags). |

## Dependencies between tasks

- No blockers — can be written in parallel with THP-80 and THP-81.
- THP-106 (final prompt) depends on this being finalised.
