# THP-114: Design the `run_eval` MCP Tool

**Date:** 2026-03-19
**Status:** Draft
**Ticket:** [THP-114](https://prosus-thymo-thesis.atlassian.net/browse/THP-114)

## Context

The eval framework's run controller (`odysseus/eval/controller.py`) exposes `async def run(config: RunConfig, deps: RunDependencies) -> RunReport`. The Eval Runner agent needs an MCP tool to invoke this controller. This document defines that tool's interface, wiring, and behavior.

### Deviations from ticket

This design deviates from the original THP-114 ticket in two ways, both deliberate:

1. **Return value:** The ticket says "a serialized score report in the format defined by THP-116." This design returns only file paths (`report_path`, `results_path`). The review agent reads the full report from disk, keeping the eval runner's context lean and avoiding token-limit issues. The ticket should be updated to reflect this.
2. **Additional parameters:** The ticket lists only `prompt_version` and `data_source`. This design adds `backend: str` (required — the agent must select a model) and `config_path: str` (optional — points to upstream config). The ticket should be updated to reflect the final parameter list.

### Responsibilities split

| Concern | Owner |
|---|---|
| Eval criteria (metrics, concurrency, retry, output paths) | Upstream agent, via config file |
| Iteration parameters (prompt version, data source, backend) | Eval Runner agent, via tool parameters |
| Interpretation of results | Review agent, reads files from disk |

## Tool Signature

```python
@mcp.tool()
async def run_eval(
    prompt_version: str,
    data_source: str,
    backend: str,
    config_path: str = "outputs/run_config.yaml",
) -> str:
    """Run an evaluation of a prompt version against a dataset.

    Args:
        prompt_version: Prompt version identifier (e.g. "v3", "latest").
        data_source: Path to the JSONL dataset file.
        backend: Backend label matching a profile in backends/ directory.
        config_path: Path to YAML config with metrics, concurrency, retry,
                     and output settings. Defaults to "outputs/run_config.yaml".

    Returns:
        JSON object with report_path and results_path pointing to
        the full evaluation output on disk.
    """
```

- `data_split` is hardcoded to `"dev"` inside the function body. It is never exposed as a parameter (see THP-115).
- Return type is `str` (serialized JSON) per MCP convention.
- The docstring serves as the tool description visible to the agent LLM.

## Config File Schema

The stable config file at `config_path` is written once by the upstream agent:

```yaml
# outputs/run_config.yaml
metrics:
  - name: accuracy
  - name: f1
  - name: cost_quality_reduction

concurrency:
  max_concurrent_requests: 20

retry:
  max_attempts: 3
  backoff_factor: 2.0
  per_call_timeout_seconds: 60.0

output:
  results_path: outputs/results.jsonl
  report_path: outputs/report.json
```

The tool loads this file and constructs the full `RunConfig` by overlaying:

- `backend` from tool parameter
- `prompt_version` from tool parameter
- `data_source` from tool parameter
- `data_split` hardcoded to `"dev"`

Optional fields not present in the YAML (e.g. `concurrency`, `retry`, `output`) fall back to `RunConfig` defaults. Required fields without defaults (`backend`, `data_source`, `data_split`, `metrics`) must be supplied either by the YAML or the tool parameter overlay.

### Overlay mechanism

The tool must **not** use `RunConfig.from_yaml()`, which expects all required fields to be present. Instead:

1. Load the YAML file as a raw `dict`.
2. Inject tool parameters: `backend`, `prompt_version`, `data_source`, and `data_split="dev"`.
3. Construct `RunConfig` via `RunConfig.model_validate(merged_dict)`.

Tool parameters override any matching keys already present in the YAML dict.

## Dependency Wiring

All concrete implementations are assembled inside the tool function:

```python
# Backend from registry
registry = BackendRegistry.from_directory(Path("backends"))
backend_instance = registry.create_backend(backend)
profile = registry.get_profile(backend)

# Other dependencies
prompt_manager = FilePromptManager(prompts_dir=Path("prompts"))
dataset_manager = JsonlDatasetManager()
metrics_engine = create_default_engine()
results_collector = JsonResultsCollector()

# Rate limits from backend profile
deps = RunDependencies(
    backend=backend_instance,
    prompt_manager=prompt_manager,
    dataset_manager=dataset_manager,
    metrics_engine=metrics_engine,
    results_collector=results_collector,
    requests_per_minute=profile.requests_per_minute,
    tokens_per_minute=profile.tokens_per_minute,
)
```

Key points:

- `BackendRegistry` loads YAML profiles from `backends/` directory.
- Rate limits (`requests_per_minute`, `tokens_per_minute`) come from `BackendProfile`, not the config file. They are backend-specific.
- `FilePromptManager` reads versioned prompts from `prompts/` directory.
- `create_default_engine()` registers all built-in metrics (accuracy, f1, confusion, cost_quality_reduction).

## Return Value

### Success

```json
{
  "report_path": "outputs/report.json",
  "results_path": "outputs/results.jsonl"
}
```

The tool returns only file paths. The full report (per-example results, metrics, summary, diffs) is written to disk by `ResultsCollector`. The review agent reads these files directly when it needs to interpret results and decide on prompt changes.

### Recoverable Errors

Known, actionable errors return a structured JSON object so the agent can interpret and adjust:

```python
except FileNotFoundError as e:
    return json.dumps({"error": "not_found", "detail": str(e)})
except (ValueError, ValidationError) as e:
    return json.dumps({"error": "validation_error", "detail": str(e)})
except PermissionError as e:
    return json.dumps({"error": "permission_denied", "detail": str(e)})
```

These cover: missing prompt version, missing dataset file, invalid config/schema (including Pydantic `ValidationError` from malformed YAML values), and holdout access denial.

### Unexpected Errors

Unhandled exceptions are raised as MCP tool errors, letting the framework signal failure natively:

```python
except Exception as e:
    raise McpError(f"run_eval failed unexpectedly: {e}") from e
```

Note: `McpError` should be imported from `mcp.shared.exceptions` (or the appropriate path in the `mcp` SDK). Check FastMCP documentation for the canonical error type.

## High Error Rate Handling

A run where many examples fail is not a tool-level error. The run completes normally, files are written to disk, and paths are returned. The review agent reads the report (which contains `summary.failed` and per-example errors) and decides how to proceed. The eval runner agent's system prompt (THP-104) may instruct it to surface a warning, but the tool itself does not gate on error rate.

## Dependencies

| Dependency | Status | Detail |
|---|---|---|
| `controller.run()` | Implemented | `odysseus/eval/controller.py` |
| `RunConfig`, `RunDependencies` | Implemented | `odysseus/eval/models.py`, `odysseus/eval/protocols.py` |
| `BackendRegistry`, `LiteLLMBackend` | Implemented | `odysseus/eval/backends/` |
| `FilePromptManager` | Implemented | `odysseus/prompts/manager.py` |
| `JsonlDatasetManager` | Implemented | `odysseus/eval/dataset.py` |
| `DefaultMetricsEngine` | Implemented | `odysseus/eval/metrics.py` |
| `JsonResultsCollector` | Implemented | `odysseus/eval/collector.py` |
| THP-115 (holdout access control) | Design complete | Enforced by hardcoding `data_split="dev"` |
| THP-116 (score report format) | To Do | Defines full report schema written to disk |
| THP-104 (agent system prompt) | To Do | References tool name and parameters |
| THP-129 (tool implementation) | To Do | Implements this design |
