# Integration Test Scenarios

Full-pipeline integration test scenarios for Project Odysseus. Each `.md` file in this directory is a self-contained test scenario executed by Claude Code. All scenarios test the complete optimization pipeline (or as much of it as the flow allows — early-exit scenarios stop intentionally at the relevant stage).

## Scenario index

### Happy Paths (01–04)

| # | Scenario | Dataset | Backend | Focus |
|---|----------|---------|---------|-------|
| 01 | Happy Path — Mock Eval | `full_pipeline_dataset.jsonl` | mock-echo | All 6 stages, deterministic eval, all fields provided upfront |
| 02 | Happy Path — OpenAI | `full_pipeline_dataset.jsonl` | openai (gpt-5.2) | All 6 stages with live OpenAI API smoke test |
| 03 | Happy Path — Binary Routing | `two_route_dataset.jsonl` | mock-echo | 2-tier routing (haiku/opus), no sonnet |
| 04 | Happy Path — All Defaults | `rationale_test_dataset.jsonl` | default | Only dataset + description provided; all optional fields default |

### Input Stage Issues (05–07)

| # | Scenario | Dataset | Focus |
|---|----------|---------|-------|
| 05 | Input Clarification Then Success | `valid_dataset.jsonl` | Missing required dataset path; user provides it; pipeline continues |
| 06 | Vague Description Refined | `rationale_test_dataset.jsonl` | Vague problem description refined via clarification; pipeline continues |
| 07 | Domain Mismatch Rejected | `valid_dataset.jsonl` | Sentiment classification rejected at Stage 1; no downstream stages fire |

### Data Validation Issues (08–10)

| # | Scenario | Dataset | Focus |
|---|----------|---------|-------|
| 08 | Malformed Data — Fix and Revalidate | `type_errors_dataset.jsonl` → `valid_dataset.jsonl` | Type errors detected; user provides corrected dataset; pipeline continues |
| 09 | Data Warnings — Proceed | `imbalanced_dataset.jsonl` | Imbalance warnings (non-blocking); user acknowledges; pipeline continues |
| 10 | Missing `expected` Field | `no_expected_field.jsonl` → `valid_dataset.jsonl` | Blocking schema error; user provides corrected dataset; pipeline continues |

### Backend Setup Variations (11–12)

| # | Scenario | Backend | Focus |
|---|----------|---------|-------|
| 11 | New Backend Creation | `openai-mini` (created during run) | User creates new OpenAI backend in Stage 3; spec gathered; YAML written |
| 12 | Existing Backend Selection | `anthropic` | User selects existing backend; no new YAML; pipeline continues |

### Refinement Loop Edge Cases (13–14)

| # | Scenario | Fixtures | Focus |
|---|----------|----------|-------|
| 13 | Review — Regression Guard | `review/def456/` | Candidate improves accuracy but drops rare-class recall; `severity="block"`, `decision="refine"` |
| 14 | Review — Convergence Exit | `review/ghi789/` | Oracle ratios >0.9, diversity collapsing; `action="exit"` with dominance threshold reason |

### Full End-to-End (15)

| # | Scenario | Dataset | Focus |
|---|----------|---------|-------|
| 15 | Full End-to-End with Final Report | `full_pipeline_dataset.jsonl` | All 6 stages verified in detail: holdout filtering, holdout eval, briefing, report content |

### SMS-EMOA Algorithm (16–17)

| # | Scenario | Dataset | Focus |
|---|----------|---------|-------|
| 16 | SMS-EMOA — Warm-Up Then Iterations | `sms_emoa_toy_dataset.jsonl` | Full SMS-EMOA loop: warm-up (μ=4 seeds → batch eval → advance_step_tool), two steady-state iterations, budget termination |
| 17 | Stage 4 — Build-Phase Dispatch Guard | pre-configured fixture | Verifies `build_dispatched.json` prevents duplicate sub-agent dispatch; `DISPATCH_REQUIRED: false` while in-flight, recovers after deletion |

## Prerequisites

- The Odysseus MCP server must be pre-configured and connected to Claude Code before running tests.
- Real LLM API calls are made — ensure `ANTHROPIC_API_KEY` is set.
- For scenario 02 only: `OPENAI_API_KEY` must be set (live OpenAI API smoke test).

## How to run a scenario

Tell Claude Code:

> Run the integration test in `tests/scenarios/01_happy_path_mock_eval.md`

Claude Code will:

1. Read the scenario file and parse its sections.
2. Spin up a **User Simulator** sub-agent with the `## User Simulator` section as its instructions.
3. Spin up the pipeline orchestrator sub-agents in sequence, beginning with the `odysseus_routing_input` MCP prompt and advancing through each stage. Early-exit scenarios (e.g., 07) stop at the stage where the rejection occurs.
4. Get the opening message from the User Simulator.
5. Broker the conversation turn-by-turn:
   - Pass user message → active agent
   - Receive agent response
   - If the agent calls `submit_input_report` → input phase done, advance to Stage 2
   - If the agent calls `save_final_report` → pipeline complete
   - Otherwise pass agent response → User Simulator → get next message → loop
6. Spin up a **Verification Agent** with the full transcript and the `## Verification Criteria` checklist.
7. Report pass/fail results.

All scenarios test the complete pipeline unless the scenario description explicitly states the pipeline stops early (domain mismatch, unrecoverable error). In those cases, verification criteria include checks that downstream stages were NOT triggered.

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
2. **Final output** — report files and tool results produced by the pipeline (input report, routing context, score reports, final report path).
3. **Verification criteria** — the `## Verification Criteria` checklist from the scenario file.

A scenario passes only if **all** verification criteria pass. The Verification Agent reports each criterion individually with pass/fail and reasoning, plus an overall verdict.

## Scenario file structure

Each scenario follows this template:

- `## Setup` — datasets, system prompts, MCP tools, and backend profiles used
- `## Scenario Description` — plain language context explaining what the scenario tests and why
- `## User Simulator` — persona, knowledge, behavior rules, and exact opening message
- `## Verification Criteria` — pass/fail checklist organized by pipeline stage

## Data files

Test datasets live in `tests/scenarios/data/`:

| File | Description |
|------|-------------|
| `valid_dataset.jsonl` | 5 valid rows, 3 tiers (haiku/sonnet/opus) |
| `full_pipeline_dataset.jsonl` | 100 rows, 3 tiers (50 haiku/30 sonnet/20 opus), full pipeline testing |
| `two_route_dataset.jsonl` | 8 rows, 2 tiers (haiku/opus), binary routing |
| `rationale_test_dataset.jsonl` | 10 rows, 3 tiers, mixed complexity |
| `no_expected_field.jsonl` | 5 rows missing the `expected` field |
| `imbalanced_dataset.jsonl` | 10 rows, 9 haiku + 1 opus |
| `type_errors_dataset.jsonl` | Numeric IDs, numeric inputs, string costs, null values |
| `small_dataset.jsonl` | 2 rows, below minimum volume per tier |
| `duplicate_ids_dataset.jsonl` | 5 rows with duplicate IDs |
| `inconsistent_routes_dataset.jsonl` | Mixed model key sets across rows |
| `warnings_dataset.jsonl` | 10 rows, null values in non-required fields |
| `borderline_dataset.jsonl` | 10 rows with ambiguous tier-boundary queries |
| `backends/mock-echo.yaml` | Deterministic mock backend for eval testing |
| `backends/openai.yaml` | OpenAI backend profile (gpt-5.2) |
| `backends/anthropic.yaml` | Anthropic backend profile (claude-haiku) |
| `review/abc123/` | Review Agent fixtures: basic review (search state, score reports, mutation log) |
| `review/def456/` | Review Agent fixtures: regression guard (v3 drops opus recall) |
| `review/ghi789/` | Review Agent fixtures: loop exit (round 4, convergence) |
| `sms_emoa_toy_dataset.jsonl` | 20 rows, 3 tiers (haiku/sonnet/opus), SMS-EMOA loop testing |
| `review/generate_fixtures.py` | Script to regenerate Review Agent fixture data (hill-climb + SMS-EMOA variants) |
