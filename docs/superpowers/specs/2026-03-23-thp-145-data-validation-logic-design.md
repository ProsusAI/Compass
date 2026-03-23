# THP-145 — Implement full dataset validation logic

**Date:** 2026-03-23
**Status:** Approved
**Epic:** THP-73 (Data Validation Agent)
**Approach:** Thin orchestration + MCP wiring (Approach A)

## Scope

Implement the remaining validation checks and wire them into the MCP server as a prompt-driven agent. The calling LLM writes the narrative summary; this task provides structured check results.

**In scope:**
- Null field detection (added to `check_schema_conformance`)
- Query length distribution (new standalone check)
- `run_all_checks` orchestration function
- MCP prompt, tool, and resources
- System prompt for the data validation agent
- Tests for all new code

**Out of scope (moved to downstream agent):**
- Missing signal type detection
- Data collection suggestions

## Dependencies

| Dependency | Status |
|---|---|
| THP-80 (data format spec) | Done |
| THP-81 (output format spec) | Done |

## Design

### 1. Check function changes

All changes in `odysseus/agents/data_validation_checks.py`.

**Extend `check_schema_conformance`:** Add a check that scans all fields across all rows for null/None values and reports which fields have nulls and in which rows. The existing null check only covers required fields; this extends to detecting nulls in any field including optional ones. Null detection is constrained to top-level fields plus `expected.*` fields — no arbitrary recursion into nested structures.

**New function `check_query_length_distribution(rows: list[dict]) -> QueryLengthDistribution`:**
- Extracts the `input` field from each row
- Computes min, max, mean, p95 character length
- Skips rows where `input` is missing or not a string

**New Pydantic model:**

```python
class QueryLengthDistribution(BaseModel):
    min: int
    max: int
    mean: float
    p95: float
    count: int  # number of valid rows analyzed
```

**Update `DataQualityReport`:** Add optional field `query_length: QueryLengthDistribution | None`.

### 2. Orchestration and MCP wiring

**`run_all_checks(rows: list[dict]) -> DataQualityReport`** in `data_validation_checks.py`:
- Calls all four check functions: `check_schema_conformance`, `check_label_distribution`, `check_volume_adequacy`, `check_query_length_distribution`
- Uses sensible defaults for thresholds (`min_tier_percentage=0.10`, `min_per_tier=5`) — these are intentional defaults, not magic numbers; comment them as such
- Sets `summary=""` (the calling LLM writes the narrative summary separately)
- Assembles and returns a `DataQualityReport`

**MCP additions in `odysseus/mcp.py`:**

1. **Prompt** `odysseus_data_validation()` — returns system prompt from `prompts/data_validation_system.md`, activating the data validation agent conversation.
2. **Tool** `validate_dataset(dataset_path: str) -> str` — loads the JSONL file, parses rows, calls `run_all_checks`, returns the report as JSON. The calling LLM uses this structured output to write its narrative report.
3. **Resources** — expose `data_validation_format.md` and `data_validation_output.md` as MCP resources so the LLM can reference the specs.

**System prompt** (`prompts/data_validation_system.md`): Instructs the LLM on its role as the Data Validation agent — call `validate_dataset`, interpret results, write narrative summary paragraphs per THP-81 format, and surface findings to the user.

### 3. Testing strategy

**Unit tests** (in `tests/test_data_validation_checks.py`):

- `check_schema_conformance` — add tests for null detection across optional fields
- `check_query_length_distribution` — new test class:
  - Normal distribution stats (known inputs, verify min/max/mean/p95)
  - Rows with missing/invalid `input` fields skipped
  - Empty rows edge case
  - Single row (p95 equals that row's length)
- `run_all_checks` — verify it calls all four checks and returns a complete `DataQualityReport`

**Integration tests** (new `tests/test_mcp_data_validation.py`):

- `validate_dataset` with temp JSONL file — verify valid JSON matching `DataQualityReport` schema
- Error case: non-existent file path
- Error case: malformed JSONL

## File inventory

| Action | File |
|---|---|
| Modify | `odysseus/agents/data_validation_checks.py` |
| Modify | `odysseus/mcp.py` |
| Modify | `odysseus/agents/__init__.py` |
| Create | `prompts/data_validation_system.md` |
| Modify | `tests/test_data_validation_checks.py` |
| Create | `tests/test_mcp_data_validation.py` |
