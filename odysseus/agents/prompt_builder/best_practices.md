# Prompt Builder — General Best Practices

Reference for writing and refining routing prompts. These principles apply regardless of the target model.

## Role Framing

Open the system prompt by assigning the model a specific role. A routing classifier needs a clear mandate.

```
You are a request routing classifier. Your task is to read each incoming
user request and assign it to exactly one of the available routes based
on the rules below.
```

Keep the role statement to 1–3 sentences. Include the word "routing" or "classifier" so the model anchors on the task type immediately.

## Rule Ordering

Place the most discriminating rules first. LLMs weight early instructions more heavily, so rules that resolve the majority of cases should appear before edge-case refinements.

Recommended structure:
1. Default route and when to use it
2. High-signal trigger rules (keywords, formats, explicit complexity markers)
3. Boundary rules for ambiguous cases
4. Fallback / catch-all rule

## Anchoring on the Default Route

Start with the most common route. This anchors the model's prior — it will default to this route when uncertain, which is usually the desired behavior (prefer the default route unless evidence demands otherwise).

```
Default route: <route_default>
Route to <route_default> unless the request meets one of the escalation criteria below.
```

## Positive Framing over Negative Framing

Define each route by what it handles, not what it excludes.

**Good:** "Route to <route_advanced> when the request exhibits [high-signal characteristics for that route]."

**Bad:** "Do not route to <route_default> if the request is not simple."

Use exclusions sparingly and only for genuinely ambiguous boundaries:

```
Route to <route_intermediate> for [intermediate-complexity tasks] — unless
the task involves only [simple characteristic], which stays on <route_default>.
```

## Precision over Length

Shorter, precise rules outperform verbose explanations. A 20-word rule that names concrete signals beats a 100-word paragraph that hedges.

**Good:** "Route to <route_advanced>: [concrete signal 1], [concrete signal 2], [concrete signal 3]."

**Bad:** "When a user submits a request that appears to involve significant complexity, including but not limited to situations where multiple reasoning steps are required, or the output would benefit from a more capable route, you should consider routing to <route_advanced>."

## Few-Shot Example Design

Examples teach the model what the rules look like in practice. Design them deliberately:

- **Cover every route** — at least one example per route class. Balance roughly proportionally to expected traffic.
- **Include boundary examples** — the most valuable examples are the ones where the correct route is not obvious. If a simple variant of a task goes to <route_default> but a more complex variant goes to <route_intermediate>, include both.
- **Show the reasoning** — if using chain-of-thought, examples should demonstrate the reasoning pattern you expect.
- **Keep inputs realistic** — use examples that resemble actual production queries, not synthetic toy cases.

## Chain-of-Thought

Request reasoning before the routing decision when route boundaries are subtle or when accuracy matters more than latency.

```
For each request:
1. Identify the core task type (lookup, analysis, generation, etc.)
2. Assess complexity: single-step or multi-step?
3. Determine if quality sensitivity is high (creative, safety-critical, nuanced)
4. Select the route based on the rules above.
```

Skip chain-of-thought when routes are obvious from surface features (e.g., keyword matching) and latency matters. Unnecessary reasoning adds tokens without improving accuracy.

## Output Format

Be explicit about the expected output format. Provide a template and stick to it across all examples.

```
Respond with exactly one JSON object:
{"route": "<route_name>"}

Do not include any other text before or after the JSON.
```

If using chain-of-thought, specify where reasoning goes and where the final answer goes:

```
First, write your reasoning. Then, on the final line, output exactly:
{"route": "<route_name>"}
```

## Iterative Refinement Signals

When revising a prompt based on evaluation results:

- **High confusion between two routes** — add a boundary example that distinguishes them, or add a specific rule addressing the overlap.
- **One route has low recall** — the trigger criteria may be too narrow. Broaden the rule or add more examples of that route's inputs.
- **One route has low precision** — the trigger criteria may be too broad. Add qualifying conditions or exclusion clauses.
- **Uniform underperformance** — the role framing or rule ordering may be off. Restructure rather than adding more rules.
