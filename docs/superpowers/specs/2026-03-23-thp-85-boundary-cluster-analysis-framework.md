# THP-85 — Skill Orchestration Framework and Execution Protocol

Date: 2026-03-23 (revised: repurposed from reasoning framework to orchestration spec)

**Blocked by:** THP-110

---

## Summary

Defines the execution protocol and data flow for THP-74's 4-skill + 1 code-step pipeline. Provides the orchestrator implementation contract — what any pipeline runner must implement to drive the skills in the correct order with the correct file handoffs.

---

## Skill Execution Order

```
skill-1 (per-example) → [skill-2 || skill-3 || code-step] → skill-4
```

- **skill-1** (`rationale-card-extraction`): Called once per example, parallelizable. All outputs collected into `rationale_cards.jsonl` before proceeding.
- **skill-2** (`ambiguity-taxonomy`), **skill-3** (`boundary-exemplar-tagging`), **code-step** (`cluster-id-assignment`): All run in parallel after skill-1 completes. All read `rationale_cards.jsonl`.
- **skill-4** (`confusion-narrative-generation`): Waits for skill-2 and skill-3. Does NOT wait for the code-step.

---

## Invocation Patterns

| Skill | Pattern | Input | Output |
|-------|---------|-------|--------|
| skill-1 | Once per example (parallelizable) | `{id, query, label}` + `quality_context.md` | appended to `rationale_cards.jsonl` |
| skill-2 | Single call | `rationale_cards.jsonl` | `taxonomy.json` |
| skill-3 | Single call | `rationale_cards.jsonl` | `tagged_cards.jsonl` |
| code-step | Single invocation | `rationale_cards.jsonl` | `cluster_ids.json` |
| skill-4 | Single call | `taxonomy.json` + `tagged_cards.jsonl` | `confusion_narratives.json` |

---

## Data Flow

```
full_dataset.jsonl
  ├─ per-example → skill-1 → rationale_cards.jsonl
  │
  ├─ rationale_cards.jsonl → skill-2 → taxonomy.json
  ├─ rationale_cards.jsonl → skill-3 → tagged_cards.jsonl
  ├─ rationale_cards.jsonl → code-step → cluster_ids.json
  │
  └─ taxonomy.json + tagged_cards.jsonl → skill-4 → confusion_narratives.json
```

Phase 2 (stratified split) receives `taxonomy.json` + `cluster_ids.json` and produces `dev.jsonl` + `holdout.jsonl`.

---

## File Naming and Directory Layout

```
outputs/<run_id>/
  rationale_cards.jsonl
  taxonomy.json
  tagged_cards.jsonl
  cluster_ids.json
  confusion_narratives.json
  dev.jsonl
  holdout.jsonl
```

All inter-skill file schemas are defined in THP-86.

---

## Orchestrator Error Handling

- **Skill-1 failure on example N:** Log error, skip example, continue. Report skipped examples in run summary.
- **Skill-2, 3, or code-step failure:** Abort Phase 1 — downstream skills cannot safely proceed with partial inputs.
- **Skill-4 failure:** Retry once. If retry fails, abort.
- **Malformed output:** Validate each skill output against THP-86 schemas before dispatching downstream. On validation failure, treat as skill failure.

---

## LLM-Agnostic Constraints

- The orchestrator must not be coupled to any specific LLM runtime.
- Skills are invoked by loading their `SKILL.md` and passing the defined input — the invocation mechanism (API call, CLI, etc.) is decoupled from orchestration logic.
- The code-step is a standard Python module invocation; no LLM call.

---

## Deliverables

- Skill orchestration spec (this document)
- Orchestrator interface contract: method signatures and contracts a runner must implement

---

## Success Criteria

- A pipeline runner can be implemented from this spec without ambiguity about invocation order, file passing, or error handling.
- The orchestration protocol is LLM-agnostic.
