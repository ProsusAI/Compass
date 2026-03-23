# THP-105 — Author Skill Files: Routing Analysis Pipeline (Wave 4 Parent)

Date: 2026-03-23 (revised: repurposed from single prompt to 5 parallel skill-authoring tasks)

---

## Summary

THP-105 is the Wave 4 parent task. It is split into 5 parallel subtasks, each responsible for one component of the routing analysis skills pipeline. All subtasks depend on THP-111 (per-skill few-shot examples), THP-85 (orchestration spec), and THP-86 (I/O schemas).

---

## Subtasks

| Task | Deliverable | Wave | Key deps |
|------|------------|------|----------|
| [THP-151](https://prosus-thymo-thesis.atlassian.net/browse/THP-151) | `skill-1-rationale-card-extraction/SKILL.md` | 4 | THP-111, THP-85, THP-86, THP-82, THP-84 |
| [THP-152](https://prosus-thymo-thesis.atlassian.net/browse/THP-152) | `skill-2-ambiguity-taxonomy/SKILL.md` | 4 | THP-111, THP-85, THP-86 |
| [THP-153](https://prosus-thymo-thesis.atlassian.net/browse/THP-153) | `skill-3-boundary-exemplar-tagging/SKILL.md` | 4 | THP-111, THP-85, THP-86 |
| [THP-154](https://prosus-thymo-thesis.atlassian.net/browse/THP-154) | `skill-4-confusion-narrative-generation/SKILL.md` | 4 | THP-111, THP-85, THP-86 |
| [THP-155](https://prosus-thymo-thesis.atlassian.net/browse/THP-155) | `cluster-id-assignment` code module | 4 | THP-110, THP-85, THP-86 |

All 5 run in parallel. Note: skill-authoring tasks (THP-151–154) may begin with placeholder few-shot examples and finalise once THP-111 is complete.

---

## SKILL.md Structure Requirements

Each `SKILL.md` must include:

1. **YAML frontmatter** — `name`, `description`
2. **Input schema** — field names, types, required/optional
3. **Step-by-step instructions** — what the LLM must do
4. **Few-shot examples** — from THP-111, embedded directly
5. **Output schema** — conforming to THP-86's inter-skill I/O schemas

---

## LLM-Agnostic Constraint

Each skill must be invocable by any LLM integration given its `SKILL.md` and defined input — not coupled to Claude or any specific API.

---

## Phase 2 Note

Phase 2 (stratified split producing `dev.jsonl` + `holdout.jsonl`) is a deterministic algorithm, not a skill. No `SKILL.md` is authored for Phase 2. Algorithm spec is in THP-86.

---

## Success Criteria

- Each skill can be invoked independently by any LLM integration given its input.
- Skill outputs conform to THP-86's I/O schemas.
- The clustering code module (THP-155) is deterministic: same inputs + config → same `cluster_ids.json`.
