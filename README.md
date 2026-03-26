# Project Odysseus

**Improved Agentic Routing Optimizer** — a multi-agent pipeline that takes a routing problem as input, iteratively refines a few-shot routing prompt using an automated evaluation loop, and produces a validated final prompt and evaluation report.

Deployed as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server, enabling any MCP-compatible AI client to invoke the full optimization pipeline as a tool.

---

## What It Does

Given a dataset of historical routing decisions, a problem description, and target metrics, the pipeline:

1. Validates the input data and checks for blocking gaps
2. Analyses the routing dataset to extract decision patterns and reasoning
3. Builds an evaluation harness and an initial few-shot prompt in parallel
4. Iteratively refines the prompt through an automated eval-review-revise loop
5. Validates the best prompt on a held-out test set
6. Delivers a final prompt and structured evaluation report

The output is a production-ready routing prompt with full transparency on how it was derived, its performance characteristics, and its known failure modes.

---

## Pipeline Architecture

```
User Input (data + problem description + target metrics)
    │
    ▼
Triage ──── Blocking gaps? ──► Clarification Request ──► (back to User Input)
    │
    │ No blocking gaps
    ▼
Data Validation Agent
    │  data quality report + collection suggestions
    ▼
Analysis Agent
    │  routing patterns + decision reasoning document
    ▼
┌───────────────────────────┐
│  Parallel Build (synced)  │
│                           │
│  Eval Framework Agent     │  ── builds eval code + test harness
│  Prompt Agent (v0)        │  ── constructs initial few-shot prompt
└───────────────────────────┘
    │
    ▼
┌─────────────────── Refinement Loop ───────────────────────┐
│                                                           │
│  Run Eval Agent ──► score report                          │
│       │                                                   │
│       ▼                                                   │
│  Review Agent ──► accept/revert + actionable insights     │
│       │                                                   │
│       ├─ Regression? ──► Revert to checkpoint             │
│       │                       └──► Prompt Agent (new view)│
│       │                                                   │
│       └─ Improvement? ──► Exit Check                      │
│                               │                           │
│                               ├─ Continue ──► Prompt Agent│
│                               └─ Exit ──────────────────► │
└───────────────────────────────────────────────────────────┘
    │
    ▼
Holdout Validation
    │
    ▼
Final Reporting Agent
    │
    ▼
Final Prompt + Evaluation Report
```

---

## Agents

| Agent | Role |
|---|---|
| **User Input Agent** | Validates submitted input; classifies gaps as blocking or non-blocking; requests clarification if needed |
| **Data Validation Agent** | Assesses data quality (schema, label distribution, volume, diversity); produces prioritized data collection suggestions |
| **Analysis Agent** | Extracts routing patterns, decision boundaries, and the latent reasoning behind the dataset; produces the knowledge base for prompt and eval |
| **Eval Framework Agent** | Builds the async Python evaluation engine, backend registry, prompt manager, dataset manager, metrics engine, and run controller |
| **Prompt Agent** | Constructs and iteratively refines the versioned few-shot routing prompt using analysis output, heuristics, and Review Agent critique |
| **Run Eval Agent** | Executes the eval harness against the current prompt on the dev set; produces a structured score report with per-example breakdowns and version diffs |
| **Review Agent** | Analyses score history and current prompt to decide accept/revert, generate ranked improvement insights, and signal loop continuation or exit |
| **Final Reporting Agent** | Synthesises all pipeline artifacts into an eight-section structured report covering executive summary, data profile, routing logic, iteration history, performance scores, confidence assessment, deployment guidance, and reproducibility block |

---

## Evaluation Engine

The eval framework (THP-75) is a Python-based async engine built on `asyncio` + `aiohttp`:

- **Backend Registry** — swap between OpenAI-compatible, Anthropic, or custom JSON endpoints via config; one backend per run
- **Prompt Manager** — versioned YAML/JSON prompts hot-reloaded from a watched directory; full version traceability
- **Dataset Manager** — streaming JSONL iterator with configurable dev/holdout split; holdout sealed during the refinement loop
- **Concurrency Engine** — `asyncio.Semaphore` per backend; token-bucket rate limiting; exponential backoff on 429/5xx
- **Metrics Engine** — pluggable metric registry; standard metrics (accuracy, F1 per class, latency p50/p95/p99, token cost) plus custom Python callables injected at runtime
- **Results Collector** — writes JSONL results on arrival; crash-safe; produces versioned score reports with diffs
- **Run Controller** — single `run(backend, prompt_version, data_source, data_split, metrics_config)` interface

### Run Configuration

```yaml
backend: <name from backend registry>
prompt_version: latest          # or specific version tag
data_source: path/to/data.jsonl
data_split: dev                 # dev | holdout
metrics:
  - name: accuracy
  - name: f1_per_class
  - name: latency_p95
  - name: token_cost
concurrency:
  max_concurrent_requests: 20
rate_limits:
  requests_per_minute: 500
  tokens_per_minute: 100000
retry:
  max_attempts: 3
  backoff_factor: 2.0
output:
  results_path: outputs/results.jsonl
  report_path: outputs/report.json
```

---

## Architecture

The project follows a **thin-adapter** pattern:

- **Agent classes** (`odysseus/agents/`) contain all business logic — config loading, dependency wiring, error handling, and pipeline orchestration. Each agent is an async Python class that can be tested and used independently.
- **MCP server** (`odysseus/mcp.py`) is a thin adapter layer that translates between MCP tool parameters and agent context dicts. It delegates to agent classes and serializes their results — no business logic lives here.

This means Odysseus works as both:
1. **An MCP plugin** for any MCP-compatible client (Claude Code, Claude Desktop, Cursor, etc.)
2. **A Python library** where agent classes can be imported and called directly

```
MCP Client (Claude Code / Cursor / ...)
    │
    ▼
odysseus/mcp.py          ← thin adapter: params → context dict → agent → JSON
    │
    ▼
odysseus/agents/*.py     ← all business logic lives here
    │
    ▼
odysseus/eval/           ← evaluation engine, metrics, backends
```

## Quick Start

### Install from GitHub (recommended for users)

Add Odysseus to your project's `.mcp.json`:

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

Then scaffold the required project directories:

```bash
odysseus init
```

This creates `outputs/`, `prompts/`, and `backends/` with starter files. Add your backend configs, routing prompts, and you're ready to go.

### Install from source (for development)

```bash
git clone https://github.com/thymofieten-prosus/project-odysseus.git
cd project-odysseus
uv sync
```

### API Keys

Odysseus needs API keys for whichever LLM backend you use. Set them as environment variables — never commit them to config files.

```bash
# Add to your shell profile (~/.zshrc, ~/.bashrc)
export ANTHROPIC_API_KEY="sk-ant-..."   # For Claude backends
export OPENAI_API_KEY="sk-..."          # For OpenAI backends
```

The MCP server reads these at runtime via the `api_key_env` field in backend profiles (`backends/*.yaml`). No keys are stored in project files.

### One-command install for Claude Code

```bash
claude mcp add odysseus -- uvx --from git+https://github.com/thymofieten-prosus/project-odysseus odysseus
```

The server inherits your shell environment variables, so if you've exported your API keys as shown above, no extra configuration is needed.

If you prefer not to set global environment variables, you can pass keys directly:

```bash
claude mcp add odysseus \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e OPENAI_API_KEY=sk-... \
  -- uvx --from git+https://github.com/thymofieten-prosus/project-odysseus odysseus
```

To verify it's connected:

```bash
claude mcp list
```

Then use the `odysseus_routing_input` prompt to start a routing optimization conversation — or just say "help me with this routing problem" and the assistant will suggest it.

### Other MCP clients

Add the server to any MCP-compatible client's config file. API keys are picked up from your shell environment — do not add them to these config files.

**Claude Desktop** (`claude_desktop_config.json`):

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

**Cursor / Windsurf** (`.cursor/mcp.json` or equivalent):

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

Cursor does not inherit your shell environment, so you need to explicitly forward your API keys via the `env` block. The `${VAR}` syntax references variables from your shell — make sure they are exported in your shell profile before launching Cursor. Alternatively, you can set the keys directly in Cursor's settings under **Settings > Environment Variables**.

**For local development** (`.mcp.json` in repo root — already included):

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

### Project initialization

After installing, run `odysseus init` in your project directory to scaffold the required directories:

```bash
odysseus init
```

This creates:
- `backends/` — LLM backend configs (a `mock-echo.yaml` starter is included)
- `prompts/` — versioned routing prompts
- `outputs/` — run outputs, reports, and config (`run_config.yaml` starter included)

The command is idempotent and will not overwrite existing files.

### Running the MCP server standalone

```bash
uv run python -m odysseus.mcp
```

### Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (required if using Claude backends) |
| `OPENAI_API_KEY` | OpenAI API key (required if using OpenAI-compatible backends) |
| `ODYSSEUS_PROJECT_DIR` | Base directory for all file I/O — `outputs/`, `prompts/`, `backends/` resolve relative to this (default: current working directory) |

---

## Input Format

The pipeline expects:

- **Routing dataset** — JSONL file where each line contains a `query`, a `routing_decision` (ground truth), and per-model cost/quality data
- **Problem description** — natural language description of the routing task and what each tier/class means
- **Target metrics** — the metrics and thresholds that define success (e.g. accuracy ≥ 0.90, F1 ≥ 0.85 per class)

### Minimum Requirements

- At least one routing class with at least a handful of labelled examples per class
- A stated problem description (routing task context)
- At least one target metric

Non-blocking gaps (e.g. unbalanced classes) are flagged with assumed defaults and included in the data quality report.

---

## Testing

### Unit tests

```bash
uv run pytest
```

### MCP integration tests (scenario runbooks)

Agent integration tests live in `tests/scenarios/`. Each scenario is a Markdown runbook executed by a Claude Code instance with the Odysseus MCP server connected.

To run a scenario, tell Claude Code:

> Run the integration test in `tests/scenarios/01_complete_submission.md`

Claude Code will spin up a User Simulator sub-agent and the agent under test, broker a multi-turn conversation, and verify the outcome against the scenario's checklist.

| Range | Agent | Count |
|-------|-------|-------|
| 01–12 | User Input Agent | 12 scenarios |
| 13–18 | Data Validation Agent | 6 scenarios |
| 19–22 | Input → Data Validation integration | 4 scenarios |

See `tests/scenarios/README.md` for the full protocol, safety valves, and how to add new scenarios.

**Adding scenarios for a new agent:** Create numbered `.md` files in `tests/scenarios/` following the standard four-section template (`Setup`, `Scenario Description`, `User Simulator`, `Verification Criteria`). Add test datasets as JSONL files in `tests/scenarios/data/`. Update the README index.

---

## Output

The pipeline produces:

1. **Final versioned prompt** — a YAML/JSON file containing the system prompt, few-shot examples, and explicit decision heuristics
2. **Evaluation report** — structured JSON/Markdown covering:
   - Executive summary
   - Data profile
   - Routing logic summary (human-readable)
   - Iteration history table (full convergence trajectory)
   - Holdout performance scores with per-class breakdowns and failure case analysis
   - Confidence assessment
   - Deployment guidance (known failure modes, monitoring recommendations, data collection priorities)
   - Reproducibility block (backend, prompt version, data split, metric config)

---
