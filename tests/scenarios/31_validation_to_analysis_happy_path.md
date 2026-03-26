# Scenario: Validation → Routing Analysis — Happy Path

## Setup
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- System prompt (validation): `odysseus/agents/prompts/data_validation_system.md`
- System prompt (routing analysis): `odysseus/agents/prompts/routing_analysis_system.md`
- Skills: `odysseus/skills/classify-example/SKILL.md`, `odysseus/skills/generate-routing-rationale/SKILL.md`, `odysseus/skills/check-semantic-overlap/SKILL.md`
- MCP tools: `validate_dataset`, `create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`

## Scenario Description
End-to-end integration across two agents: Data Validation validates a clean 10-row dataset, produces a passing data quality report and routing_context, then Routing Analysis receives all 4 context dict keys and completes all 4 phases (classify, rationale, validate, split). Tests the basic handoff contract between these two agents.

## User Simulator
You are the pipeline orchestrator coordinating the Data Validation and Routing Analysis agents.

**Your knowledge:**
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl` — 10 labeled routing examples, 3 tiers (haiku/sonnet/opus)
- Problem description: "Route customer queries to haiku, sonnet, or opus tiers based on complexity — simple factual questions to haiku, moderate tasks to sonnet, complex reasoning to opus."
- A validated input report exists with: accuracy >= 0.90 target, evaluation_threshold 0.80, data_split_ratio 0.70, max_iterations 10.

**Behavior:**
1. Ask the Data Validation agent to validate `tests/scenarios/data/rationale_test_dataset.jsonl`.
2. After validation completes, provide all four context dict keys to the Routing Analysis agent:
   - `validated_input_report_path`: reference to the input report
   - `data_quality_report`: the full report from validation
   - `routing_context`: the routing context YAML block from validation
   - `dataset_path`: `tests/scenarios/data/rationale_test_dataset.jsonl`
3. Let the Routing Analysis agent run through all four phases autonomously.

**Opening message:** "Please validate the dataset at `tests/scenarios/data/rationale_test_dataset.jsonl` for our routing optimization pipeline. The problem is routing customer queries to haiku, sonnet, or opus tiers based on complexity."

## Verification Criteria
- [ ] `validate_dataset` was called with `tests/scenarios/data/rationale_test_dataset.jsonl`
- [ ] All schema findings have status `pass`
- [ ] routing_context has 3 routes (haiku, sonnet, opus) with descriptions derived from the data
- [ ] Routing Analysis received all 4 context dict keys before starting Phase 1
- [ ] Agent called `create_seed_registry` or `resolve_registry` to initialize vocabulary
- [ ] Phase 1: All 10 examples classified with `intent_pattern` and `complexity_structure`
- [ ] Phase 2: All 10 examples have `route_exclusions` and `ambiguity_tags`
- [ ] Phase 3: `validate_rationale_card_set` called, `check-semantic-overlap` skill activated
- [ ] Phase 4: `stratified_split` called, dev and holdout sets produced
- [ ] Output contract satisfied: all 7 context keys set (5 Prompt Builder + 2 Final Reporting)
- [ ] dataset_hash in routing analysis artifacts matches the validated dataset
