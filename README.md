# Project Odysseus

**Improved Agentic Routing Optimizer** — a multi-agent pipeline that iteratively refines few-shot routing prompts using an automated evaluation loop. Deployed as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server.

Given a routing dataset, a problem description, and target metrics, Odysseus validates the data, extracts routing patterns, builds an eval harness, and iteratively refines a prompt through an automated eval-review-revise loop — producing a production-ready routing prompt with full performance transparency.

---

## Setup

Odysseus runs as an MCP server. Pick the setup that matches your client.

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
claude mcp add odysseus -- uvx --from git+https://github.com/thymofieten-prosus/project-odysseus odysseus
```

The server inherits your shell environment, so exported API keys work automatically.

To pass keys explicitly instead:

```bash
claude mcp add odysseus \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e OPENAI_API_KEY=sk-... \
  -- uvx --from git+https://github.com/thymofieten-prosus/project-odysseus odysseus
```

Verify with `claude mcp list`.

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "odysseus": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/thymofieten-prosus/project-odysseus", "odysseus"]
    }
  }
}
```

### Cursor / Windsurf

Add to `.cursor/mcp.json` (or equivalent):

```json
{
  "mcpServers": {
    "odysseus": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/thymofieten-prosus/project-odysseus", "odysseus"],
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
    "odysseus": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/thymofieten-prosus/project-odysseus", "odysseus"]
    }
  }
}
```

### Project initialization

After connecting the server, run `odysseus init` in your project directory:

```bash
odysseus init
```

This creates:
- `backends/` — LLM backend configs (a `mock-echo.yaml` starter is included)
- `prompts/` — versioned routing prompts
- `outputs/` — run outputs, reports, and config (`run_config.yaml` starter included)

The command is idempotent and will not overwrite existing files.

### Development setup

```bash
git clone https://github.com/thymofieten-prosus/project-odysseus.git
cd project-odysseus
uv sync
```

For local development, the repo includes a `.mcp.json` that runs the server from source:

```json
{
  "mcpServers": {
    "odysseus": {
      "command": "uv",
      "args": ["run", "python", "-m", "odysseus.mcp"]
    }
  }
}
```

---

## How It Works

The pipeline runs through these stages:

1. **Validate input** — checks for blocking gaps, requests clarification if needed
2. **Validate data** — assesses schema, label distribution, volume, diversity
3. **Analyse routing patterns** — extracts decision boundaries and reasoning from the dataset
4. **Build eval + initial prompt** (parallel) — creates the eval harness and a first-draft prompt
5. **Refinement loop** — iteratively evaluates, reviews, and revises the prompt
6. **Holdout validation** — tests the best prompt on unseen data
7. **Final report** — produces a structured evaluation report

```
User Input (data + problem description + target metrics)
    |
    v
Triage ---- Blocking gaps? --> Clarification Request --> (back to User Input)
    |
    | No blocking gaps
    v
Data Validation Agent
    |  data quality report + collection suggestions
    v
Analysis Agent
    |  routing patterns + decision reasoning document
    v
+---------------------------+
|  Parallel Build (synced)  |
|                           |
|  Eval Framework Agent     |  -- builds eval code + test harness
|  Prompt Agent (v0)        |  -- constructs initial few-shot prompt
+---------------------------+
    |
    v
+------------------- Refinement Loop -------------------+
|                                                       |
|  Run Eval Agent --> score report                      |
|       |                                               |
|       v                                               |
|  Review Agent --> accept/revert + actionable insights |
|       |                                               |
|       +- Regression? --> Revert to checkpoint         |
|       |                       +-> Prompt Agent (new)  |
|       |                                               |
|       +- Improvement? --> Exit Check                  |
|                               |                       |
|                               +- Continue -> Prompt   |
|                               +- Exit --------------> |
+-------------------------------------------------------+
    |
    v
Holdout Validation
    |
    v
Final Reporting Agent
    |
    v
Final Prompt + Evaluation Report
```

### Agents

| Agent | Role |
|---|---|
| **User Input Agent** | Validates submitted input; classifies gaps as blocking or non-blocking; requests clarification if needed |
| **Data Validation Agent** | Assesses data quality (schema, label distribution, volume, diversity); produces prioritized data collection suggestions |
| **Analysis Agent** | Extracts routing patterns, decision boundaries, and the latent reasoning behind the dataset |
| **Eval Framework Agent** | Builds the async Python evaluation engine, backend registry, prompt manager, dataset manager, metrics engine, and run controller |
| **Prompt Agent** | Constructs and iteratively refines the versioned few-shot routing prompt using analysis output and Review Agent critique |
| **Run Eval Agent** | Executes the eval harness against the current prompt; produces a structured score report with per-example breakdowns |
| **Review Agent** | Analyses score history and current prompt to decide accept/revert, generate ranked improvement insights, and signal loop exit |
| **Final Reporting Agent** | Synthesises all pipeline artifacts into a structured report covering performance, confidence, deployment guidance, and reproducibility |

---

## Input Format

The pipeline expects:

- **Routing dataset** — JSONL file where each line contains a `query`, a `routing_decision` (ground truth), and per-model cost/quality data
- **Problem description** — natural language description of the routing task and what each tier/class means
- **Target metrics** — the metrics and thresholds that define success (e.g. accuracy >= 0.90, F1 >= 0.85 per class)

### Minimum requirements

- At least one routing class with labelled examples per class
- A stated problem description
- At least one target metric

Non-blocking gaps (e.g. unbalanced classes) are flagged with assumed defaults and included in the data quality report.

---

## Output

The pipeline produces:

1. **Final versioned prompt** — YAML/JSON file containing the system prompt, few-shot examples, and decision heuristics
2. **Evaluation report** — structured report covering:
   - Executive summary
   - Data profile
   - Routing logic summary
   - Iteration history (full convergence trajectory)
   - Holdout performance with per-class breakdowns and failure analysis
   - Confidence assessment
   - Deployment guidance (failure modes, monitoring, data collection priorities)
   - Reproducibility block (backend, prompt version, data split, metric config)

---

## Evaluation Engine

The eval framework is a Python-based async engine built on `asyncio` + `aiohttp`:

- **Backend Registry** — swap between OpenAI-compatible, Anthropic, or custom JSON endpoints via config
- **Prompt Manager** — versioned YAML/JSON prompts hot-reloaded from a watched directory
- **Dataset Manager** — streaming JSONL iterator with configurable dev/holdout split
- **Concurrency Engine** — `asyncio.Semaphore` per backend; token-bucket rate limiting; exponential backoff on 429/5xx
- **Metrics Engine** — pluggable metric registry; standard metrics (accuracy, F1 per class, latency p50/p95/p99, token cost) plus custom callables
- **Results Collector** — writes JSONL results on arrival; crash-safe; versioned score reports with diffs
- **Run Controller** — single `run(backend, prompt_version, data_source, data_split, metrics_config)` interface

---

## Testing

### Unit tests

```bash
uv run pytest
```

### MCP integration tests (scenario runbooks)

Integration tests are Markdown runbooks in `tests/scenarios/`. Each scenario defines a simulated user conversation that exercises one or more pipeline agents end-to-end through the MCP server.

**Prerequisites:**
- The Odysseus MCP server must be connected to your AI coding assistant (see [Setup](#setup))
- `ANTHROPIC_API_KEY` must be set (scenarios make real LLM API calls)
- For scenario 49 only: `OPENAI_API_KEY` must be set

**Running a scenario:**

Open your MCP-connected AI assistant (Claude Code, Cursor, or any MCP-compatible client) in the project directory and say:

> Run the integration test in `tests/scenarios/01_complete_submission.md`

The assistant reads the scenario file, spins up a User Simulator sub-agent to play the user role, brokers a multi-turn conversation with the agent under test, then runs a Verification Agent to check the outcome against the scenario's pass/fail criteria. Each scenario has a 20-turn safety limit.

**Running multiple scenarios:**

> Run all integration tests in `tests/scenarios/` from 01 to 12

**Scenario coverage:**

| Range | Stage | Count |
|-------|-------|-------|
| 01-12 | User Input Agent | 12 |
| 13-18 | Data Validation Agent | 6 |
| 19-22 | Input + Data Validation integration | 4 |
| 23-30 | Routing Analysis Agent | 8 |
| 31-36 | Validation + Routing Analysis integration | 6 |
| 37-42 | Input + Validation + Routing Analysis integration | 6 |
| 43-44 | Prompt Builder Agent | 2 |
| 45-47 | Prompt Builder + Eval Runner integration | 3 |
| 48-50 | Full pipeline (all 5 stages) | 3 |
| 51-53 | Review Agent | 3 |
| 54-55 | Backend Setup Agent | 2 |

See `tests/scenarios/README.md` for the full protocol, scenario file format, and how to add new scenarios.

---

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (required for Claude backends) |
| `OPENAI_API_KEY` | OpenAI API key (required for OpenAI-compatible backends) |
