# THP-111 — Define Few-Shot Examples of Reasoning Document Output

Date: 2026-03-23
Wave: 3 (after THP-110 + THP-85)
Epic: THP-74 — Routing Analysis Agent

---

## Summary

Create one or more concrete examples of what a good routing analysis output looks like. These examples ground the final prompt and serve as the reference for what THP-85 (reasoning framework) should produce.

---

## Scope

- Create fully populated routing analysis output examples that demonstrate correct application of the reasoning framework (THP-85)
- Cover prototypical cases, boundary cases, hard-negative cases, and rare-class cases
- Examples must conform to the schema defined in THP-82 and the format defined in THP-86
- These examples are the reference material for validating THP-86's schema

---

## Deliverables

- One or more annotated few-shot examples of complete routing analysis document output

---

## Dependencies

- THP-110 (methodology — defines what the output should reflect)
- THP-85 (reasoning framework — defines the steps the output demonstrates)

---

## Downstream Use

- THP-105 (final prompt) — few-shot examples are included in the system prompt
- THP-86 — reference for validating the artifact schema
