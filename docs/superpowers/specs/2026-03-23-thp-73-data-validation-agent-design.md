# THP-73 — Data Validation Agent

## Summary

Design and implement the Data Validation agent — a pipeline stage that assesses the structural quality of the user's submitted routing dataset and generates a prioritised list of data collection suggestions. The agent runs immediately after the User Input agent (THP-68) validates the submission, and produces a data quality report that downstream agents (Routing Analysis, THP-74) use to contextualise their analysis.

## Context

The User Input agent (THP-107) currently accepts a dataset path as-is. THP-73 adds the next stage: once a path is confirmed, the Data Validation agent loads the dataset, inspects its quality, and either surfaces issues back to the user or produces a data quality report for downstream use.

Integration point in `prompts/user_input_system.md` (THP-107, section 6 — "Data Validation agent dispatch") already has a placeholder for this: "When user provides a dataset, dispatch the Data Validation agent to assess quality." THP-73 delivers the agent that fills that placeholder.

### Dependencies

| Artifact | Status | Role |
|---|---|---|
| THP-107 | Complete | System prompt — contains dispatch protocol for this agent |
| THP-72 | Complete | Validated input report schema — provides dataset path and problem description as inputs |
| THP-74 | Pending | Routing Analysis agent — consumes this agent's data quality report |

## Tasks

### THP-80 — Define data format

**Status:** To Do

Define the expected format of the routing dataset submitted by the user:

- **File format:** JSONL (one JSON object per line).
- **Required fields per row:** `input` (object, must contain `query`), `expected` (object, must contain `route`).
- **Optional fields:** `id` (string), `metadata` (object).
- **Schema constraints:** no null required fields, no extra nesting beyond spec, consistent field types across all rows.

This spec is the primary input to THP-145 (validation logic) and THP-81 (code generation context).

**Deliverable:** `odysseus/agents/data_validation_format.md` — a markdown reference file describing the schema with field types, required/optional classification, and examples of valid and invalid records.

---

### THP-81 — Define output format and code generation context

**Status:** To Do  
**Note:** Merges THP-83.

Two concerns combined into one artifact:

**Output format** — The structure of the data quality report the agent produces:

- **Schema consistency findings:** required fields present, correct types, no structural violations.
- **Label distribution stats:** per-class counts, imbalance ratio.
- **Volume adequacy assessment:** minimum rows per class, overall row count verdict.
- **Missing signal types:** query diversity gaps, underrepresented routing cases.
- **Prioritised data collection suggestions:** ranked by expected impact on routing performance.

**Code generation context** — Static context preloaded into the agent to guide generation of analysis code:

- Dataset schema from THP-80 (field names, types, required vs optional).
- Available Python libraries: `pandas`, `json`, `collections`.
- Output format defined above (so generated code targets the correct structure).
- Canonical examples of checks to run: label distribution counts, null field detection, row count per class, query length distribution.

**Deliverable:** `odysseus/agents/data_validation_output.md` — a markdown reference file covering both the report schema and the code generation context. This is the primary input to THP-106 (final prompt assembly).

---

### THP-82 — Expand analysis dimensions into routing rationale schema

**Status:** To Do

Define a structured routing rationale schema that powers clustering, retrieval, and boundary analysis:

- **Normalised fields per routing example:** intent pattern, required capability, risk/ambiguity level, tool dependency, disqualifiers, tie-breaker logic.
- **Ambiguity taxonomy and confusion tags:** reusable across analysis and review.
- **Schema richness requirements:** sufficient for skill-based retrieval, cluster assignment, and decision-boundary mining.
- **Annotation guidance:** how rationale fields are extracted reproducibly from labeled routing examples.
- **Validation checks:** schema consistency and coverage verification.

**Success criteria:** each routing example can be represented as a structured skill/rationale card directly usable by exemplar optimisation and mixture-of-prompts workflows.

**Deliverable:** `odysseus/agents/data_validation_rationale_schema.md` — routing rationale schema, ambiguity taxonomy, and annotation guidance.

---

### THP-84 — Create context for routing dataset quality

**Status:** To Do

Define the static domain knowledge preloaded into the agent about what makes a high-quality routing dataset:

- **Ideal label balance:** recommended class ratios, acceptable imbalance thresholds.
- **Minimum query diversity requirements:** what "diverse enough" means for a routing dataset.
- **Decision boundary coverage:** ensuring examples near tier boundaries are represented.
- **Edge case representation:** rare but important routing cases that must appear in training data.

This context grounds the agent's quality assessment in domain knowledge rather than generic data-quality heuristics. It is tailored to cost-quality routing specifically.

**Deliverable:** `odysseus/agents/data_validation_quality_context.md` — static domain context for the agent.

---

### THP-83 — [MERGED into THP-81]

Scope fully covered by THP-81. No work to be done here.

---

### THP-106 — Add final prompt

**Status:** To Do  
**Blocked by:** THP-80, THP-81, THP-82, THP-84

Write the final system prompt for the Data Validation agent, incorporating all four context artifacts:

- Data format spec (THP-80) — so the agent knows what to validate against.
- Output format and code generation context (THP-81) — so the agent knows what to produce and how to generate analysis code.
- Routing rationale schema (THP-82) — so the agent can produce structured annotations.
- Routing dataset quality context (THP-84) — so quality judgements are domain-grounded.

The prompt must:

1. Receive the dataset path and problem description as inputs (from the validated input report, THP-72).
2. Load and inspect the dataset using generated Python analysis code.
3. Produce a data quality report in the structure defined by THP-81.
4. Surface blocking issues (missing `expected` field, malformed records) back to the User Input agent using the "fix" question type.

The Data Validation agent is a pure analysis agent — it does not handle conversational clarification directly. When blocking issues are found, it returns structured findings to the User Input agent, which owns the clarification conversation flow and surfaces issues to the user.

**Out of scope:** Data collection suggestions are handled by the Routing Analysis agent (THP-74) downstream, which has full context of the routing task and evaluation results.

**Deliverable:** `prompts/data_validation_system.md` — the standalone system prompt.

---

### THP-145 — Implement full dataset validation logic

**Status:** To Do  
**Blocked by:** THP-80, THP-81

Implement the end-to-end validation logic the agent executes against the user-submitted routing dataset:

1. **Schema conformance** — validate against THP-80: required fields present, correct types, no structural violations.
2. **Statistical checks** — label distribution counts, null field detection, row count per class, query length distribution (min, max, mean, p95).
3. **Volume adequacy** — minimum rows per class, overall row count threshold, flag under-covered classes.
4. **Missing signal types** — query diversity gaps, underrepresented routing cases relative to the problem description.
5. **Data quality report** — produce the report structure from THP-81: schema check results, statistical summary, volume adequacy verdict per class, missing signal flags.
6. **Data collection suggestions** — prioritised list ranked by expected impact on routing performance, tailored to the user's problem description.

**Suggested file:** `odysseus/agents/data_validation_logic.py`

**Inputs:**
- Raw routing dataset (JSONL file path).
- User's problem description (from validated input report).
- Data format spec (THP-80).
- Output format and code generation context (THP-81).

**Output:** Fully populated data quality report, ready for presentation to the user and consumption by downstream agents.

---

## Dependency order

```
THP-80 (data format)
THP-81 (output format + code gen context)  ←─ merges THP-83
THP-82 (rationale schema)
THP-84 (quality context)
    └─► THP-106 (final prompt)
    └─► THP-145 (validation logic)
```

THP-80 and THP-81 are the critical-path blockers — THP-145 cannot be started without them. THP-82, THP-84, and THP-106 can proceed in parallel once THP-80 and THP-81 are done.

## File inventory

| Action | File | Task |
|---|---|---|
| Create | `odysseus/agents/data_validation_format.md` | THP-80 |
| Create | `odysseus/agents/data_validation_output.md` | THP-81 |
| Create | `odysseus/agents/data_validation_rationale_schema.md` | THP-82 |
| Create | `odysseus/agents/data_validation_quality_context.md` | THP-84 |
| Create | `prompts/data_validation_system.md` | THP-106 |
| Create | `odysseus/agents/data_validation_logic.py` | THP-145 |

## Integration with the pipeline

Once complete, the User Input agent's dispatch protocol (section 6 of `prompts/user_input_system.md`) activates: when the user provides a dataset path, the User Input agent dispatches the Data Validation agent and incorporates its findings as potential blocking gaps — surfacing data issues conversationally using the "fix" question type before producing the validated input report.

This also unblocks integration test scenario 6 in THP-146 (`06_malformed_dataset.md`), which is currently deferred pending THP-73.

## Out of scope

- **Automated test runner** — validation logic tests are added to `tests/` via `pytest`, but end-to-end agent tests follow the THP-146 integration test pattern.
- **Routing Analysis agent (THP-74)** — the data quality report format must be consumable by THP-74, but THP-74's implementation is a separate epic.
- **User-facing visualisations** — the report is text/Markdown, no charts or interactive output.
