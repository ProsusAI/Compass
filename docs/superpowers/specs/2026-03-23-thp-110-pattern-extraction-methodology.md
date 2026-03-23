# THP-110 — Define Routing Pattern Extraction Methodology

Date: 2026-03-23
Wave: 1 (parallel with THP-82, THP-84, THP-86)
Epic: THP-74 — Routing Analysis Agent

---

## Summary

Design the method selection for how the Routing Analysis agent goes from raw (query, label) pairs to structured routing patterns. This ticket decides the approach — it does not implement or execute it.

**Note:** This ticket blocks THP-85. THP-85 must not be started until this decision is made.

---

## Scope

- Evaluate candidate approaches: cluster by query type, sample decision boundaries, analyse ambiguous cases, or a hybrid
- Select and justify the chosen methodology based on what best serves downstream consumers (exemplar optimization, mixture-of-prompts, context assembler)
- Define the unit of analysis (per-example, per-cluster, per-boundary region) and sequencing
- Specify what inputs the methodology requires from the dataset and in what form
- Declare the embedding model and provider used for cluster ID generation — this is a named dependency consumed by the Phase 2 stratified split algorithm (THP-86)

---

## Deliverable

- Methodology decision document: chosen approach, rationale, unit of analysis, input requirements, and embedding model declaration

---

## Dependencies

None — Wave 1 task.

---

## Blocks

- **THP-85** (reasoning framework execution)
