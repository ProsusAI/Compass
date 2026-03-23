# THP-74 — Routing Analysis Agent: Updated Design

Date: 2026-03-23 (revised: skills-based architecture)

---

## Summary

THP-74's Phase 1 is restructured from a single monolithic agent prompt into a pipeline of 4 LLM-agnostic Agent Skills and 1 deterministic code step. Each skill is a self-contained `SKILL.md` instruction package with explicit input/output schemas. Phase 2 (stratified split) is unchanged.

Key changes from original design:
1. THP-74 receives the **full dataset** — owns the dev/holdout split.
2. Phase 1 is a **stateless skills pipeline** — 4 LLM skills + 1 code step.
3. Phase 2 produces **`dev.jsonl` + `holdout.jsonl`** — actual dataset files, not a flag mapping.
4. Skills are **LLM-agnostic** — work with any LLM integration.

---

## Goal

Extract the latent logic behind existing routing decisions via a composable skills pipeline, produce a structured routing analysis artifact, and emit a failure-mode-stratified dev/holdout split as two separate dataset files.

---

## Input

The full labeled routing dataset — all samples, no pre-existing split. THP-74 owns the split decision.

---

## Phase 1 — Skills Pipeline

### Execution Order

```
full_dataset.jsonl
      │ (per-example, parallelizable)
      ▼
┌─────────────────────────────┐
│ skill-1                     │
│ rationale-card-extraction   │
└──────────────┬──────────────┘
               │ rationale_cards.jsonl
     ┌─────────┼──────────────────────┐
     ▼         ▼                      ▼
┌──────────┐ ┌───────────────────┐ ┌──────────────────────┐
│ skill-2  │ │ skill-3           │ │ code-step            │
│ ambiguity│ │ boundary-exemplar-│ │ cluster-id-          │
│ taxonomy │ │ tagging           │ │ assignment           │
└────┬─────┘ └────────┬──────────┘ └──────────────────────┘
     │ taxonomy.json   │ tagged_cards.jsonl   │ cluster_ids.json
     └──────┬──────────┘
            ▼
┌───────────────────────────┐
│ skill-4                   │
│ confusion-narrative-      │
│ generation                │
└──────────────┬────────────┘
               │ confusion_narratives.json
               ▼
    routing_analysis_artifact/
```

Skills 2, 3, and the code-step all run in parallel after skill-1 — all only require `rationale_cards.jsonl`. Skill-4 waits for skills 2 and 3.

### Skill Interfaces

**skill-1: `rationale-card-extraction`**

```
Input:  { id, query, label }  (one example per call)
        quality_context.md    (bundled resource from THP-84)
        vocabulary_registry   (current registry — seed or inherited)
Output: {
          id, intent_pattern, complexity_structure,
          tier_disqualifiers, ambiguity_tags,
          proposed_entries (optional — new vocabulary proposals)
        }
```
Schema defined by THP-82. See `2026-03-23-thp-82-routing-rationale-schema.md` for field definitions, vocabulary registry rules, and annotation skill guidance.
Called once per example. Results collected into `rationale_cards.jsonl`.

**skill-2: `ambiguity-taxonomy`**

```
Input:  rationale_cards.jsonl (full set)
Output: taxonomy.json {
          failure_modes: [{ tag, description, example_ids[] }],
          confusion_tags: [{ tag, description }]
        }
```
One call over the full card set.

**skill-3: `boundary-exemplar-tagging`**

```
Input:  rationale_cards.jsonl (full set)
Output: tagged_cards.jsonl — each card annotated with {
          boundary_tag: "prototypical" | "boundary" |
                        "hard-negative" | "rare-class",
          boundary_rationale: string
        }
```
One call over the full card set. Parallel with skill-2.

**skill-4: `confusion-narrative-generation`**

```
Input:  taxonomy.json + tagged_cards.jsonl
Output: confusion_narratives.json {
          narratives: [{
            route_pair, overlap_explanation,
            fragility_assessment, example_ids[]
          }]
        }
```
One call synthesising across all prior outputs.

**code-step: `cluster-id-assignment`**

```
Input:  rationale_cards.jsonl
Process: embed concatenated card fields → k-means
         (embedding model and k declared in THP-110)
Output: cluster_ids.json {
          clusters: [{ cluster_id, label, example_ids[] }],
          model: "<embedding model>",
          k: <int>
        }
```
Deterministic — no LLM call. k is configurable; THP-110 specifies the selection criterion (silhouette-based) and must declare a sensible default range relative to dataset size. k must be large enough to support distinct mixture-of-prompts routing regions (THP-133) without over-fragmenting.

---

## Phase 2 — Stratified Split

Using the failure mode tags (from `taxonomy.json`) and cluster IDs (from `cluster_ids.json`) produced in Phase 1, the orchestrator runs a deterministic stratification algorithm producing two separate dataset files:

- **`dev.jsonl`** — dev set samples (80% default)
- **`holdout.jsonl`** — holdout set samples (20% default)

Split ratio configurable via pipeline run config. Best-effort proportional representation per stratum; strata with fewer than 2 members go entirely to dev. The strata key definition (how failure mode tags and cluster IDs are combined into a single stratum identifier per example) is delegated to THP-86. Algorithm spec owned by THP-86.

---

## Outputs

| Artifact | Description |
|----------|-------------|
| `rationale_cards.jsonl` | One rationale card per example (skill-1) |
| `taxonomy.json` | Failure modes + confusion tags (skill-2) |
| `tagged_cards.jsonl` | Cards annotated with boundary tags (skill-3) |
| `confusion_narratives.json` | Route-overlap narratives (skill-4) |
| `cluster_ids.json` | Cluster assignments (code-step) |
| `dev.jsonl` | Dev set — 80% default (Phase 2) |
| `holdout.jsonl` | Holdout set — 20% default, sealed (Phase 2) |

---

## Holdout Contract

The holdout is sealed for all downstream pipeline agents in the refinement loop. It is unsealed only for the final evaluation agent (THP-76 / THP-79). Enforcement mechanism: the pipeline runner passes only the `dev.jsonl` path to refinement-loop agent invocations; `holdout.jsonl` is never included in their input configuration. The final eval agent receives both paths explicitly. This is a path-level control — agents never have access to a file whose path they are not given.

---

## Downstream Consumers

| Consumer | Uses |
|----------|------|
| Example mining (TBD) | `rationale_cards.jsonl`, `tagged_cards.jsonl`, `dev.jsonl` |
| Exemplar optimization (THP-117) | `rationale_cards.jsonl`, `tagged_cards.jsonl`, `dev.jsonl` |
| Mixture-of-prompts (THP-133) | `cluster_ids.json`, `dev.jsonl` |
| Context assembler (THP-134) | `taxonomy.json`, `confusion_narratives.json` |
| All refinement-loop agents | `dev.jsonl` only |
| Final eval agent (THP-76 / THP-79) | `dev.jsonl` + `holdout.jsonl` |

---

## Task Breakdown Mapping

| Task | Previous scope | New scope |
|------|---------------|-----------|
| THP-82 | Rationale schema | skill-1 output schema — 4-field rationale card (`intent_pattern`, `complexity_structure`, `tier_disqualifiers`, `ambiguity_tags`) + dynamic vocabulary registry. THP-82 is the authoritative schema owner. |
| THP-84 | Quality context doc | Becomes `quality_context.md` — a bundled resource loaded by skill-1 at runtime |
| THP-110 | Methodology decision | Extended: also specifies skill execution order, embedding model, and k parameter |
| THP-86 | Output format + split algorithm | Extended: now also owns the 4 inter-skill I/O schemas |
| THP-85 | Reasoning framework | Repurposed: skill orchestration spec — execution order, data flow, orchestrator error handling |
| THP-112 | Routing Analysis → Prompt Builder contract | Unchanged; now references specific skill output files. **Also depends on THP-86** (inter-skill I/O schemas define the file shapes THP-112 must reference) |
| THP-111 | One set of few-shot examples | Expanded: 4 sets — one per LLM skill, embedded in each SKILL.md |
| THP-105 | One final system prompt | Split into 5 parallel tasks (see below) |

### THP-105 Split

THP-105 is split into 5 parallel Wave 4 tasks:

| New task | Deliverable |
|----------|------------|
| THP-105a | `skill-1-rationale-card-extraction/SKILL.md` |
| THP-105b | `skill-2-ambiguity-taxonomy/SKILL.md` |
| THP-105c | `skill-3-boundary-exemplar-tagging/SKILL.md` |
| THP-105d | `skill-4-confusion-narrative-generation/SKILL.md` |
| THP-105e | `cluster-id-assignment` code module |

All 5 depend on THP-111 (per-skill examples) and THP-85 (orchestration spec). None depend on each other.

---

## Updated Wave Structure

```
Wave 1 (parallel): THP-110, THP-82, THP-84, THP-86
Wave 2 (parallel): THP-85 (needs 110), THP-112 (needs 110 + 86)
Wave 3:            THP-111 (needs 110+85)
Wave 4 (parallel): THP-105a, THP-105b, THP-105c, THP-105d, THP-105e
                   (all need THP-111, THP-85, THP-86)
                   Note: skills may begin with placeholder examples
                   and finalise after THP-111 to avoid blocking
```

---

## Implementation Flow Notes

- **THP-136:** Consumes `cluster_ids.json` from THP-74 and specialises clusters for mixture-of-prompts — does not re-derive clusters.
- **THP-134:** Depends on THP-74 (consumes `taxonomy.json` + `confusion_narratives.json`) in addition to THP-77.

---

## Design Decision Record

**Decision:** 4 stateless LLM skills + 1 code step rather than one monolithic prompt or context-accumulating pipeline.

**Rationale:** Each analysis type has a clean, bounded scope with no need for cross-skill context during execution. Stateless skills are independently testable and improvable; the orchestrator's data flow contract is explicit. LLM-agnostic SKILL.md format works with any integration target.

**Rejected alternatives:**
- Context accumulation (Option B) — richer downstream context but harder to test in isolation; not needed given the clean dependency structure.
- Composite two-call design (Option C) — fewer LLM calls but collapses modularity; synthesis skills lose independent invocability.
- Single monolithic prompt — no modularity, hardest to iterate.
