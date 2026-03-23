# THP-85 — Expand Reasoning Framework into Boundary and Cluster Analysis Framework

Date: 2026-03-23
Wave: 2 (after THP-110)
Epic: THP-74 — Routing Analysis Agent

---

## Summary

Define the stepwise reasoning framework that executes the methodology selected in THP-110. This ticket is **blocked by THP-110** — it must not be started until the methodology decision is made.

---

## Scope

- Translate the chosen methodology (THP-110) into a concrete, step-by-step analysis workflow the agent follows
- Define how the agent moves through the dataset to identify routing patterns, decision boundaries, edge cases, and confusion regions
- Require explicit narrative outputs for why routes differ and where boundaries are fragile — use THP-84's boundary coverage criteria as the benchmark for what "sufficient" boundary coverage looks like
- Specify how the framework surfaces hard negatives, rare cases, and ambiguous examples for downstream use by exemplar optimization (THP-117) and mixture-of-prompts (THP-133)
- Define cluster discovery steps that produce cluster IDs conforming to THP-82's schema — these cluster IDs are also consumed by Phase 2's stratified split algorithm (THP-86)

---

## Deliverables

- Analysis workflow for routing-pattern and boundary discovery
- Confusion-matrix narrative template
- Cluster discovery guidance and output requirements (cluster IDs feed both THP-133 and the Phase 2 split)
- Edge-case and hard-negative surfacing policy

---

## Dependencies

- **Blocked by THP-110** (methodology selection)
- Uses THP-84 (routing dataset quality context) as benchmark for boundary coverage adequacy
- Produces artifacts that conform to the schema defined in THP-82 and the format defined in THP-86

---

## Success Criteria

- The analysis framework consistently produces artifacts that are useful for prompt-program search, exemplar optimization, and mixture-of-prompts specialisation
- Cluster IDs are rich enough to support failure-mode-stratified splitting in Phase 2
