# Project Compass  
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**Improved Agentic Routing Optimizer** — a multi-agent pipeline that iteratively refines few-shot routing prompts using an automated evaluation loop. Deployed as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server.

Given a routing dataset, a problem description, and target metrics, Compass validates the data, sets up the evaluation backend, and iteratively builds and refines a prompt through an automated eval-review-revise loop — producing a production-ready routing prompt with full performance transparency.

---

## Setup

Compass runs as an MCP server. Pick the setup that matches your client.

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- API keys for your LLM backend(s):

```bash
# Add to your shell profile (~/.zshrc, ~/.bashrc)
export ANTHROPIC_API_KEY="sk-ant-..."   # For Claude backends
export OPENAI_API_KEY="sk-..."          # For OpenAI backends
```

### Claude Code

One command:

```bash
claude mcp add compass -- uvx --from git+https://github.com/thymofieten-prosus/Compass compass
```

The server inherits your shell environment, so exported API keys work automatically.

To pass keys explicitly instead:

```bash
claude mcp add compass \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e OPENAI_API_KEY=sk-... \
  -- uvx --from git+https://github.com/thymofieten-prosus/Compass compass
```

Verify with `claude mcp list`.

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "compass": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/thymofieten-prosus/Compass", "compass"]
    }
  }
}
```

### Cursor / Windsurf

Add to `.cursor/mcp.json` (or equivalent):

```json
{
  "mcpServers": {
    "compass": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/thymofieten-prosus/Compass", "compass"],
      "env": {
        "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
        "OPENAI_API_KEY": "${OPENAI_API_KEY}"
      }
    }
  }
}
```

Cursor does not inherit your shell environment — you must forward API keys via the `env` block. The `${VAR}` syntax references variables from your shell profile. Alternatively, set them in **Cursor Settings > Environment Variables**.

### Any MCP-compatible client

Add to your client's MCP config (usually `.mcp.json`):

```json
{
  "mcpServers": {
    "compass": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/thymofieten-prosus/Compass", "compass"]
    }
  }
}
```

### Project initialization

After connecting the server, run `compass init` in your project directory:

```bash
compass init
```

This creates:
- `backends/` — LLM backend configs (a `mock-echo.yaml` starter is included)
- `prompts/` — versioned routing prompts
- `outputs/` — run outputs, reports, and config (`run_config.yaml` starter included)

The command is idempotent and will not overwrite existing files.

### Development setup

```bash
git clone https://github.com/thymofieten-prosus/Compass.git
cd Compass
uv sync
```

For local development, create a `.mcp.json` in the project root that runs the server from source:

```json
{
  "mcpServers": {
    "compass": {
      "command": "uv",
      "args": ["run", "python", "-m", "compass.mcp"]
    }
  }
}
```

---

## Usage

After setup, start the pipeline by asking your MCP-connected assistant:

> Optimize a routing prompt

Compass walks through six stages. Each stage runs as a sub-agent — you interact with it conversationally, and it calls the appropriate MCP tools behind the scenes. Here's what happens at each stage and what you need to provide.

### Stage 1: Input Validation

The pipeline starts by collecting and validating your input.

**What you provide:**
- **Routing dataset** — a JSONL, CSV, or JSON file where each row contains a query and a ground-truth routing decision
- **Problem description** — a natural language explanation of the routing task (what each tier/class means, when to route where)
- **Target metrics** — the metrics and thresholds that define success (e.g. "accuracy >= 0.90", "F1 >= 0.85 per class")

The agent checks for blocking gaps (missing dataset, no problem description) and flags non-blocking issues (class imbalance, missing cost data) with assumed defaults. If anything is blocking, it asks for clarification before proceeding.

### Stage 2: Data Validation

Automatically detects your dataset format, maps fields to the canonical schema, and runs quality checks.

**What you may be asked:**
- **Field mapping confirmation** — if column names don't match the expected schema, the agent proposes a mapping and asks you to confirm

The stage produces a data quality report covering schema conformance, label distribution, volume adequacy, and query diversity. It also builds a routing context document that downstream stages use.

### Stage 3: Backend Setup

Configures the LLM backend used for evaluation.

**What you provide:**
- **Backend selection** — which LLM provider and model to use for evaluation (e.g. "openai/gpt-4o-mini", "anthropic/claude-haiku")

The agent looks up default pricing and writes a backend config file. A starter `mock-echo.yaml` config is included from `compass init` for testing.

### Stage 4: Refinement Loop

The core refinement loop. Starts with seed example selection, compiles an initial prompt, then iteratively evaluates and improves it.

**What happens (no input needed):**
1. **Seed selection** — the Review Agent performs a cold-start pass to select representative seed examples from the dev split
2. **Initial prompt (v1)** — the Prompt Builder compiles the first versioned prompt using the analysis output, rationale cards, and selected seed examples
3. **Evaluation** — the eval engine runs the prompt against the dev dataset and produces a score report (accuracy, per-class F1, latency, cost)
4. **Review** — the Review Agent analyses results, decides whether to accept or revert, and generates ranked improvement directives
5. **Revision** — the Prompt Builder revises the prompt based on the Review Agent's directives
6. Steps 3–5 repeat until the loop converges (no further improvement) or hits the round limit

The loop tracks a Pareto front of candidates (quality vs. cost) and detects stagnation to avoid wasting iterations.

### Stage 5: Holdout Validation

Tests the best prompt from the eval loop on the held-out data.

**What happens (no input needed):**
- Filters few-shot examples out of the holdout set to prevent data contamination
- Runs a final evaluation on unseen data
- Produces a holdout score report with per-class breakdowns

### Stage 6: Final Report

Synthesises all pipeline artifacts into a structured evaluation report.

**What you get:**
- **Final versioned prompt** — the production-ready routing prompt (YAML/JSON)
- **Evaluation report** — executive summary, data profile, iteration history, holdout performance, confidence assessment, deployment guidance, and reproducibility block

---

## Datasets

The [`datasets/`](datasets/) directory contains supplementary datasets accompanying the Compass paper appendix (model routing and image-generation routing benchmarks), licensed separately under CC-BY-4.0. See [`datasets/README.md`](datasets/README.md) for the data card.

---

## Testing

### Unit tests

```bash
uv run pytest
```

### MCP integration tests (scenario runbooks)

Integration tests are Markdown runbooks in `tests/scenarios/`. Each scenario defines a simulated user conversation that exercises one or more pipeline agents end-to-end through the MCP server.

**Prerequisites:**
- The Compass MCP server must be connected to your AI coding assistant (see [Setup](#setup))
- At least one LLM API key must be set (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`) — scenarios make real LLM API calls

**Running a scenario:**

Open your MCP-connected AI assistant (Claude Code, Cursor, or any MCP-compatible client) in the project directory and say:

> Run the integration test in `tests/scenarios/01_complete_submission.md`

The assistant reads the scenario file, spins up a User Simulator sub-agent to play the user role, brokers a multi-turn conversation with the agent under test, then runs a Verification Agent to check the outcome against the scenario's pass/fail criteria. Each scenario has a 20-turn safety limit.

**Running multiple scenarios:**

> Run all integration tests in `tests/scenarios/` from 01 to 12

**Scenario coverage:**

| Range | Focus | Count |
|-------|-------|-------|
| 01-04 | Full pipeline happy paths | 4 |
| 05-07 | Pipeline with input issues | 3 |
| 08-10 | Pipeline with data validation issues | 3 |
| 11-12 | Pipeline with backend setup variations | 2 |
| 13-14 | Pipeline with refinement loop edge cases | 2 |
| 15 | Full pipeline end-to-end with final report | 1 |

See `tests/scenarios/README.md` for the full protocol, scenario file format, and how to add new scenarios.

---

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (required for Claude backends) |
| `OPENAI_API_KEY` | OpenAI API key (required for OpenAI-compatible backends) |

---

## License

Copyright © 2026 MIH AI B.V.

Project Compass is licensed under the [Apache License, Version 2.0](LICENSE). See
the [`NOTICE`](NOTICE) file for third-party attributions.

### Dependencies

Runtime dependencies are retrieved at install time and are not redistributed in
this repository. Their licenses:

| Dependency | License |
|---|---|
| `mcp`, `anthropic`, `pyyaml`, `pydantic` | MIT |
| `openai`, `boto3`, `aiohttp` | Apache-2.0 (`aiohttp`: Apache-2.0 AND MIT) |
| `matplotlib` | Matplotlib License (BSD/PSF-style, permissive) |
| `certifi`, `tqdm` | MPL-2.0 (weak/file-level copyleft; used unmodified) `tqdm`: MPL-2.0 AND MIT |

A full SPDX SBOM is generated by CI ([`.github/workflows/open-source-ally.yml`](.github/workflows/open-source-ally.yml)).

## Contributing & Security

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for contribution terms (including IP
assignment) and [`SECURITY.md`](SECURITY.md) for vulnerability reporting.
