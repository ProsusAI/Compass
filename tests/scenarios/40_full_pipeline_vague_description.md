# Scenario: Full Pipeline — Vague Description Degrades Routing Context

## Setup
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- System prompt (input): `odysseus/agents/prompts/user_input_system.md`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- System prompt (routing analysis): `odysseus/agents/prompts/routing_analysis_system.md`
- Skills: `odysseus/skills/classify-example/SKILL.md`, `odysseus/skills/generate-routing-rationale/SKILL.md`, `odysseus/skills/check-semantic-overlap/SKILL.md`
- MCP tools: `submit_input_report`, `validate_dataset`, `create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`

## Scenario Description
The user provides the dataset but only a vague problem description: "sort queries by difficulty." The User Input agent attempts clarification, but the user gives minimal follow-up. Data Validation synthesizes a routing_context using both the weak description and the data, but the data signal dominates. Routing Analysis works with that weaker context. Tests that the pipeline completes even with degraded routing context quality.

## User Simulator
You are a manager who has a dataset but hasn't thought deeply about the routing problem.

**Your knowledge:**
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- You vaguely want to "sort queries by difficulty" but can't articulate the routing logic.

**Behavior:**
- Provide the dataset and a vague description in your opening message.
- When the agent asks clarifying questions, give minimal unhelpful responses like "just figure it out from the data" or "I don't know, whatever makes sense."
- When the agent mentions assumed defaults, confirm they are fine.

**Opening message:** "I have a dataset at `tests/scenarios/data/rationale_test_dataset.jsonl`. I want to sort queries by difficulty."

## Verification Criteria

### Stage 1 — User Input
- [ ] Input agent attempted to clarify the vague description (at least one clarification question asked)
- [ ] User provided unhelpful response, input agent proceeded with what it has
- [ ] `submit_input_report` called with the vague description

### Stage 2 — Data Validation
- [ ] `validate_dataset` called, schema findings pass
- [ ] routing_context `domain` field is structurally valid but relies primarily on data patterns due to weak user-provided intent
- [ ] Route descriptions are derived primarily from observed data patterns (the vague description provides minimal signal)

### Stage 3 — Routing Analysis
- [ ] Routing Analysis does not fail — it uses the data-derived context for classification
- [ ] Classification quality may be lower but annotations are structurally complete (all required fields present)
- [ ] All 4 phases complete
- [ ] Output contract satisfied: all 7 context keys set despite weak context
