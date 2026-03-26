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
