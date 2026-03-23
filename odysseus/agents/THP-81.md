# THP-81 — Define output format and code generation context

**Type:** Task  
**Status:** To Do  
**Epic:** [THP-73](https://prosus-thymo-thesis.atlassian.net/browse/THP-73) — Data validation agent  
**Jira:** [THP-81](https://prosus-thymo-thesis.atlassian.net/browse/THP-81)

> **Note:** This ticket merges THP-83 ("Create context for generating data analysis code"). All scope from THP-83 is covered here.

## Description

Define two things in a single artifact: the structure of the data quality report the agent produces, and the static code generation context preloaded into the agent to guide generation of analysis code. These two concerns are combined because the code generation context must target the output format directly — they need to be designed together.

## What to build

Produce a reference document covering both concerns.

### Part 1 — Output format (data quality report)

Define the structure of the report the Data Validation agent produces:

1. **Schema consistency findings** — per-field results for required field presence, type correctness, and structural violations. Each finding includes: field name, pass/fail, and a short description of the violation if applicable.

2. **Label distribution stats** — per routing tier: record count, percentage of total, and an imbalance flag if any tier's share falls below a minimum threshold.

3. **Volume adequacy assessment** — per tier: verdict (adequate / insufficient / absent), actual count, and minimum required count. Overall verdict for the dataset.

4. **Missing signal types** — list of detected diversity gaps: query clusters that are semantically redundant, routing cases underrepresented relative to the user's problem description.

5. **Prioritised data collection suggestions** — ordered list of additional data to collect, each item containing: what data to collect, why it helps, and estimated impact on routing performance (high / medium / low).

### Part 2 — Code generation context

Define the static context preloaded into the agent to guide generation of analysis code:

1. **Dataset schema reference** — field names, types, and required/optional status from THP-80. Inlined so the agent does not need to load a separate file.

2. **Available Python libraries** — `pandas`, `json`, `collections`. The agent generates code using only these; no third-party ML libraries.

3. **Output format target** — the report structure defined in Part 1, so generated code produces values in the correct shape.

4. **Canonical check examples** — working code snippets for:
   - Label distribution counts (per-tier value counts).
   - Null field detection (rows where required keys are missing or null).
   - Row count per routing class.
   - Query length distribution (min, max, mean, p95 character count).

Suggested file: `odysseus/agents/data_validation_output.md`

## How it links with the rest of the codebase

| Touch point | Detail |
|---|---|
| THP-80 | Data format spec defines the schema referenced in the code generation context. |
| THP-145 | Validation logic must produce a report matching the structure defined in Part 1. |
| THP-106 | Final system prompt embeds both Parts 1 and 2; this artifact is the primary input to prompt assembly. |
| THP-74 (Routing Analysis) | Consumes the data quality report; the report structure here determines what THP-74 receives. |

## Dependencies between tasks

- Blocked by THP-80 (data format spec must be finalised before the code generation context can reference it).
- THP-145 (validation logic) and THP-106 (final prompt) are blocked on this being finalised.
