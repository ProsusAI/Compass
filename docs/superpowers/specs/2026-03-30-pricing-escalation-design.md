# Backend Pricing: Auto-Resolution with Orchestrator Escalation

## Problem

In non-interactive sub-agent environments (Cursor, some Claude Code setups), the orchestrator asks all backend setup questions upfront before dispatching the sub-agent. The `get_default_pricing` tool is only available inside the `backend_setup` stage scope, so the orchestrator can't call it. Result: the user is **always** asked for manual pricing input, even when defaults exist in the pricing table.

## Design

Move pricing out of the orchestrator's upfront question flow. The backend setup sub-agent auto-resolves pricing after dispatch using `get_default_pricing`. If lookup fails, the sub-agent escalates back to the orchestrator, which relays the pricing question to the user and re-dispatches.

## Flow

### Happy path (pricing found)

```
Orchestrator                          Sub-agent
    │                                     │
    ├─ asks: label, provider, model,      │
    │        rpm, tpm                      │
    ├─ start_stage("backend_setup")       │
    ├─ spawns sub-agent ─────────────────►│
    │                                     ├─ get_default_pricing(provider, model)
    │                                     │  → found: true
    │                                     ├─ writes YAML (with pricing)
    │                                     ├─ get_pipeline_status → complete
    │                                     ├─ exits
    ├─ complete_stage()                   │
    ├─ get_pipeline_status → stage 4      │
    └─ continues pipeline                 │
```

### Escalation path (pricing not found)

```
Orchestrator                          Sub-agent
    │                                     │
    ├─ asks: label, provider, model,      │
    │        rpm, tpm                      │
    ├─ start_stage("backend_setup")       │
    ├─ spawns sub-agent ─────────────────►│
    │                                     ├─ get_default_pricing(provider, model)
    │                                     │  → found: false
    │                                     ├─ writes YAML (WITHOUT pricing)
    │                                     ├─ exits with message:
    │                                     │  "PRICING_MISSING: {provider}/{model}.
    │  ◄──────────────────────────────────┤   User must provide pricing."
    ├─ complete_stage()                   │
    ├─ get_pipeline_status → incomplete   │
    │  (detail: "pricing_missing")        │
    ├─ asks user for pricing fields       │
    ├─ re-dispatches sub-agent ──────────►│
    │  (mode: "pricing_update",           ├─ updates YAML with provided pricing
    │   pricing values in context)        ├─ get_pipeline_status → complete
    │  ◄──────────────────────────────────┤
    ├─ complete_stage()                   │
    ├─ get_pipeline_status → stage 4      │
    └─ continues pipeline                 │
```

### Existing backend path

When the user selects an existing backend at step 2, the sub-agent checks its pricing before confirming:

- **Pricing present:** Confirm selection, proceed to exit.
- **Pricing missing:** Run `get_default_pricing(provider, model)` for that backend. If found, update the YAML. If not found, escalate (same as new-backend escalation path).

## Changes Required

### 1. Stage 3 completion check (`status.py`: `_check_stage_3`)

**Current:** Checks that at least one `*.yaml` file exists in `backends/`.

**Change:** Also validate that the YAML contains a non-null `pricing` section. Use a lazy import of `BackendProfile` inside the function to avoid adding top-level dependencies to `status.py`. Wrap the parse in `try/except` (following the `_check_stage_5` pattern) — malformed YAML is treated as incomplete, not as a crash.

Semantics: **`any()`** — stage 3 is complete when at least one backend has valid pricing. Backends without pricing are not blocking if another valid one exists.

When incomplete due to missing pricing, return `detail: "pricing_missing"` in the stage check tuple. This gives the orchestrator a machine-readable signal rather than relying on sub-agent message parsing.

### 2. Backend setup system prompt (`backend_setup_system.md`)

**Change step 6** (pricing) from an interactive question to auto-resolution:

```markdown
6. Look up pricing via `get_default_pricing(provider, model)`:
   - **Found:** Apply the resolved pricing. Show it in the summary (step 10).
   - **Not found:** Write the YAML without pricing. Exit immediately with
     the message: "PRICING_MISSING for {provider}/{model}. The user must
     provide: input_cost_per_million_tokens, cached_cost_per_million_tokens,
     and output_cost_per_million_tokens."
```

**Add "pricing update" mode** to the flow (new step before step 1):

```markdown
0. Check if you were dispatched with pricing values in your conversation
   context (the orchestrator will include them after collecting from the user).
   If so, load the existing backend YAML at `/backends/<label>.yaml`, merge
   the provided pricing, write the updated YAML, and skip to exit verification.
```

**Add existing-backend pricing check** to step 2:

```markdown
2. Ask: "Would you like to use one of these existing backends, or create a new one?"
   - **Existing:** Load the selected backend YAML. If `pricing` is present,
     confirm selection → skip to step 10. If `pricing` is null, run
     `get_default_pricing(provider, model)` for that backend. If found,
     update YAML with pricing and confirm. If not found, escalate
     (same as step 6 "Not found").
   - **New:** Continue to step 3.
```

**Change exit verification:**

```markdown
## Exit verification

Before you finish, call `get_pipeline_status` and confirm your stage shows
`status: complete`. If any required artifacts are missing, fix them before
exiting — do not exit with an incomplete stage.

**Exception:** If pricing lookup failed and you wrote the YAML without
pricing, exit with an incomplete stage. Your final message must explain
what pricing fields the user needs to provide.
```

Note: the sub-agent never calls `complete_stage` (it's an orchestrator-scope tool not in the sub-agent's tool set). The "exit without completing" instruction means: exit knowing the stage is incomplete, rather than trying to fix it.

### 3. Stage 3 HARD_STOP template (`status.py`: stage 3 entry)

Update the POST-EXIT instructions with a structured escalation clause:

```
POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'),
then call get_pipeline_status.
If Stage 3 is not complete:
  - Check the status detail field. If detail is "pricing_missing", ask the user
    for input_cost_per_million_tokens, cached_cost_per_million_tokens, and
    output_cost_per_million_tokens. Then re-dispatch the sub-agent with these
    pricing values in the conversation context.
  - Otherwise, re-dispatch the sub-agent. Do not perform backend setup yourself.
  - If Stage 3 remains incomplete after 2 re-dispatches, report the error to the
    user and halt.
```

### 4. Backend setup taxonomy (`backend_setup_taxonomy.md`)

Update the pricing field classification:

| Priority | Field | Category | Notes |
|----------|-------|----------|-------|
| 4 | pricing | Auto-resolved | Resolved silently via `get_default_pricing`. Escalates to orchestrator if lookup fails. Never asked by this agent directly. |

### 5. Backend setup defaults (`backend_setup_defaults.md`)

Update to reflect that pricing is always auto-resolved, not conditionally blocking:

> **pricing**: Auto-resolved via `get_default_pricing(provider, model)`. If lookup returns no result, the agent exits without completing the stage and the orchestrator collects pricing from the user.

## What Does NOT Change

- `get_default_pricing` tool stays in `backend_setup` stage scope only — no new tools for the orchestrator.
- `complete_stage` return value stays a plain string — no structured metadata added.
- No new pipeline states — stages remain binary (complete/incomplete). The `detail` field in the stage check tuple already exists; we just populate it with a specific value.
- The interactive flow (where the sub-agent CAN talk to the user) still works: the sub-agent auto-resolves pricing silently, and only if it fails does the escalation path trigger. In interactive environments the orchestrator can still relay the question.

## Implementation Notes

- **Lazy import in `_check_stage_3`:** Import `BackendProfile` inside the function body, not at module level, to keep `status.py` lightweight and avoid circular import risk.
- **Error handling:** Wrap `BackendProfile.from_yaml()` in `try/except (ValidationError, yaml.YAMLError, Exception)`. Malformed YAML = incomplete, not a crash.
- **Test fixture updates:** The existing `_setup_through_stage3` helper in `tests/test_pipeline_status.py` writes minimal YAML (`label: mock`). This must be updated to write valid `BackendProfile` YAML with pricing, since `_check_stage_3` will now parse the file.

## Testing

- **Unit test:** `_check_stage_3` returns incomplete with `detail="pricing_missing"` when YAML exists but `pricing` is null.
- **Unit test:** `_check_stage_3` returns incomplete (not crash) when YAML is malformed.
- **Unit test:** `_check_stage_3` returns complete when at least one YAML has valid pricing.
- **Unit test:** `_check_stage_3` returns complete when one of two YAMLs has pricing (any-semantics).
- **Scenario test:** New scenario in `tests/scenarios/` covering the escalation path — sub-agent exits without completing, orchestrator reads `pricing_missing` detail, asks user, re-dispatches with pricing update mode.
