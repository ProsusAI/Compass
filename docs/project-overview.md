# Agentic Routing Optimizer — Project Overview

> **Status:** All pipeline agents implemented and operational.
> **Last updated:** 2026-03-31
>
> For technical architecture detail, see [docs/architecture.md](architecture.md).

---

## 1. What This Is

The **Agentic Routing Optimizer** is a multi-agent AI pipeline that takes a routing problem as input and automatically produces an optimized routing prompt, validated against held-out data, together with a full evaluation report.

The system is deployed as an **MCP (Model Context Protocol) server** so it can be invoked as a tool by an LLM-based orchestrator or IDE agent.

---

## 2. The Problem It Solves

Routing — deciding which model, service, or handler should process a given query — is a common and surprisingly hard prompt engineering problem. The quality of the routing prompt depends on:

- Selecting representative few-shot examples that cover the decision boundary
- Iterating against real metrics rather than vibes
- Validating against held-out data to confirm generalization

Doing this manually is slow, inconsistent, and hard to validate. This pipeline automates the full cycle: **validate → setup → build → evaluate → refine → validate → report**.

---

## 3. Pipeline Architecture

The pipeline is structured as six sequential stages, with an inner refinement loop. The diagram below maps to the Excalidraw design file (`Agentic-Workflow-Prompt-Routing.excalidraw`).

```
┌─────────────────────────────────────────────────────────┐
│ Stage 1: User Input                                      │
│  Collect routing dataset, problem description, metrics  │
│  Check for blocking gaps; request clarification if any  │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│ Stage 2: Data Validation                                 │
│  Schema conformance, label distribution, volume checks  │
│  Produces routing context document + validated splits   │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│ Stage 3: Backend Setup                                   │
│  Configure LLM backend for evaluation                   │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│ Stage 4: Refinement Loop                                 │
│                                                          │
│  ┌─► Prompt Builder ──► Eval Runner ──► Review Agent ──►┤
│  │                                          │            │
│  │                              [Met threshold / max?]  │
│  │                              │  No ──► Prompt Builder┘
│  └──────────────────────────────┘
│                              Yes
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│ Stage 5: Holdout Validation                              │
│  Run final eval on held-out data                        │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│ Stage 6: Final Report                                    │
│  Synthesise all artifacts → Final Prompt + Eval Report  │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Agents

### 4.1 User Input Agent (THP-68)

| | |
|---|---|
| **Goal** | Determine whether the user's submission is sufficient to proceed; classify any gaps as blocking or non-blocking |
| **Input** | Raw user submission: routing dataset, problem description, target metrics |
| **Output** | Validated input package + gap report |
| **Blocking gaps** | → Clarification request back to user |
| **Non-blocking gaps** | → Flagged with assumed defaults, pipeline proceeds |

---

### 4.2 Data Validation Agent (THP-73)

| | |
|---|---|
| **Goal** | Assess structural data quality and advise on what additional data would most improve the output |
| **Input** | Raw routing dataset + problem description |
| **Output** | Data quality report (schema consistency, label distribution, volume adequacy, missing signal types) + prioritized data collection suggestions |

This agent works together with the User Input Agent during the triage phase — its data quality report is an input to the validated input package that the two agents jointly produce before the pipeline proceeds downstream.

---

### 4.3 Eval Framework (THP-75)

The evaluation engine is fully implemented in `odysseus/eval/`. It is a production-grade async Python engine:

| Component | Description |
|---|---|
| **Backend Registry** | Named backends (OpenAI-compatible, Anthropic, custom) selectable per run via config |
| **Prompt Manager** | Versioned prompts as YAML/JSON with hot-reload from watched directory |
| **Dataset Manager** | Streaming JSONL iterator; dev/holdout split applied on load; holdout sealed until exit |
| **Concurrency Engine** | `asyncio` + `aiohttp`; token-bucket rate limiting; exponential backoff on 4xx/5xx |
| **Metrics Engine** | Dynamic metric registry; custom metrics injected as Python callables per run config |
| **Results Collector** | Writes per-result JSONL immediately; aggregates + diffs against prior run on completion |
| **Run Controller** | Single-call orchestrator: `run(backend, prompt_version, data_source, split, metrics_config)` |

Completed tasks: THP-87 through THP-93, THP-113, THP-114, THP-115, THP-116.

---

### 4.4 Eval Runner Agent (THP-76)

| | |
|---|---|
| **Goal** | Execute the eval harness against the current prompt version and produce a structured score report |
| **Input** | Current versioned prompt + dev set (holdout never accessed during the loop) |
| **Output** | Score report: aggregate metrics, per-example breakdowns, diff vs previous version |
| **MCP interface** | `run_eval` tool wrapping the Run Controller |

The agent calls `run_eval` as an MCP tool and returns the score report to the Review Agent. It never has access to the holdout partition during refinement iterations.

---

### 4.5 Prompt Builder Agent (THP-77)

| | |
|---|---|
| **Goal** | Construct and iteratively refine a routing prompt using few-shot examples and decision heuristics |
| **First run input** | Routing context document + routing dataset (for few-shot selection) |
| **Subsequent run input** | Current prompt version + Review Agent insights + iteration number |
| **Output** | Versioned prompt (v0, v1, v2…) with few-shot examples, heuristics, and changelog entry |

Produces the initial v0 baseline and then refines the prompt on each loop iteration in Stage 4.

---

### 4.6 Review Agent (THP-78)

| | |
|---|---|
| **Goal** | Determine if the current version is an improvement; identify failure patterns; decide loop continuation |
| **Input** | Current prompt, score report, full score history across all iterations |
| **Output** | (1) Accept or revert decision + justification; (2) Ranked actionable insights; (3) Loop continuation signal (refine / exit) |
| **Loop signals** | `refine` → back to Prompt Builder; `exit` → forward to Holdout Validation |
| **Exit conditions** | Metric threshold met OR max iterations reached OR diminishing returns detected |

This agent is the central intelligence of the refinement loop. It has access to the full score history to anchor its critique.

---

### 4.7 Final Reporting Agent (THP-79)

| | |
|---|---|
| **Goal** | Synthesise all pipeline artifacts into a structured report for both technical and non-technical audiences |
| **Input** | All versioned prompts + changelogs, raw results + score reports, loop decision history, data quality report, original problem description, holdout eval results |
| **Output** | Eight-section report (see below) |

**Report sections:**
1. Executive summary (non-technical)
2. Data profile (result quality vs input data quality)
3. Routing logic summary (what the final prompt actually does, in plain language)
4. Iteration history (full convergence trajectory table)
5. Final holdout performance (per-class breakdowns + failure analysis)
6. Confidence assessment (explicit reasoning on how much to trust the scores)
7. Deployment guidance (failure modes, monitoring, future data collection)
8. Reproducibility block (backend, prompt version, data split, metric config used)

---

## 5. Data Flow

```
User
 └── routing dataset (JSONL)
 └── problem description
 └── target metrics
      │
      ├──────────────────────────────────┐
      ▼                                  ▼
[User Input Agent] ◄──────► [Data Validation Agent]
      │       jointly produce the        │
      │       validated input package    │
      │           +  data quality report │
      └──────────────────┬───────────────┘
                         │
                         ▼
              [Prompt Builder Agent]
              v0 prompt
                         │
            ┌────────────▼────────────────┐
            │      REFINEMENT LOOP       │
            │  Run Eval → Review → Refine│
            └─────────────────────────────┘
                          │
            ┌─────────────▼──────────────┐
            │   Holdout Validation       │
            └─────────────────────────────┘
                          │
                          ▼
                [Final Report Agent]
                Final Prompt + Eval Report
```

---

## 6. Key Design Decisions

### Holdout Isolation
The dataset is split into `dev` and `holdout` at load time. During all refinement loop iterations, only the dev split is accessible. The holdout is sealed behind an explicit `load_holdout()` call and is only triggered after the loop exits. This prevents metric leakage and ensures the final reported score reflects true generalization.

### Versioned Prompts
Every prompt mutation is stored as a versioned YAML/JSON file with a changelog entry. This gives the Review Agent a full history to reason over and makes the final report reproducible.

### Dynamic Metrics
The metric set is not hardcoded. The Review Agent produces metric specifications as structured config between iterations; the Metrics Engine reads this config and assembles the active metric set for the next run. User-stated goals translate into measurable criteria without code changes.

### Regression Guard
Before accepting a new prompt version, the Review Agent checks whether metrics have improved relative to the previous best checkpoint. If they have regressed, the version is discarded and the Prompt Builder is instructed to "refine from a different viewpoint" rather than continuing in the same direction.

### MCP Deployment
The system exposes a `run_eval` MCP tool that wraps the Run Controller, enabling the Eval Runner Agent to trigger evaluation runs as tool calls. The full pipeline is also deployable as an MCP server via `python -m odysseus.mcp`.

---

## 7. Current Status

| Epic | Title | Status |
|---|---|---|
| THP-68 | User Input Agent | Done |
| THP-73 | Data Validation Agent | Done |
| THP-75 | Eval Framework Code | Done |
| THP-76 | Eval Runner Agent | Done |
| THP-77 | Prompt Builder Agent | Done |
| THP-78 | Review Agent | Done |
| THP-79 | Final Reporting Agent | Done |

---

## 8. Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Package manager | `uv` |
| Async runtime | `asyncio` + `aiohttp` |
| Deployment | MCP server (`python -m odysseus.mcp`) |
| Testing | `pytest` + `pytest-asyncio` |
| Linting | `ruff` |
| Type checking | `pyright` |
| Data format | JSONL |
| Prompt storage | YAML / JSON (versioned) |

---

## 9. Repository Structure

```
odysseus/
  mcp/                # MCP server package
    server.py         # FastMCP app, shared helpers, main()
    *_tools.py        # Stage-specific tool modules
    resources.py      # MCP resource definitions
    prompts.py        # MCP prompt definitions
  agents/             # Agent implementations
    prompts/          # Agent system prompts
  eval/               # Evaluation engine (complete)
    backends/         # Backend registry + LiteLLM client
    controller.py     # Run Controller
    dataset.py        # Dataset Manager
    metrics.py        # Metrics Engine
    collector.py      # Results Collector
    rate_limiter.py   # Token-bucket rate limiter
    pricing.py        # Token cost estimation
    protocols.py      # Shared type protocols
    models.py         # Data models
    docs/             # Eval engine documentation
  prompts/            # Prompt Manager
data/                 # Dataset files (JSONL)
outputs/              # Run outputs and reports
prompts/              # Routing prompt store (versioned prompts)
configs/              # Run configuration YAML
tests/                # Full test suite
docs/                 # Design specs and plans
```
