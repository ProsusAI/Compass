# THP-74 — Routing Analysis Agent: Updated Design

Date: 2026-03-23

---

## Summary

This document captures the updated design for THP-74 (Routing Analysis Agent). Key changes from the original epic:

1. THP-74 receives the **full dataset** (no pre-existing split) and owns the dev/holdout split decision.
2. The agent operates in **two sequential phases**: routing analysis first, then stratified splitting.
3. Phase 2 produces **two separate dataset files** (`dev.jsonl` + `holdout.jsonl`) — not a flag mapping.
4. The holdout is structurally sealed by file-level separation, not convention.

---

## Goal

Extract the latent logic behind existing routing decisions, produce a structured routing analysis artifact, and emit a failure-mode-stratified dev/holdout split as two separate dataset files. Together these outputs form the upstream dependency for example mining, exemplar optimization, cluster-based prompt specialization, skill-based retrieval, and final evaluation.

---

## Input

The full labeled routing dataset — all samples, no pre-existing split. THP-74 owns the split decision and therefore must receive the complete dataset.

---

## Two-Phase Operation

### Phase 1 — Routing Analysis (full dataset)

The agent analyzes every sample and produces the **routing analysis artifact** containing:

- **Routing rationale cards** — one per labeled example; normalized fields: intent pattern, required capability, risk/ambiguity level, tool dependency, disqualifiers, tie-breaker logic
- **Ambiguity taxonomy** — confusion tags classifying examples by type of decision difficulty (failure modes)
- **Decision-boundary exemplars** — examples tagged as prototypical, boundary, hard-negative, or rare-class
- **Confusion-matrix narratives** — human-readable explanations of where routes overlap and why
- **Cluster IDs** — initial groupings of examples into routing regions derived from embedding similarity over concatenated rationale card fields. Clustering algorithm and k are determined in THP-110; a silhouette-based k selection over a k-means base is the expected approach.

### Phase 2 — Stratified Split

Using the confusion tags (failure modes, from Phase 1 ambiguity taxonomy) and cluster IDs produced in Phase 1, the agent produces two separate dataset files:

- **`dev.jsonl`** — dev set samples
- **`holdout.jsonl`** — holdout set samples

Default split ratio: 80% dev / 20% holdout; configurable via pipeline run config. The split targets best-effort proportional representation of each failure mode and cluster in both sets; strata with fewer than 2 members are assigned entirely to dev as an exception. Strata with 2+ members always contribute at least one sample to holdout. The embedding model used for cluster ID generation is declared as a dependency in THP-110.

---

## Outputs

| Artifact | Description |
|----------|-------------|
| Routing analysis artifact | Rationale cards, ambiguity taxonomy, boundary exemplars, confusion narratives, cluster IDs — produced over the full dataset |
| `dev.jsonl` | Dev set samples (80% default), stratified on failure modes and cluster IDs |
| `holdout.jsonl` | Holdout set samples (20% default), sealed for refinement-loop agents |

---

## Holdout Contract

The holdout set is sealed for all downstream pipeline agents in the refinement loop. It is unsealed only for the final evaluation agent (THP-76 / THP-79). No agent in the prompt optimization loop (THP-77, THP-78, THP-117, THP-133, THP-134) may consume holdout samples. The pipeline runner passes `dev.jsonl` to refinement-loop agents and `holdout.jsonl` exclusively to the final eval agent — structural file-level separation prevents accidental leakage.

---

## Downstream Consumers

| Consumer | Uses |
|----------|------|
| Example mining (TBD — separate from THP-117) | Analysis artifact (rationale cards, boundary tags) + `dev.jsonl` |
| Exemplar optimization (THP-117) | Analysis artifact (rationale cards, boundary tags) + `dev.jsonl` |
| Mixture-of-prompts (THP-133) | Analysis artifact (cluster IDs) + `dev.jsonl` |
| Context assembler (THP-134) | Analysis artifact (ambiguity taxonomy, confusion narratives) |
| All pipeline agents in refinement loop | `dev.jsonl` only |
| Final evaluation agent (THP-76 / THP-79) | `dev.jsonl` + `holdout.jsonl` |

---

## Implementation Flow Notes

- **THP-136 scope:** THP-136 (*"Specialise routing region clusters from THP-74 analysis artifact"*, child of THP-133) consumes THP-74's cluster IDs and specialises them for the mixture-of-prompts context — it does not re-derive clusters from scratch.
- **THP-134 dependency:** The implementation flow has been updated to add THP-74 as a dependency of THP-134, since THP-134 consumes the ambiguity taxonomy and confusion narratives from THP-74's analysis artifact.
- **Wave ordering:** THP-85 is blocked by THP-110 and must be in Wave 2. Correct wave sequence: Wave 1 (THP-110, THP-82, THP-84, THP-86) → Wave 2 (THP-85, THP-112) → Wave 3 (THP-111) → Wave 4 (THP-105).

---

## Design Decision Record

**Decision:** Phase 2 produces two separate dataset files (`dev.jsonl`, `holdout.jsonl`) rather than a `split_manifest.json` flag mapping or embedding a split field on each rationale card.

**Rationale:** Structural file-level separation makes holdout leakage impossible rather than just a convention — a consumer either has the file or it doesn't. Downstream agents receive `dev.jsonl` directly with no filtering logic required. The split is auditable and self-contained.

**Rejected alternatives:**
- `split_manifest.json` (ID → flag) — cleaner than embedding in cards but still requires every consumer to implement filtering correctly; leakage harder to detect.
- Embedding `split: "dev" | "holdout"` on each rationale card — simplest output but pushes filtering responsibility onto every consumer and makes leakage hardest to audit.
