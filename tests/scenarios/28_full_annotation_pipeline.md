# Scenario: Full Annotation Pipeline — Classify Then Generate Rationale

## Setup
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- Skills:
  - `odysseus/skills/classify-example/SKILL.md`
  - `odysseus/skills/classify-example/references/vocabulary-registry-rules.md`
  - `odysseus/skills/generate-routing-rationale/SKILL.md`
  - `odysseus/skills/generate-routing-rationale/references/disqualifier-guidelines.md`

## Scenario Description
End-to-end annotation of a single example (rt-3: "Translate 'good morning' to Spanish" → haiku) through both skills sequentially. First classify-example determines intent_pattern and complexity_structure, then generate-routing-rationale uses that classification to produce disqualifiers and assess ambiguity. This tests that the two skills chain together correctly — the output of skill 1 feeds into skill 2.

## User Simulator
You are a routing analysis pipeline running the full 2-skill annotation on a single example.

**Your knowledge:**
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- Available routes: haiku, sonnet, opus
- Vocabulary registry (partially populated):
  ```yaml
  intent_pattern:
    - name: factual-lookup
      definition: "Query asks for a single factual answer retrievable from common knowledge"
      example_ids: ["rt-1", "rt-10"]
  complexity_structure:
    - name: single-hop
      definition: "Answer requires one retrieval or computation step with no dependencies"
      example_ids: ["rt-1", "rt-5", "rt-10"]
  ambiguity_tags:
    - name: AMBIGUOUS_COMPLEXITY
      definition: "Complexity signals point to different routes"
      example_ids: []
    - name: BOUNDARY_CASE
      definition: "Example sits at the decision boundary between two routes"
      example_ids: []
  ```

**Behavior:**
- First, ask the agent to run classify-example on rt-3.
- Then, take the classification output and ask the agent to run generate-routing-rationale using that output.
- Log everything.

**Opening message:**
"We're going to annotate example rt-3 through the full 2-skill pipeline.

Read both skills first:
- `odysseus/skills/classify-example/SKILL.md` and its references
- `odysseus/skills/generate-routing-rationale/SKILL.md` and its references

Vocabulary registry:
```yaml
intent_pattern:
  - name: factual-lookup
    definition: 'Query asks for a single factual answer retrievable from common knowledge'
    example_ids: ['rt-1', 'rt-10']
complexity_structure:
  - name: single-hop
    definition: 'Answer requires one retrieval or computation step with no dependencies'
    example_ids: ['rt-1', 'rt-5', 'rt-10']
ambiguity_tags:
  - name: AMBIGUOUS_COMPLEXITY
    definition: 'Complexity signals point to different routes'
    example_ids: []
  - name: BOUNDARY_CASE
    definition: 'Example sits at the decision boundary between two routes'
    example_ids: []
```

Available routes: haiku, sonnet, opus. Dataset size: 10.

**Step 1 — classify-example:**
Example rt-3:
- Query: 'Translate good morning to Spanish'
- Ground-truth route: haiku

Please classify this example following the classify-example skill procedure."

**Follow-up message:**
After receiving the classification, send:
"Good. Now run **Step 2 — generate-routing-rationale** on the same example using the classification you just produced.

Example rt-3:
- Query: 'Translate good morning to Spanish'
- Ground-truth route: haiku
- Classification: [use the intent_pattern and complexity_structure from your Step 1 output]
- All routes: haiku, sonnet, opus
- Ambiguity tag registry: AMBIGUOUS_COMPLEXITY, BOUNDARY_CASE

Please follow the generate-routing-rationale skill procedure."

## Verification Criteria

### Step 1 output (classify-example)
- [ ] Output contains `intent_pattern` in kebab-case
- [ ] Output contains `complexity_structure` in kebab-case
- [ ] The classification is reasonable for a simple translation task (likely single-hop complexity, and an intent related to translation or factual-lookup)
- [ ] Reasoning follows complexity-first procedure

### Step 2 input (pipeline handoff)
- [ ] The agent uses the ACTUAL classification output from Step 1 as input to Step 2
- [ ] The classification values passed to generate-routing-rationale match what classify-example produced (no mismatch or drift)

### Step 2 output (generate-routing-rationale)
- [ ] Disqualifiers cover sonnet and opus (the two non-assigned routes)
- [ ] Route values are exactly "sonnet" and "opus"
- [ ] Reasons reference observable query properties (simple translation task)
- [ ] Reasons do NOT reference model capabilities
- [ ] Each reason is a single non-empty sentence

### Ambiguity assessment
- [ ] This is a clear-cut haiku example (quality scores: haiku=0.96, sonnet=0.95, opus=0.94) — ambiguity tags should be empty
- [ ] If tags are proposed, the reasoning is documented for human review

### Full rationale card assembly
- [ ] The combined output from both skills contains all 4 fields needed for a RationaleCard: intent_pattern, complexity_structure, tier_disqualifiers, ambiguity_tags
- [ ] The output could be parsed into a valid RationaleCard (kebab-case names, SCREAMING_SNAKE tags, non-empty reasons)

### Human review log
- [ ] The full pipeline reasoning is traceable: complexity → intent → disqualifiers → ambiguity
- [ ] The handoff between skill 1 and skill 2 is clean and visible
- [ ] The final annotation is coherent — the disqualifiers make sense given the classification
