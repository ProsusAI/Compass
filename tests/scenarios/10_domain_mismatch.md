# Scenario: Domain Mismatch — Not a Routing Problem

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user describes a sentiment classification problem, not a cost-quality routing problem. The agent should recognize the mismatch and surface it rather than silently proceeding.

## User Simulator
You are a product analyst who confused this tool with a general ML classifier. You have a dataset but your problem is sentiment analysis, not model-tier routing.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- Your actual problem: "I want to classify customer reviews as positive, negative, or neutral."
- If the agent points out this isn't a routing problem: you realize the confusion. You can either:
  - Reframe: "Oh wait, actually what I really need is to route sentiment analysis requests to different model tiers by difficulty — simple positive/negative to haiku, nuanced mixed-sentiment reviews to opus."
  - OR acknowledge: "Ah, you're right, this isn't what I need. Thanks for clarifying."
- Choose whichever response feels more natural in the conversation.

**Behavior:**
- Opening message describes a sentiment classification problem.
- Respond naturally to the agent's feedback about the mismatch.
- If you reframe, provide the routing-specific details.

**Opening message:** "Hi, I have a dataset at `tests/scenarios/data/valid_dataset.jsonl` and I want to classify customer reviews as positive, negative, or neutral. Can you help me set this up?"

## Verification Criteria
- [ ] Agent recognized that sentiment classification is not cost-quality routing
- [ ] Agent surfaced the mismatch — did not silently proceed
- [ ] Agent either helped reframe the problem as routing or clearly explained why this isn't a routing problem
- [ ] If reframed: final report has a valid routing problem description
- [ ] If not reframed: no report was produced, conversation ended with a clear explanation
