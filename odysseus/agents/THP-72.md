# THP-72 — Define validated input report schema

**Type:** Task  
**Status:** To Do  
**Epic:** [THP-68](https://prosus-thymo-thesis.atlassian.net/browse/THP-68) — User input agent  
**Jira:** [THP-72](https://prosus-thymo-thesis.atlassian.net/browse/THP-72)

## Description

Define the structure of the validated input package the agent produces — including the confirmed input fields, the gap report (listing each identified gap with its classification as blocking or non-blocking, the default applied if non-blocking, or the clarification request if blocking), and any assumed values flagged for the user's awareness.

## What to build

Produce a schema definition for the validated input report. The report is the agent's output and the contract consumed by all downstream agents (Data Validation, Routing Analysis, etc.).

### Top-level structure

```json
{
  "status": "proceed" | "proceed_with_defaults" | "clarification_required",
  "confirmed_inputs": { ... },
  "gap_report": [ ... ],
  "assumed_defaults": [ ... ]
}
```

### `confirmed_inputs`

Fields that were present and validated in the user's submission:

```json
{
  "routing_dataset": "<path or inline JSONL>",
  "problem_description": "<string>",
  "target_metrics": ["<metric spec>", ...]
}
```

### `gap_report` entries

One entry per identified gap:

```json
{
  "field": "<field name>",
  "classification": "blocking" | "non-blocking",
  "rationale": "<why this classification>",
  "default_applied": "<value>" | null,
  "clarification_request": "<template text from THP-109>" | null
}
```

### `assumed_defaults` entries

One entry per non-blocking gap where a default was applied (convenience list for downstream transparency):

```json
{
  "field": "<field name>",
  "assumed_value": "<value>",
  "user_note": "<plain-language note>"
}
```

### Status values

| Status | Meaning |
|---|---|
| `proceed` | All required fields present; no defaults needed. |
| `proceed_with_defaults` | Required fields present; one or more optional fields defaulted. |
| `clarification_required` | At least one blocking gap detected; pipeline halted. |

### Format

The report is produced as a JSON object. Downstream agents consume it via the pipeline context. The MCP server renders `clarification_required` reports back to the user using the embedded clarification request templates.

Suggested schema file: `odysseus/agents/user_input_schema.json`

## How it links with the rest of the codebase

| Touch point | Detail |
|---|---|
| THP-70 | Confirmed inputs map directly to the required/optional field definitions. |
| THP-71 | Assumed defaults section populated from the defaults table. |
| THP-108 | Gap classification in the gap report entries comes from the taxonomy. |
| THP-109 | Clarification request text for blocking gaps comes from the templates. |
| THP-73 (Data Validation) | Consumes `confirmed_inputs.routing_dataset` from this report. |
| THP-74 (Routing Analysis) | Consumes `confirmed_inputs.problem_description` and the dataset from this report. |
| `odysseus/mcp.py` | MCP server reads `status` to decide whether to continue the pipeline or surface a clarification to the user. |

## Dependencies between tasks

- Blocked by THP-70 (field definitions) and THP-71 (defaults table).
- THP-107 (final system prompt) depends on this schema being finalized.
- Can be developed in parallel with THP-109.
