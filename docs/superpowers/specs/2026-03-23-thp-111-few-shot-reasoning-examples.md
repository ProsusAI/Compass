# THP-111 — Create 4 Sets of Few-Shot Examples (One Per LLM Skill)

Date: 2026-03-23 (revised: expanded from one set to four per-skill sets)

**Wave:** 3 (blocked by THP-110 + THP-85)

---

## Summary

Create four sets of few-shot examples — one per LLM skill — to be embedded in each skill's `SKILL.md`. Examples must conform to THP-82's rationale schema and THP-86's I/O schemas.

Note: THP-151–154 (skill authoring) may begin with placeholder examples and finalise once this task is complete.

---

## Per-Skill Example Requirements

### skill-1: `rationale-card-extraction`

- **Count:** 2–3 examples
- **Format:** `(id, query, label)` → rationale card
- **Coverage:** prototypical, boundary, and hard-negative cases
- **Schema:** conforms to THP-82 rationale card schema

### skill-2: `ambiguity-taxonomy`

- **Count:** 1–2 examples
- **Format:** rationale card set → `taxonomy.json`
- **Coverage:** shows distinct failure mode tags with different confusion classifications

### skill-3: `boundary-exemplar-tagging`

- **Count:** 2–3 examples
- **Format:** rationale card set → `tagged_cards.jsonl` annotations
- **Coverage:** all four boundary tags (`prototypical`, `boundary`, `hard-negative`, `rare-class`) with clear rationales

### skill-4: `confusion-narrative-generation`

- **Count:** 1–2 examples
- **Format:** `(taxonomy + tagged cards)` → `confusion_narratives.json`
- **Coverage:** route-pair overlap explanations and fragility assessments

---

## Deliverables

- Four sets of few-shot examples, formatted for direct inclusion in `SKILL.md` files
- Each set embedded in the corresponding `SKILL.md` by THP-151–154

---

## Success Criteria

- Each example set is sufficient to ground the skill's output format and reasoning style.
- Examples cover the full range of boundary tags and failure mode types.
- All examples are consistent with THP-82's rationale schema and THP-86's I/O schemas.
