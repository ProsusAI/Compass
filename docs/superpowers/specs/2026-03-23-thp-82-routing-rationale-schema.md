# THP-82 — Expand Analysis Dimensions into Routing Rationale Schema

Date: 2026-03-23
Wave: 1 (parallel with THP-110, THP-84, THP-86)
Epic: THP-74 — Routing Analysis Agent

---

## Summary

Refocus this task on defining the structured routing rationale schema that powers clustering, retrieval, and boundary analysis.

---

## Reference: Existing Few-Shot Prompt

The existing routing prompt with 22 annotated examples is the primary starting point for schema design:

**File:** `../../prompt-routing/prompts/fewshot_v16_reduce_overrouting.md`
(absolute: `/Users/thymo.fieten/Documents/prompt-routing/prompts/fewshot_v16_reduce_overrouting.md`)

This file contains:
- The full tier decision framework (tiers 0, 1, 2) with routing rules and heuristics
- 22 labeled examples, each with a natural-language reasoning narrative and a tier assignment

The reasoning narratives in these examples are the raw material for the rationale schema. Each narrative already encodes — informally — the dimensions the schema must formalize:

| Narrative pattern | Maps to schema field |
|-------------------|---------------------|
| "single-entity factual lookup" / "generation task" | `intent_pattern` |
| "cheapest model gets wrong" / "precision-dependent" / "domain-specialist knowledge required" | `required_capability` |
| "torn between 1 and 2" / "could go either way" | `risk_ambiguity_level` |
| "specialized database filtering" / "named data source" | `tool_dependency` |
| "NOT tier 2 just because..." / "do not upgrade if..." | `disqualifiers` |
| "when torn between X and Y, choose..." | `tie_breaker_logic` |

Schema design should start by extracting these dimensions systematically from the 22 examples before generalizing. The goal is a schema that can regenerate the same routing decision from structured fields alone, without requiring the free-text narrative.

---

## Scope

- Define normalized fields per routing example: intent pattern, required capability, risk/ambiguity level, tool dependency, disqualifiers, and tie-breaker logic — grounded in the patterns observed in `fewshot_v16_reduce_overrouting.md`
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
