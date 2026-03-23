# THP-86 — Expand Output Format into Structured Routing Analysis Artifact Spec and Split Output

Date: 2026-03-23
Wave: 1 (parallel with THP-110, THP-82, THP-84)
Epic: THP-74 — Routing Analysis Agent

---

## Summary

Define the machine-readable serialization format, validation rules, provenance requirements, and stratified split algorithm for THP-74's outputs. The logical schema (field semantics) is owned by THP-82 — this ticket builds the format layer on top of it and owns the split output specification.

---

## Scope — Routing Analysis Artifact

- Define the serialization format for each artifact type: routing rationale cards (using fields from THP-82), ambiguity tags, decision-boundary exemplars, confusion narratives, and cluster IDs
- Specify mandatory vs optional fields per artifact type and the validation rules enforcing them
- Add provenance fields linking each structured artifact back to its source examples and analysis run
- Define versioning requirements so downstream systems can detect format changes
- Ensure the format can power skill-based retrieval, coverage-aware example selection, and mixture-of-prompts routing

---

## Scope — Stratified Split Output

- Define the stratification algorithm: using failure mode tags (from ambiguity taxonomy) and cluster IDs from Phase 1, assign samples to dev or holdout with best-effort proportional representation of each stratum in both sets
- Default split ratio: 80% dev / 20% holdout, configurable via pipeline run config
- Thin-strata rule: strata with fewer than 2 members are assigned entirely to dev; strata with 2+ members contribute at least one sample to holdout
- Phase 2 produces two separate dataset files — `dev.jsonl` and `holdout.jsonl` — containing the actual samples, not a flag mapping
- Define validation rules for the split output (all source samples present across both files, no duplicates, correct format)

---

## Deliverables

- Routing analysis artifact schema (serialization layer over THP-82's logical schema)
- Stratification algorithm spec
- `dev.jsonl` / `holdout.jsonl` output format and validation rules
- Provenance and versioning requirements

---

## Dependencies

- Consumes THP-82 (logical schema and field semantics)
- Consumes Phase 1 outputs (failure mode tags + cluster IDs) for the split algorithm
- Examples provided by THP-111
- Format is consumed by THP-112 (Prompt Builder interface contract)

**Note:** Examples of fully populated artifacts are owned by THP-111 — do not duplicate them here.

---

## Success Criteria

- Downstream systems can consume analysis artifacts without brittle ad hoc parsing
- The split is deterministic given the same Phase 1 outputs and config
- Holdout leakage is structurally prevented — consumers receive `dev.jsonl` only; `holdout.jsonl` is passed exclusively to the final eval agent
