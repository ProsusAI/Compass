# THP-112 — Routing Analysis → Prompt Builder Interface Contract

Date: 2026-03-23 (revised: now references skill output files from THP-86; also depends on THP-86)

**Wave:** 2 (blocked by THP-110 and THP-86)

---

## Summary

Defines the interface contract between the Routing Analysis agent pipeline and the Prompt Builder agent. References THP-86's inter-skill I/O schemas — does not redefine them.

---

## Scope

### What the Prompt Builder Consumes

Identify which skill output files and which fields within each the Prompt Builder ingests:

| File | Fields consumed |
|------|----------------|
| `rationale_cards.jsonl` | TBD — at minimum: `intent_pattern`, `required_capability`, `disqualifiers` |
| `tagged_cards.jsonl` | `boundary_tag` — for exemplar selection |
| `cluster_ids.json` | `cluster_id` per example — for cluster-aware prompt construction |
| `confusion_narratives.json` | `route_pair`, `overlap_explanation` — for heuristic injection |
| `taxonomy.json` | `failure_modes` — for failure-mode-aware few-shot selection |

### Contract Definition

- Field names, types, cardinality, and ordering guarantees the Prompt Builder depends on
- Required vs optional fields
- Any required transformations or projections from the full artifact to what the Prompt Builder ingests

### Failure Modes

- What happens if required fields are missing or malformed
- Which fields are strictly required vs gracefully degradable

---

## Dependency Note

THP-112 depends on **THP-86** (inter-skill I/O schemas define the file shapes referenced here) in addition to THP-110. The contract references, not redefines, those schemas.

---

## Deliverable

Interface contract document: the exact subset and shape of the routing analysis artifact the Prompt Builder consumes.

---

## Success Criteria

- The Prompt Builder can be implemented against this contract without reading THP-86 directly.
- The contract is stable enough to version independently of the full artifact format.
