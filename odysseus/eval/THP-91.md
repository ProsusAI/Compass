# THP-91 — Build Dataset Manager with Streaming and Partitioning

**Type:** Task  
**Status:** To Do  
**Epic:** [THP-75](https://prosus-thymo-thesis.atlassian.net/browse/THP-75) — Eval framework Code  
**Jira:** [THP-91](https://prosus-thymo-thesis.atlassian.net/browse/THP-91)

## Description

Implement the dataset manager to load datasets as streaming iterators from JSONL files, support swappable data sources, and enforce a configurable dev/holdout split with sealed holdout access.

## What to build

Implement a concrete class that satisfies the `DatasetManager` protocol defined in `odysseus/eval/protocols.py`:

```python
class DatasetManager(Protocol):
    def load(self, path: str, split: Literal["dev", "holdout"]) -> list[Example]: ...
```

The implementation should:

- **Read JSONL** — open the file at `path`, parse each line as JSON, and validate/construct an `Example` (`id`, `input`, `expected`) using Pydantic. Raise a clear error on malformed lines.
- **Enforce dev/holdout split** — JSONL files should contain a `split` field per record (or an index-based convention). The manager must return only records matching the requested split. If `split="holdout"`, consider whether to add an access guard (e.g. require an env var `ALLOW_HOLDOUT=1`) to prevent accidental leakage during development iteration.
- **Swappable sources** — the `path` argument points to any JSONL file, so the same manager works for any dataset. The `data_source` in `RunConfig` is passed through unchanged by the controller.
- **Streaming-friendly** — even though the return type is `list[Example]`, load lazily where possible and avoid holding the full file in memory before validation. For very large files, document the memory tradeoff.
- **Logging** — log the number of examples loaded per split at `INFO`.

Suggested file: `odysseus/eval/dataset.py`

Data files live in `data/` (project root, excluded from version control).

## How it links with the rest of the codebase

| Touch point | Detail |
|---|---|
| `odysseus/eval/protocols.py` | Defines the `DatasetManager` protocol this class must satisfy. |
| `odysseus/eval/models.py` | Produces `list[Example]`. `Example` has `id: str`, `input: dict[str, Any]`, `expected: dict[str, Any]`. |
| `odysseus/eval/controller.py` | Calls `deps.dataset_manager.load(config.data_source, config.data_split)` as step 1 of `run()`. The returned list is fanned out to `_eval_with_retry` for each example. |
| `odysseus/eval/models.py` (`RunConfig`) | `data_source: str` (path to JSONL) and `data_split: Literal["dev", "holdout"]` come from the run config. |
| `data/` (project root) | On-disk store for JSONL datasets. Excluded from version control; directory created via `.gitkeep`. |
| `odysseus/mcp.py` | The MCP tool will wire a concrete `DatasetManager` into `RunDependencies`. |

## Dependencies between tasks

- No hard blockers — can be developed and unit-tested independently using mock JSONL data.
- THP-92 (Run Controller) consumes this via `RunDependencies.dataset_manager`.
- THP-93 (Configuration Schema) defines `data_source` and `data_split` in `RunConfig`; both are already in `models.py`.
