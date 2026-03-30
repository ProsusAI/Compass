# Scenario: Prompt Builder — Initial Compilation

## Setup
- Dev dataset: `tests/scenarios/data/dev.jsonl`
- Holdout dataset: `tests/scenarios/data/holdout.jsonl`
- Split report: `tests/scenarios/data/split_report.json`
- Backend: `anthropic`

## Scenario Description
The pipeline has produced split datasets and a split report. The Prompt Builder agent now reads these artifacts, detects the provider from the backend name, compiles an initial routing prompt with all required sections (system instruction, route definitions, few-shot examples, output format), initialises a search state via `init_search_state_tool`, registers the first candidate via `register_candidate_tool`, and writes the compiled prompt to the `prompts/` directory.

## User Simulator
You are a pipeline orchestrator handing off routing analysis artifacts to the Prompt Builder agent.

**Your knowledge:**
- Dev dataset: `tests/scenarios/data/dev.jsonl` (8 examples: haiku, sonnet, opus tiers)
- Holdout dataset: `tests/scenarios/data/holdout.jsonl` (2 examples)
- Dev rationale cards: `tests/scenarios/data/dev_rationale_card_set.json`
- Holdout rationale cards: `tests/scenarios/data/holdout_rationale_card_set.json`
- Split report: `tests/scenarios/data/split_report.json`
- Backend: `anthropic`
- Problem description: "Route customer support queries to haiku (simple), sonnet (moderate), or opus (complex reasoning) tiers based on query complexity."

**Behavior:**
- Provide all artifact paths and the backend in your opening message.
- Answer any clarifying questions the agent asks (there should be none for this happy-path scenario).
- Do not provide the initial prompt text — the agent must compile it itself.

**Opening message:** "Please compile an initial routing prompt. Here are the pipeline artifacts:
- Dev dataset: `tests/scenarios/data/dev.jsonl`
- Holdout dataset: `tests/scenarios/data/holdout.jsonl`
- Split report: `tests/scenarios/data/split_report.json`
- Backend: `anthropic`
- Problem: Route customer support queries to haiku (simple), sonnet (moderate), or opus (complex reasoning) based on complexity."

## Verification Criteria

### Tool calls
- [ ] `init_search_state_tool` was called with `backend="anthropic"` (or equivalent)
- [ ] `register_candidate_tool` was called with the search state ID from `init_search_state_tool`
- [ ] A prompt version identifier was provided to `register_candidate_tool`

### Compiled prompt structure
- [ ] The compiled prompt contains a system instruction section describing the routing task
- [ ] The compiled prompt includes route definitions for haiku, sonnet, and opus
- [ ] The compiled prompt includes at least one few-shot example drawn from `dev.jsonl`
- [ ] The compiled prompt specifies an output format (route selection)

### Provider detection
- [ ] Agent correctly identified the provider as Anthropic/Claude from the backend name
- [ ] Prompt style reflects Claude conventions (e.g. XML tags or Claude-appropriate formatting)

### Persistence
- [ ] Agent wrote or referenced a prompt file path in the `prompts/` directory
