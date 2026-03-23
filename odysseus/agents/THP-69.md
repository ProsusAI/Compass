# THP-69 — Define agent static knowledge context

**Type:** Task  
**Status:** In Review  
**Epic:** [THP-68](https://prosus-thymo-thesis.atlassian.net/browse/THP-68) — User input agent  
**Jira:** [THP-69](https://prosus-thymo-thesis.atlassian.net/browse/THP-69)

## Description

Define the static context that is preloaded into the User Input agent to help it function — this includes the definition of a complete problem specification, the list of required and optional input fields, acceptable metric formats, and minimum data volume thresholds. This context is fixed at agent design time and does not change between runs.

This context forms the reference frame the agent uses when evaluating submissions and producing the validated input report for downstream agents.

## What to build

Produce a structured static context document that the agent loads as part of its system prompt. It must specify:

1. **Complete problem specification** — what a fully described routing problem looks like: routing dataset, problem description, model tiers, and target metrics all present and well-formed.
2. **Required fields** — the minimum set of inputs the agent must receive to proceed:
   - `routing_dataset` — path or inline JSONL, must contain `input` and `expected` fields per record.
   - `problem_description` — free-text description of the routing problem, minimum meaningful length.
   - `target_metrics` — at least one named metric with an optional threshold (e.g. `accuracy >= 0.85`).
3. **Optional fields** — fields that improve output quality but can be defaulted when absent:
   - `evaluation_threshold` — overall pass/fail threshold for the pipeline exit check.
   - `data_split_ratio` — fraction of data reserved for holdout (default: 20%).
   - `max_iterations` — maximum refinement loop rounds.
4. **Acceptable metric formats** — what constitutes a valid metric specification (e.g. `accuracy >= 0.85`, `f1_macro`, `latency_p95 <= 200ms`).
5. **Minimum data volume thresholds** — rules for what data volume is sufficient to proceed (e.g. minimum number of labeled examples per routing class).
6. **Format validity rules** — per-field checks the agent applies at runtime:
   - Dataset: parseable JSONL, `input` and `expected` keys present, minimum record count.
   - Metrics: parseable as `metric_name [operator threshold]`, threshold in `[0, 1]` for ratio metrics.
7. **Completeness decision logic** — the rule used to decide between proceed, default-and-proceed, or halt-and-clarify (see THP-108 for gap taxonomy).

> Note: THP-70 (Define valid and complete input) was merged into this task. The valid/complete input definition is now part of the static context document.

Suggested file: `odysseus/agents/user_input_context.md` (embedded into the system prompt at THP-107).

## How it links with the rest of the codebase

| Touch point | Detail |
|---|---|
| THP-108 | Gap taxonomy classifies each field absence as blocking or non-blocking against the field definitions here. |
| THP-71 | Default values are applied for non-blocking gaps identified against the field definitions here. |
| THP-72 | The validated input report captures the outcome of checking against this definition. |
| THP-107 | This context is directly embedded into the final system prompt. |
| THP-73 (Data Validation) | Volume thresholds defined here should align with the data quality criteria in the Data Validation agent. |

## Dependencies between tasks

- No blockers — can start immediately.
- THP-108 can be written in parallel.
- THP-71 (defaults table) depends on knowing which fields are optional, defined here.
- THP-72 (output schema) and THP-107 (final system prompt) are blocked on this being finalized.
