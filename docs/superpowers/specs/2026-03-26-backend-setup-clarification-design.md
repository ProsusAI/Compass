# Backend Setup Clarification Design

**Date:** 2026-03-26
**Branch:** `feature/backend-setup-clarification`
**Status:** Draft

## Problem

The eval runner currently accepts a backend label and assumes the corresponding YAML profile exists. There is no mechanism for the user to configure which backend to use at the start of an optimization loop. Users should be prompted to select or create a backend on the first eval run, giving them control over provider, model, rate limits, and pricing.

## Solution

Add a **pre-flight check** to the `run_eval` MCP tool that triggers a backend setup clarification flow on the first eval run in an optimization loop. A new MCP prompt (`odysseus_backend_setup`) uses the structured-clarification skill to collect all information needed for a valid `BackendProfile`, then writes the YAML file.

## Trigger Condition

The pre-flight check fires when **all** of the following are true:

- `search_state_id` is provided to `run_eval`
- `SearchState.round == 0`
- `len(SearchState.round_history) == 0`

On subsequent runs (round > 0 or history non-empty), `run_eval` proceeds normally.

## Pre-flight Response

When the trigger fires, `run_eval` returns early with:

```json
{
  "action_required": "backend_setup",
  "search_state_id": "abc123",
  "available_backends": ["anthropic", "openai", "mock-echo"]
}
```

`available_backends` is populated by scanning `/backends/*.yaml` filenames (without extension). The orchestrating agent (Review Agent) routes the user through the `odysseus_backend_setup` MCP prompt, then re-calls `run_eval` with the confirmed backend label.

## Field Taxonomy

### Blocking Fields

| Priority | Field | Type | Rationale |
|----------|-------|------|-----------|
| 0 | `backend_choice` | `"existing"` or `"new"` | Gates the entire flow. If `"existing"`, user picks from `available_backends` and the flow short-circuits — no further questions. |
| 1 | `label` | `str` | YAML filename in `/backends/`. Must be unique if creating new. |
| 2 | `provider` | `Literal["anthropic", "openai", "bedrock", "mock_echo"]` | Determines SDK, pricing lookup, and `api_key_env` default. |
| 3 | `model` | `str` | Model identifier (e.g., `claude-haiku-4-5`, `gpt-5.2`). |
| 4 | `pricing` | `ModelPricing` | **Conditionally blocking.** Auto-resolved if `(provider, model)` exists in `DEFAULT_PRICING`. Blocking if not found — user must provide `input_cost_per_million_tokens`, `cached_cost_per_million_tokens`, and `output_cost_per_million_tokens`. |
| 5 | `requests_per_minute` | `int >= 1` | Rate limit. No safe universal default. |
| 6 | `tokens_per_minute` | `int >= 1` | Rate limit. No safe universal default. |

### Non-blocking Fields

| Field | Type | Default | Rationale |
|-------|------|---------|-----------|
| `api_key_env` | `str` | Inferred from provider: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `AWS_ACCESS_KEY_ID` | Standard env var names per provider. |
| `temperature` | `float \| None` | `None` (provider default) | Routing responses are short; provider default is fine. |
| `max_tokens` | `int \| None` | `None` (provider default) | Provider default sufficient for routing. |
| `reasoning_level` | `str \| None` | `"medium"` | Sensible middle ground for cost/quality balance. |

### Omitted Fields

`api_base`, `extra_params`, `provider_params` — too advanced for the clarification flow. Power users can edit the YAML directly after creation.

## Clarification Flow

```
1. Present available_backends from pre-flight response
2. Ask: "Use an existing backend or create a new one?"
   ├─ Existing → confirm selection → short-circuit to handoff
   └─ New → continue to step 3
3. Ask for label (validate uniqueness against /backends/)
4. Ask for provider (multiple choice: anthropic, openai, bedrock, mock_echo)
5. Ask for model
6. Look up DEFAULT_PRICING[(provider, model)]
   ├─ Found → show resolved pricing, offer override → step 7
   └─ Not found → ask for input_cost, cached_cost, output_cost → step 7
7. Ask for requests_per_minute
8. Ask for tokens_per_minute
9. Apply non-blocking defaults (api_key_env, temperature, max_tokens, reasoning_level)
10. Present full config summary for confirmation
    ├─ User confirms → write YAML, return label
    └─ User requests changes → loop back to relevant step
```

## Default Pricing Table

A `DEFAULT_PRICING` dict in `odysseus/eval/backends/pricing.py`, keyed by `(provider, model)` tuples mapping to `ModelPricing` instances. Populated with current rates for common models.

Example entries:

| Provider | Model | Input $/1M | Cached $/1M | Output $/1M |
|----------|-------|-----------|-------------|-------------|
| anthropic | claude-haiku-4-5 | 0.80 | 0.08 | 4.00 |
| anthropic | claude-sonnet-4-5 | 3.00 | 0.30 | 15.00 |
| anthropic | claude-opus-4 | 15.00 | 1.50 | 75.00 |
| openai | gpt-4.1 | 2.00 | 0.50 | 8.00 |
| openai | gpt-4.1-mini | 0.40 | 0.10 | 1.60 |
| openai | gpt-4.1-nano | 0.10 | 0.025 | 0.40 |
| openai | o3 | 2.00 | 0.50 | 8.00 |
| openai | o4-mini | 1.10 | 0.275 | 4.40 |

Bedrock pricing mirrors the underlying model but may differ — entries should reflect Bedrock-specific rates.

If `(provider, model)` is not in the dict, pricing becomes a blocking field.

## Changes to Existing Code

### `BackendProfile` (`odysseus/eval/backends/profile.py`)

Add field:

```python
reasoning_level: str | None = None
```

### Backend Implementations

Pass `reasoning_level` to API calls where supported:
- **AnthropicBackend:** Map to `thinking` budget parameter
- **OpenAIBackend:** Map to `reasoning_effort` parameter
- **BedrockBackend:** Pass through if supported by the underlying model
- **MockEchoBackend:** Ignore

### `run_eval` MCP Tool (`odysseus/mcp.py`)

Add `search_state_id: str | None = None` parameter. When provided:

```python
if search_state_id:
    state = get_search_state(search_state_id)
    if state.round == 0 and len(state.round_history) == 0:
        available = [p.stem for p in project_dir.glob("backends/*.yaml")]
        return json.dumps({
            "action_required": "backend_setup",
            "search_state_id": search_state_id,
            "available_backends": available,
        })
```

When `search_state_id` is `None`, no pre-flight check — backwards compatible.

### New MCP Prompt Registration (`odysseus/mcp.py`)

```python
@mcp.prompt()
def odysseus_backend_setup() -> list[PromptMessage]:
    # Load system prompt from odysseus/agents/prompts/backend_setup_system.md
    # Include taxonomy and defaults as resources
```

### New MCP Resources

| URI | Source File |
|-----|------------|
| `odysseus://agents/backend-setup/taxonomy` | `odysseus/agents/backend_setup_taxonomy.md` |
| `odysseus://agents/backend-setup/defaults` | `odysseus/agents/backend_setup_defaults.md` |

## New Files

| File | Purpose |
|------|---------|
| `odysseus/agents/prompts/backend_setup_system.md` | System prompt for backend setup agent |
| `odysseus/agents/backend_setup_taxonomy.md` | Field taxonomy (blocking/non-blocking classification) |
| `odysseus/agents/backend_setup_defaults.md` | Defaults table with pricing lookup reference |
| `odysseus/eval/backends/pricing.py` | `DEFAULT_PRICING` dict with known model pricing |

## Handoff

The backend setup agent writes the YAML file to `/backends/<label>.yaml` and returns the label. No new MCP tool is needed — the agent writes the file directly. The `BackendRegistry.from_directory()` picks it up on the next `run_eval` call.

## Testing

- Unit test for pre-flight check: round 0 + no history triggers `action_required`; round > 0 proceeds normally
- Unit test for `DEFAULT_PRICING` lookup: known models resolve, unknown models return `None`
- Unit test for `BackendProfile` with `reasoning_level` field
- Integration test scenario in `tests/scenarios/`: full flow from `run_eval` → backend setup clarification → YAML written → `run_eval` succeeds
