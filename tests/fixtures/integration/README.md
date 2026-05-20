# Integration Test Runbook

Run these tests in a conversation with the Compass MCP server enabled.

## Prerequisites

Add the MCP server to your Claude Code config:

```json
{
  "mcpServers": {
    "compass": {
      "command": "uv",
      "args": ["run", "python", "-m", "compass.mcp"],
      "cwd": "<path-to-project-compass>"
    }
  }
}
```

## Test 1: Happy path — all examples correct

After preparing a Stage 4 integration run whose `outputs/<run_id>/analysis/dev.jsonl`
uses `tests/fixtures/integration/dataset.jsonl`, call `run_batch_eval` with a
single candidate:

```
run_batch_eval(
  run_id="integration-run",
  candidates=[
    {
      "prompt_version": "v1",
      "example_ids": []
    }
  ]
)
```

**Expected result:**
- Returns JSON with `succeeded` containing one entry and `failed` empty
- `outputs/integration-run/eval/v1/report.json` shows:
  - `summary.total` = 5
  - `summary.succeeded` = 5
  - `summary.failed` = 0
  - `metrics.accuracy` = 1.0 (mock echoes expected route)

**Verify:** Read `outputs/integration-run/eval/v1/report.json` and `outputs/integration-run/eval/v1/results.jsonl`.

## Test 2: Unknown run id

```
run_batch_eval(
  run_id="does-not-exist",
  candidates=[
    {
      "prompt_version": "v1",
      "example_ids": []
    }
  ]
)
```

**Expected:** The tool raises an error because the pipeline search state and Stage 4 artifacts do not exist for that run.

## Test 3: Unknown backend configured on the run

```
run_batch_eval(
  run_id="integration-run",
  candidates=[
    {
      "prompt_version": "v1",
      "example_ids": []
    }
  ]
)
```

**Expected:** The tool raises an error if the run's initialized backend profile does not exist.

## Cleanup

Delete generated output files:

```bash
rm -rf outputs/integration-run/
```
