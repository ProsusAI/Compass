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
