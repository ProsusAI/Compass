# Scenario: Classify Example — Simple Single-Hop Queries

## Setup
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- Skill: `odysseus/skills/classify-example/SKILL.md`
- Reference: `odysseus/skills/classify-example/references/vocabulary-registry-rules.md`

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
The classify-example skill is run on three simple, clearly single-hop queries from the dataset (rt-1: "What is the capital of France?", rt-5: "What is 15% of 240?", rt-10: "Define the word 'serendipity'"). All three are routed to haiku. The skill should produce consistent `complexity_structure` values for these straightforward queries and assign `intent_pattern` values that reflect their task types. Since no vocabulary registry exists yet, the agent should propose new entries.

## User Simulator
You are a routing analysis pipeline invoking the classify-example skill on individual examples.

**Your knowledge:**
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- Available routes: haiku, sonnet, opus
- Vocabulary registry: empty (fresh start — no existing entries for intent_pattern or complexity_structure)

**Behavior:**
- Read the SKILL.md and its reference file into context.
- For each of the three examples (rt-1, rt-5, rt-10), ask the agent to classify it following the skill procedure.
- Provide the query text, ground-truth route, and the current (empty) vocabulary registry each time.
- After each classification, log the full output including the proposed vocabulary entries.

**Opening message:**
"I need you to classify three routing examples using the classify-example skill. Read `odysseus/skills/classify-example/SKILL.md` and `odysseus/skills/classify-example/references/vocabulary-registry-rules.md` first, then classify each example I give you.

The vocabulary registry is currently empty (no existing entries). Available routes are: haiku, sonnet, opus. Dataset size is 10.

Example rt-1:
- Query: 'What is the capital of France?'
- Ground-truth route: haiku

Please follow the skill procedure and produce the structured output."

**Follow-up messages:**
After receiving the classification for rt-1, send:
"Now classify example rt-5:
- Query: 'What is 15% of 240?'
- Ground-truth route: haiku
Use the same vocabulary registry (still empty — proposed entries are not confirmed yet)."

After receiving rt-5, send:
"Now classify example rt-10:
- Query: 'Define the word serendipity'
- Ground-truth route: haiku
Same empty registry."

## Verification Criteria

### Structural correctness
- [ ] Each classification output contains an `intent_pattern` value in kebab-case
- [ ] Each classification output contains a `complexity_structure` value in kebab-case
- [ ] Proposed entries (if any) include name, definition, example_ids, and justification

### Reasoning quality — complexity_structure
- [ ] All three examples are classified with the same or equivalent complexity_structure (they are all single-step lookups)
- [ ] The complexity_structure reflects low complexity (e.g., something like single-hop, direct-retrieval, or similar — exact name is flexible)
- [ ] The agent identifies the reasoning topology BEFORE classifying intent (procedure Step 1 before Step 2)

### Reasoning quality — intent_pattern
- [ ] rt-1 (capital of France) and rt-10 (define serendipity) receive the same or similar intent_pattern (both are factual lookups)
- [ ] rt-5 (15% of 240) may receive a different intent_pattern from rt-1/rt-10 (it is a computation, not a factual lookup) — OR a reasonable justification for grouping them

### Vocabulary proposals
- [ ] Since the registry is empty, the agent proposes at least one new vocabulary entry for intent_pattern
- [ ] Since the registry is empty, the agent proposes at least one new vocabulary entry for complexity_structure
- [ ] Proposed entry names follow kebab-case convention
- [ ] Proposed entries have non-empty definitions

### Human review log
- [ ] The agent's reasoning for each classification is visible and understandable in the transcript
- [ ] The reasoning follows the skill procedure: complexity first, then intent
- [ ] Any disagreement between the agent's classification and the expected route is explained
