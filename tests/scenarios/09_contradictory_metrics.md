# Scenario: Contradictory Metrics — Invalid Optimization Target

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user requests optimization for the confusion matrix, which is diagnostic only and not suitable as an optimization target. The agent should catch this, explain why, suggest alternatives, and guide the user to a valid metric.

## User Simulator
You are a data scientist who is familiar with confusion matrices from sklearn but hasn't thought about what makes a good optimization target vs. a diagnostic tool.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- Problem description: "We route user queries to haiku, sonnet, or opus based on task complexity. Simple questions go to haiku, moderate to sonnet, complex to opus."
- Initial metric preference: confusion matrix (you think it gives the most complete picture)
- Fallback metric (use when agent explains the issue): "okay, then let's go with accuracy, at least 85%"
- You have NO preferences for other optional fields.

**Behavior:**
- Provide dataset, problem description, and your metric preference in the opening message.
- When the agent explains that confusion is diagnostic only, accept the explanation and switch to accuracy.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I want to optimize my routing. Dataset is at `tests/scenarios/data/valid_dataset.jsonl`. We route queries to haiku, sonnet, or opus by complexity — simple to haiku, moderate to sonnet, complex to opus. I want to optimize for the confusion matrix since it gives the fullest picture of how the routing is performing."

## Verification Criteria
- [ ] Agent identified that `confusion` is not suitable as an optimization target
- [ ] Agent explained why (diagnostic only, no single scalar to optimize)
- [ ] Agent suggested valid alternatives
- [ ] Final report lists a valid optimization metric (not confusion)
- [ ] Agent handled this conversationally, not as a hard error
- [ ] Final report status is `proceed_with_defaults`
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
