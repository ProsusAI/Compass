# Backend Setup Clarification Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pre-flight check to `run_eval` that triggers a clarification flow on the first eval run, letting users select or create a backend.

**Architecture:** The `run_eval` MCP tool gains a `search_state_id` parameter. On first run (round 0, no history), it returns `action_required: backend_setup` instead of running the eval. A new `odysseus_backend_setup` MCP prompt uses the structured-clarification skill to collect backend config from the user. A `DEFAULT_PRICING` dict in `odysseus/eval/pricing.py` provides auto-resolved pricing for known models. `BackendProfile` gains a `reasoning_level` field wired through backend implementations.

**Tech Stack:** Python 3.11+, Pydantic, FastMCP, pytest

**Spec:** `docs/superpowers/specs/2026-03-26-backend-setup-clarification-design.md`

---

## Chunk 1: DEFAULT_PRICING and BackendProfile.reasoning_level

### Task 1: Add DEFAULT_PRICING to pricing.py

**Files:**
- Modify: `odysseus/eval/pricing.py`
- Test: `tests/test_pricing.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_pricing.py`, add tests for the new `DEFAULT_PRICING` dict and a `get_default_pricing()` lookup function:

```python
"""Tests for DEFAULT_PRICING lookup."""

from odysseus.eval.pricing import ModelPricing, get_default_pricing


class TestDefaultPricing:
    def test_known_anthropic_model_resolves(self) -> None:
        pricing = get_default_pricing("anthropic", "claude-haiku-4-5")
        assert pricing is not None
        assert isinstance(pricing, ModelPricing)
        assert pricing.input_cost_per_million_tokens == 0.80

    def test_known_openai_model_resolves(self) -> None:
        pricing = get_default_pricing("openai", "gpt-4.1")
        assert pricing is not None
        assert pricing.input_cost_per_million_tokens == 2.00

    def test_unknown_model_returns_none(self) -> None:
        pricing = get_default_pricing("anthropic", "nonexistent-model")
        assert pricing is None

    def test_unknown_provider_returns_none(self) -> None:
        pricing = get_default_pricing("unknown_provider", "some-model")
        assert pricing is None

    def test_all_entries_are_model_pricing(self) -> None:
        from odysseus.eval.pricing import DEFAULT_PRICING

        for key, value in DEFAULT_PRICING.items():
            assert isinstance(key, tuple) and len(key) == 2, f"Key {key} should be (provider, model)"
            assert isinstance(value, ModelPricing), f"Value for {key} should be ModelPricing"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pricing.py -v`
Expected: ImportError — `get_default_pricing` does not exist yet.

- [ ] **Step 3: Implement DEFAULT_PRICING and get_default_pricing**

Add to the bottom of `odysseus/eval/pricing.py`:

```python
DEFAULT_PRICING: dict[tuple[str, str], ModelPricing] = {
    # Anthropic
    ("anthropic", "claude-haiku-4-5"): ModelPricing(
        input_cost_per_million_tokens=0.80,
        cached_cost_per_million_tokens=0.08,
        output_cost_per_million_tokens=4.00,
    ),
    ("anthropic", "claude-sonnet-4-5"): ModelPricing(
        input_cost_per_million_tokens=3.00,
        cached_cost_per_million_tokens=0.30,
        output_cost_per_million_tokens=15.00,
    ),
    ("anthropic", "claude-opus-4"): ModelPricing(
        input_cost_per_million_tokens=15.00,
        cached_cost_per_million_tokens=1.50,
        output_cost_per_million_tokens=75.00,
    ),
    # OpenAI
    ("openai", "gpt-4.1"): ModelPricing(
        input_cost_per_million_tokens=2.00,
        cached_cost_per_million_tokens=0.50,
        output_cost_per_million_tokens=8.00,
    ),
    ("openai", "gpt-4.1-mini"): ModelPricing(
        input_cost_per_million_tokens=0.40,
        cached_cost_per_million_tokens=0.10,
        output_cost_per_million_tokens=1.60,
    ),
    ("openai", "gpt-4.1-nano"): ModelPricing(
        input_cost_per_million_tokens=0.10,
        cached_cost_per_million_tokens=0.025,
        output_cost_per_million_tokens=0.40,
    ),
    ("openai", "o3"): ModelPricing(
        input_cost_per_million_tokens=2.00,
        cached_cost_per_million_tokens=0.50,
        output_cost_per_million_tokens=8.00,
    ),
    ("openai", "o4-mini"): ModelPricing(
        input_cost_per_million_tokens=1.10,
        cached_cost_per_million_tokens=0.275,
        output_cost_per_million_tokens=4.40,
    ),
}


def get_default_pricing(provider: str, model: str) -> ModelPricing | None:
    """Look up default pricing for a (provider, model) pair.

    Returns None if the combination is not in the table.
    """
    return DEFAULT_PRICING.get((provider, model))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pricing.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/pricing.py tests/test_pricing.py
git commit -m "feat: add DEFAULT_PRICING table with get_default_pricing lookup"
```

---

### Task 2: Add reasoning_level to BackendProfile

**Files:**
- Modify: `odysseus/eval/backends/profile.py`
- Modify: `tests/test_backends.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_backends.py` inside the `TestBackendProfileConstruction` class (or a new class):

```python
class TestBackendProfileReasoningLevel:
    def test_reasoning_level_defaults_to_none(self) -> None:
        profile = BackendProfile(**MINIMAL_PROFILE)
        assert profile.reasoning_level is None

    def test_reasoning_level_accepts_valid_values(self) -> None:
        for level in ("low", "medium", "high"):
            profile = BackendProfile(**{**MINIMAL_PROFILE, "reasoning_level": level})
            assert profile.reasoning_level == level

    def test_reasoning_level_rejects_invalid_value(self) -> None:
        with pytest.raises(ValidationError):
            BackendProfile(**{**MINIMAL_PROFILE, "reasoning_level": "extreme"})

    def test_reasoning_level_from_yaml(self, tmp_path: Path) -> None:
        yaml_content = """
model: test-model
provider: anthropic
requests_per_minute: 100
tokens_per_minute: 50000
reasoning_level: high
"""
        p = tmp_path / "test.yaml"
        p.write_text(yaml_content)
        profile = BackendProfile.from_yaml(p)
        assert profile.reasoning_level == "high"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backends.py::TestBackendProfileReasoningLevel -v`
Expected: FAIL — `reasoning_level` field does not exist on BackendProfile.

- [ ] **Step 3: Add reasoning_level field to BackendProfile**

In `odysseus/eval/backends/profile.py`, add after `temperature`:

```python
reasoning_level: Literal["low", "medium", "high"] | None = None
```

Update the `Literal` import to include it (it's already imported).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backends.py::TestBackendProfileReasoningLevel -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/backends/profile.py tests/test_backends.py
git commit -m "feat: add reasoning_level field to BackendProfile"
```

---

### Task 3: Wire reasoning_level through AnthropicBackend

**Files:**
- Modify: `odysseus/eval/backends/anthropic_backend.py`
- Modify: `tests/test_backends.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_backends.py` in the `TestAnthropicBackend` section:

```python
class TestAnthropicBackendReasoningLevel:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("level,expected_budget", [
        ("low", 1024),
        ("medium", 4096),
        ("high", 16384),
    ])
    async def test_reasoning_level_sets_thinking_budget(
        self, level: str, expected_budget: int
    ) -> None:
        profile = BackendProfile(
            **{**MINIMAL_PROFILE, "reasoning_level": level, "api_key_env": None}
        )
        backend = AnthropicBackend(profile)
        with patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = _make_anthropic_mock_response(text="test")
            await backend.call("prompt", EXAMPLE)
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["thinking"] == {"type": "enabled", "budget_tokens": expected_budget}

    @pytest.mark.asyncio
    async def test_no_reasoning_level_omits_thinking(self) -> None:
        profile = BackendProfile(**{**MINIMAL_PROFILE, "api_key_env": None})
        backend = AnthropicBackend(profile)
        with patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = _make_anthropic_mock_response(text="test")
            await backend.call("prompt", EXAMPLE)
            call_kwargs = mock_create.call_args.kwargs
            assert "thinking" not in call_kwargs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backends.py::TestAnthropicBackendReasoningLevel -v`
Expected: FAIL — thinking param not passed.

- [ ] **Step 3: Implement reasoning_level in AnthropicBackend.call()**

In `odysseus/eval/backends/anthropic_backend.py`, in the `call()` method, add before `response = await self._client.messages.create(...)`:

```python
REASONING_BUDGET_MAP: dict[str, int] = {"low": 1024, "medium": 4096, "high": 16384}

# Inside call(), after kwargs.update(self._profile.extra_params):
if self._profile.reasoning_level is not None:
    budget = REASONING_BUDGET_MAP[self._profile.reasoning_level]
    kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
```

Move the `REASONING_BUDGET_MAP` to module level, outside the class.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backends.py::TestAnthropicBackendReasoningLevel -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/backends/anthropic_backend.py tests/test_backends.py
git commit -m "feat: wire reasoning_level through AnthropicBackend as thinking.budget_tokens"
```

---

### Task 4: Wire reasoning_level through OpenAIBackend

**Files:**
- Modify: `odysseus/eval/backends/openai_backend.py`
- Modify: `tests/test_backends.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_backends.py`:

```python
class TestOpenAIBackendReasoningLevel:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("level", ["low", "medium", "high"])
    async def test_reasoning_level_sets_reasoning_effort(self, level: str) -> None:
        profile = BackendProfile(
            **{**MINIMAL_PROFILE, "provider": "openai", "reasoning_level": level, "api_key_env": None}
        )
        backend = OpenAIBackend(profile)
        with patch.object(backend._client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = _make_openai_mock_response(content="test")
            await backend.call("prompt", EXAMPLE)
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["reasoning_effort"] == level

    @pytest.mark.asyncio
    async def test_no_reasoning_level_omits_reasoning_effort(self) -> None:
        profile = BackendProfile(
            **{**MINIMAL_PROFILE, "provider": "openai", "api_key_env": None}
        )
        backend = OpenAIBackend(profile)
        with patch.object(backend._client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = _make_openai_mock_response(content="test")
            await backend.call("prompt", EXAMPLE)
            call_kwargs = mock_create.call_args.kwargs
            assert "reasoning_effort" not in call_kwargs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backends.py::TestOpenAIBackendReasoningLevel -v`
Expected: FAIL — reasoning_effort not passed.

- [ ] **Step 3: Implement reasoning_level in OpenAIBackend.call()**

In `odysseus/eval/backends/openai_backend.py`, in the `call()` method, add after `kwargs.update(self._profile.extra_params)`:

```python
if self._profile.reasoning_level is not None:
    kwargs["reasoning_effort"] = self._profile.reasoning_level
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backends.py::TestOpenAIBackendReasoningLevel -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add odysseus/eval/backends/openai_backend.py tests/test_backends.py
git commit -m "feat: wire reasoning_level through OpenAIBackend as reasoning_effort"
```

---

## Chunk 2: Pre-flight Check in run_eval

### Task 5: Add pre-flight check to run_eval MCP tool

**Files:**
- Modify: `odysseus/mcp.py:184-223`
- Modify: `tests/test_run_eval_tool.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_run_eval_tool.py`:

```python
from odysseus.agents.prompt_builder_search import SearchState

GET_SEARCH_STATE = "odysseus.mcp.get_search_state"
BACKEND_REGISTRY = "odysseus.mcp.BackendRegistry"


@pytest.mark.asyncio
async def test_run_eval_preflight_triggers_on_round_zero() -> None:
    """First run in loop (round 0, no history) returns action_required."""
    state = SearchState(
        search_state_id="test-123",
        backend="anthropic",
        round=0,
        round_history=[],
    )
    mock_registry = AsyncMock()
    mock_registry.list_profiles.return_value = ["anthropic", "openai"]

    with (
        patch(GET_SEARCH_STATE, return_value=state),
        patch(BACKEND_REGISTRY) as MockRegistry,
        patch("odysseus.mcp.get_project_dir", return_value=Path("/fake")),
    ):
        MockRegistry.from_directory.return_value = mock_registry

        result = await run_eval(
            prompt_version="v1",
            data_source="data/test.jsonl",
            backend="anthropic",
            search_state_id="test-123",
        )

    parsed = json.loads(result)
    assert parsed["action_required"] == "backend_setup"
    assert parsed["search_state_id"] == "test-123"
    assert "anthropic" in parsed["available_backends"]


@pytest.mark.asyncio
async def test_run_eval_preflight_skipped_after_round_zero() -> None:
    """After first round, run_eval proceeds normally (no action_required)."""
    state = SearchState(
        search_state_id="test-123",
        backend="anthropic",
        round=1,
        round_history=[],  # round > 0 is enough
    )
    score_report = _stub_score_report()

    with (
        patch(GET_SEARCH_STATE, return_value=state),
        patch(AGENT_RUN, new_callable=AsyncMock) as mock_run,
    ):
        mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

        result = await run_eval(
            prompt_version="v1",
            data_source="data/test.jsonl",
            backend="anthropic",
            search_state_id="test-123",
        )

    parsed = json.loads(result)
    assert "action_required" not in parsed
    assert "report_path" in parsed


@pytest.mark.asyncio
async def test_run_eval_no_search_state_id_skips_preflight() -> None:
    """Without search_state_id, run_eval behaves as before."""
    score_report = _stub_score_report()

    with patch(AGENT_RUN, new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {ScoreReport.CONTEXT_KEY: score_report}

        result = await run_eval(
            prompt_version="v1",
            data_source="data/test.jsonl",
            backend="anthropic",
        )

    parsed = json.loads(result)
    assert "action_required" not in parsed
    assert "report_path" in parsed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_run_eval_tool.py::test_run_eval_preflight_triggers_on_round_zero -v`
Expected: FAIL — `run_eval` does not accept `search_state_id` parameter.

- [ ] **Step 3: Implement pre-flight check in run_eval**

In `odysseus/mcp.py`:

Add import at the top (near existing imports):
```python
from odysseus.eval.backends.registry import BackendRegistry
```

Modify `run_eval` function signature and add pre-flight check:

```python
@mcp.tool()
async def run_eval(
    prompt_version: str,
    data_source: str,
    backend: str,
    config_path: str = "outputs/run_config.yaml",
    search_state_id: str | None = None,
) -> str:
    """Run an evaluation of a prompt version against a dataset.

    Args:
        prompt_version: Prompt version identifier (e.g. "v3", "latest").
        data_source: Path to the JSONL dataset file.
        backend: Backend label matching a profile in backends/ directory.
        config_path: Path to YAML config with metrics, concurrency, retry,
                     and output settings. Defaults to "outputs/run_config.yaml".
        search_state_id: Search state ID for the optimization loop. When
                         provided and the loop is at round 0 with no history,
                         returns an action_required response instead of running
                         the eval, signalling the orchestrator to collect
                         backend configuration first.

    Returns:
        JSON object with report_path and results_path pointing to
        the full evaluation output on disk, OR an action_required
        object on first run.
    """
    # Pre-flight: on first run in loop, signal backend setup needed
    if search_state_id is not None:
        state = get_search_state(search_state_id=search_state_id)
        if state.round == 0 and len(state.round_history) == 0:
            project_dir = get_project_dir()
            registry = BackendRegistry.from_directory(project_dir / "backends")
            return json.dumps({
                "action_required": "backend_setup",
                "search_state_id": search_state_id,
                "available_backends": registry.list_profiles(),
            })

    agent = EvalRunnerAgent()
    result = await agent.run(
        {
            "prompt_version": prompt_version,
            "data_source": data_source,
            "backend": backend,
            "config_path": config_path,
        }
    )

    if "error" in result:
        err = result["error"]
        raise ToolError(f"run_eval failed: [{err['category']}] {err['detail']}")

    score_report: ScoreReport = result[ScoreReport.CONTEXT_KEY]
    return json.dumps(
        {
            "report_path": score_report.report_path,
            "results_path": score_report.results_path,
        }
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_run_eval_tool.py -v`
Expected: All tests PASS (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add odysseus/mcp.py tests/test_run_eval_tool.py
git commit -m "feat: add pre-flight check to run_eval for backend setup on first run"
```

---

## Chunk 3: Backend Setup Agent Prompt and MCP Surface

### Task 6: Create backend setup field taxonomy

**Files:**
- Create: `odysseus/agents/backend_setup_taxonomy.md`

- [ ] **Step 1: Create the taxonomy file**

Follow the format of `odysseus/agents/user_input_taxonomy.md`:

```markdown
# Backend Setup — Field Taxonomy

Classification rules for backend configuration fields.

## Blocking Fields

| Priority | Field | Classification | Rationale | Default |
|----------|-------|---------------|-----------|---------|
| 0 | `backend_choice` | Blocking | Determines whether to use existing or create new | — |
| 1 | `label` | Blocking | YAML filename; must be unique if creating new | — |
| 2 | `provider` | Blocking | Determines SDK, pricing lookup, and api_key_env | — |
| 3 | `model` | Blocking | Model identifier for API calls | — |
| 4 | `pricing` | Conditionally blocking | Auto-resolved via `get_default_pricing(provider, model)`. Blocking only if lookup returns `None` — user must then provide `input_cost_per_million_tokens`, `cached_cost_per_million_tokens`, `output_cost_per_million_tokens` | Resolved from DEFAULT_PRICING |
| 5 | `requests_per_minute` | Blocking | Rate limit; no safe universal default | — |
| 6 | `tokens_per_minute` | Blocking | Rate limit; no safe universal default | — |

## Non-blocking Fields

| Field | Classification | Rationale | Default |
|-------|---------------|-----------|---------|
| `api_key_env` | Non-blocking | Standard env var names per provider | Inferred: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `AWS_ACCESS_KEY_ID` |
| `temperature` | Non-blocking | Provider default is fine for routing | `None` |
| `max_tokens` | Non-blocking | Provider default sufficient | `None` |
| `reasoning_level` | Non-blocking | Sensible middle ground | `"medium"` |

## Status Decision Logic

1. User selects existing backend → short-circuit, no further fields needed
2. Any blocking gap unresolved → continue conversing
3. Pricing lookup succeeds → show resolved pricing, offer override, treat as resolved
4. Pricing lookup fails → pricing becomes blocking, ask user
5. All blocking fields resolved → apply non-blocking defaults → produce output
```

- [ ] **Step 2: Commit**

```bash
git add odysseus/agents/backend_setup_taxonomy.md
git commit -m "feat: add backend setup field taxonomy"
```

---

### Task 7: Create backend setup defaults table

**Files:**
- Create: `odysseus/agents/backend_setup_defaults.md`

- [ ] **Step 1: Create the defaults file**

Follow the format of `odysseus/agents/user_input_defaults.md`:

```markdown
# Backend Setup — Defaults Table

Default values for non-blocking backend configuration fields.

## Defaults

| Field | Default value | Rationale | User-facing note |
|-------|--------------|-----------|------------------|
| `api_key_env` | Inferred from provider | Standard env var per provider: `ANTHROPIC_API_KEY` for anthropic, `OPENAI_API_KEY` for openai, `AWS_ACCESS_KEY_ID` for bedrock | "API key environment variable set to `<var>` based on provider. You can specify a different env var if needed." |
| `temperature` | `None` | Uses provider default; routing responses are short and don't need temperature tuning | "No temperature specified — using provider default." |
| `max_tokens` | `None` | Provider default is sufficient for routing responses | "No max_tokens specified — using provider default." |
| `reasoning_level` | `"medium"` | Balances cost and quality for eval runs | "Reasoning level set to medium. Options: low (cheaper), medium, high (more thorough)." |

## Provider → api_key_env Mapping

| Provider | Default `api_key_env` |
|----------|-----------------------|
| `anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `bedrock` | `AWS_ACCESS_KEY_ID` |
| `mock_echo` | `None` |

## Pricing Resolution

Pricing is resolved via `get_default_pricing(provider, model)` from `odysseus/eval/pricing.py`.
- If found: show the resolved `ModelPricing` values and offer override
- If not found: pricing becomes blocking — ask user for all three cost fields

## Override Mechanism

- User can override any default in the confirmation step
- Overrides replace the full default value
- Only non-blocking fields can have defaults; blocking fields always require explicit input (except conditionally-blocking pricing when auto-resolved)
```

- [ ] **Step 2: Commit**

```bash
git add odysseus/agents/backend_setup_defaults.md
git commit -m "feat: add backend setup defaults table"
```

---

### Task 8: Create backend setup system prompt

**Files:**
- Create: `odysseus/agents/prompts/backend_setup_system.md`

- [ ] **Step 1: Create the system prompt**

Follow the structure of `odysseus/agents/prompts/user_input_system.md`:

```markdown
# Backend Setup Agent

## Job

You are the backend configuration assistant for the Odysseus eval pipeline. Your job is to help the user select an existing backend or configure a new one before the first evaluation run.

You are activated when the `run_eval` tool returns `action_required: backend_setup`. The response includes `available_backends` (existing backend labels) and `search_state_id`.

## Conversational Strategy

Use the **Structured Clarification** skill (resource: `odysseus://agents/backend-setup/clarification-skill`).

Read the field taxonomy (resource: `odysseus://agents/backend-setup/taxonomy`) and defaults table (resource: `odysseus://agents/backend-setup/defaults`) before starting.

## Domain Context

A **backend** is a configured LLM service provider (Anthropic, OpenAI, Bedrock, or mock) used to execute evaluation calls. Backends are defined as YAML files in the `/backends/` directory. Each backend specifies a provider, model, rate limits, and optionally pricing and reasoning level.

## Flow

1. Present the list of available backends from the `action_required` response.
2. Ask: "Would you like to use one of these existing backends, or create a new one?"
   - **Existing:** Confirm selection → skip to handoff
   - **New:** Continue to step 3
3. Ask for the backend **label** (will become the YAML filename). Validate it doesn't collide with existing backends.
4. Ask for **provider** (multiple choice: `anthropic`, `openai`, `bedrock`, `mock_echo`).
5. Ask for **model** (model identifier, e.g., `claude-haiku-4-5`, `gpt-4.1`).
6. Look up pricing via `get_default_pricing(provider, model)`:
   - **Found:** Show resolved pricing (input/cached/output per 1M tokens). Ask if the user wants to adjust.
   - **Not found:** Ask the user for `input_cost_per_million_tokens`, `cached_cost_per_million_tokens`, and `output_cost_per_million_tokens`.
7. Ask for **requests_per_minute** (integer, >= 1).
8. Ask for **tokens_per_minute** (integer, >= 1).
9. Apply non-blocking defaults:
   - `api_key_env`: inferred from provider (see defaults table)
   - `temperature`: `None`
   - `max_tokens`: `None`
   - `reasoning_level`: `"medium"`
10. Present the full configuration summary for confirmation.
    - If user confirms → write YAML and handoff
    - If user requests changes → loop back to the relevant field

## One Question at a Time

Ask exactly **one question per message**. Do not bundle multiple fields into a single question.

## Output: Backend YAML

When the user confirms, write the backend configuration as a YAML file at `/backends/<label>.yaml`:

```yaml
model: <model>
provider: <provider>
requests_per_minute: <rpm>
tokens_per_minute: <tpm>
pricing:
  input_cost_per_million_tokens: <input_cost>
  cached_cost_per_million_tokens: <cached_cost>
  output_cost_per_million_tokens: <output_cost>
api_key_env: <api_key_env>
reasoning_level: <reasoning_level>
# temperature and max_tokens omitted when None (use provider defaults)
```

## Handoff

After writing the YAML file (or selecting an existing backend), report the confirmed backend label. The orchestrating agent will re-call `run_eval` with this label to proceed with the evaluation.

Example handoff message:
> Backend `<label>` is ready. The orchestrating agent can now call `run_eval` with `backend="<label>"`.
```

- [ ] **Step 2: Commit**

```bash
git add odysseus/agents/prompts/backend_setup_system.md
git commit -m "feat: add backend setup agent system prompt"
```

---

### Task 9: Register MCP prompt and resources

**Files:**
- Modify: `odysseus/mcp.py`

- [ ] **Step 1: Add MCP prompt registration**

In `odysseus/mcp.py`, after the existing prompt registrations (after `odysseus_prompt_builder` around line 101), add:

```python
@mcp.prompt()
async def odysseus_backend_setup() -> list[Message]:
    """Activate the Odysseus backend setup agent.

    Use when run_eval returns action_required: backend_setup on the first
    evaluation run. Guides the user through selecting or creating a backend.
    """
    system_prompt = _load_text("odysseus/agents/prompts/backend_setup_system.md")
    return [UserMessage(content=system_prompt)]
```

- [ ] **Step 2: Add MCP resource registrations**

After the existing input agent resources (around line 113), add:

```python
@mcp.resource("odysseus://agents/backend-setup/clarification-skill")
async def backend_setup_clarification_skill() -> str:
    """Structured clarification skill — conversational strategy for the backend setup agent."""
    return _load_text("odysseus/agents/skills/structured-clarification.md")


@mcp.resource("odysseus://agents/backend-setup/taxonomy")
async def backend_setup_taxonomy() -> str:
    """Field taxonomy for backend configuration — blocking vs non-blocking fields."""
    return _load_text("odysseus/agents/backend_setup_taxonomy.md")


@mcp.resource("odysseus://agents/backend-setup/defaults")
async def backend_setup_defaults() -> str:
    """Default values and pricing resolution for backend configuration."""
    return _load_text("odysseus/agents/backend_setup_defaults.md")
```

- [ ] **Step 3: Verify MCP server starts**

Run: `uv run python -c "from odysseus.mcp import mcp; print('MCP server imports OK')"`
Expected: Prints "MCP server imports OK" without errors.

- [ ] **Step 4: Commit**

```bash
git add odysseus/mcp.py
git commit -m "feat: register backend setup MCP prompt and resources"
```

---

## Chunk 4: Documentation and Integration Test Scenario

### Task 10: Update documentation

**Files:**
- Modify: `docs/architecture.md`
- Modify: `odysseus/agents/README.md`

- [ ] **Step 1: Read current docs**

Read `docs/architecture.md` and `odysseus/agents/README.md` to find the agent tables and MCP surface tables.

- [ ] **Step 2: Add backend setup agent to agent tables**

In `docs/architecture.md`, add a row to the agent registry table:

| Backend Setup | LLM-driven | Collects backend config (provider, model, rate limits, pricing) from user on first eval run | `odysseus/agents/prompts/backend_setup_system.md` |

In `odysseus/agents/README.md`, add a matching row to the prompts table:

| `backend_setup_system.md` | Backend Setup Agent | Guides user through selecting or creating a backend before first eval run |

- [ ] **Step 3: Add MCP surface entries**

In `docs/architecture.md`, add to the MCP prompts table:

| `odysseus_backend_setup` | Backend setup agent — select or create backend |

Add to the MCP resources table:

| `odysseus://agents/backend-setup/clarification-skill` | Structured clarification skill for backend setup |
| `odysseus://agents/backend-setup/taxonomy` | Backend field taxonomy (blocking/non-blocking) |
| `odysseus://agents/backend-setup/defaults` | Backend defaults and pricing resolution |

- [ ] **Step 4: Add reasoning_level to BackendProfile docs**

In `docs/architecture.md`, find the BackendProfile or backend configuration section and add `reasoning_level` (`Literal["low", "medium", "high"] | None`) to the field listing.

- [ ] **Step 5: Commit**

```bash
git add docs/architecture.md odysseus/agents/README.md
git commit -m "docs: add backend setup agent and reasoning_level to architecture docs"
```

---

### Task 11: Add integration test scenarios

**Files:**
- Create: `tests/scenarios/54_backend_setup_existing_backend.md`
- Create: `tests/scenarios/55_backend_setup_new_backend.md`
- Create: `tests/scenarios/data/backends/anthropic.yaml` (test fixture)

- [ ] **Step 1: Create test fixture backend**

Create `tests/scenarios/data/backends/anthropic.yaml`:

```yaml
model: claude-haiku-4-5
provider: anthropic
requests_per_minute: 100
tokens_per_minute: 100000
pricing:
  input_cost_per_million_tokens: 0.80
  cached_cost_per_million_tokens: 0.08
  output_cost_per_million_tokens: 4.00
api_key_env: ANTHROPIC_API_KEY
```

- [ ] **Step 2: Create scenario 54 — existing backend selection**

Create `tests/scenarios/54_backend_setup_existing_backend.md`:

```markdown
# Scenario: Backend Setup — Select Existing Backend

## Setup
- Backend directory: `tests/scenarios/data/backends/` (contains `anthropic.yaml`)
- Search state: round 0, no history
- Precondition: `run_eval` has returned `action_required: backend_setup` with `available_backends: ["anthropic"]`

## Scenario Description
The optimization loop has just started and `run_eval` returned an `action_required` response. The orchestrator activates the Backend Setup Agent via the `odysseus_backend_setup` prompt. The user wants to use the existing `anthropic` backend rather than create a new one.

## User Simulator
You are a user who wants to use the existing anthropic backend.

**Your knowledge:**
- You want to use the `anthropic` backend that already exists
- You do not want to create a new backend

**Behavior:**
1. When the agent presents available backends and asks existing vs new, choose existing.
2. When asked which existing backend, select `anthropic`.
3. Confirm the selection when presented.

**Opening message:** "The eval runner needs a backend configured. Available backends: anthropic."

## Verification Criteria

### Flow
- [ ] Agent presented the list of available backends (including `anthropic`)
- [ ] Agent asked whether to use existing or create new
- [ ] Agent confirmed the `anthropic` backend selection

### Handoff
- [ ] Agent produced a handoff message containing the backend label `anthropic`
- [ ] No new YAML file was created in `backends/`

### One question at a time
- [ ] Each agent message contained at most one question
```

- [ ] **Step 3: Create scenario 55 — new backend creation**

Create `tests/scenarios/55_backend_setup_new_backend.md`:

```markdown
# Scenario: Backend Setup — Create New Backend

## Setup
- Backend directory: `tests/scenarios/data/backends/` (contains `anthropic.yaml`)
- Search state: round 0, no history
- Precondition: `run_eval` has returned `action_required: backend_setup` with `available_backends: ["anthropic"]`

## Scenario Description
The optimization loop has just started and `run_eval` returned an `action_required` response. The orchestrator activates the Backend Setup Agent. The user wants to create a new OpenAI backend for evaluation with GPT-4.1-mini.

## User Simulator
You are a user who wants to create a new OpenAI backend.

**Your knowledge:**
- Label: `openai-mini`
- Provider: `openai`
- Model: `gpt-4.1-mini`
- Requests per minute: 200
- Tokens per minute: 150000
- You are happy with auto-resolved pricing and default reasoning level

**Behavior:**
1. When asked existing vs new, choose new.
2. Answer each question with the values above, one at a time.
3. When pricing is shown (auto-resolved for gpt-4.1-mini), accept it.
4. When the full configuration summary is presented, confirm it.
5. Do not volunteer information before being asked.

**Opening message:** "The eval runner needs a backend configured. Available backends: anthropic. I'd like to create a new one."

## Verification Criteria

### Field collection
- [ ] Agent asked for label
- [ ] Agent asked for provider (multiple choice)
- [ ] Agent asked for model
- [ ] Agent showed auto-resolved pricing for `(openai, gpt-4.1-mini)` with input=$0.40, cached=$0.10, output=$1.60 per 1M tokens
- [ ] Agent asked for requests_per_minute
- [ ] Agent asked for tokens_per_minute

### Non-blocking defaults
- [ ] Agent applied `api_key_env: OPENAI_API_KEY` (inferred from provider)
- [ ] Agent applied `reasoning_level: "medium"` as default

### Confirmation
- [ ] Agent presented a full configuration summary before writing
- [ ] Summary included all fields: label, provider, model, pricing, rate limits, api_key_env, reasoning_level

### Output
- [ ] A YAML file was written at `backends/openai-mini.yaml`
- [ ] YAML contains `model: gpt-4.1-mini`, `provider: openai`, `requests_per_minute: 200`, `tokens_per_minute: 150000`
- [ ] YAML contains pricing section with correct values

### Handoff
- [ ] Agent produced a handoff message containing the backend label `openai-mini`

### One question at a time
- [ ] Each agent message contained at most one question
```

- [ ] **Step 4: Update scenarios README**

Add a new section to `tests/scenarios/README.md`:

```markdown
### Backend Setup Agent (54-55)

| # | Scenario | Description |
|---|----------|-------------|
| 54 | Select existing backend | User picks an existing backend, no new YAML created |
| 55 | Create new backend | User creates new OpenAI backend, pricing auto-resolved, YAML written |
```

- [ ] **Step 5: Commit**

```bash
git add tests/scenarios/54_backend_setup_existing_backend.md tests/scenarios/55_backend_setup_new_backend.md tests/scenarios/data/backends/anthropic.yaml tests/scenarios/README.md
git commit -m "feat: add backend setup integration test scenarios"
```

---

### Task 12: Run full test suite

- [ ] **Step 1: Run all unit tests**

Run: `uv run pytest tests/ -v --ignore=tests/scenarios`
Expected: All tests PASS.

- [ ] **Step 2: Run linting**

Run: `uv run ruff check .`
Expected: No errors.

- [ ] **Step 3: Run formatting**

Run: `uv run ruff format --check .`
Expected: No formatting issues (or run `uv run ruff format .` to fix).

- [ ] **Step 4: Final commit if any fixes needed**

Stage only the files that were changed by formatting/lint fixes:

```bash
git add -u
git commit -m "style: fix lint/format issues"
```
