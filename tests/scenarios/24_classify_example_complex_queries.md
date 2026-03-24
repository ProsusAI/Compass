# Scenario: Classify Example — Complex Multi-Step Queries

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
The classify-example skill is run on three complex queries routed to opus (rt-2: economic policy comparison, rt-6: persuasive essay with counterarguments, rt-8: customer support pattern analysis). These represent multi-step reasoning tasks. The agent should identify higher complexity structures and distinct intent patterns compared to the simple queries. A pre-populated registry from scenario 23 is provided so the agent must decide whether existing entries fit or new ones are needed.

## User Simulator
You are a routing analysis pipeline invoking the classify-example skill on individual examples.

**Your knowledge:**
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- Available routes: haiku, sonnet, opus
- Vocabulary registry (pre-populated from previous run):
  ```yaml
  intent_pattern:
    - name: factual-lookup
      definition: "Query asks for a single factual answer retrievable from common knowledge"
      example_ids: ["rt-1", "rt-10"]
    - name: arithmetic-computation
      definition: "Query requires a numerical calculation with a definite answer"
      example_ids: ["rt-5"]
  complexity_structure:
    - name: single-hop
      definition: "Answer requires one retrieval or computation step with no dependencies"
      example_ids: ["rt-1", "rt-5", "rt-10"]
  ambiguity_tags: []
  ```

**Behavior:**
- Read the SKILL.md and reference into context.
- For each of the three examples, provide query text, ground-truth route, and the pre-populated registry.
- Log the full output.

**Opening message:**
"I need you to classify three complex routing examples using the classify-example skill. Read `odysseus/skills/classify-example/SKILL.md` and `odysseus/skills/classify-example/references/vocabulary-registry-rules.md` first.

Here is the current vocabulary registry:
```yaml
intent_pattern:
  - name: factual-lookup
    definition: 'Query asks for a single factual answer retrievable from common knowledge'
    example_ids: ['rt-1', 'rt-10']
  - name: arithmetic-computation
    definition: 'Query requires a numerical calculation with a definite answer'
    example_ids: ['rt-5']
complexity_structure:
  - name: single-hop
    definition: 'Answer requires one retrieval or computation step with no dependencies'
    example_ids: ['rt-1', 'rt-5', 'rt-10']
ambiguity_tags: []
```

Available routes: haiku, sonnet, opus. Dataset size: 10.

Example rt-2:
- Query: 'Compare the economic policies of Keynesianism and monetarism, then evaluate which framework better explains the 2008 financial crisis and its aftermath'
- Ground-truth route: opus

Please follow the skill procedure and produce the structured output."

**Follow-up messages:**
After rt-2, send:
"Now classify example rt-6:
- Query: 'Write a persuasive essay arguing for renewable energy adoption, incorporating counterarguments and rebuttals, with citations to recent studies'
- Ground-truth route: opus
Same registry as before."

After rt-6, send:
"Now classify example rt-8:
- Query: 'Given a dataset of customer support tickets, identify recurring complaint patterns across product categories, rank them by business impact, and recommend three process improvements'
- Ground-truth route: opus
Same registry."

## Verification Criteria

### Structural correctness
- [ ] Each classification output contains an `intent_pattern` value in kebab-case
- [ ] Each classification output contains a `complexity_structure` value in kebab-case
- [ ] Proposed entries (if any) include name, definition, example_ids, and justification

### Reasoning quality — complexity_structure
- [ ] All three examples receive a complexity_structure that is different from `single-hop` (they require multi-step reasoning)
- [ ] The agent recognizes sequential dependencies or multi-step structure in these queries
- [ ] rt-2 (compare then evaluate) is identified as having sequential or dependent reasoning steps
- [ ] rt-8 (identify, rank, recommend) is identified as having multiple dependent phases

### Reasoning quality — intent_pattern
- [ ] The agent does NOT classify these as `factual-lookup` or `arithmetic-computation` (existing entries clearly don't fit)
- [ ] The agent proposes new intent_pattern entries for these complex tasks
- [ ] Different intent_patterns are assigned to different task types (comparison vs. generation vs. analysis) — OR a reasonable justification for grouping them

### Vocabulary proposals
- [ ] At least one new complexity_structure entry is proposed (since `single-hop` doesn't fit)
- [ ] At least one new intent_pattern entry is proposed
- [ ] Justifications explain why existing entries (`factual-lookup`, `arithmetic-computation`, `single-hop`) are insufficient
- [ ] Proposed entry names follow kebab-case convention

### Human review log
- [ ] The agent's reasoning shows it considered the existing registry entries before proposing new ones
- [ ] The reasoning clearly follows complexity-first, then intent
- [ ] The distinction between simple and complex queries is evident in the classifications
