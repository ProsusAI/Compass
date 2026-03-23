# Scenario: Generate Routing Rationale — Ambiguous Boundary Examples

## Setup
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- Skill: `odysseus/skills/generate-routing-rationale/SKILL.md`
- Reference: `odysseus/skills/generate-routing-rationale/references/disqualifier-guidelines.md`

## Scenario Description
The generate-routing-rationale skill is run on two examples that sit near routing boundaries: rt-4 (summarize + draft questions → sonnet, but close to opus) and rt-9 (rewrite for conciseness → sonnet, but close to haiku). These examples have small quality score gaps between adjacent tiers, making the routing decision genuinely ambiguous. The agent should produce disqualifiers and SHOULD flag at least one ambiguity tag for at least one of these examples.

## User Simulator
You are a routing analysis pipeline invoking the generate-routing-rationale skill on boundary examples.

**Your knowledge:**
- Dataset: `tests/scenarios/data/rationale_test_dataset.jsonl`
- Available routes: haiku, sonnet, opus
- rt-4 quality scores: haiku=0.40, sonnet=0.88, opus=0.92 (sonnet vs opus gap is only 0.04)
- rt-9 quality scores: haiku=0.55, sonnet=0.90, opus=0.92 (sonnet vs opus gap is only 0.02)
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
- For each example, provide query, route, classification, registry, and route list.
- Mention the quality score context so the agent understands the boundary nature.
- Log full output.

**Opening message:**
"I need you to generate routing rationales for two boundary-case examples. Read `odysseus/skills/generate-routing-rationale/SKILL.md` and `odysseus/skills/generate-routing-rationale/references/disqualifier-guidelines.md` first.

Available routes: haiku, sonnet, opus.

Ambiguity tag registry:
- AMBIGUOUS_COMPLEXITY: Complexity signals point to different routes
- AMBIGUOUS_DOMAIN: Domain knowledge required to determine correct route
- POTENTIAL_MISLABEL: Ground-truth route assignment may be incorrect
- BOUNDARY_CASE: Example sits at the decision boundary between two routes

Example rt-4:
- Query: 'Summarize the following quarterly earnings report highlighting key revenue drivers, margin changes, and forward guidance, then draft three follow-up questions for the CFO'
- Ground-truth route: sonnet
- Classification: intent_pattern=summarization-with-generation, complexity_structure=sequential-dependency
- Context: quality scores are haiku=0.40, sonnet=0.88, opus=0.92 — note the small gap between sonnet and opus (0.04)

Please follow the skill procedure and produce the structured output."

**Follow-up message:**
After rt-4, send:
"Now generate the rationale for example rt-9:
- Query: 'Rewrite this paragraph to be more concise while keeping the key points'
- Ground-truth route: sonnet
- Classification: intent_pattern=text-transformation, complexity_structure=single-hop
- Context: quality scores are haiku=0.55, sonnet=0.90, opus=0.92 — note the small gap between sonnet and opus (0.02), and this could arguably be done by haiku

Same route list and ambiguity registry."

## Verification Criteria

### Structural correctness — both examples
- [ ] rt-4 has disqualifiers for both haiku and opus
- [ ] rt-9 has disqualifiers for both haiku and opus
- [ ] All disqualifier route values exactly match "haiku", "sonnet", or "opus"
- [ ] All reasons are non-empty single sentences

### Disqualifier quality
- [ ] rt-4 haiku disqualifier references observable complexity (multiple steps: summarize + draft questions)
- [ ] rt-4 opus disqualifier is harder to write convincingly (the gap is small) — the reasoning should reflect this difficulty
- [ ] rt-9 haiku disqualifier references the quality judgment needed for conciseness
- [ ] rt-9 opus disqualifier acknowledges the task doesn't require the full capability of the top route
- [ ] No disqualifiers reference model capabilities

### Ambiguity detection
- [ ] At least one of rt-4 or rt-9 receives at least one ambiguity tag
- [ ] The proposed tag(s) come from the registry (AMBIGUOUS_COMPLEXITY, BOUNDARY_CASE, etc.) OR are new well-justified proposals
- [ ] The agent explains WHY ambiguity was detected (e.g., difficulty writing the opus disqualifier for rt-4, or the haiku-sonnet boundary for rt-9)
- [ ] If BOUNDARY_CASE is used, it is appropriate — the quality scores genuinely support this

### Human review log
- [ ] The agent's reasoning about ambiguity is visible and traces back to the disqualifier-writing process
- [ ] The transcript shows the agent noticed the small quality gaps as part of its reasoning
- [ ] The difference in confidence between clear-cut disqualifiers (haiku for rt-4) and boundary disqualifiers (opus for rt-4) is evident in the language
- [ ] For any tag proposed, the reasoning is substantive, not just "the scores are close"
