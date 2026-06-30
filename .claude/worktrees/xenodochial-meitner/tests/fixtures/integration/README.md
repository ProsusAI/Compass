# Integration Test Runbook

Run these tests in a conversation with the Odysseus MCP server enabled.

## Prerequisites

Add the MCP server to your Claude Code config:

```json
{
  "mcpServers": {
    "odysseus": {
      "command": "uv",
      "args": ["run", "python", "-m", "odysseus.mcp"],
      "cwd": "<path-to-project-odysseus>"
    }
  }
}
```

## Test 1: Happy path — all examples correct

Call `run_eval` with the integration fixtures:

```
run_eval(
  prompt_version="v1",
  data_source="tests/fixtures/integration/dataset.jsonl",
  backend="mock-echo",
  config_path="tests/fixtures/integration/run_config.yaml"
)
```

**Expected result:**
- Returns JSON with `report_path` and `results_path`
- `report.json` shows:
  - `summary.total` = 5
  - `summary.succeeded` = 5
  - `summary.failed` = 0
  - `metrics.accuracy` = 1.0 (mock echoes expected route)

**Verify:** Read `tests/fixtures/integration/outputs/report.json` and `results.jsonl`.

## Test 2: Missing config

```
run_eval(
  prompt_version="v1",
  data_source="tests/fixtures/integration/dataset.jsonl",
  backend="mock-echo",
  config_path="nonexistent.yaml"
)
```

**Expected:** Returns `{"error": "not_found", "detail": "..."}`.

## Test 3: Unknown backend

```
run_eval(
  prompt_version="v1",
  data_source="tests/fixtures/integration/dataset.jsonl",
  backend="does-not-exist",
  config_path="tests/fixtures/integration/run_config.yaml"
)
```

**Expected:** Returns `{"error": "not_found", "detail": "..."}`.

## Cleanup

Delete generated output files:

```bash
rm -rf tests/fixtures/integration/outputs/
```
