# THP-90 — Develop Results Collector and Report Generator

**Type:** Task  
**Status:** To Do  
**Epic:** [THP-75](https://prosus-thymo-thesis.atlassian.net/browse/THP-75) — Eval framework Code  
**Jira:** [THP-90](https://prosus-thymo-thesis.atlassian.net/browse/THP-90)

## Description

Implement the results collector to write responses to JSONL files as they arrive, aggregate results, compute metrics, and generate structured, versioned score reports with diffs against previous runs.

## What to build

Implement a concrete class that satisfies the `ResultsCollector` protocol defined in `odysseus/eval/protocols.py`:

```python
class ResultsCollector(Protocol):
    def write_results(self, results: list[EvalResult], path: str) -> None: ...
    def write_report(self, report: RunReport, path: str) -> None: ...
```

The implementation should:

- **`write_results(results, path)`** — serialize each `EvalResult` to a JSON line and write them to the JSONL file at `path`. Parent directories are guaranteed to exist by the controller before this is called.
- **`write_report(report, path)`** — serialize the full `RunReport` to a pretty-printed JSON file at `path`. `RunReport` is a Pydantic model so use `.model_dump_json(indent=2)`.
- **Versioned reports** — optionally append a timestamp or run ID to output filenames (or this may be handled at the config level via `OutputConfig`; defer to THP-93 / `RunConfig` as the source of truth for paths).
- **Diff against previous runs** — when a previous report file exists at the same path, generate a human-readable diff of the `metrics` dict (e.g. `accuracy: 0.82 → 0.85`) and log it at `INFO`.

Suggested file: `odysseus/eval/collector.py`

## How it links with the rest of the codebase

| Touch point | Detail |
|---|---|
| `odysseus/eval/protocols.py` | Defines the `ResultsCollector` protocol this class must satisfy. |
| `odysseus/eval/models.py` | Serializes `EvalResult` (JSONL) and `RunReport` (JSON). Both are Pydantic models — use `.model_dump()` / `.model_dump_json()`. |
| `odysseus/eval/controller.py` | Calls `deps.results_collector.write_results(results, config.output.results_path)` and `deps.results_collector.write_report(report, config.output.report_path)` as the final step of `run()`. Parent directories are pre-created by the controller. |
| `odysseus/eval/models.py` (`OutputConfig`) | `results_path` and `report_path` come from `RunConfig.output`. Defaults: `outputs/results.jsonl` and `outputs/report.json`. |
| `outputs/` (project root) | On-disk destination. Excluded from version control via `.gitignore`; directory created via `.gitkeep`. |
| `odysseus/mcp.py` | The MCP tool will wire a concrete `ResultsCollector` into `RunDependencies`. |

## Dependencies between tasks

- No hard blockers — can be developed and unit-tested independently.
- THP-92 (Run Controller) consumes this via `RunDependencies.results_collector`.
- THP-93 (Configuration Schema) defines `OutputConfig`; that model is already in `models.py`.
