# Scenario: Routing Analysis Agent — Startup & Input Validation

## Setup
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- System prompt: `odysseus/agents/prompts/routing_analysis_system.md`
- Skills: `odysseus/skills/classify-example/SKILL.md`, `odysseus/skills/generate-routing-rationale/SKILL.md`, `odysseus/skills/check-semantic-overlap/SKILL.md`
- MCP tools: `create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`

## Scenario Description
Verify the Routing Analysis Agent correctly reads and validates its startup inputs. The agent should read all four context dict keys (`validated_input_report_path`, `data_quality_report`, `routing_context`, `dataset_path`), initialize the vocabulary registry via `create_seed_registry`, and confirm readiness to proceed with Phase 1. If any input is missing, the agent should fail immediately with a clear error.

## User Simulator
You are the pipeline orchestrator providing context to the Routing Analysis Agent.

**Your knowledge:**
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl` (10 examples, 3 tiers: haiku/sonnet/opus)
- Routing context: 3 routes (haiku, sonnet, opus), 2 dimensions (cost, quality_score)
- A validated input report exists at a known path

**Behavior:**
1. Provide all four context dict keys to the agent and ask it to begin.
2. Verify the agent reads all inputs and initializes the registry.
3. Then provide a scenario where `dataset_path` is missing and verify the agent fails with a clear error message.

## Verification Criteria
- [ ] Agent reads all four context dict keys before starting any annotation
- [ ] Agent calls `create_seed_registry` or `resolve_registry` to initialize vocabulary
- [ ] Agent confirms readiness to begin Phase 1 after successful startup
- [ ] When `dataset_path` is missing, agent fails immediately with a descriptive error
- [ ] Agent does not attempt partial processing when inputs are incomplete
