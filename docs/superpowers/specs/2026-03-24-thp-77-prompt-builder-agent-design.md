# THP-77: Prompt Builder Agent Design

**Type:** Design Spec
**Status:** Draft
**Parent Epic:** [THP-77: Prompt-Program Compiler and Search Optimizer](2026-03-24-thp-77-prompt-program-compiler-search-optimizer.md)
**Date:** 2026-03-24

---

## Goal

Design the Prompt Builder Agent — an LLM-driven agent that (1) compiles routing prompts using model-specific best practices grounded in routing analysis artifacts, and (2) runs a tournament-selection search loop with lightweight Pareto tracking to iteratively improve prompts without getting stuck in local optima.

---

## Prerequisites

**Fix `FilePromptManager` path in `EvalRunnerAgent`.** The eval runner at `odysseus/agents/eval_runner.py:125` initializes `FilePromptManager(prompts_dir=Path(__file__).resolve().parent / "prompts")`, which resolves to `odysseus/agents/prompts/` (agent system prompts). It should point to the project root `prompts/` directory (the versioned routing prompt store). This must be fixed before the Prompt Builder can write prompts that `run_eval` can find.

---

## Architecture

The Prompt Builder Agent follows the established Odysseus pattern: an **LLM-driven agent** (system prompt in `odysseus/agents/prompts/prompt_builder_system.md`) that calls **code-driven MCP tools** for deterministic operations (search state management, Pareto tracking, convergence detection, holdout filtering).

### Pipeline Position

```
Routing Analysis Agent
    | (dev_rationale_card_set_path, dev_jsonl_path, vocabulary_registry_path,
    |  split_report_path, routing_context, holdout_jsonl_path,
    |  holdout_rationale_card_set_path)
    v
Prompt Builder Agent
    | (prompt_version)          ^ (review directives from Review Agent)
    v                           |
Eval Runner Agent           Review Agent
    | (eval_score_report)       ^
    +---------------------------+
```

### Round 1 — Initial Compilation

1. Read all inputs from context dict.
2. Detect the target model's provider (Anthropic/OpenAI) from the backend profile.
3. Read `best-practices` resource + provider-specific conventions resource.
4. Call `init_search_state(backend, max_rounds=50, stagnation_limit=3, convergence_limit=5)`.
5. Select few-shot examples from the holdout set (using holdout rationale cards for coverage).
6. Compile the initial prompt using routing artifacts, best practices, and model conventions.
7. Write to `prompts/v1.txt`.
8. Call `register_candidate(search_state_id, "v1", parent=None)`.
9. Call `run_eval(prompt_version="v1", data_source=dev_jsonl_path, backend=backend)`.
10. Extract the primary quality metric from `ScoreReport.metrics` (see Primary Metric Resolution below) and cost from `ScoreReport.summary.total_cost`. Call `record_eval_result(search_state_id, "v1", quality_score, cost)`.
11. Call `advance_round(search_state_id)`.
12. Set `prompt_version = "v1"` in context -> triggers Review Agent.

### Round 2+ — Optimization Loop

1. Receive Review Agent's block-level edit directives + ScoreReport.
2. Call `get_search_state(search_state_id)` to see current front, mutation mode, round number.
3. **Select 2 parents** from the Pareto front (if front has only 1, use it twice with different mutation strategies).
4. **Generate children** — per parent, apply 1-2 mutations:
   - If `mutation_mode = "targeted"`: follow Review Agent's directives (paraphrase, reorder, tighten rules, swap examples).
   - If `mutation_mode = "exploratory"`: larger structural changes (add/delete sections, different example sets, different prompting style).
5. Write each child as `prompts/vN.txt`, call `register_candidate` for each.
6. **Evaluate** all new candidates via `run_eval`.
7. Call `record_eval_result` for each candidate.
8. Call `advance_round` — returns whether converged, new stagnation count, recommended mutation mode.
9. If `converged = true` -> select the best candidate from the front (highest quality score, ties broken by lowest cost), set `prompt_version` in context, done.
10. If not converged -> set `prompt_version` to the best new candidate, trigger Review Agent for next round.

---

## Prompt Format

Prompts are **flat text files** with a consistent internal structure using section headers. No separate structured YAML representation — the structure lives in the prompt's formatting, making prompts human-readable and human-editable.

### Section Convention

```
# Routing Objective
<high-level instruction: what the router does, domain context>

# Routes
<route definitions with descriptions, ordered by routing dimensions>

# Decision Rules
<ordered rule clauses - core routing logic>
<edge-case handling>
<tie-breaker rules>

# Examples
<few-shot examples selected from holdout rationale cards>

# Output Format
<expected output schema/format>
```

The section headers (`# Routing Objective`, `# Routes`, etc.) are the "blocks" that mutation operators target. The compiler identifies, replaces, reorders, or extends them.

### Model-Specific Compilation

The compiler adapts the prompt style based on the detected provider:

| Aspect | Claude (Anthropic/Bedrock) | OpenAI |
|---|---|---|
| Structure | XML tags for sections (`<routes>`, `<rules>`) | Markdown headers, numbered lists |
| Examples | `<example>` tags with `<input>` / `<output>` | `User:` / `Assistant:` turn format |
| Output format | Prefilled assistant turn for structured output | JSON mode / function calling instruction |
| Emphasis | `<important>` tags for critical rules | Bold/caps for emphasis, system message for rules |

The provider is detected from the backend profile via `BackendRegistry`. Bedrock inherits Claude conventions.

### Few-Shot Example Selection

The compiler selects examples from the **holdout set** (not the dev set) to prevent data contamination. Selection criteria:

- Coverage across intent patterns, complexity structures, and ambiguity tags
- Prioritize boundary examples (cards with ambiguity tags or route exclusions)
- The IDs of selected examples are tracked as `few_shot_example_ids` for holdout filtering before final eval

---

## Best Practices Resources

Three MCP resources provide the compiler with prompt engineering context:

| Resource | Content | When Read |
|---|---|---|
| `odysseus://agents/prompt-builder/best-practices` | General prompt engineering principles for routing prompts (chain-of-thought, role framing, ordering effects, negative vs positive framing) | Every compilation |
| `odysseus://agents/prompt-builder/conventions-claude` | Claude conventions + Anthropic cookbook patterns (XML tags, prefills, structured output, few-shot formatting) | When provider is Anthropic or Bedrock |
| `odysseus://agents/prompt-builder/conventions-openai` | OpenAI conventions + OpenAI cookbook patterns (JSON mode, system messages, function calling, few-shot formatting) | When provider is OpenAI |

Convention files combine official best practices distilled from provider documentation with concrete cookbook patterns relevant to structured classification/routing tasks.

---

## Primary Metric Resolution

`ScoreReport.metrics` is a generic `dict[str, float]` — the keys depend on the eval config. The Prompt Builder resolves the primary quality metric as follows:

1. Use the **first metric** listed in the eval config's `metrics` list. The eval config is user-defined, and the first metric is treated as the primary optimization target.
2. The `init_search_state` tool accepts an optional `primary_metric_name` parameter. If provided, it overrides the first-metric convention.
3. Cost is always `ScoreReport.summary.total_cost`.

The `record_eval_result` tool accepts `quality_score: float` and `cost: float` — the agent extracts these from the ScoreReport before calling the tool.

---

## Search Strategy

**Tournament selection with escalating mutation radius.**

Each round, 2 parents are selected from the Pareto front. Each parent produces 1-2 child variants (3-5 total candidates per round). All candidates are evaluated on the full dev set. Non-dominated candidates advance to the Pareto front.

### Mutation Operators

Applied based on the Review Agent's block-level edit directives:

| Operator | Targeted | Exploratory | Description |
|---|---|---|---|
| `paraphrase` | Yes | Yes | Reword a section without changing semantics |
| `reorder` | Yes | Yes | Change section or rule ordering |
| `tighten` | Yes | Yes | Increase precision of rules or schema |
| `swap_examples` | Yes | Yes | Replace few-shot subset |
| `add` | No | Yes | Insert a new block |
| `delete` | No | Yes | Remove an existing block |
| `restyle` | No | Yes | Change prompting style (e.g., XML -> markdown) |

### Pareto Front

Two objectives: **quality_score** (higher is better) and **cost** (lower is better).

Dominance: candidate A dominates B if `A.quality_score >= B.quality_score AND A.cost <= B.cost` with at least one strict inequality.

**Deduplication:** Candidates with identical `(quality_score, cost)` pairs are treated as duplicates — only the first one added to the front is retained. This prevents front inflation without information gain.

The front is the set of all non-dominated, deduplicated candidates across all rounds.

### Convergence & Termination

| Parameter | Default | Description |
|---|---|---|
| `max_rounds` | 50 | Hard safety cap |
| `stagnation_limit` | 3 | Rounds without Pareto improvement before switching to exploratory mutations |
| `convergence_limit` | 5 | Rounds without Pareto improvement to declare convergence |

**Escalation:** After `stagnation_limit` rounds without a new Pareto point, `mutation_mode` switches from `"targeted"` to `"exploratory"`. If `convergence_limit` is reached without improvement (including the exploratory rounds), the loop declares convergence.

**User target thresholds** from the input report are used as focus signals (prioritize mutations that close the gap to the target) but do not trigger termination.

**Final selection:** Highest quality score on the Pareto front, breaking ties by lowest cost.

---

## Data Contamination Prevention

Few-shot examples are drawn from the **holdout set**, not the dev set. This ensures:

- The full dev set is used for every evaluation — all candidates scored on identical data
- No contamination between prompt examples and eval examples
- Scores are directly comparable across candidates

Before the Final Reporting Agent runs holdout evaluation, the `filter_holdout_dataset` tool removes any examples used as few-shots, producing a clean holdout eval set.

### Flow

1. **Prompt Builder** reads `holdout_jsonl_path` + `holdout_rationale_card_set_path` for few-shot selection.
2. **Dev eval** runs on the full, unmodified dev set.
3. **Prompt Builder** writes `few_shot_example_ids` to context.
4. **Final Reporting Agent** calls `filter_holdout_dataset` to get a clean holdout set for final evaluation.

---

## MCP Surface

### New Prompt

| Name | Purpose | Backing File |
|---|---|---|
| `odysseus_prompt_builder` | Activate the Prompt Builder agent | `odysseus/agents/prompts/prompt_builder_system.md` |

### New Resources

| URI | Purpose | Backing File |
|---|---|---|
| `odysseus://agents/prompt-builder/best-practices` | General prompt engineering principles | `odysseus/agents/prompt_builder_best_practices.md` |
| `odysseus://agents/prompt-builder/conventions-claude` | Claude conventions + cookbook patterns | `odysseus/agents/prompt_builder_conventions_claude.md` |
| `odysseus://agents/prompt-builder/conventions-openai` | OpenAI conventions + cookbook patterns | `odysseus/agents/prompt_builder_conventions_openai.md` |

### New Tools

| Name | Purpose | Input | Output |
|---|---|---|---|
| `init_search_state` | Initialize search state for optimization run | `backend`, `max_rounds`, `stagnation_limit`, `convergence_limit`, `primary_metric_name` (optional) | Search state ID + initial state JSON |
| `register_candidate` | Register a new prompt candidate | `search_state_id`, `prompt_version`, `parent_version` (optional) | Candidate ID |
| `record_eval_result` | Record eval results for Pareto tracking | `search_state_id`, `prompt_version`, `quality_score`, `cost` | Updated Pareto front status |
| `advance_round` | Close round, update front, check convergence | `search_state_id` | Round summary: new Pareto points, stagnation count, converged, mutation mode |
| `get_search_state` | Read current search state | `search_state_id` | Full search state JSON |
| `filter_holdout_dataset` | Remove few-shot examples from holdout before final eval (used by Final Reporting Agent, not Prompt Builder) | `holdout_jsonl_path`, `exclude_ids` | Filtered holdout JSONL path |

### Existing Tools Used

| Name | Purpose | Notes |
|---|---|---|
| `run_eval` | Evaluate a prompt version against the dev set | Uses the default `config_path` (`outputs/run_config.yaml`). The Prompt Builder assumes a valid eval config exists; config setup is the user's responsibility or handled by an earlier pipeline stage. |

### Context Dict Changes

**New keys:**

| Key | Type | Set By | Consumed By |
|---|---|---|---|
| `few_shot_example_ids` | `list[str]` | Prompt Builder Agent | `filter_holdout_dataset` / Final Reporting Agent |

**Modified access:**

| Key | Change |
|---|---|
| `holdout_jsonl_path` | Now also read by Prompt Builder (few-shot selection only) |
| `holdout_rationale_card_set_path` | Now also read by Prompt Builder (few-shot selection only) |

---

## Search State Model

```python
SearchState:
    search_state_id: str
    backend: str
    primary_metric_name: str             # name of the quality metric from eval config
    round: int
    pareto_front: list[Candidate]        # non-dominated (quality_score, cost)
    round_history: list[RoundSummary]    # per-round: candidates, evals, front changes
    stagnation_count: int                # rounds since last Pareto improvement
    stagnation_limit: int                # threshold for exploratory switch (default: 3)
    convergence_limit: int               # threshold for convergence (default: 5)
    max_rounds: int                      # hard cap (default: 50)
    mutation_mode: "targeted" | "exploratory"
    converged: bool

Candidate:
    prompt_version: str
    parent_version: str | None
    quality_score: float
    cost: float
    round_introduced: int
    dominated: bool

RoundSummary:
    round: int
    candidates_evaluated: list[str]      # prompt versions
    new_pareto_points: int
    front_size: int
    mutation_mode: str
    stagnation_count: int
```

Search state is persisted to `outputs/<search_state_id>/search_state.json` and checkpointed after each round.

---

## File Layout

### New Files

| File | Purpose |
|---|---|
| `odysseus/agents/prompts/prompt_builder_system.md` | Agent system prompt |
| `odysseus/agents/prompt_builder_best_practices.md` | General prompt engineering principles resource |
| `odysseus/agents/prompt_builder_conventions_claude.md` | Claude conventions + cookbook patterns resource |
| `odysseus/agents/prompt_builder_conventions_openai.md` | OpenAI conventions + cookbook patterns resource |
| `odysseus/agents/prompt_builder_search.py` | Search state models + Pareto dominance logic |
| `odysseus/agents/prompt_builder_search_ops.py` | Stateful operations: init, register, record, advance, get — persists to `outputs/` |
| `odysseus/agents/prompt_builder_holdout_filter.py` | Holdout dataset filtering |
| `tests/test_prompt_builder_search.py` | Unit tests for Pareto dominance, stagnation, convergence |
| `tests/test_prompt_builder_holdout_filter.py` | Unit tests for holdout filtering |

### Modified Files

| File | Change |
|---|---|
| `odysseus/mcp.py` | Add new tools, prompt, and resources |
| `odysseus/agents/eval_runner.py` | Fix `FilePromptManager` path to point to project root `prompts/` (prerequisite) |
| `docs/architecture.md` | Update agent registry, context dict, MCP surface tables (including `holdout_*` consumer columns) |
