# THP-80 — Define data format

**Type:** Task  
**Status:** To Do  
**Epic:** [THP-73](https://prosus-thymo-thesis.atlassian.net/browse/THP-73) — Data validation agent  
**Jira:** [THP-80](https://prosus-thymo-thesis.atlassian.net/browse/THP-80)

## Description

Define the expected format of the routing dataset submitted by the user — including the file format, required fields per row, optional fields, and schema constraints the Data Validation agent checks during validation.

## What to build

Produce a structured reference document that specifies:

1. **File format** — JSONL (one JSON object per line). Each line is parsed independently; blank lines and trailing newlines are tolerated.

2. **Required fields per row:**
   - `input` — object; must contain at minimum a `query` key (string).
   - `expected` — object; must contain a `route` key (string) naming the target routing tier.

3. **Optional fields per row:**
   - `id` — string; a stable identifier for the example. Used for deduplication and result tracking.
   - `metadata` — object; arbitrary additional context (e.g. source, domain, difficulty). Not validated beyond type.

4. **Schema constraints:**
   - No null values in required fields.
   - No missing required keys — every row must have both `input` and `expected`.
   - Consistent `route` values across the dataset — the set of unique route values defines the routing tiers.
   - Correct types: `input` and `expected` must be objects, `id` must be a string if present.
   - Minimum record count — at least one record per unique routing tier (exact threshold defined in THP-69).

5. **Examples of valid and invalid records** — at least two valid examples and two invalid examples (missing `expected`, wrong type for `input`, null `route`, etc.) to anchor the validation logic in THP-145.

Suggested file: `odysseus/agents/data_validation_format.md`

## How it links with the rest of the codebase

| Touch point | Detail |
|---|---|
| THP-145 | Validation logic implements the schema constraints defined here. |
| THP-81 | Code generation context references this schema so generated analysis code targets the correct fields. |
| THP-106 | Final system prompt embeds this spec so the agent knows what to validate against. |
| THP-69 | Volume thresholds defined there should align with the minimum record count thresholds here. |

## Dependencies between tasks

- No blockers — can start immediately.
- THP-81 (output format and code generation context) can be written in parallel.
- THP-145 (validation logic) and THP-106 (final prompt) are blocked on this being finalised.
