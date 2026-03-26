# Data Validation Agent — Ingestion Phase Design

**Date:** 2026-03-26
**Status:** Draft
**Scope:** Add a data ingestion and transformation phase to the Data Validation Agent

## Problem

The Data Validation Agent assumes it receives a pre-formatted JSONL file matching the canonical schema. Real users provide data in CSV, JSON arrays, or JSONL with non-standard field names. There is no transformation step, so the agent fails or produces bad results on non-canonical input.

## Approach

Extend the Data Validation Agent into a two-phase agent:

- **Phase 1 — Ingestion & Mapping** (conversational): detect the input format, infer field mappings using an alias table + LLM reasoning, present the mapping to the user for confirmation, and transform the data into canonical JSONL.
- **Phase 2 — Validation & Reporting** (autonomous, unchanged): the existing validate-then-report flow.

This follows the phase pattern established by the Routing Analysis Agent and keeps transformation and validation in the same agent that owns the format spec knowledge.

## Agent Workflow

```
User Input Agent hands off (dataset_path + problem_description)
    ↓
Phase 1 — Ingestion & Mapping (conversational)
  1. Call detect_and_parse_dataset(dataset_path)
     → raw rows + detected schema + source format
  2. LLM infers field mappings using alias table + reasoning
  3. If all required target fields are mapped:
     → present full mapping table, explain each target field, drop unmapped extras
  4. If required fields are missing/ambiguous:
     → present mapping table, ask about each unresolved required field one at a time
  5. User confirms
     → call transform_dataset(dataset_path, mapping, output_path)
     → writes canonical JSONL to data/transformed_<name>.jsonl
  6. If source is already canonical JSONL matching schema:
     → skip Phase 1, proceed directly to Phase 2
    ↓
Phase 2 — Validation & Reporting (autonomous, unchanged)
  7. Call validate_dataset(transformed_path)
  8. Interpret results, write data quality report (existing 6 sections)
  9. Set context dict keys for downstream
```

## New MCP Tool: `detect_and_parse_dataset`

**Purpose:** Format detection and raw parsing. Returns structured info for LLM mapping inference.

**Input:**
- `dataset_path: str` — path to the user's file (CSV, JSON, or JSONL)

**Returns** (JSON):
```json
{
  "source_format": "csv | json | jsonl",
  "num_rows": 123,
  "columns": ["prompt", "answer", "model_tier", "price", "score"],
  "sample_rows": [{"prompt": "...", "answer": "...", "model_tier": "..."}],
  "nested_paths": ["expected.route", "expected.routes.opus.cost"]
}
```

| Field | Description |
|-------|-------------|
| `source_format` | Detected by file extension + content sniffing (`.csv` → CSV, `.json` → try JSON array, `.jsonl` → JSONL) |
| `columns` | Top-level keys (JSONL/JSON) or column headers (CSV) |
| `nested_paths` | Dot-path keys for nested objects (e.g. `expected.route`) |
| `sample_rows` | First 5 rows as dicts — the LLM inspects values to reason about ambiguous mappings |

Fails with `ToolError` if format is unrecognizable or file is empty.

## New MCP Tool: `transform_dataset`

**Purpose:** Apply a confirmed field mapping and write canonical JSONL.

**Inputs:**
- `dataset_path: str` — original file path
- `field_mapping: str` — JSON object mapping source fields to target fields (e.g. `{"prompt": "input", "model_tier": "expected.route"}`)
- `output_path: str` — where to write the transformed JSONL

**Returns** (JSON):
```json
{
  "output_path": "/abs/path/to/transformed_file.jsonl",
  "rows_written": 123,
  "fields_mapped": {"prompt": "input", "model_tier": "expected.route"},
  "fields_dropped": ["answer"]
}
```

Behavior:
- Re-parses the source file, applies the mapping, writes one JSONL line per row
- Generates `id` fields if none exist (`row-0`, `row-1`, ...)
- Does **not** set `split` — that's the Routing Analysis Agent's job downstream
- Fails with `ToolError` if required target fields aren't covered by the mapping

## System Prompt Changes (`data_validation_system.md`)

### Identity update

Updated to reflect the dual-phase role: "You are the pipeline's format gate and data engineer."

### Phase 1 section (new)

Added before the existing workflow:
- Call `detect_and_parse_dataset` with the dataset path from the validated input report
- Examine the returned columns, sample rows, and nested paths
- Use the alias table (from the format-spec resource) + LLM reasoning to infer mappings to canonical target fields: `id`, `input`, `expected.route`, `expected.routes.*.cost`, `expected.routes.*.quality_score`
- Present the proposed mapping as a table with brief explanations of each target field
- If all required fields are confidently mapped → ask user to confirm, drop extras silently
- If any required field is ambiguous/unmapped → ask about each one individually
- Once confirmed, call `transform_dataset` → write to `data/transformed_<name>.jsonl`
- If the source file is already canonical JSONL matching the schema → skip Phase 1

### Phase 2 section (existing, minor changes)

- Operates on the transformed file path (or original if Phase 1 was skipped)
- "You do not interact with the user directly" line removed (Phase 1 is conversational)

### Available tools

Updated to list all three: `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`.

### Decision rules

Unchanged — they only apply to Phase 2.

## User Input Agent Handoff Update (`user_input_system.md`)

The User Input Agent's prompt currently treats Data Validation as a silent sub-step it dispatches and mediates. This changes to a clean handoff:

- Update the "Data Validation agent" section to clarify the full pipeline flow: User Input → Data Validation → Routing Analysis
- Make explicit that after `submit_input_report`, the Data Validation Agent activates and may talk to the user directly to confirm field mappings
- Remove the implication that User Input mediates validation issues — Data Validation handles that directly with the user
- The User Input Agent's job is done once it produces the validated input report

## Pipeline Integration

**Upstream (User Input Agent):** Handoff update described above. No structural changes — it still passes `dataset_path` and `problem_description`.

**Downstream (Routing Analysis Agent):** No changes. Receives `dataset_path` pointing to canonical JSONL.

**Context dict:** One addition:
- `original_dataset_path` — path to the user's original file (before transformation), for provenance tracking

**MCP registration (`mcp.py`):**
- Register `detect_and_parse_dataset` and `transform_dataset` as new tools
- No new resources or prompts needed

**Documentation:**
- `docs/architecture.md` — update Data Validation Agent description for two-phase workflow
- `odysseus/agents/data_validation_output.md` — no changes
- `odysseus/agents/data_validation_format.md` — no changes (alias table already present)

## Supported Input Formats

| Format | Detection | Notes |
|--------|-----------|-------|
| CSV | `.csv` extension or comma-delimited content | Headers required |
| JSON | `.json` extension, content is a JSON array | Array of objects |
| JSONL | `.jsonl` extension or newline-delimited JSON | One object per line |

## Out of Scope

- No new agent in the pipeline
- No changes to Routing Analysis, Prompt Builder, or any downstream agent
- No Parquet/Excel support (future)
- No schema migration or versioning of the transformation
- No automatic re-transformation on mapping changes — user starts over
