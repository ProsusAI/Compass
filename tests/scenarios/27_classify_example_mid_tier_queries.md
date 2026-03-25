# Scenario: Classify Example — Mid-Tier Sonnet Queries

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
The classify-example skill is run on the two sonnet-routed examples: rt-4 (summarize + draft questions) and rt-9 (rewrite for conciseness). These sit between simple lookups and complex multi-step analysis. The agent must determine where they fall on the complexity spectrum and assign intent patterns that reflect their task types. A registry with entries from both simple and complex queries is provided.

## User Simulator
You are a routing analysis pipeline invoking the classify-example skill on mid-tier examples.

**Your knowledge:**
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- Available routes: haiku, sonnet, opus
- Vocabulary registry (accumulated from previous classifications):
  ```yaml
  intent_pattern:
    - name: factual-lookup
      definition: "Query asks for a single factual answer retrievable from common knowledge"
      example_ids: ["rt-1", "rt-10"]
    - name: arithmetic-computation
      definition: "Query requires a numerical calculation with a definite answer"
      example_ids: ["rt-5"]
    - name: comparative-analysis
      definition: "Query requires comparing multiple entities or frameworks and evaluating tradeoffs"
      example_ids: ["rt-2"]
    - name: persuasive-generation
      definition: "Query asks for a structured argument with counterpoints and evidence"
      example_ids: ["rt-6"]
    - name: pattern-analysis
      definition: "Query requires identifying patterns across data and producing ranked recommendations"
      example_ids: ["rt-8"]
  complexity_structure:
    - name: single-hop
      definition: "Answer requires one retrieval or computation step with no dependencies"
      example_ids: ["rt-1", "rt-5", "rt-10"]
    - name: sequential-dependency
      definition: "Multiple reasoning steps where each depends on prior output"
      example_ids: ["rt-2", "rt-6", "rt-8"]
  ambiguity_tags: []
  ```

**Behavior:**
- Read the SKILL.md and reference into context.
- Provide each example with the full registry.
- Log full output.

**Opening message:**
"I need you to classify two mid-tier routing examples. Read `odysseus/skills/classify-example/SKILL.md` and `odysseus/skills/classify-example/references/vocabulary-registry-rules.md` first.

Here is the current vocabulary registry:
```yaml
intent_pattern:
  - name: factual-lookup
    definition: 'Query asks for a single factual answer retrievable from common knowledge'
    example_ids: ['rt-1', 'rt-10']
  - name: arithmetic-computation
    definition: 'Query requires a numerical calculation with a definite answer'
    example_ids: ['rt-5']
  - name: comparative-analysis
    definition: 'Query requires comparing multiple entities or frameworks and evaluating tradeoffs'
    example_ids: ['rt-2']
  - name: persuasive-generation
    definition: 'Query asks for a structured argument with counterpoints and evidence'
    example_ids: ['rt-6']
  - name: pattern-analysis
    definition: 'Query requires identifying patterns across data and producing ranked recommendations'
    example_ids: ['rt-8']
complexity_structure:
  - name: single-hop
    definition: 'Answer requires one retrieval or computation step with no dependencies'
    example_ids: ['rt-1', 'rt-5', 'rt-10']
  - name: sequential-dependency
    definition: 'Multiple reasoning steps where each depends on prior output'
    example_ids: ['rt-2', 'rt-6', 'rt-8']
ambiguity_tags: []
```

Available routes: haiku, sonnet, opus. Dataset size: 10.

Example rt-4:
- Query: 'Summarize the following quarterly earnings report highlighting key revenue drivers, margin changes, and forward guidance, then draft three follow-up questions for the CFO'
- Ground-truth route: sonnet

Please follow the skill procedure and produce the structured output."

**Follow-up message:**
After rt-4, send:
"Now classify example rt-9:
- Query: 'Rewrite this paragraph to be more concise while keeping the key points'
- Ground-truth route: sonnet
Same registry."

## Verification Criteria

### Structural correctness
- [ ] Both outputs have `intent_pattern` in kebab-case
- [ ] Both outputs have `complexity_structure` in kebab-case
- [ ] Proposed entries (if any) have all required fields

### Reasoning quality — rt-4 (summarize + draft questions)
- [ ] The agent recognizes this has at least two distinct steps (summarize, then draft questions)
- [ ] The complexity_structure reflects multi-step or sequential structure (NOT single-hop)
- [ ] The intent_pattern reflects the summarization/generation nature of the task
- [ ] If an existing entry fits, the agent uses it with justification; if not, a new entry is proposed

### Reasoning quality — rt-9 (rewrite for conciseness)
- [ ] The agent recognizes this is a simpler transformation task than rt-4
- [ ] The complexity_structure could reasonably be single-hop (one transformation step) OR a mild multi-step — either is acceptable with reasoning
- [ ] The intent_pattern reflects text transformation/editing
- [ ] The classification differentiates rt-9 from the simple factual lookups despite both being "simple-ish"

### Vocabulary decisions
- [ ] The agent checks existing registry entries before proposing new ones
- [ ] If new entries are proposed, justifications explain why existing entries don't cover the pattern
- [ ] The agent does not create overlapping entries with existing ones

### Human review log
- [ ] Reasoning shows the agent considered the complexity spectrum (rt-4 is more complex than rt-9)
- [ ] The mid-tier nature of these queries is reflected in the classifications — they don't get lumped with the simple or the complex extremes
- [ ] Complexity is determined before intent in the reasoning chain
