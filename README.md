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

## MCP Server Deployment

This project is deployed as an MCP server, exposing the optimization pipeline as callable tools to any MCP-compatible client (Claude Desktop, Cursor, etc.).

### Installation

```bash
git clone https://github.com/your-org/project-odysseus.git
cd project-odysseus
pip install -e .
```

### Running the MCP Server

```bash
python -m odysseus.mcp
```

Or with `uvx` / `uv`:

```bash
uvx odysseus
```

### MCP Client Configuration

Add the server to your MCP client config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "odysseus": {
      "command": "python",
      "args": ["-m", "odysseus.mcp"],
      "env": {
        "ANTHROPIC_API_KEY": "<your-key>",
        "OPENAI_API_KEY": "<your-key>"
      }
    }
  }
}
```

### Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (required if using Claude backends) |
| `OPENAI_API_KEY` | OpenAI API key (required if using OpenAI-compatible backends) |
| `ODYSSEUS_DATA_DIR` | Directory for dataset files (default: `./data`) |
| `ODYSSEUS_OUTPUT_DIR` | Directory for run outputs and reports (default: `./outputs`) |
| `ODYSSEUS_PROMPTS_DIR` | Directory for versioned prompt files (default: `./prompts`) |

---

## Input Format

The pipeline expects:

- **Routing dataset** — JSONL file where each line contains a `query`, a `routing_decision` (ground truth), and optional `metadata`
- **Problem description** — natural language description of the routing task and what each tier/class means
- **Target metrics** — the metrics and thresholds that define success (e.g. accuracy ≥ 0.90, F1 ≥ 0.85 per class)

### Minimum Requirements

- At least one routing class with at least a handful of labelled examples per class
- A stated problem description (routing task context)
- At least one target metric

Non-blocking gaps (e.g. missing metadata fields, unbalanced classes) are flagged with assumed defaults and included in the data quality report.

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
