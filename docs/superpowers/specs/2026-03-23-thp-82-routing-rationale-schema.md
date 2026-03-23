# THP-82 — Expand Analysis Dimensions into Routing Rationale Schema

Date: 2026-03-23
Wave: 1 (parallel with THP-110, THP-84, THP-86)
Epic: THP-74 — Routing Analysis Agent

---

## Summary

Refocus this task on defining the structured routing rationale schema that powers clustering, retrieval, and boundary analysis.

---

## Scope

- Define normalized fields per routing example: intent pattern, required capability, risk/ambiguity level, tool dependency, disqualifiers, and tie-breaker logic
- Add ambiguity taxonomy and confusion tags that can be reused across analysis and review
- Ensure the schema is rich enough for skill-based retrieval, cluster assignment, and decision-boundary mining
- Document how rationale fields are extracted reproducibly from labeled routing examples

---

## Deliverables

- Routing rationale schema
- Ambiguity and confusion taxonomy
- Annotation guidance for populating the schema across the dataset
- Validation checks for schema consistency and coverage

---

## Dependencies

None — Wave 1 task.

---

## Success Criteria

- Each example can be represented as a structured skill / rationale card
- The schema is directly usable by exemplar optimization and mixture-of-prompts workflows
