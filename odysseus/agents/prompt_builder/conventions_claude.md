# Prompt Builder — Claude Conventions

Claude-specific conventions for routing prompts. Distilled from Anthropic's prompt engineering guide and cookbook patterns.

## XML Tags for Structure

Claude responds well to XML-tagged structure. Use these tags consistently in routing prompts:

```xml
<routes>
  <route name="haiku">Simple factual lookups, greetings, status checks</route>
  <route name="sonnet">Analytical tasks, summarization, moderate code</route>
  <route name="opus">Multi-step reasoning, creative writing, complex code</route>
</routes>

<rules>
1. Default to haiku unless escalation criteria are met.
2. Route to sonnet for tasks requiring synthesis or comparison.
3. Route to opus for multi-step reasoning or long-form generation.
</rules>

<examples>
  <example>
    <input>What time does the store close?</input>
    <output>{"route": "haiku"}</output>
  </example>
  <example>
    <input>Compare the trade-offs between microservices and monolithic architecture for a startup with 5 engineers.</input>
    <output>{"route": "sonnet"}</output>
  </example>
</examples>
```

Do not nest XML tags deeply — one level of nesting (e.g., `<examples>` containing `<example>`) is the sweet spot.

## System Prompt Style

Claude performs best with structured system prompts that separate instructions from context. Organize the system prompt in this order:

1. Role assignment
2. Route definitions (`<routes>`)
3. Routing rules (`<rules>`)
4. Few-shot examples (`<examples>`)
5. Output format specification (must be last section)

Keep each section self-contained. Claude handles long system prompts well — do not sacrifice clarity for brevity.

## Prefilled Assistant Responses

Use assistant turn prefill to lock Claude into structured output. Start the assistant turn with the opening of the expected JSON:

```
[assistant] {"route": "
```

This eliminates preamble and forces the model to complete the JSON object directly. Particularly effective for routing prompts where the output is always a single JSON object.

When using chain-of-thought with prefill, prefill after the reasoning section:

```
[assistant] <thinking>
```

This steers Claude into the reasoning block first.

## Emphasis with `<important>` Tags

For critical rules that must not be overridden, use `<important>` tags:

```xml
<important>
Never route safety-critical requests (medical, legal, financial advice) to haiku.
Always escalate these to opus regardless of apparent simplicity.
</important>
```

Avoid ALL CAPS for emphasis — Claude treats `<important>` tags as a stronger signal. Reserve them for 1–2 truly critical rules; overuse dilutes their effect.

## Chain-of-Thought with `<thinking>` Tags

When routing decisions need reasoning, use `<thinking>` tags to contain the chain-of-thought:

```xml
<thinking>
Analyze the request:
- Task type: [identify]
- Complexity: [single-step / multi-step]
- Quality sensitivity: [low / medium / high]
- Matching route rule: [cite specific rule number]
</thinking>

{"route": "<route_name>"}
```

Include a `<thinking>` example in the few-shot section so Claude follows the pattern:

```xml
<example>
  <input>Write a haiku about Monday mornings</input>
  <output>
<thinking>
Task type: creative writing. Complexity: single-step, very short output. Quality sensitivity: low — a haiku is 17 syllables. This matches the default haiku tier.
</thinking>
{"route": "haiku"}
  </output>
</example>
```

## Example Formatting

Each example should be a self-contained `<example>` block with clear `<input>` and `<output>` separation. Claude treats these as canonical demonstrations.

For routing prompts, include the reasoning in examples when chain-of-thought is enabled, and omit it when not. Mixing patterns confuses the model.

**Boundary examples are high-value for Claude.** Claude is strong at following demonstrated patterns, so an example that shows "this looks like route A but is actually route B because of X" is more effective than a rule stating the same thing.

**Rendering reasoning and exclusions.** When `example_content` includes both `reasoning` and `exclusions`, combine them into a single `<thinking>` block. The block should read as one coherent analytical passage — first explain why the assigned route applies, then explain why plausible alternative routes do not apply to this specific input. Do not format exclusions as a bulleted list or separate section inside the `<thinking>` tags; weave them naturally into the analysis.

## Long Context Handling

Claude handles long prompts well. Practical implications for routing prompts:

- Include more few-shot examples rather than fewer — 8–12 examples across routes is fine.
- Do not compress rules into terse shorthand. Full sentences with clear conditions perform better.
- Place the most important rules and examples early in the prompt (recency and primacy effects both apply, but primacy is stronger for system prompts).

## Structured Output Pattern

For routing, the standard structured output pattern is:

```xml
<output_format>
Respond with exactly one JSON object on a single line:
{"route": "<route_name>"}

Valid route names: haiku, sonnet, opus

Do not include any text before or after the JSON object.
</output_format>
```

Wrapping format instructions in their own tagged section prevents them from blending into the routing rules.

## Classification Cookbook Pattern

Claude's classification pattern adapted for routing:

1. Define the taxonomy in `<routes>` — exhaustive, mutually exclusive categories
2. Provide decision criteria in `<rules>` — ordered by discriminating power
3. Demonstrate with `<examples>` — at least one per route, emphasizing boundaries
4. Constrain output with `<output_format>` and assistant prefill

This four-part structure is the recommended skeleton for all Claude routing prompts.
