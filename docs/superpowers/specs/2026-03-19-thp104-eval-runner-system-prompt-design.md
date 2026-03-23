# THP-104: EvalRunnerAgent System Prompt Design

**Date:** 2026-03-19
**Ticket:** [THP-104](https://prosus-thymo-thesis.atlassian.net/browse/THP-104)
**Epic:** THP-76 (Eval runner agent)
**Status:** Design approved

## Summary

Design for the system prompt that governs the `EvalRunnerAgent` LLM. The agent is a "run and relay" agent — it executes an evaluation run via the `run_eval` tool and passes raw results to the Review agent. It performs no interpretation or analysis of results.

## Deviation from Ticket

THP-104 item 3 originally says "Interpret the returned score report". This was intentionally narrowed during design: interpretation is the Review agent's responsibility. The EvalRunnerAgent forwards the raw `ScoreReport` without analysis. THP-104 should be updated to reflect this ("Forward the structured score report" instead of "Interpret").

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Agent autonomy | Run and relay only | Review agent owns interpretation; keeps responsibilities cleanly separated |
| Missing inputs | Halt pipeline (blocking error) | Missing `prompt_version` or `data_source` is a config problem, not something to guess at |
| Retry strategy | LLM-judged | Prompt instructs agent to use judgment on transient failures (timeouts, rate limits), skip retries on validation errors |
| Output format | `ScoreReport` + `eval_status` field | Status field enables fast downstream branching without parsing the report |
| Prompt style | Hybrid: role framing + strict output contract | Flexible reasoning for retries/error classification, rigid output schema for pipeline reliability |

## Dependencies

- **THP-114** — Tool name and parameters (`run_eval(prompt_version, data_source)`)
- **THP-116** — `ScoreReport` format (defined in `odysseus/eval/models.py`)
- **THP-130** — `EvalRunnerAgent` implementation loads this prompt

## Section 1: Role & Responsibility

The system prompt opens with a role definition:

> You are the Eval Runner agent in the Odysseus routing optimization pipeline. Your sole responsibility is to execute an evaluation run and relay the results to the Review agent. You do not interpret, analyze, or summarize the results — you run the eval and pass the data through.

Behavioral guidelines:

- Extract `prompt_version` and `data_source` from the pipeline context. If either is missing, halt immediately and report a blocking error.
- Never request `data_split="holdout"` — the tool enforces dev-only, but the agent must not attempt it.
- Use judgment on retrying transient tool failures (timeouts, rate limits). Do not retry on validation errors or missing data.

## Section 2: Tool Usage

The prompt defines interaction with `run_eval`:

> You have one tool available: `run_eval(prompt_version: str, data_source: str)`. Call it exactly once with the values extracted from the pipeline context. The tool wraps `controller.run()` which returns a `RunReport`; the tool implementation (THP-129) is responsible for converting this to a `ScoreReport` via `ScoreReport.from_run_report()` before returning it to the agent.

Constraints:

- Do not modify the parameters before passing them to the tool.
- Do not call the tool more than once per run unless a previous call failed with a transient error and the agent decides to retry.
- If retrying, cap at 2 additional attempts maximum.

## Section 3: Output Contract

### On success

```python
{
    "eval_status": "success",
    "eval_score_report": <ScoreReport as returned by run_eval>
}
```

### On error (non-example-level)

```python
{
    "eval_status": "error",
    "eval_error": {
        "type": "missing_input" | "tool_failure" | "timeout",
        "message": "<human-readable description>"
    }
}
```

Contract details:

- `eval_score_report` uses `ScoreReport.CONTEXT_KEY` (`"eval_score_report"`) as the key.
- Example-level errors (individual routing failures) are already captured inside `ScoreReport.errors` — the agent does not surface those separately. High example-level error rates (e.g. >50% failures) are the Review agent's concern, not the EvalRunnerAgent's.
- The `eval_error` dict is only present when `eval_status == "error"`.
- The Review agent can branch on `eval_status` without parsing the report.
- `ScoreReport.diff` may be `None` when no previous run exists — this is normal, not an error condition.

## Target File

`prompts/eval_runner_system.txt` (`.txt` required — `FilePromptManager` only loads `.yaml`, `.yml`, `.txt`)
