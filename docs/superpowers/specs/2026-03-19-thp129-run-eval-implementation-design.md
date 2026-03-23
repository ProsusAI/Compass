# THP-129: Implement the `run_eval` MCP Tool

**Date:** 2026-03-19
**Status:** Draft
**Ticket:** [THP-129](https://prosus-thymo-thesis.atlassian.net/browse/THP-129)
**Depends on:** THP-114 (tool design), THP-115 (holdout enforcement)

## Context

All eval framework components are implemented: controller, protocols, backends, prompt manager, dataset manager, metrics engine, and results collector. The `run_eval` MCP tool in `odysseus/mcp.py` is currently a stub. This spec defines how to wire the concrete dependencies and implement the tool per the THP-114 design.

### Deviation from THP-114

`config_path` defaults to `configs/run_config.yaml` instead of `outputs/run_config.yaml`. The `configs/` directory is the project convention for configuration files.

## Tool Signature

```python
@mcp.tool()
async def run_eval(
    prompt_version: str,
    data_source: str,
    backend: str,
    config_path: str = "configs/run_config.yaml",
) -> str:
    """Run an evaluation of a prompt version against a dataset.

    Args:
        prompt_version: Prompt version identifier (e.g. "v3", "latest").
        data_source: Path to the JSONL dataset file.
        backend: Backend label matching a profile in backends/ directory.
        config_path: Path to YAML config with metrics, concurrency, retry,
                     and output settings. Defaults to "configs/run_config.yaml".

    Returns:
        JSON object with report_path and results_path pointing to
        the full evaluation output on disk.
    """
```

`data_split` is hardcoded to `"dev"` inside the function body (THP-115). It is never exposed as a parameter.

## Config Overlay Mechanism

A new `_load_config()` helper replaces the existing `_build_run_config()`:

1. Load `config_path` as a raw dict via `yaml.safe_load()`.
2. Overlay tool parameters: `backend`, `prompt_version`, `data_source`, `data_split="dev"`.
3. Validate via `RunConfig.model_validate(merged_dict)`.

Tool parameters always override YAML keys. All sections are optional in the YAML — `concurrency`, `retry`, and `output` fall back to `RunConfig` defaults, and `metrics` falls back to all 4 built-in metrics (accuracy, confusion, f1, cost_quality_reduction) if omitted.

```python
_DEFAULT_METRICS = [
    MetricConfig(name="accuracy"),
    MetricConfig(name="confusion"),
    MetricConfig(name="f1"),
    MetricConfig(name="cost_quality_reduction"),
]


def _load_config(
    prompt_version: str,
    data_source: str,
    backend: str,
    data_split: Literal["dev", "holdout"],
    config_path: str,
) -> RunConfig:
    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    raw.update({
        "backend": backend,
        "prompt_version": prompt_version,
        "data_source": data_source,
        "data_split": data_split,
    })

    if "metrics" not in raw:
        raw["metrics"] = [m.model_dump() for m in _DEFAULT_METRICS]

    return RunConfig.model_validate(raw)
```

## Dependency Wiring

All concrete implementations are assembled inside the tool function body:

```python
registry = BackendRegistry.from_directory(Path("backends"))
backend_instance = registry.create_backend(backend)
profile = registry.get_profile(backend)

deps = RunDependencies(
    backend=backend_instance,
    prompt_manager=FilePromptManager(prompts_dir=Path("prompts")),
    dataset_manager=JsonlDatasetManager(),
    metrics_engine=create_default_engine(),
    results_collector=JsonResultsCollector(),
    requests_per_minute=profile.requests_per_minute,
    tokens_per_minute=profile.tokens_per_minute,
)
```

- Rate limits come from `BackendProfile`, not the config file.
- Fresh instances per call (stateless, no singletons).
- Directory paths (`backends/`, `prompts/`) are relative to CWD (MCP server runs from project root).

## Return Value

### Success

```json
{"report_path": "outputs/report.json", "results_path": "outputs/results.jsonl"}
```

Paths are read from `config.output.report_path` and `config.output.results_path` so they reflect whatever the config specifies.

### Recoverable Errors

Structured JSON so the agent can interpret and adjust:

| Exception | Error code | Example |
|---|---|---|
| `FileNotFoundError`, `KeyError` | `not_found` | Missing prompt version, dataset, config file, backend profile (`KeyError` from `BackendRegistry.get_profile()`) |
| `ValueError`, `ValidationError` | `validation_error` | Bad config values, schema violations |
| `PermissionError` | `permission_denied` | Holdout access denied |

All error handling is inside the tool function body (i.e., `_load_config()` and dependency wiring are called within the try/except block).

```python
except (FileNotFoundError, KeyError) as e:
    return json.dumps({"error": "not_found", "detail": str(e)})
except (ValueError, ValidationError) as e:
    return json.dumps({"error": "validation_error", "detail": str(e)})
except PermissionError as e:
    return json.dumps({"error": "permission_denied", "detail": str(e)})
```

### Unexpected Errors

Unexpected exceptions are not caught — FastMCP automatically wraps any unhandled exception in `ToolError` (see `mcp.server.fastmcp.tools.base`). No explicit `except Exception` block is needed.

### High Error Rate

Not a tool-level error. The run completes, files are written, paths are returned. The review agent reads `summary.failed` from the report and decides how to proceed.

## Changes to `mcp.py`

| Change | Detail |
|---|---|
| Remove `_build_run_config()` | Replaced by `_load_config()` |
| Add `_load_config()` | YAML load, overlay, validate |
| Rewrite `run_eval()` | New signature (`backend`, `config_path`), wire deps, call `controller.run()`, return paths |
| Leave `run_holdout_eval()` unchanged | Out of THP-129 scope; signature and stub body stay as-is |
| New imports | `yaml`, `json`, `pathlib.Path`, `odysseus.eval.backends.registry.BackendRegistry`, `odysseus.prompts.manager.FilePromptManager`, `odysseus.eval.dataset.JsonlDatasetManager`, `odysseus.eval.metrics.create_default_engine`, `odysseus.eval.collector.JsonResultsCollector`, `odysseus.eval.protocols.RunDependencies`, `odysseus.eval.controller` (module import, called as `controller.run()`), `pydantic.ValidationError` |

## Testing

### `_load_config()` unit tests

- YAML values are loaded correctly
- Tool parameters override YAML keys
- Missing optional sections use `RunConfig` defaults
- Missing config file raises `FileNotFoundError`
- Invalid YAML values raise `ValidationError`

### `run_eval()` integration tests

- End-to-end with mocked `controller.run()`: verify deps are wired correctly and return JSON contains paths
- Missing backend profile returns `{"error": "not_found", ...}`
- Missing config file returns `{"error": "not_found", ...}`
- Validation error returns `{"error": "validation_error", ...}`
- Unexpected exception raises `McpError`

## Dependencies

| Component | Status |
|---|---|
| `controller.run()` | Implemented |
| `RunConfig`, `RunDependencies` | Implemented |
| `BackendRegistry`, `LiteLLMBackend` | Implemented |
| `FilePromptManager` | Implemented |
| `JsonlDatasetManager` | Implemented |
| `DefaultMetricsEngine` | Implemented |
| `JsonResultsCollector` | Implemented |
| THP-115 (holdout access control) | Enforced by hardcoding `data_split="dev"` |
