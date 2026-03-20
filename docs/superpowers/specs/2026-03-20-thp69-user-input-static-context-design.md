# THP-69 — User Input Agent Static Context Design

**Date:** 2026-03-20
**Task:** [THP-69](https://prosus-thymo-thesis.atlassian.net/browse/THP-69) — Define agent static knowledge context
**Epic:** [THP-68](https://prosus-thymo-thesis.atlassian.net/browse/THP-68) — User Input Agent

## Overview

THP-69 defines the static domain knowledge preloaded into the User Input agent's system prompt. This is the agent's reference frame — what it knows about the routing domain, what a complete problem looks like, and what metrics are available. It does not define validation rules (THP-70), gap logic (THP-108), or default values (THP-71).

**Output file:** `odysseus/agents/user_input_context.md` — a single markdown document embedded into the system prompt at THP-107.

**Format:** Structured markdown. No programmatic config, no Python dataclass. This is prose for an LLM to read.

**Target length:** ~500–800 words. The document is embedded in a system prompt (THP-107) alongside content from THP-70, THP-71, THP-72, THP-108, and THP-109. Keep it concise to leave token budget for the other components.

## Design Decisions

### Scope boundary

The static context is **high-level domain knowledge only**. Detailed field-by-field validation rules live in THP-70. Blocking/non-blocking gap logic lives in THP-108. Default values live in THP-71. This document provides the domain frame those other documents operate within.

**Note:** The THP-69 task description mentions "acceptable metric formats" and "minimum data volume thresholds" as deliverables. These have been intentionally moved: metric format syntax is prescriptive and belongs in THP-70; data volume thresholds are the Data Validation agent's responsibility (THP-73). This spec keeps THP-69 descriptive rather than prescriptive.

### Data validation is not owned here

Data validation (volume, format, quality) is handled by the **Data Validation agent** (THP-73). The User Input agent dispatches the Data Validation agent and uses its findings — it does not validate data itself. The static context establishes this relationship but does not define the Data Validation agent's interface.

### Routing domain

Scoped to **cost-quality routing**: routing requests to different LLM model tiers or tools that produce the same type of output but differ in cost and quality. This includes model-tier routing (e.g. Haiku/Sonnet/Opus) and tool routing (e.g. fast tool vs. high-quality tool for the same task).

### Metrics sourced from eval framework

The 4 metrics described in the context come directly from `odysseus/eval/metrics.py` and its `create_default_engine()` registry: `accuracy`, `f1`, `confusion`, and `cost_quality_reduction`. The context presents these in plain language so the agent can help the user choose and set thresholds.

## Document Structure

The static context document has 3 sections:

### Section 1: Domain & Role

Establishes the domain and the agent's responsibilities.

**Domain definition:**
- Cost-quality routing: the problem of routing requests to different LLM model tiers or tools that produce the same type of output but differ in cost and quality.
- The goal is to route each request to the cheapest option that still meets quality requirements.
- Examples: routing between GPT-4o/Claude Sonnet/Haiku based on query complexity; routing between a fast tool and a high-quality tool for the same task.

**Agent role — entry gate and orchestrator:**
- The agent is the pipeline's entry gate. It receives raw user input and ensures the problem is well-defined before downstream agents begin.
- It is also an orchestrator: it dispatches the Data Validation agent to assess dataset quality, and incorporates those findings into its report.
- The agent works iteratively with the user — if the problem definition or data is insufficient, it surfaces issues and requests clarification until everything is sufficient to proceed.

**Relationship with Data Validation agent:**
- The User Input agent dispatches the Data Validation agent and uses its findings to assess data sufficiency.
- Data volume, format, and quality checks are the Data Validation agent's responsibility, not the User Input agent's.
- The User Input agent incorporates data validation findings into its gap report and may surface data issues as blocking gaps requiring user action.

### Section 2: Complete Problem Specification

Describes what a fully-described routing problem looks like — the "gold standard" submission. This is descriptive, not prescriptive (THP-70 owns the rules).

**Required components:**
- **Routing dataset** — labeled examples in JSONL format. Each example contains an input (the request to be routed) and the expected routing decision. The context describes what good data looks like without specifying validation rules.
- **Problem description** — free-text explaining the routing context: what types of requests are being routed, what the available tiers/tools are, and what trade-offs matter most (e.g. cost vs. quality).
- **Target metrics** — at least one metric the user wants to optimize for, optionally with a target threshold.

**Optional components (listed by name, defaults defined in THP-71):**
- Evaluation threshold — overall pass/fail threshold for the pipeline exit check.
- Data split ratio — fraction of data reserved for holdout evaluation.
- Max iterations — maximum refinement loop rounds.

### Section 3: Available Metrics

Presents the 4 metrics from the eval framework in plain language. The agent uses this to guide users toward appropriate metric choices and threshold-setting.

**accuracy**
- *What it measures:* Fraction of requests routed to the correct tier/tool.
- *When to use:* Good starting point for any routing problem. Simple and interpretable.
- *Limitation:* Doesn't distinguish between types of misrouting (e.g. routing a complex query to a cheap model vs. routing a simple query to an expensive one).
- *Optimization target:* Yes. Example: `accuracy >= 0.85`.

**f1** (per-class + macro)
- *What it measures:* Precision, recall, and F1 per route class, plus macro-averaged F1.
- *When to use:* When route classes are imbalanced (e.g. 80% of requests are simple). Reveals whether the router performs well across all classes, not just the dominant one.
- *Optimization target:* Yes (typically `f1/macro`). Example: `f1/macro >= 0.80`.

**confusion**
- *What it measures:* Full confusion matrix showing which classes get misrouted where.
- *When to use:* Diagnostic — helps understand *how* the router fails. Not an optimization target.
- *Optimization target:* No. Diagnostic only.

**cost_quality_reduction**
- *What it measures:* Percentage change in cost and quality vs. a baseline (the highest-quality tier). Outputs 4 keys:
  - `cost_reduction` — % cost change vs. baseline (negative = savings, e.g. -0.30 means 30% cheaper)
  - `quality_reduction` — % quality change vs. baseline (negative = quality loss)
  - `oracle_cost_reduction` — theoretical best-case cost change (if every request were routed perfectly)
  - `oracle_quality_reduction` — theoretical best-case quality change
- *Sign convention:* Values are negative when the router saves cost or loses quality compared to always using the baseline. A `cost_reduction` of -0.30 means 30% cost savings. A `quality_reduction` of -0.05 means 5% quality loss.
- *When to use:* The core cost-quality trade-off metric. Essential for understanding whether the router is actually saving money without sacrificing too much quality. The oracle values show how close the router is to the theoretical optimum.
- *Parameters:* `baseline_class` — which route class to use as the all-traffic baseline. Auto-selects the highest-quality class if not specified. The user specifies this via the metric config params (e.g. `cost_quality_reduction` with `baseline_class: "opus"`); if omitted, auto-selection applies. Detailed metric format syntax is defined in THP-70.
- *Optimization target:* Yes. Example: `cost_reduction <= -0.30` (at least 30% cost savings).

## What This Document Does NOT Cover

- **Field validation rules** — owned by THP-70
- **Blocking vs. non-blocking gap classification** — owned by THP-108
- **Default values for optional fields** — owned by THP-71
- **Clarification request templates** — owned by THP-109
- **Data validation logic** — owned by THP-73 (Data Validation agent)
- **The system prompt itself** — owned by THP-107, which assembles this context with the above components

## Dependencies

- **No blockers** — can be implemented immediately.
- **THP-70 and THP-108** can be written in parallel, referencing this context.
- **THP-107** (final system prompt) is blocked on this being finalized.
- **Metrics definitions** are sourced from `odysseus/eval/metrics.py` — if metrics change, this document must be updated.
