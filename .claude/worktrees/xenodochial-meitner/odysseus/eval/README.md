# odysseus/eval — Evaluation Engine

Runs a versioned prompt against a dataset split, fans out concurrent LLM calls with rate limiting and retry, computes routing metrics, and writes a structured `RunReport`.

The engine evaluates one prompt version against one dataset split per run. The optimisation loop that iterates over prompt versions lives above this layer.

## How it works

`controller.run(config, deps)` is the single entry point.

1. Load prompt (`PromptManager`) and examples (`DatasetManager`).
2. Fan out all examples concurrently using `asyncio` tasks, throttled by a dual-bucket rate limiter (RPM + TPM) and an `asyncio.Semaphore`.
3. Each example goes through `_eval_with_retry` — calls `Backend.call()`, handles exponential backoff, computes cost from `Backend.pricing`.
4. Compute metrics via `MetricsEngine`.
5. Write `results.jsonl` and `report.json` via `ResultsCollector`, then return `RunReport`.

All five collaborators (`Backend`, `PromptManager`, `DatasetManager`, `MetricsEngine`, `ResultsCollector`) are injected via `RunDependencies` — the controller depends only on protocols, not concrete implementations.

## Key concepts

| Concept | What it is |
|---------|-----------|
| `RunDependencies` | Dataclass holding all injected collaborators + rate-limit ints sourced from the backend profile. Passed to `controller.run()`. |
| `RunConfig` | Pydantic model: `backend`, `prompt_version`, `data_source`, `data_split`, `metrics`, `concurrency`, `retry`, `output`. Load from YAML via `RunConfig.from_yaml()`. |
| `ScoreReport` | Slim summary built from `RunReport` after a run; includes `metrics`, `RunSummary`, error breakdown, and an optional run-over-run `RunDiff`. This is the contract between `EvalRunnerAgent` and the review step. |
| Backend profiles | YAML files in `backends/` that define `model`, rate limits (`requests_per_minute`, `tokens_per_minute`), pricing, and provider-specific params. Loaded by `BackendRegistry`. |

## Deep dives

| Document | Contents |
|----------|----------|
| [`docs/README.md`](docs/README.md) | Module inventory, quick-start example |
| [`docs/architecture.md`](docs/architecture.md) | System diagram, data-flow walkthrough, full field references for all models, metrics reference |
| [`docs/backends.md`](docs/backends.md) | Backend registry design, YAML format, provider examples (Anthropic, OpenAI, Bedrock, Vertex AI), error reference |

## How EvalRunnerAgent wires it

`odysseus/agents/eval_runner.py` — `EvalRunnerAgent.run(context)`:

1. **Config loading** — reads `outputs/run_config.yaml`, then overlays `prompt_version`, `data_source`, `backend`, and `data_split="dev"` from context.
2. **Dependency construction** (`_wire_dependencies`) — loads `BackendRegistry` from `backends/`, looks up the profile by label, constructs `RunDependencies` with `FilePromptManager`, `JsonlDatasetManager`, `create_default_engine()`, and `JsonResultsCollector`. Rate-limit ints come from the profile.
3. **Report diffing** — loads the previous `report.json` (if any) before running, so `ScoreReport.from_run_report()` can populate `RunDiff` for run-over-run metric and cost comparison.
4. Returns `{ScoreReport.CONTEXT_KEY: score_report}` for the downstream review agent.
