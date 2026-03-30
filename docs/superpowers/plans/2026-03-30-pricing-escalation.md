# Backend Pricing Escalation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-resolve backend pricing in the sub-agent via `get_default_pricing`, escalating to the orchestrator when lookup fails, so users aren't always asked for manual pricing input.

**Architecture:** Tighten `_check_stage_3` to validate pricing in backend YAMLs (returning a `detail` signal when missing). Update the backend setup prompt to auto-resolve pricing and support a "pricing update" re-dispatch mode. Update the HARD_STOP template so the orchestrator knows how to handle the escalation.

**Tech Stack:** Python, Pydantic, PyYAML, pytest

**Spec:** `docs/superpowers/specs/2026-03-30-pricing-escalation-design.md`

---

## Chunk 1: Stage 3 Completion Check with Pricing Validation

### Task 1: Update `_check_stage_3` to validate pricing

**Files:**
- Modify: `odysseus/agents/pipeline/status.py:421-430`
- Modify: `tests/test_pipeline_status.py:113-117` (fixture)
- Test: `tests/test_pipeline_status.py`

- [ ] **Step 1: Write failing test — incomplete when YAML has no pricing**

In `tests/test_pipeline_status.py`, add:

```python
class TestStage3PricingValidation:
    def test_incomplete_when_yaml_has_no_pricing(self, tmp_path: Path) -> None:
        """Stage 3 is incomplete when backend YAML exists but has no pricing."""
        _setup_through_stage2(tmp_path, "r1")
        backends = tmp_path / "backends"
        backends.mkdir(parents=True, exist_ok=True)
        (backends / "mock.yaml").write_text(
            "model: claude-haiku-4-5\n"
            "provider: anthropic\n"
            "requests_per_minute: 100\n"
            "tokens_per_minute: 100000\n"
        )
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][2]["status"] == "complete"  # stage 2 OK
        assert result["stages"][3]["status"] == "incomplete"
        assert result["stages"][3]["detail"] == "pricing_missing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_status.py::TestStage3PricingValidation::test_incomplete_when_yaml_has_no_pricing -xvs`
Expected: FAIL — currently returns "complete" because `_check_stage_3` only checks file existence.

- [ ] **Step 3: Write failing test — incomplete (not crash) when YAML is malformed**

```python
    def test_incomplete_when_yaml_is_malformed(self, tmp_path: Path) -> None:
        """Stage 3 treats malformed YAML as incomplete, not a crash."""
        _setup_through_stage2(tmp_path, "r1")
        backends = tmp_path / "backends"
        backends.mkdir(parents=True, exist_ok=True)
        (backends / "bad.yaml").write_text("not: valid: yaml: [")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][3]["status"] == "incomplete"
```

- [ ] **Step 4: Write failing test — complete when at least one YAML has pricing**

```python
    def test_complete_when_one_backend_has_pricing(self, tmp_path: Path) -> None:
        """Stage 3 is complete when at least one backend has valid pricing (any-semantics)."""
        _setup_through_stage2(tmp_path, "r1")
        backends = tmp_path / "backends"
        backends.mkdir(parents=True, exist_ok=True)
        # Backend without pricing
        (backends / "no_pricing.yaml").write_text(
            "model: custom-model\n"
            "provider: openai\n"
            "requests_per_minute: 50\n"
            "tokens_per_minute: 50000\n"
        )
        # Backend with pricing
        (backends / "with_pricing.yaml").write_text(
            "model: claude-haiku-4-5\n"
            "provider: anthropic\n"
            "requests_per_minute: 100\n"
            "tokens_per_minute: 100000\n"
            "pricing:\n"
            "  input_cost_per_million_tokens: 0.80\n"
            "  cached_cost_per_million_tokens: 0.08\n"
            "  output_cost_per_million_tokens: 4.00\n"
        )
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][3]["status"] == "complete"
```

- [ ] **Step 5: Run all three tests to verify they fail**

Run: `uv run pytest tests/test_pipeline_status.py::TestStage3PricingValidation -xvs`
Expected: FAIL

- [ ] **Step 6: Implement `_check_stage_3` pricing validation**

Replace `_check_stage_3` in `odysseus/agents/pipeline/status.py:421-430` with:

```python
def _check_stage_3(project_dir: Path) -> tuple[str, list[str], str]:
    """Stage 3: Backend Configured — checks project_dir/backends/*.yaml.

    At least one backend must have valid pricing for the stage to be complete.
    Malformed YAML files are silently skipped (treated as incomplete).
    """
    from odysseus.eval.backends.profile import BackendProfile

    backends_dir = project_dir / "backends"
    if not backends_dir.is_dir():
        return "incomplete", [], ""
    yaml_files = list(backends_dir.glob("*.yaml"))
    if not yaml_files:
        return "incomplete", [], ""

    artifacts = [str(f) for f in sorted(yaml_files)]
    has_priced_backend = False

    for yf in yaml_files:
        try:
            profile = BackendProfile.from_yaml(yf)
            if profile.pricing is not None:
                has_priced_backend = True
                break
        except Exception:
            continue

    if not has_priced_backend:
        return "incomplete", artifacts, "pricing_missing"
    return "complete", artifacts, ""
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline_status.py::TestStage3PricingValidation -xvs`
Expected: PASS

- [ ] **Step 8: Update `_setup_through_stage3` fixture**

The existing helper writes `label: mock` which is invalid for `BackendProfile`. Find the `_setup_through_stage3` function in `tests/test_pipeline_status.py` and update it:

```python
def _setup_through_stage3(base: Path, run_id: str) -> None:
    """Set up stages 1-3 complete: validation + split + backend."""
    _setup_through_stage2(base, run_id)
    (base / "backends").mkdir(parents=True, exist_ok=True)
    (base / "backends" / "mock.yaml").write_text(
        "model: mock-model\n"
        "provider: mock_echo\n"
        "requests_per_minute: 100\n"
        "tokens_per_minute: 100000\n"
        "pricing:\n"
        "  input_cost_per_million_tokens: 0.0\n"
        "  cached_cost_per_million_tokens: 0.0\n"
        "  output_cost_per_million_tokens: 0.0\n"
    )
```

- [ ] **Step 9: Run full test suite to verify no regressions**

Run: `uv run pytest tests/test_pipeline_status.py -xvs`
Expected: ALL PASS — existing tests that use `_setup_through_stage3` continue to work because the mock YAML now has valid pricing.

- [ ] **Step 10: Lint and commit**

```bash
uv run ruff check odysseus/agents/pipeline/status.py tests/test_pipeline_status.py
uv run ruff format odysseus/agents/pipeline/status.py tests/test_pipeline_status.py
git add odysseus/agents/pipeline/status.py tests/test_pipeline_status.py
git commit -m "feat: validate pricing in _check_stage_3, return pricing_missing detail"
```

---

## Chunk 2: HARD_STOP Template and Prompt Updates

### Task 2: Update Stage 3 HARD_STOP template

**Files:**
- Modify: `odysseus/agents/pipeline/status.py:156-174`

- [ ] **Step 1: Update the HARD_STOP template**

Replace the stage 3 entry in `_STAGE_ACTIONS` at `status.py:156-174`:

```python
    3: (
        "Configure at least one routing backend (create a backends/*.yaml file). "
        "REQUIRED: activate prompt 'odysseus_backend_setup' for guided configuration.",
        [],
        ["odysseus_backend_setup"],
        (
            "<HARD_STOP>\n"
            "You MUST NOT perform backend setup from the current context.\n\n"
            "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
            "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='backend_setup') BEFORE spawning the sub-agent.\n\n"
            "Sub-agent tools: get_pipeline_status, get_default_pricing\n"
            "Your tools: get_pipeline_status only\n\n"
            "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
            "then call get_pipeline_status.\n"
            "If Stage 3 is not complete:\n"
            "  - Check the status detail field. If detail is 'pricing_missing', ask the user\n"
            "    for input_cost_per_million_tokens, cached_cost_per_million_tokens, and\n"
            "    output_cost_per_million_tokens. Then re-dispatch the sub-agent with these\n"
            "    pricing values in the conversation context.\n"
            "  - Otherwise, re-dispatch the sub-agent. Do not perform backend setup yourself.\n"
            "  - If Stage 3 remains incomplete after 2 re-dispatches, report the error to the\n"
            "    user and halt.\n"
            "</HARD_STOP>\n\n"
            "<stage_system_prompt></stage_system_prompt>"
        ),
    ),
```

- [ ] **Step 2: Run existing HARD_STOP test to verify no regression**

Run: `uv run pytest tests/test_pipeline_status.py -k "stage" -xvs`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/pipeline/status.py
git commit -m "feat: add pricing escalation clause to stage 3 HARD_STOP template"
```

### Task 3: Update backend setup system prompt

**Files:**
- Modify: `odysseus/agents/prompts/backend_setup_system.md`

- [ ] **Step 1: Add pricing update mode (step 0) and update step 2, step 6, and exit verification**

Replace the full content of `backend_setup_system.md` with:

```markdown
## Entry verification

Your first action — before anything else — is to call `get_pipeline_status`.
Confirm the response shows `current_stage: 3`.
If the stage does not match, stop immediately and report:
"This sub-agent was spawned for stage 3 but the pipeline is at stage N. Aborting."
Do not call any tools. Do not proceed.

---

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

0. **Pricing update mode:** Check if you were dispatched with pricing values in your conversation context (the orchestrator will include them after collecting from the user). If so, load the existing backend YAML at `/backends/<label>.yaml`, merge the provided pricing into it, write the updated YAML, and skip to exit verification.
1. Present the list of available backends from the `action_required` response.
2. Ask: "Would you like to use one of these existing backends, or create a new one?"
   - **Existing:** Load the selected backend YAML. If `pricing` is present, confirm selection → skip to step 10. If `pricing` is null, run `get_default_pricing(provider, model)` for that backend. If found, update YAML with pricing and confirm. If not found, escalate (same as step 6 "Not found").
   - **New:** Continue to step 3
3. Ask for the backend **label** (will become the YAML filename). Validate it doesn't collide with existing backends.
4. Ask for **provider** (multiple choice: `anthropic`, `openai`, `bedrock`, `mock_echo`).
5. Ask for **model** (model identifier, e.g., `claude-haiku-4-5`, `gpt-4.1`).
6. Look up pricing via `get_default_pricing(provider, model)`:
   - **Found:** Apply the resolved pricing. Show it in the summary (step 10).
   - **Not found:** Write the YAML without pricing. Exit immediately with the message: "PRICING_MISSING for {provider}/{model}. The user must provide: input_cost_per_million_tokens, cached_cost_per_million_tokens, and output_cost_per_million_tokens."
7. Ask for **requests_per_minute** (integer, >= 1).
8. Ask for **tokens_per_minute** (integer, >= 1).
9. Apply non-blocking defaults:
   - `api_key_env`: inferred from provider (see defaults table)
   - `temperature`: `None`
   - `max_tokens`: `None`
   - `reasoning_level`: `"medium"`
10. Present the full configuration summary for confirmation.
    - If user confirms → write YAML
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

---

## Exit verification

Before you finish, call `get_pipeline_status` and confirm your stage shows `status: complete`.
If any required artifacts are missing, fix them before exiting — do not exit with an incomplete stage.

**Exception:** If pricing lookup failed and you wrote the YAML without pricing, exit with an incomplete stage. Your final message must explain what pricing fields the user needs to provide.
```

- [ ] **Step 2: Commit**

```bash
git add odysseus/agents/prompts/backend_setup_system.md
git commit -m "feat: add pricing auto-resolution and update mode to backend setup prompt"
```

### Task 4: Update taxonomy and defaults docs

**Files:**
- Modify: `odysseus/agents/backend_setup_taxonomy.md`
- Modify: `odysseus/agents/backend_setup_defaults.md`

- [ ] **Step 1: Update taxonomy — pricing field classification**

In `backend_setup_taxonomy.md`, replace the pricing row (line 13):

Old:
```
| 4 | `pricing` | Conditionally blocking | Auto-resolved via `get_default_pricing(provider, model)`. Blocking only if lookup returns `None` — user must then provide `input_cost_per_million_tokens`, `cached_cost_per_million_tokens`, `output_cost_per_million_tokens` | Resolved from DEFAULT_PRICING |
```

New:
```
| 4 | `pricing` | Auto-resolved | Resolved silently via `get_default_pricing`. Escalates to orchestrator if lookup fails — never asked by this agent directly. | Resolved from DEFAULT_PRICING |
```

Also update the Status Decision Logic section (lines 27-32):

Old:
```
3. Pricing lookup succeeds → show resolved pricing, offer override, treat as resolved
4. Pricing lookup fails → pricing becomes blocking, ask user
```

New:
```
3. Pricing lookup succeeds → apply resolved pricing, show in summary
4. Pricing lookup fails → write YAML without pricing, exit with PRICING_MISSING — orchestrator collects pricing from user and re-dispatches
```

- [ ] **Step 2: Update defaults — pricing resolution section**

In `backend_setup_defaults.md`, replace lines 39-40:

Old:
```
- If found: show the resolved `ModelPricing` values and offer override
- If not found: pricing becomes blocking — ask user for the required cost fields (at minimum input, cached/read, output; include cache-write fields for Anthropic if not using table defaults)
```

New:
```
- If found: apply the resolved `ModelPricing` values, show in confirmation summary
- If not found: write YAML without pricing and exit — the orchestrator collects pricing from the user and re-dispatches the sub-agent in pricing update mode
```

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/backend_setup_taxonomy.md odysseus/agents/backend_setup_defaults.md
git commit -m "docs: update taxonomy and defaults for pricing auto-resolution"
```

---

## Chunk 3: Integration Verification

### Task 5: Run full test suite and lint

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -x`
Expected: ALL PASS

- [ ] **Step 2: Lint and type check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: No errors

- [ ] **Step 3: Fix any issues found, commit if needed**

**Deferred:** The spec calls for a scenario test in `tests/scenarios/` covering the full orchestrator escalation path. This requires a running MCP server and is best written as a separate follow-up after the core logic is verified.
