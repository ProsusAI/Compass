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
```

## Project Structure

```
odysseus/              # Main package
  mcp.py               # MCP server entrypoint
  agents/              # Agent implementations
  eval/                # Evaluation engine
  prompts/             # Prompt management
data/                  # Dataset files (JSONL)
outputs/               # Run outputs and reports
prompts/               # Versioned prompt files
tests/                 # Test suite
pyproject.toml         # Project config (uv)
```

## Conventions

- All agents are async Python classes
- Use `pyproject.toml` for project metadata and dependencies (no `requirements.txt`)
- Keep `uv.lock` committed for reproducibility
- Environment variables for API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) — never hardcode secrets
- JSONL for data interchange between pipeline stages
- Versioned prompts in YAML/JSON format
