# Scenario 17: Stage 4 — Build-Phase Dispatch Guard (In-Flight Detection)

## Setup

Create a fresh run directory for a pipeline in Stage 4 `warmup_build` phase with a stalled sub-agent. Use the `mock_echo` backend.

### Directory structure

```
outputs/<run_id>/
  input/input_report.md
  validation/transformed.jsonl
  validation/data_quality_report.json
  validation/routing_context.json
  analysis/dev.jsonl
  analysis/holdout.jsonl
  search/directive_history.json
  search/child_variants.json  # non-empty, triggers warmup_build phase
  search/search_state.json    # algorithm_state.warm_up_complete=false, iteration=0
  search/build_dispatched.json  # written to simulate a stalled sub-agent
backends/mock.yaml
```

`search_state.json`:
```json
{
  "search_state_id": "<run_id>",
  "backend": "mock-echo",
  "loop_phase": "build",
  "converged": false,
  "algorithm": "sms_emoa",
  "algorithm_state": {
    "iteration": 0,
    "warm_up_complete": false,
    "mu": 4
  },
  "elite_set": [],
  "active_evals": []
}
```

`build_dispatched.json`:
```json
{"phase": "warmup_build", "dispatched_at": "2026-04-21T10:00:00.000Z", "iteration": 0}
```

`child_variants.json`:
```json
[{"parent_version": "base", "hypothesis": "test hypothesis", "directives": [], "variant_id": null}]
```

## Scenario Description

This scenario verifies that when a build sub-agent is already dispatched and in flight (indicated by `build_dispatched.json`), calling `get_pipeline_status` does NOT produce a `DISPATCH_REQUIRED: true` response. Instead it should return `DISPATCH_REQUIRED: false` with an `active_dispatch` field indicating the orchestrator should WAIT.

The scenario also verifies that once the build marker is cleared (simulating the sub-agent completing its work by calling `advance_step_tool`), `get_pipeline_status` returns to normal `DISPATCH_REQUIRED: true` behavior.

## User Simulator

The User Simulator sub-agent should:

1. Call `get_pipeline_status(run_id=<run_id>)` on the pre-configured state.
2. Report what it observes in the response: specifically whether `DISPATCH_REQUIRED` is `true` or `false`, and whether an `active_dispatch` field is present.
3. If `active_dispatch` is present, note its contents (phase, iteration, action).
4. Manually delete `search/build_dispatched.json` (simulating the sub-agent completing).
5. Call `get_pipeline_status(run_id=<run_id>)` again.
6. Report the new response.

The User Simulator should NOT call `start_stage` or any stage tools — this is a read-only verification scenario.

## Verification Criteria

**PASS** if all of the following are true:

1. **First `get_pipeline_status` call** (with `build_dispatched.json` present):
   - Response contains `"DISPATCH_REQUIRED": false` (not `true`).
   - Response contains an `"active_dispatch"` field with:
     - `"phase": "warmup_build"`
     - `"iteration": 0`
     - `"action": "WAIT"`
   - Response `next_action` text contains "WAIT" (case-insensitive).
   - Response does NOT contain a `subagent_instruction` field (or it is `null`).

2. **After deleting `build_dispatched.json`** and second `get_pipeline_status` call:
   - Response contains `"DISPATCH_REQUIRED": true`.
   - Response does NOT contain an `"active_dispatch"` field.
   - Response contains a `subagent_instruction` referencing the prompt builder.

**FAIL** if:
- First call returns `DISPATCH_REQUIRED: true` (guard is not working).
- First call `active_dispatch` is absent when `build_dispatched.json` is present with matching iteration.
- Second call (after deletion) still returns `DISPATCH_REQUIRED: false`.
