# Project Odysseus

Improved Agentic Routing Optimizer — a multi-agent pipeline that takes a routing problem as input, iteratively refines a few-shot routing prompt using an automated evaluation loop, and produces a validated final prompt and evaluation report. Deployed as an MCP (Model Context Protocol) server.

## Tech Stack

- **Language**: Python 3.11+
- **Package manager**: `uv` (use `uv` for all dependency management, virtual environments, and running scripts — never pip directly)
- **Deployment target**: MCP server (via `python -m odysseus.mcp` or `uvx odysseus`)
- **Async runtime**: `asyncio` + `aiohttp`
- **Testing**: `pytest` with `pytest-asyncio`
- **Linting/formatting**: `ruff`
- **Type checking**: `pyright`

## Commands

```bash
uv sync                     # Install dependencies
uv run pytest               # Run tests
uv run ruff check .         # Lint
uv run ruff format .        # Format
uv run pyright              # Type check
uv run python -m odysseus.mcp  # Run MCP server locally
uv run odysseus init           # Scaffold project dirs (outputs/, prompts/, backends/)
```

## Project Structure

For detailed architecture, see [`docs/architecture.md`](docs/architecture.md).

```
odysseus/              # Main package
  mcp.py               # MCP server entrypoint
  agents/              # Domain models, validation, registry ops (see agents/README.md)
    prompts/           # Agent system prompts (Markdown, surfaced via MCP)
  eval/                # Evaluation engine (see eval/README.md)
    docs/              # Eval engine detailed documentation
  prompts/             # Prompt management (FilePromptManager)
data/                  # Dataset files (JSONL)
outputs/               # Run outputs and reports
prompts/               # Routing prompt store — versioned prompts (see prompts/README.md)
tests/                 # Test suite
  scenarios/           # MCP integration test scenarios (runbooks)
  fixtures/integration/# Eval runner integration fixtures
pyproject.toml         # Project config (uv)
```

## Conventions

- Agents are primarily LLM-driven (system prompts in `odysseus/agents/prompts/` surfaced via MCP); `EvalRunnerAgent` is the one code-driven exception
- Use `pyproject.toml` for project metadata and dependencies (no `requirements.txt`)
- Keep `uv.lock` committed for reproducibility
- Environment variables for API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) — never hardcode secrets
- JSONL for data interchange between pipeline stages
- Versioned prompts in YAML/JSON format

## Integration Testing

Agent integration tests are MCP scenario runbooks in `tests/scenarios/`. Each scenario is a Markdown file executed by a Claude Code instance with the Odysseus MCP server configured.

**When adding a new agent**, add integration test scenarios following this pattern:

1. Create scenario files in `tests/scenarios/` numbered sequentially (e.g. `13_data_validation_clean_dataset.md`)
2. Add test datasets in `tests/scenarios/data/` as JSONL files
3. Each scenario file has four sections: `## Setup`, `## Scenario Description`, `## User Simulator`, `## Verification Criteria`
4. A User Simulator sub-agent plays the user role; a Verification Agent checks pass/fail criteria against the transcript
5. Update `tests/scenarios/README.md` with the new scenarios in the index table

See `tests/scenarios/README.md` for the full runbook protocol and existing scenarios.
