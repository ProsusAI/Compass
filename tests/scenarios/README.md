# Integration Test Scenarios

Test scenarios for the User Input agent, Data Validation agent, and Routing Analysis agent. Each `.md` file in this directory is a self-contained test scenario executed by Claude Code.

## Scenario index

### User Input Agent (01–12)

| # | Scenario | Focus |
|---|----------|-------|
| 01 | Complete Submission | All fields provided, single turn, status `proceed` |
| 02 | Missing Optional Defaults | Defaults applied for optional fields |
| 03 | Missing Required Clarification | Clarification loop for missing dataset |
| 04 | Multiple Blocking Gaps | Priority-ordered gap resolution |
| 05 | Mixed Blocking/Non-blocking | Blocking gap asked, non-blocking defaulted |
| 06 | Malformed Dataset | Data validation catches missing `expected` field, user fixes |
| 07 | Vague Problem Description | Agent refines vague problem via clarification |
| 08 | Ambiguous Tiers | Choose question type for ambiguous tier names |
| 09 | Contradictory Metrics | Invalid optimization target caught and corrected |
| 10 | Domain Mismatch | Non-routing problem detected |
| 11 | Persistent Clarification | Agent persists through unhelpful answers |
| 12 | Natural Language Answers | Extraction from unstructured conversational input |

### Data Validation Agent (13–18)

| # | Scenario | Focus |
|---|----------|-------|
| 13 | Clean Dataset | All checks pass on valid dataset |
| 14 | Imbalanced Tiers | Volume inadequacy and imbalance detection |
| 15 | Inconsistent Routes | Mixed model key sets across rows |
| 16 | Duplicate IDs | Unique ID constraint violation |
| 17 | Type Errors | Wrong types and null values detected |
| 18 | Insufficient Volume | Dataset too small for reliable evaluation |

### Input → Data Validation Integration (19–22)

| # | Scenario | Focus |
|---|----------|-------|
| 19 | Full Happy Path | Complete submission → validation, both succeed |
| 20 | Defaults Then Validate | Defaults applied → validation unaffected |
| 21 | Fix and Revalidate | Type errors detected → user fixes → revalidation passes |
| 22 | Nonexistent File | Missing dataset file handled gracefully |

### Routing Analysis Agent — Annotation Skills (23–28)

| # | Scenario | Focus |
|---|----------|-------|
| 23 | Classify Simple Queries | classify-example on 3 single-hop haiku queries, empty registry |
| 24 | Classify Complex Queries | classify-example on 3 multi-step opus queries, pre-populated registry |
| 25 | Rationale Clear-Cut | generate-routing-rationale on obvious haiku + opus examples, no ambiguity |
| 26 | Rationale Ambiguous | generate-routing-rationale on boundary sonnet examples, ambiguity expected |
| 27 | Classify Mid-Tier | classify-example on 2 sonnet queries, full registry, mid-complexity |
| 28 | Full Pipeline | Both skills sequentially on one example (classify → generate) |

**Note on routing analysis scenarios (23–28):** These scenarios test LLM-consumed annotation skills. The agent's classifications and rationales are not deterministic — exact vocabulary names and phrasing will vary across runs. Verification criteria focus on structural correctness, reasoning quality, and adherence to the skill procedure rather than exact string matches. The Verification Agent evaluates whether outputs are reasonable, and the transcript serves as a human-readable log for manual review.

### Routing Analysis Agent — Full Pipeline (29–30)

| # | Scenario | Focus |
|---|----------|-------|
| 29 | Startup & Input Validation | Agent reads context dict inputs, initializes registry, fails on missing input |
| 30 | Full Pipeline | All 4 phases end-to-end: classify → rationale → validate → split |

### Validation → Routing Analysis Integration (31–36)

| # | Scenario | Focus |
|---|----------|-------|
| 31 | Happy Path | Clean validation → all 4 routing analysis phases complete |
| 32 | Small Dataset + Degenerate Split | Volume warnings propagated, stratified_split on 5 rows |
| 33 | Imbalanced Tiers | 9:1 haiku:opus skew, split constraints on single-example tier |
| 34 | Two-Route Dataset | Binary routing (haiku + opus only), reduced exclusions and strata |
| 35 | Warnings Don't Block | Non-critical null_fields and route_in_routes warnings propagate without blocking |
| 36 | Borderline Examples | Ambiguous queries, potential semantic overlap → validation loop |

### Full Pipeline — Input → Validation → Routing Analysis (37–42)

| # | Scenario | Focus |
|---|----------|-------|
| 37 | Full Happy Path | All 3 stages succeed sequentially, complete output contract |
| 38 | Fix and Revalidate | Broken dataset → user fixes → re-validation → full analysis |
| 39 | Defaults Cascade | Minimal input, defaults propagate to split ratio in Phase 4 |
| 40 | Vague Description | Weak problem description → data-derived routing context |
| 41 | Re-Validation Changes Context | Dataset switch changes routing_context (2 routes → 3 routes) |
| 42 | Volume Warning Proceed | Tiny dataset (2 rows), user proceeds despite warning |

### Prompt Builder Agent (43–44)

| # | Scenario | Focus |
|---|----------|-------|
| 43 | Initial Compilation | Read routing analysis artifacts, detect provider, compile prompt, init search state |
| 44 | Optimization Loop | Receive directives, generate variants, evaluate, update Pareto front, detect stagnation |

### Prompt Builder ↔ Eval Runner Integration (45–47)

| # | Scenario | Focus |
|---|----------|-------|
| 45 | Initial Compilation with Live Eval | Compile v1 → run_eval → ScoreReport → record result → advance round |
| 46 | Multi-Round Optimization with Live Eval | 2 optimization rounds with real eval (mock-echo), Pareto tracking |
| 47 | Convergence and Holdout Evaluation | Stagnation → convergence → filter holdout → holdout eval |

### Full Pipeline — Input → Validation → Routing Analysis → Prompt Builder → Eval (48–50)

| # | Scenario | Focus |
|---|----------|-------|
| 48 | Full Pipeline Happy Path (Mock Eval) | All 5 stages with mock-echo, complete context flow |
| 49 | Full Pipeline (OpenAI) | All 5 stages with live OpenAI API, smoke test |
| 50 | Full Pipeline Two-Route | Binary routing (haiku + opus only) end-to-end |

## Prerequisites

- The Odysseus MCP server must be pre-configured and connected to Claude Code before running tests.
- Real LLM API calls are made — ensure `ANTHROPIC_API_KEY` is set.
- For scenario 49 only: `OPENAI_API_KEY` must be set (live OpenAI API smoke test).

## How to run a scenario

Tell Claude Code:

> Run the integration test in `tests/scenarios/01_complete_submission.md`

Claude Code will:

1. Read the scenario file and parse its sections.
2. Spin up a **User Simulator** sub-agent with the `## User Simulator` section as its instructions.
3. Spin up the appropriate **Agent** sub-agent:
   - **Scenarios 01–12, 19–21:** User Input Agent using the `odysseus_routing_input` MCP prompt, connected to the Odysseus MCP tools.
   - **Scenarios 13–18, 22:** Data Validation Agent using the `odysseus_data_validation` MCP prompt, connected to the Odysseus MCP tools.
   - **Scenarios 06, 19–21:** Both agents run in sequence — User Input Agent first, then Data Validation Agent on the submitted dataset.
   - **Scenarios 23–28:** Routing Analysis Agent — the agent reads SKILL.md files and follows the annotation procedures. No MCP tools are called; the agent produces structured text output evaluated by the Verification Agent.
   - **Scenarios 31–36:** Data Validation Agent first (via `odysseus_data_validation` prompt), then Routing Analysis Agent (via `odysseus_routing_analysis` prompt with skills and MCP tools). Context dict drives handoff between stages.
   - **Scenarios 37–42:** All three agents run in sequence — User Input Agent first (via `odysseus_routing_input` prompt), then Data Validation Agent (via `odysseus_data_validation` prompt), then Routing Analysis Agent (via `odysseus_routing_analysis` prompt with skills and MCP tools).
   - **Scenarios 43–44:** Prompt Builder Agent using the `odysseus_prompt_builder` MCP prompt, connected to the Odysseus MCP tools.
   - **Scenarios 45–47:** Prompt Builder Agent (via `odysseus_prompt_builder` prompt) + Eval Runner Agent (code-driven, invoked via `run_eval` tool). No separate agent spin-up for Eval Runner — it is called as a tool by the Prompt Builder.
   - **Scenarios 48–50:** All five stages in sequence — User Input Agent (via `odysseus_routing_input` prompt), then Data Validation Agent (via `odysseus_data_validation` prompt), then Routing Analysis Agent (via `odysseus_routing_analysis` prompt with skills and MCP tools), then Prompt Builder Agent (via `odysseus_prompt_builder` prompt) which calls Eval Runner via `run_eval` tool.
4. Get the opening message from the User Simulator.
5. Broker the conversation turn-by-turn:
   - Pass user message → active Agent
   - Receive agent response
   - If the agent calls the `submit_input_report` tool → input phase done
   - If the agent calls the `validate_dataset` tool → validation phase active
   - If response contains `# Validated Input Report` (fallback) → input phase done
   - Otherwise pass agent response → User Simulator → get next message → loop
6. Spin up a **Verification Agent** with the transcript, report(s), and criteria.
7. Report pass/fail results.

The primary conversation completion signal is the `submit_input_report` tool call for input scenarios and the completion of the data quality report for validation scenarios. The `# Validated Input Report` heading check is a fallback for robustness.

## Safety valve

Maximum **20 turns**. If the conversation has not produced its expected output within 20 turns, the test fails with "conversation did not converge."

## Verification Agent input format

The Verification Agent receives:

1. **Conversation transcript** — interleaved messages in this format:
   ```
   User: <message>
   Agent: <message>
   [Tool call: tool_name(args)]
   [Tool result: ...]
   User: <next message>
   ...
   ```
2. **Final output** — the validated input report Markdown and/or data quality report JSON, depending on the scenario.
3. **Verification criteria** — the `## Verification Criteria` checklist from the scenario file.

A scenario passes only if **all** verification criteria pass. The Verification Agent reports each criterion individually with pass/fail and reasoning, plus an overall verdict.

## Scenario file structure

Each scenario follows this template:

- `## Setup` — data files and preconditions
- `## Scenario Description` — plain language context
- `## User Simulator` — persona, knowledge, behavior, opening message
- `## Verification Criteria` — pass/fail checklist

## Data files

Test datasets live in `tests/scenarios/data/`:

| File | Description |
|------|-------------|
| `valid_dataset.jsonl` | 5 valid rows, 3 tiers (haiku/sonnet/opus) |
| `no_expected_field.jsonl` | 5 rows missing the `expected` field |
| `imbalanced_dataset.jsonl` | 10 rows, 9 haiku + 1 opus |
| `inconsistent_routes_dataset.jsonl` | Mixed model key sets (haiku/sonnet/opus vs gpt4/gpt35) |
| `duplicate_ids_dataset.jsonl` | 5 rows with duplicate IDs |
| `type_errors_dataset.jsonl` | Numeric id, numeric input, string costs, null values |
| `small_dataset.jsonl` | 2 rows, below minimum volume per tier |
| `rationale_test_dataset.jsonl` | 10 rows, 3 tiers (haiku/sonnet/opus), mixed complexity for annotation skill testing |
| `full_pipeline_dataset.jsonl` | 100 rows, 3 tiers (50 haiku/30 sonnet/20 opus), full pipeline integration testing |
| `two_route_dataset.jsonl` | 8 rows, 2 tiers (haiku/opus), binary routing |
| `warnings_dataset.jsonl` | 10 rows, 3 tiers, null values in non-required fields (triggers null_fields warning) |
| `borderline_dataset.jsonl` | 10 rows, 3 tiers, ambiguous tier-boundary queries for semantic overlap testing |
| `backends/mock-echo.yaml` | Mock echo backend profile for deterministic eval testing |
| `backends/openai.yaml` | OpenAI backend profile (gpt-5.2) for live API smoke test |

See the design spec at `docs/superpowers/specs/2026-03-23-thp-146-integration-tests-design.md` for full details.
