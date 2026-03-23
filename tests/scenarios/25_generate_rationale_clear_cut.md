# Scenario: Generate Routing Rationale — Clear-Cut Examples

## Setup
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- Skill: `odysseus/skills/generate-routing-rationale/SKILL.md`
- Reference: `odysseus/skills/generate-routing-rationale/references/disqualifier-guidelines.md`

## Scenario Description
The generate-routing-rationale skill is run on two clear-cut examples: rt-1 (simple factual lookup → haiku) and rt-2 (complex multi-step analysis → opus). These examples have obvious route assignments with large quality score gaps between tiers. The agent should produce disqualifiers for all non-assigned routes and should NOT flag ambiguity tags, since the routing decisions are unambiguous.

## User Simulator
You are a routing analysis pipeline invoking the generate-routing-rationale skill after classification.

**Your knowledge:**
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- Available routes: haiku, sonnet, opus
- Vocabulary registry:
  ```yaml
  ambiguity_tags:
    - name: AMBIGUOUS_COMPLEXITY
      definition: "Complexity signals point to different routes"
      example_ids: []
    - name: AMBIGUOUS_DOMAIN
      definition: "Domain knowledge required to determine correct route"
      example_ids: []
    - name: POTENTIAL_MISLABEL
      definition: "Ground-truth route assignment may be incorrect"
      example_ids: []
    - name: BOUNDARY_CASE
      definition: "Example sits at the decision boundary between two routes"
      example_ids: []
  ```

**Behavior:**
- Read the SKILL.md and reference into context.
- For each example, provide query text, ground-truth route, classification output, the registry, and the full route list.
- Log the full output.

**Opening message:**
"I need you to generate routing rationales for two examples. Read `odysseus/skills/generate-routing-rationale/SKILL.md` and `odysseus/skills/generate-routing-rationale/references/disqualifier-guidelines.md` first.

Available routes in dataset: haiku, sonnet, opus.

Ambiguity tag registry:
- AMBIGUOUS_COMPLEXITY: Complexity signals point to different routes
- AMBIGUOUS_DOMAIN: Domain knowledge required to determine correct route
- POTENTIAL_MISLABEL: Ground-truth route assignment may be incorrect
- BOUNDARY_CASE: Example sits at the decision boundary between two routes

Example rt-1:
- Query: 'What is the capital of France?'
- Ground-truth route: haiku
- Classification: intent_pattern=factual-lookup, complexity_structure=single-hop

Please follow the skill procedure and produce the structured output."

**Follow-up message:**
After rt-1, send:
"Now generate the rationale for example rt-2:
- Query: 'Compare the economic policies of Keynesianism and monetarism, then evaluate which framework better explains the 2008 financial crisis and its aftermath'
- Ground-truth route: opus
- Classification: intent_pattern=comparative-analysis, complexity_structure=sequential-dependency

Same route list and ambiguity registry."

## Verification Criteria

### Structural correctness — rt-1 (haiku)
- [ ] Disqualifiers cover both non-assigned routes: `sonnet` and `opus`
- [ ] Each disqualifier has a `route` field exactly matching "sonnet" or "opus"
- [ ] Each disqualifier has a non-empty `reason` field
- [ ] `ambiguity_tags` is empty or omitted (this is a clear-cut case)

### Structural correctness — rt-2 (opus)
- [ ] Disqualifiers cover both non-assigned routes: `haiku` and `sonnet`
- [ ] Each disqualifier has a `route` field exactly matching "haiku" or "sonnet"
- [ ] Each disqualifier has a non-empty `reason` field
- [ ] `ambiguity_tags` is empty or omitted (large quality gap makes this clear-cut)

### Disqualifier quality — rt-1
- [ ] Disqualifiers for sonnet/opus reference observable query properties (e.g., "single factual answer", "no multi-step reasoning required")
- [ ] Disqualifiers do NOT reference model capabilities (e.g., NOT "haiku can handle this" or "opus is overkill")
- [ ] Each reason is a single sentence, not a compound sentence

### Disqualifier quality — rt-2
- [ ] Disqualifiers for haiku reference observable query properties showing the query is too complex for a simple route (e.g., "query requires comparing two economic frameworks then evaluating against a historical event")
- [ ] Disqualifiers for sonnet reference why mid-tier is insufficient (e.g., "sequential evaluation step depends on the comparison output")
- [ ] Disqualifiers do NOT reference model capabilities
- [ ] Each reason is a single sentence

### Ambiguity assessment
- [ ] Neither example is tagged with ambiguity tags (both are clear-cut with large quality gaps)
- [ ] If any tags ARE proposed, the agent provides reasoning — this should be flagged for human review

### Human review log
- [ ] The agent's reasoning for writing each disqualifier is visible
- [ ] The agent follows the ordering specified in the skill (lowest route to highest if ordered)
- [ ] The distinction between a simple query (rt-1) and a complex query (rt-2) is clear in the disqualifier language
