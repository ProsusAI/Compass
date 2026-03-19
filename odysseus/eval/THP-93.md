# THP-93 — Define and Validate Configuration Schema

**Type:** Task  
**Status:** To Do  
**Epic:** [THP-75](https://prosus-thymo-thesis.atlassian.net/browse/THP-75) — Eval framework Code  
**Jira:** [THP-93](https://prosus-thymo-thesis.atlassian.net/browse/THP-93)

## Description

Specify the configuration schema for the evaluation framework, including backend selection, prompt version, data source, metrics, concurrency, rate limits, retry policy, and output paths. Implement validation logic to ensure correctness before runs.

## What to build

The Pydantic config models are already implemented in `odysseus/eval/models.py`. This task is about ensuring they are complete, validated, and documented as the authoritative source of truth.

### Review and harden `odysseus/eval/models.py`

All config classes live here:

| Class | Fields |
|---|---|
| `RunConfig` | `backend`, `prompt_version`, `data_source`, `data_split`, `metrics`, `concurrency`, `retry`, `output` |
| `MetricConfig` | `name`, `params` |
| `ConcurrencyConfig` | `max_concurrent_requests`, `requests_per_minute`, `tokens_per_minute` |
| `RetryConfig` | `max_attempts`, `backoff_factor`, `per_call_timeout_seconds` |
| `OutputConfig` | `results_path`, `report_path` |

Tasks for this ticket:

1. **Add field-level validators** — e.g. `max_concurrent_requests > 0`, `max_attempts >= 1`, `data_split` is already a `Literal["dev", "holdout"]`. Add `@field_validator` where useful.
2. **Add cross-field validators** — e.g. `per_call_timeout_seconds` should be less than what a reasonable backoff sequence would accumulate.
3. **Write a YAML example** — create `prompts/example-config.yaml` (or similar) showing all fields with comments, so users know how to write a valid run config.
4. **Unit-test `from_yaml()`** — `RunConfig.from_yaml(path)` already loads and validates via Pydantic. Add tests covering: valid round-trip, missing required field raises `ValidationError`, invalid `data_split` value raises `ValidationError`.
5. **Document defaults** — ensure all default values are intentional and documented in docstrings.

### `RunConfig.from_yaml()` (already implemented)

```python
@classmethod
def from_yaml(cls, path: str | Path) -> RunConfig:
    with open(path) as f:
        data = yaml.safe_load(f)
    return cls(**data)
```

Pydantic handles validation on construction. Invalid YAML will raise `yaml.YAMLError`; invalid field values will raise `pydantic.ValidationError`.

## How it links with the rest of the codebase

| Touch point | Detail |
|---|---|
| `odysseus/eval/models.py` | **This is the file this task owns.** All config Pydantic models live here. |
| `odysseus/eval/controller.py` | `run(config: RunConfig, deps: RunDependencies)` — the controller is parameterised entirely by `RunConfig`. Every field is accessed directly (e.g. `config.concurrency.requests_per_minute`). |
| `odysseus/eval/rate_limiter.py` | Constructed from `ConcurrencyConfig` fields by the controller. |
| All other tasks | Every component reads its settings from a nested config sub-model. The schema defined here is the contract for THP-87, THP-88, THP-89, THP-90, THP-91, THP-113. |
| `odysseus/mcp.py` | The MCP tool receives `data_path` and calls `RunConfig.from_yaml()` (or builds `RunConfig` programmatically) before calling `run()`. |

## Dependencies between tasks

- No blockers — this task can (and should) be done first or in parallel, as every other task depends on these types.
- Already partially complete: all models exist in `models.py`. This task finalises and tests them.
