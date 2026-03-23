# THP-93 — Config Schema Validation Design

**Date:** 2026-03-19
**Ticket:** [THP-93](https://prosus-thymo-thesis.atlassian.net/browse/THP-93)
**Status:** Design approved

## Goal

Harden the existing Pydantic config models in `odysseus/eval/models.py` with field-level and cross-field validators, create an example YAML config, and add comprehensive tests. Every `RunConfig` instance must be valid on construction — no separate validation step.

## Approach

Inline validators in `models.py` using Pydantic's `@field_validator` and `@model_validator` decorators. No new files or abstractions beyond the example config and tests.

## Changes

### 1. Field-level validators (`@field_validator`)

**`MetricConfig`**
- `name`: must be non-empty after stripping whitespace

**`ConcurrencyConfig`**
- `max_concurrent_requests`: must be `>= 1`
- `requests_per_minute`: must be `>= 1`
- `tokens_per_minute`: must be `>= 1`

**`RetryConfig`**
- `max_attempts`: must be `>= 1`
- `backoff_factor`: must be `>= 1.0`
- `per_call_timeout_seconds`: must be `> 0`

**`OutputConfig`**
- `results_path`: must end with `.jsonl`
- `report_path`: must end with `.json`

**`RunConfig`**
- `backend`: must be non-empty after stripping whitespace
- `prompt_version`: must be non-empty after stripping whitespace (consistent with `backend`/`data_source`)
- `data_source`: must be non-empty after stripping whitespace
- `metrics`: must contain at least one entry
- `data_split`: already constrained by `Literal["dev", "holdout"]` — no extra validator needed

### 2. Cross-field validator (`@model_validator`)

**`RetryConfig` — `mode="after"`**

Two hard bounds:

1. `per_call_timeout_seconds <= 300` — a single call hanging for 5+ minutes is almost certainly misconfigured.
2. Total worst-case duration `<= 1800s` (30 minutes). Computed as:
   ```
   total = sum(backoff_factor**i for i in range(1, max_attempts)) + max_attempts * per_call_timeout_seconds
   ```
   This catches pathological combos like `max_attempts=10, backoff_factor=3.0, timeout=60s`.

### 3. Example YAML config

**File:** `configs/example-run.yaml`

A fully commented YAML file showing all fields with defaults and valid values. Serves as documentation and copy-paste starting point for users.

Contents will cover:
- `backend`, `prompt_version`, `data_source`, `data_split`
- `metrics` list with `name` and `params`
- `concurrency` block with all three fields
- `retry` block with all three fields
- `output` block with both paths
- Inline comments documenting defaults, constraints, and valid options

### 4. Tests

All tests in `tests/test_models.py`. Additions organized into groups:

**Valid construction (extend existing)**
- Round-trip through `configs/example-run.yaml` via `from_yaml()` — asserts the example config stays valid

**Field-level rejection (one test per validator)**
- `ConcurrencyConfig(max_concurrent_requests=0)` raises `ValidationError`
- `ConcurrencyConfig(requests_per_minute=-1)` raises `ValidationError`
- `ConcurrencyConfig(tokens_per_minute=0)` raises `ValidationError`
- `RetryConfig(max_attempts=0)` raises `ValidationError`
- `RetryConfig(backoff_factor=0.5)` raises `ValidationError`
- `RetryConfig(per_call_timeout_seconds=0)` raises `ValidationError`
- `OutputConfig(results_path="foo.txt")` raises `ValidationError`
- `OutputConfig(report_path="bar.csv")` raises `ValidationError`
- `RunConfig(backend="", ...)` raises `ValidationError`
- `RunConfig(prompt_version="  ", ...)` raises `ValidationError`
- `RunConfig(data_source="  ", ...)` raises `ValidationError`
- `RunConfig(metrics=[], ...)` raises `ValidationError`
- `MetricConfig(name="")` raises `ValidationError`

**Cross-field rejection**
- `RetryConfig(per_call_timeout_seconds=301)` raises `ValidationError`
- `RetryConfig(per_call_timeout_seconds=300)` is accepted (boundary)
- `RetryConfig(max_attempts=10, backoff_factor=3.0, per_call_timeout_seconds=60)` raises `ValidationError` (total worst-case > 1800s)
- A config where total worst-case is just under 1800s is accepted (boundary)

**Positive boundary tests (minimum valid values accepted)**
- `ConcurrencyConfig(max_concurrent_requests=1, requests_per_minute=1, tokens_per_minute=1)` succeeds
- `RetryConfig(max_attempts=1, backoff_factor=1.0, per_call_timeout_seconds=0.1)` succeeds
- `OutputConfig(results_path="r.jsonl", report_path="r.json")` succeeds
- `MetricConfig(name="a")` succeeds

**Whitespace handling**
- `MetricConfig(name="   ")` raises `ValidationError`
- `RunConfig(data_source="   ", ...)` raises `ValidationError` (in addition to `""` test)

**Existing coverage preserved**
- `data_split="test"` raises `ValidationError` (already covered)
- Missing required fields raises `ValidationError` (already covered)

### 5. Docstring updates

Update docstrings on each config class to document:
- Default values for each field
- Constraints enforced by validators
- Brief explanation of cross-field validation on `RetryConfig`

## Files touched

| File | Action |
|---|---|
| `odysseus/eval/models.py` | Add validators, update docstrings |
| `configs/example-run.yaml` | New file |
| `tests/test_models.py` | Add validation tests |

## Out of scope

- No changes to `controller.py`, `rate_limiter.py`, or other consumers — they already trust `RunConfig` is valid on construction
- No new modules or abstractions
- No runtime warning mode — all validators are hard errors
