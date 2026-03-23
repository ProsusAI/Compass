# THP-112 — Define How Patterns Translate into Prompt-Ready Heuristics

Date: 2026-03-23
Wave: 2 (after THP-110)
Epic: THP-74 — Routing Analysis Agent

---

## Summary

Define the interface contract between the Routing Analysis agent and the Prompt Builder agent. This ticket does not define a new output format — it references THP-86's artifact format and specifies only what the Prompt Builder requires from it.

---

## Scope

- Identify which fields from THP-86's routing analysis artifact the Prompt Builder consumes (e.g. routing rationale cards, cluster IDs, confusion narratives, boundary exemplars)
- Specify any required transformations or projections from the full artifact format (THP-86) to what the Prompt Builder ingests
- Define the contract: field names, types, cardinality, and ordering guarantees the Prompt Builder depends on
- Document failure modes: what happens if required fields are missing or malformed

---

## Deliverable

- Interface contract document specifying the exact subset and shape of the routing analysis artifact the Prompt Builder consumes

---

## Dependencies

- THP-110 (methodology — informs which fields are meaningful)
- Consumes THP-86 (full artifact format) — must not redefine the schema, only reference it

---

## Success Criteria

- The Prompt Builder can be implemented against this contract without needing to read THP-86 directly
- The contract is stable enough to version independently of the full artifact format
