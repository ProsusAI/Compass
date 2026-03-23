# THP-105 — Create Final Prompt (Phase 1)

Date: 2026-03-23
Wave: 4 (after all above)
Epic: THP-74 — Routing Analysis Agent

---

## Summary

Write the final system prompt for the Routing Analysis agent's Phase 1 (analysis). The prompt drives Phase 1 only: analyzing the full labeled routing dataset and producing the structured routing analysis artifact. Phase 2 (stratified split → `dev.jsonl` + `holdout.jsonl`) is a deterministic algorithm defined in THP-86 and does not require a separate prompt.

---

## Scope

- Incorporate the reasoning framework (THP-85)
- Incorporate the output format spec (THP-86)
- Incorporate the pattern extraction methodology (THP-110)
- Incorporate few-shot examples of reasoning document output (THP-111)
- Incorporate the heuristic translation / Prompt Builder interface spec (THP-112)
- The agent receives all samples — there is no pre-existing split at this stage

---

## Deliverable

- Final system prompt for the Routing Analysis agent (Phase 1)

---

## Dependencies

- THP-85 (reasoning framework)
- THP-86 (output format)
- THP-110 (methodology)
- THP-111 (few-shot examples)
- THP-112 (Prompt Builder interface contract)

---

## Success Criteria

- The prompt consistently produces a structured routing analysis artifact that conforms to THP-86's format
- The artifact is directly consumable by the Prompt Builder agent (THP-112 contract) and by exemplar optimization, mixture-of-prompts, and context assembler downstream
