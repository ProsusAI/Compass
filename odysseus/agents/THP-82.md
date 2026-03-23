# THP-82 — Expand analysis dimensions into routing rationale schema

**Type:** Task  
**Status:** To Do  
**Epic:** [THP-73](https://prosus-thymo-thesis.atlassian.net/browse/THP-73) — Data validation agent  
**Jira:** [THP-82](https://prosus-thymo-thesis.atlassian.net/browse/THP-82)

## Description

Define the structured routing rationale schema that powers clustering, retrieval, and decision-boundary analysis within the Data Validation agent. Each routing example in the dataset can be annotated using this schema, turning raw labeled records into structured skill/rationale cards.

## What to build

Produce a reference document covering:

1. **Routing rationale schema** — normalised fields per routing example:
   - `intent_pattern` — the query type or task category (e.g. factual lookup, multi-step reasoning, code generation).
   - `required_capability` — what the handling model must be able to do (e.g. tool use, long-context reasoning, arithmetic).
   - `risk_level` — how ambiguous or borderline the routing decision is (low / medium / high).
   - `tool_dependency` — whether the query requires a tool call to resolve (boolean + tool name if applicable).
   - `disqualifiers` — conditions that rule out a routing tier for this example (e.g. "haiku cannot handle multi-hop reasoning").
   - `tie_breaker` — the deciding factor when two tiers could both handle the query (e.g. cost preference, latency constraint).

2. **Ambiguity taxonomy and confusion tags** — a controlled vocabulary for labelling examples that sit near routing boundaries:
   - `AMBIGUOUS_COMPLEXITY` — complexity signals point to different tiers.
   - `AMBIGUOUS_DOMAIN` — domain knowledge requirements are unclear.
   - `POTENTIAL_MISLABEL` — the assigned route seems inconsistent with the query content.
   - `BOUNDARY_CASE` — the example would be handled acceptably by two or more tiers.

3. **Annotation guidance** — how rationale fields are extracted reproducibly from labeled routing examples:
   - Decision rules for each field.
   - Examples of correctly annotated records.
   - Common annotation mistakes and how to avoid them.

4. **Validation checks** — rules for schema consistency and coverage:
   - All required rationale fields are present.
   - `risk_level` is one of the defined enum values.
   - Confusion tags are drawn from the controlled vocabulary.
   - Each routing class has at least one non-`AMBIGUOUS` example.

**Success criteria:** each routing example can be represented as a structured skill/rationale card, and the schema is directly usable by exemplar optimisation and mixture-of-prompts workflows.

Suggested file: `odysseus/agents/data_validation_rationale_schema.md`

## How it links with the rest of the codebase

| Touch point | Detail |
|---|---|
| THP-80 | Each annotated record begins with the base fields defined in the data format spec. |
| THP-81 | Missing signal detection in the output report (diversity gaps, underrepresented cases) uses the rationale schema to identify what is absent. |
| THP-106 | Final system prompt embeds this schema so the agent can produce structured annotations. |
| THP-74 (Routing Analysis) | Rationale cards produced here feed into the routing analysis stage for cluster assignment and boundary mining. |

## Dependencies between tasks

- No blockers — can be written in parallel with THP-80 and THP-81.
- THP-106 (final prompt) depends on this being finalised.
