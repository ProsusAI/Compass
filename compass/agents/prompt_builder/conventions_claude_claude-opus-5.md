# Prompt Builder — Claude Opus 5 Addendum

This supplements the base conventions (`conventions-claude`). Only Opus-5-specific differences relevant to routing prompt generation are covered here. Read the base conventions first.

## Response length is not controlled by effort

Opus 5's default responses run longer than prior Opus models'. The `effort` parameter controls how much the model *thinks*, not how much it *says* — lowering effort does not reliably shorten the visible response. Routing prompts need a single JSON object with nothing else, so the `<output_format>` section's "do not include any text before or after the JSON object" instruction is load-bearing on Opus 5 specifically — do not rely on low effort alone to keep output terse.

## Remove verification instructions

Opus 5 verifies and self-corrects its own output without being asked. Instructions like "double-check your answer before responding" or "verify the route matches the rules" add cost with no quality gain on this model and should be dropped from routing prompts targeting Opus 5, even if they were useful on earlier Opus models.

## State scope explicitly

Opus 5 can expand a task's scope on its own judgment. For a routing classifier this is rarely desirable — reinforce that the deliverable is exactly one route decision:

```xml
<output_format>
Respond with exactly one JSON object on a single line: {"route": "<route_name>"}
Do not include any text, explanation, or additional fields before or after the JSON object.
</output_format>
```

## Prefer low-effort thinking over disabled thinking

Thinking is on by default and can only be disabled at `effort: high` or below. With thinking disabled, Opus 5 can occasionally leak a tool call or internal `<thinking>`-style tags into the visible response — a real risk for routing prompts, which parse the raw output as JSON. For routing use cases, keep thinking enabled at `low` effort rather than disabling it; this both avoids the leakage risk and is cheaper than it sounds, since `low`/`medium` effort already produce strong quality at a fraction of the cost of `high`/`xhigh`.
