# THP-115 Holdout Access Control Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement tool-only enforcement of holdout access control so `run_eval` always uses `data_split="dev"` and `run_holdout_eval` always uses `data_split="holdout"`.

**Architecture:** A shared `_build_run_config` helper in `odysseus/mcp.py` constructs `RunConfig` with the split hardcoded by the caller. Both `run_eval` (THP-129) and `run_holdout_eval` (future task) call this helper. This plan implements the helper, a stub `run_holdout_eval` tool, and tests verifying split enforcement.

**Tech Stack:** Pydantic, FastMCP, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-19-thp115-holdout-access-control-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `odysseus/mcp.py` | Modify | Add `_build_run_config` helper, `run_eval` stub, `run_holdout_eval` stub |
| `tests/test_mcp.py` | Modify | Add split enforcement tests |

---

## Chunk 1: Config builder helper and split enforcement

### Task 1: Test that `_build_run_config` hardcodes the split

**Files:**
- Modify: `tests/test_mcp.py`
- Modify: `odysseus/mcp.py`

- [ ] **Step 1: Write failing tests for `_build_run_config`**

Add to `tests/test_mcp.py`:

```python
from odysseus.mcp import _build_run_config


def test_build_run_config_dev_split():
    """_build_run_config with split='dev' sets data_split='dev'."""
    config = _build_run_config(
        prompt_version="v1",
        data_source="data/test.jsonl",
        data_split="dev",
    )
    assert config.data_split == "dev"
    assert config.prompt_version == "v1"
    assert config.data_source == "data/test.jsonl"


def test_build_run_config_holdout_split():
    """_build_run_config with split='holdout' sets data_split='holdout'."""
    config = _build_run_config(
        prompt_version="v1",
        data_source="data/test.jsonl",
        data_split="holdout",
    )
    assert config.data_split == "holdout"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mcp.py::test_build_run_config_dev_split tests/test_mcp.py::test_build_run_config_holdout_split -v`
Expected: FAIL with `ImportError: cannot import name '_build_run_config'`

- [ ] **Step 3: Implement `_build_run_config` in `odysseus/mcp.py`**

Add below the existing imports in `odysseus/mcp.py`:

```python
from typing import Literal

from odysseus.eval.models import MetricConfig, RunConfig


def _build_run_config(
    prompt_version: str,
    data_source: str,
    data_split: Literal["dev", "holdout"],
) -> RunConfig:
    """Build a RunConfig with the given split hardcoded.

    This is the single place where RunConfig is assembled for MCP tools.
    The split is always provided by the calling tool, never by the agent.
    """
    # TODO(THP-129): read backend/metrics from environment or config file
    return RunConfig(
        backend="default",
        prompt_version=prompt_version,
        data_source=data_source,
        data_split=data_split,
        metrics=[MetricConfig(name="accuracy")],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mcp.py::test_build_run_config_dev_split tests/test_mcp.py::test_build_run_config_holdout_split -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/mcp.py tests/test_mcp.py
git commit -m "feat(THP-115): add _build_run_config helper with split enforcement"
```

### Task 2: Test that `run_eval` tool hardcodes `data_split="dev"`

**Files:**
- Modify: `tests/test_mcp.py`
- Modify: `odysseus/mcp.py`

- [ ] **Step 1: Write failing test for `run_eval` tool**

Add to `tests/test_mcp.py`:

```python
from unittest.mock import patch


async def test_run_eval_hardcodes_dev_split():
    """run_eval must always construct RunConfig with data_split='dev'."""
    with patch("odysseus.mcp._build_run_config") as mock_build:
        mock_build.return_value = _build_run_config("v1", "data/test.jsonl", "dev")
        # Import the tool function and call it directly
        from odysseus.mcp import run_eval

        await run_eval(prompt_version="v1", data_source="data/test.jsonl")
        mock_build.assert_called_once_with(
            prompt_version="v1",
            data_source="data/test.jsonl",
            data_split="dev",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mcp.py::test_run_eval_hardcodes_dev_split -v`
Expected: FAIL with `ImportError: cannot import name 'run_eval'`

- [ ] **Step 3: Implement `run_eval` stub in `odysseus/mcp.py`**

Add below `_build_run_config` in `odysseus/mcp.py`:

```python
@mcp.tool()
async def run_eval(prompt_version: str, data_source: str) -> str:
    """Run evaluation on the dev split.

    Args:
        prompt_version: Prompt version to evaluate.
        data_source: Path to the dataset file.

    Returns:
        Serialized score report.
    """
    config = _build_run_config(
        prompt_version=prompt_version,
        data_source=data_source,
        data_split="dev",
    )
    # TODO(THP-129): wire RunDependencies and call controller.run()
    return f"run_eval stub: config.data_split={config.data_split}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mcp.py::test_run_eval_hardcodes_dev_split -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/mcp.py tests/test_mcp.py
git commit -m "feat(THP-115): add run_eval stub hardcoding data_split=dev"
```

### Task 3: Test that `run_holdout_eval` tool hardcodes `data_split="holdout"`

**Files:**
- Modify: `tests/test_mcp.py`
- Modify: `odysseus/mcp.py`

- [ ] **Step 1: Write failing test for `run_holdout_eval` tool**

Add to `tests/test_mcp.py`:

```python
async def test_run_holdout_eval_hardcodes_holdout_split():
    """run_holdout_eval must always construct RunConfig with data_split='holdout'."""
    with patch("odysseus.mcp._build_run_config") as mock_build:
        mock_build.return_value = _build_run_config("v1", "data/test.jsonl", "holdout")
        from odysseus.mcp import run_holdout_eval

        await run_holdout_eval(prompt_version="v1", data_source="data/test.jsonl")
        mock_build.assert_called_once_with(
            prompt_version="v1",
            data_source="data/test.jsonl",
            data_split="holdout",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mcp.py::test_run_holdout_eval_hardcodes_holdout_split -v`
Expected: FAIL with `ImportError: cannot import name 'run_holdout_eval'`

- [ ] **Step 3: Implement `run_holdout_eval` stub in `odysseus/mcp.py`**

Add below `run_eval` in `odysseus/mcp.py`:

```python
@mcp.tool()
async def run_holdout_eval(prompt_version: str, data_source: str) -> str:
    """Run evaluation on the holdout split.

    This tool must only be available to the Final Evaluation agent.
    It must NOT be in the Eval Runner agent's tool list.

    Args:
        prompt_version: Prompt version to evaluate.
        data_source: Path to the dataset file.

    Returns:
        Serialized score report.
    """
    config = _build_run_config(
        prompt_version=prompt_version,
        data_source=data_source,
        data_split="holdout",
    )
    # TODO: wire RunDependencies and call controller.run()
    return f"run_holdout_eval stub: config.data_split={config.data_split}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mcp.py::test_run_holdout_eval_hardcodes_holdout_split -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add odysseus/mcp.py tests/test_mcp.py
git commit -m "feat(THP-115): add run_holdout_eval stub hardcoding data_split=holdout"
```

### Task 4: Test that both tools are registered and `data_split` is not a parameter

**Files:**
- Modify: `tests/test_mcp.py`

- [ ] **Step 1: Write tests for tool registration, schema enforcement, and internal misuse guard**

Add to `tests/test_mcp.py`:

```python
def test_run_eval_does_not_construct_holdout_config():
    """run_eval's hardcoded split must be 'dev', never 'holdout'.

    This is the spec's 'internal misuse' guard (Section 2): verify that
    only run_holdout_eval constructs a holdout RunConfig.
    """
    import ast
    import inspect
    from odysseus.mcp import run_eval

    source = inspect.getsource(run_eval)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "data_split":
            assert isinstance(node.value, ast.Constant)
            assert node.value.value == "dev", (
                "run_eval must hardcode data_split='dev'"
            )


async def test_run_eval_tool_registered():
    """run_eval must be registered as an MCP tool."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "run_eval" in tool_names


async def test_run_holdout_eval_tool_registered():
    """run_holdout_eval must be registered as an MCP tool."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "run_holdout_eval" in tool_names


async def test_run_eval_does_not_expose_data_split():
    """run_eval must not expose data_split as a parameter."""
    tools = await mcp.list_tools()
    run_eval_tool = next(t for t in tools if t.name == "run_eval")
    schema_properties = run_eval_tool.inputSchema.get("properties", {})
    assert "data_split" not in schema_properties, (
        "data_split must not be exposed as a tool parameter"
    )


async def test_run_holdout_eval_does_not_expose_data_split():
    """run_holdout_eval must not expose data_split as a parameter."""
    tools = await mcp.list_tools()
    holdout_tool = next(t for t in tools if t.name == "run_holdout_eval")
    schema_properties = holdout_tool.inputSchema.get("properties", {})
    assert "data_split" not in schema_properties, (
        "data_split must not be exposed as a tool parameter"
    )
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_mcp.py::test_run_eval_tool_registered tests/test_mcp.py::test_run_holdout_eval_tool_registered tests/test_mcp.py::test_run_eval_does_not_expose_data_split tests/test_mcp.py::test_run_holdout_eval_does_not_expose_data_split -v`
Expected: PASS (these should pass immediately since the tools are already registered)

- [ ] **Step 3: Commit**

```bash
git add tests/test_mcp.py
git commit -m "test(THP-115): verify tool registration and data_split not exposed"
```

### Task 5: Run full test suite and lint

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 2: Run linter**

Run: `uv run ruff check .`
Expected: No errors

- [ ] **Step 3: Run formatter**

Run: `uv run ruff format .`
Expected: No changes (or apply formatting)

- [ ] **Step 4: Run type checker**

Run: `uv run pyright`
Expected: No errors

- [ ] **Step 5: Final commit if any formatting changes**

```bash
git add -u
git commit -m "style(THP-115): apply formatting"
```

---

## Deferred Work (Not Part of This Plan)

- **System prompt reinforcement** (`prompts/eval_runner_system.md`): the spec requires a no-holdout statement in the Eval Runner agent's system prompt. This is THP-104's responsibility.
- **`_build_run_config` configuration**: the hardcoded `backend="default"` and `metrics` values are placeholders. THP-129 will replace them with environment/config-driven assembly.
- **`run_eval` full wiring**: THP-129 will wire `RunDependencies` and call `controller.run()`.
- **Task 4 tests are regression guards**, not TDD red-green — they pass immediately after Tasks 2–3 since the tools are already registered. They guard against future regressions where someone might accidentally expose `data_split`.
