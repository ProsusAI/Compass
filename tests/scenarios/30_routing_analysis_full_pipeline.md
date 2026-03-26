# Scenario: Routing Analysis Agent — Full Pipeline

## Setup
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- System prompt: `odysseus/agents/prompts/routing_analysis_system.md`
- Skills: `odysseus/skills/classify-example/SKILL.md`, `odysseus/skills/generate-routing-rationale/SKILL.md`, `odysseus/skills/check-semantic-overlap/SKILL.md`
- MCP tools: `create_seed_registry`, `resolve_registry`, `validate_rationale_card_set`, `prune_registry`, `stratified_split`

```yaml
routing_context:
  domain: >
    LLM model tier routing for query complexity. Queries span general
    knowledge, mathematics, creative writing, and simple computation.
  routes:
    - name: "haiku"
      description: "Handles simple factual lookups and single-step tasks"
    - name: "sonnet"
      description: "Handles moderate tasks requiring multi-step reasoning"
    - name: "opus"
      description: "Handles complex analysis with sequential dependencies"
  routing_dimensions:
    - name: cost
      direction: lower_is_better
      description: "Per-query inference cost"
    - name: quality_score
      direction: higher_is_better
      description: "Response quality rating"
  route_ordering:
    dimension: quality_score
    order: ["haiku", "sonnet", "opus"]
  seed_vocabulary:
    intent_pattern: []
    complexity_structure: []
    ambiguity_tags: []
```

## Scenario Description
The Routing Analysis Agent runs the complete four-phase pipeline on the 10-example test dataset. Phase 1 classifies all examples (intent_pattern + complexity_structure). Phase 2 generates routing rationales (route_exclusions + ambiguity_tags). Phase 3 validates the card set and fixes any issues. Phase 4 splits into dev/holdout with matched card sets.

## User Simulator
You are the pipeline orchestrator providing context and monitoring the Routing Analysis Agent.

**Your knowledge:**
- Dataset has 10 examples across 3 tiers (haiku, sonnet, opus)
- Expected output: dev.jsonl, holdout.jsonl, dev_rationale_card_set.json, holdout_rationale_card_set.json, split_report.json, vocabulary_registry.json
- Default split ratio: 0.30 dev / 0.70 holdout

**Behavior:**
1. Provide all four context dict keys to the agent.
2. Let the agent run through all four phases autonomously.
3. After completion, verify the output artifacts exist and are structurally valid.

## Verification Criteria

### Phase 1 — Classification
- [ ] Agent activates `classify-example` skill
- [ ] All 10 examples have `intent_pattern` and `complexity_structure` assigned
- [ ] Values are kebab-case and present in the vocabulary registry
- [ ] Checkpoint written to scratch directory

### Phase 2 — Rationale
- [ ] Agent activates `generate-routing-rationale` skill
- [ ] All 10 examples have `route_exclusions` covering every non-assigned route
- [ ] Each exclusion references an observable query property
- [ ] Checkpoint written to scratch directory

### Phase 3 — Validation
- [ ] Agent calls `prune_registry` before validation
- [ ] Agent calls `validate_rationale_card_set` for deterministic checks
- [ ] Agent activates `check-semantic-overlap` skill
- [ ] Any validation failures are auto-fixed and re-validated

### Phase 4 — Split & Output
- [ ] Agent calls `stratified_split` with correct parameters
- [ ] Dev and holdout card sets contain only their respective examples' cards
- [ ] Both card sets share the same registry and dataset_hash
- [ ] Split report shows per-stratum distribution
- [ ] Scratch directory cleaned up after success

### Output Contract
- [ ] All 5 Prompt Builder context keys are set (dev_rationale_card_set_path, dev_jsonl_path, vocabulary_registry_path, split_report_path, routing_context)
- [ ] All 2 Final Reporting context keys are set (holdout_rationale_card_set_path, holdout_jsonl_path)
- [ ] Holdout paths are not exposed to the Prompt Builder
