# Entry Point Refinement Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `optimize_routing_prompt` stub with a real implementation that activates the User Input Agent in a single tool call, eliminating the model's exploration step at session start.

**Architecture:** `optimize_routing_prompt` calls `_get_pipeline_status` server-side and returns an XML activation package (pipeline status + instructions + User Input Agent system prompt) as a single tool result. The `user_input_system.md` Pipeline Discovery section is updated to remove the now-redundant `get_pipeline_status` call instruction.

**Tech Stack:** Python 3.11, FastMCP, pytest, uv

**Spec:** `docs/specs/2026-03-27-optimize-routing-prompt-entry-point-design.md`

---

## Chunk 1: Update `user_input_system.md`

### Task 1: Remove `get_pipeline_status` call instruction from the system prompt

**Files:**
- Modify: `odysseus/agents/prompts/user_input_system.md:65`

No test needed — this is a prose change to an agent system prompt, not executable code.

- [ ] **Step 1: Edit `user_input_system.md`**

  In the `## Pipeline Discovery` section, replace line 65:

  **Before:**
  ```
  Before collecting the problem spec, check if previous pipeline runs exist by calling `get_pipeline_status`. If previous runs exist, ask the user:
  ```

  **After:**
  ```
  Pipeline status has already been retrieved and is pre-injected above — use it directly. If previous runs exist, ask the user:
  ```

  Everything else in the section (the quoted question, the two bullet points) stays unchanged.

- [ ] **Step 2: Verify the edit looks right**

  Run: `grep -A 6 "## Pipeline Discovery" odysseus/agents/prompts/user_input_system.md`

  Expected output:
  ```
  ## Pipeline Discovery

  Pipeline status has already been retrieved and is pre-injected above — use it directly. If previous runs exist, ask the user:

  > "I found existing pipeline runs. Would you like to start fresh, or bootstrap from an existing run's prompt?"
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add odysseus/agents/prompts/user_input_system.md
  git commit -m "fix(prompts): remove get_pipeline_status call from user_input_system

  Status is now pre-injected by the optimize_routing_prompt tool."
  ```

---

## Chunk 2: Implement `optimize_routing_prompt`

### Task 2: Schema shape — drop the three stub parameters

**Files:**
- Modify: `odysseus/mcp.py:254-273`
- Test: `tests/test_mcp.py`

- [ ] **Step 1: Write the failing test**

  Add this test to `tests/test_mcp.py` (after `test_run_holdout_eval_does_not_expose_data_split`, around line 65):

  ```python
  async def test_optimize_routing_prompt_has_no_user_params():
      """optimize_routing_prompt must expose no user-facing parameters."""
      tools = await mcp.list_tools()
      tool = next(t for t in tools if t.name == "optimize_routing_prompt")
      schema_properties = tool.inputSchema.get("properties", {})
      assert schema_properties == {}, (
          f"optimize_routing_prompt must have no parameters, got: {list(schema_properties)}"
      )
  ```

- [ ] **Step 2: Run to confirm failure**

  Run: `uv run pytest tests/test_mcp.py::test_optimize_routing_prompt_has_no_user_params -v`

  Expected: FAIL — the current stub exposes `data_path`, `problem_description`, `target_metrics`.

- [ ] **Step 3: Replace the stub signature in `odysseus/mcp.py`**

  Replace the entire `optimize_routing_prompt` function (lines 254-273) with:

  ```python
  @mcp.tool()
  async def optimize_routing_prompt(ctx: Context) -> str:
      """Start the Odysseus routing prompt optimization pipeline.

      Call this to begin. Activates the User Input Agent, which will guide
      you through providing a problem description and dataset before the
      pipeline runs.
      """
      # Implementation added in next task — placeholder to pass schema test
      raise ToolError("Not yet implemented")
  ```

- [ ] **Step 4: Run schema test to confirm it passes**

  Run: `uv run pytest tests/test_mcp.py::test_optimize_routing_prompt_has_no_user_params -v`

  Expected: PASS

- [ ] **Step 5: Commit**

  ```bash
  git add odysseus/mcp.py tests/test_mcp.py
  git commit -m "test: add schema shape test for optimize_routing_prompt

  Drops the three stub parameters; tool now accepts ctx only."
  ```

---

### Task 3: Happy path — return activation package

**Files:**
- Modify: `odysseus/mcp.py` (implement `optimize_routing_prompt` body)
- Test: `tests/test_mcp.py`

- [ ] **Step 1: Write the failing test**

  Add `TestOptimizeRoutingPrompt` class to `tests/test_mcp.py` (after `TestGetPipelineStatus`):

  ```python
  class TestOptimizeRoutingPrompt:
      """Tests for the optimize_routing_prompt MCP tool."""

      async def test_tool_registered(self):
          """optimize_routing_prompt is listed as an MCP tool."""
          tools = await mcp.list_tools()
          tool_names = [t.name for t in tools]
          assert "optimize_routing_prompt" in tool_names

      async def test_returns_activation_package(self, tmp_path: Path):
          """Returns a string with all three XML sections."""
          from odysseus.mcp import optimize_routing_prompt

          with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
              result = await optimize_routing_prompt(ctx=None)

          assert "<pipeline_status>" in result
          assert "</pipeline_status>" in result
          assert "<instructions>" in result
          assert "</instructions>" in result
          assert "<system_prompt>" in result
          assert "</system_prompt>" in result

      async def test_pipeline_status_is_valid_json(self, tmp_path: Path):
          """The content inside <pipeline_status> is valid JSON."""
          from odysseus.mcp import optimize_routing_prompt

          with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
              result = await optimize_routing_prompt(ctx=None)

          start = result.index("<pipeline_status>") + len("<pipeline_status>")
          end = result.index("</pipeline_status>")
          status_json = result[start:end].strip()
          data = json.loads(status_json)
          assert "current_stage" in data
          assert "next_action" in data

      async def test_system_prompt_contains_agent_content(self, tmp_path: Path):
          """The <system_prompt> section contains the User Input Agent content."""
          from odysseus.mcp import optimize_routing_prompt

          with patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path):
              result = await optimize_routing_prompt(ctx=None)

          start = result.index("<system_prompt>") + len("<system_prompt>")
          end = result.index("</system_prompt>")
          system_prompt = result[start:end].strip()
          # Verify it's the User Input Agent prompt, not something else
          assert "User Input agent" in system_prompt or "pipeline's entry gate" in system_prompt
  ```

- [ ] **Step 2: Run to confirm failure**

  Run: `uv run pytest tests/test_mcp.py::TestOptimizeRoutingPrompt -v`

  Expected: FAIL — all tests fail with `ToolError("Not yet implemented")`.

- [ ] **Step 3: Implement the activation package body**

  Replace the placeholder body in `optimize_routing_prompt` in `odysseus/mcp.py`:

  ```python
  @mcp.tool()
  async def optimize_routing_prompt(ctx: Context) -> str:
      """Start the Odysseus routing prompt optimization pipeline.

      Call this to begin. Activates the User Input Agent, which will guide
      you through providing a problem description and dataset before the
      pipeline runs.
      """
      try:
          system_prompt = _load_text("odysseus/agents/prompts/user_input_system.md")
      except FileNotFoundError as e:
          raise ToolError(
              f"User Input Agent system prompt not found — MCP server installation may be broken: {e}"
          )

      project_dir = await resolve_project_dir(ctx)
      outputs_dir = project_dir / "outputs"

      try:
          status = _get_pipeline_status(outputs_dir=outputs_dir, run_id=None, project_dir=project_dir)
      except Exception as e:
          raise ToolError(f"Failed to read pipeline status from {outputs_dir}: {e}")

      status_json = json.dumps(status, indent=2)

      return (
          f"<pipeline_status>\n{status_json}\n</pipeline_status>\n\n"
          f"<instructions>\n"
          f"You are now operating as the User Input Agent for the Odysseus pipeline.\n"
          f"The pipeline status above has already been checked — use it to decide whether\n"
          f"to greet the user for a fresh run or surface existing runs and offer to bootstrap.\n"
          f"Follow your system prompt below exactly.\n"
          f"</instructions>\n\n"
          f"<system_prompt>\n{system_prompt}\n</system_prompt>"
      )
  ```

  Note: `json` is already imported at the top of `mcp.py` (line 8).

- [ ] **Step 4: Run happy path tests**

  Run: `uv run pytest tests/test_mcp.py::TestOptimizeRoutingPrompt -v`

  Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add odysseus/mcp.py tests/test_mcp.py
  git commit -m "feat: implement optimize_routing_prompt as pipeline entry point

  Returns activation package (pipeline status + instructions + User Input
  Agent system prompt) in a single tool call, eliminating model exploration."
  ```

---

### Task 4: Error paths

**Files:**
- Test: `tests/test_mcp.py` (add error tests to `TestOptimizeRoutingPrompt`)

- [ ] **Step 1: Write the failing error tests**

  Add these two methods inside `TestOptimizeRoutingPrompt` in `tests/test_mcp.py`:

  ```python
      async def test_missing_system_prompt_raises_tool_error(self, tmp_path: Path):
          """FileNotFoundError from _load_text is surfaced as ToolError with installation message."""
          from odysseus.mcp import optimize_routing_prompt

          with (
              patch("odysseus.mcp._load_text", side_effect=FileNotFoundError("no such file")),
              patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
              pytest.raises(ToolError, match="installation may be broken"),
          ):
              await optimize_routing_prompt(ctx=None)

      async def test_pipeline_status_error_raises_tool_error(self, tmp_path: Path):
          """OSError from _get_pipeline_status is surfaced as ToolError with outputs_dir in message."""
          from odysseus.mcp import optimize_routing_prompt

          with (
              patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
              patch(
                  "odysseus.mcp._get_pipeline_status",
                  side_effect=OSError("disk read error"),
              ),
              pytest.raises(ToolError, match="outputs"),
          ):
              await optimize_routing_prompt(ctx=None)
  ```

- [ ] **Step 2: Run to confirm failure**

  Run: `uv run pytest tests/test_mcp.py::TestOptimizeRoutingPrompt::test_missing_system_prompt_raises_tool_error tests/test_mcp.py::TestOptimizeRoutingPrompt::test_pipeline_status_error_raises_tool_error -v`

  Expected: FAIL — both tests fail because the implementation is not yet in place (or the error messages don't match).

  > If the implementation from Task 3 is already correct, the tests may pass immediately — that's fine, verify and proceed.

- [ ] **Step 3: Run the full test class**

  Run: `uv run pytest tests/test_mcp.py::TestOptimizeRoutingPrompt -v`

  Expected: all 6 tests PASS.

- [ ] **Step 4: Run the full test suite**

  Run: `uv run pytest -v`

  Expected: all tests pass, no regressions.

- [ ] **Step 5: Commit**

  ```bash
  git add tests/test_mcp.py
  git commit -m "test: add error path tests for optimize_routing_prompt"
  ```

---

## Chunk 3: Verify and wrap up

### Task 5: Final verification

**Files:** None modified — verification only.

- [ ] **Step 1: Run the full test suite one more time**

  Run: `uv run pytest -v`

  Expected: all tests pass.

- [ ] **Step 2: Run linter and formatter**

  Run: `uv run ruff check . && uv run ruff format --check .`

  Expected: no errors. If `ruff format --check` reports formatting issues, run `uv run ruff format .` and commit the result.

  > Note: `uv run pyright` requires Node.js to be available. If it works in your environment, run it too. If it fails with a Node.js bootstrapping error, skip it — this is an environment issue, not a code issue.

- [ ] **Step 3: Confirm branch state**

  Run: `git log --oneline main..HEAD`

  Expected output (5 commits — the first is the spec doc committed during brainstorming):
  ```
  <hash> test: add error path tests for optimize_routing_prompt
  <hash> feat: implement optimize_routing_prompt as pipeline entry point
  <hash> test: add schema shape test for optimize_routing_prompt
  <hash> fix(prompts): remove get_pipeline_status call from user_input_system
  <hash> docs: add entry point refinement spec
  ```
