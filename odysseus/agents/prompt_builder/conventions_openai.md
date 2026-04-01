# Prompt Builder — OpenAI GPT-5 Conventions

OpenAI-specific conventions for routing prompts targeting the GPT-5 model family (gpt-5, gpt-5-mini). Distilled from OpenAI's GPT-5 prompting guide and cookbook patterns.

## Key GPT-5 characteristics

GPT-5 follows instructions with surgical precision, but spends reasoning tokens reconciling contradictions. For routing prompts this means:

- **Non-contradictory rules are critical.** If two rules can conflict, add explicit priority or scope to disambiguate. GPT-5 will burn tokens (and cost) trying to reconcile them rather than picking one.
- **Concise, precise instructions outperform verbose ones.** GPT-5's improved instruction-following means shorter, clearer rules work better than long explanations.
- **Reasoning effort is controllable.** The `reasoning_effort` parameter (`high`, `medium`, `low`, `minimal`) lets you trade depth for latency. For routing classifiers, `low` or `minimal` is usually sufficient.

## System vs User Messages

Put all rules, role assignment, and route definitions in the **system message**. Use user messages for the actual request to classify and for few-shot examples formatted as turn pairs.

```
[system]
You are a request routing classifier. Assign each incoming request
to exactly one route based on the rules below.

## Routes

1. **haiku** — Simple factual lookups, greetings, status checks
2. **sonnet** — Analytical tasks, summarization, moderate code generation
3. **opus** — Multi-step reasoning, creative writing, complex code

## Rules

1. Default to haiku unless escalation criteria are met.
2. Route to sonnet for tasks requiring synthesis or comparison.
3. Route to opus for multi-step reasoning or long-form generation.

## Output Format

Respond with exactly one JSON object: {"route": "<route_name>"}
```

## Markdown and XML Structure

GPT-5 parses both Markdown and XML tags effectively. Use Markdown as the primary structure, and XML tags for semantically distinct blocks when it aids clarity:

- `##` headers to separate prompt sections (Routes, Rules, Examples, Output Format)
- **Bold** for route names and critical terms
- Numbered lists for ordered rules (ordering signals priority)
- Bullet lists for unordered attributes of a route
- XML tags for grouping structured blocks (e.g., `<routes>`, `<rules>`) when the prompt has complex nested structure

```xml
<routing_rules>
1. Default to haiku unless escalation criteria are met.
2. Route to sonnet for tasks requiring synthesis or comparison.
3. Route to opus for multi-step reasoning or long-form generation.
</routing_rules>
```

Unlike earlier GPT-4o models, GPT-5 treats XML tags as structural markers rather than literal text, so they can be used when Markdown headers alone are insufficient. Prefer Markdown for simple prompts; add XML when sections need explicit boundaries.

## Emphasis

Use **bold** and numbered lists to highlight critical rules. For must-not-violate constraints, use bold within a dedicated section:

```markdown
## Critical Rules

1. **Never route safety-critical requests to haiku.** Medical, legal, and financial advice must go to opus.
2. **When uncertain, prefer the cheaper route.** Only escalate when criteria are clearly met.
```

Avoid ALL CAPS. Bold is the strongest reliable emphasis mechanism for GPT-5.

## Instruction hierarchy for conflicting rules

GPT-5 expends significant reasoning effort trying to reconcile contradictory instructions. Avoid this by:

1. **Ordering rules by priority** — place higher-priority rules first in numbered lists.
2. **Adding explicit scope** — "In the case of X, rule A takes precedence over rule B."
3. **Removing dead rules** — delete any rule that is always overridden by another.

Bad (contradictory):

```
1. Default to the cheapest route for all requests.
2. Always route code-related requests to opus.
```

Good (explicit priority):

```
1. Route code-related requests to opus.
2. For all other requests, default to the cheapest route.
```

## JSON Mode for Structured Output

Enable JSON mode to guarantee valid JSON responses:

```python
response = client.chat.completions.create(
    model="gpt-5",
    response_format={"type": "json_object"},
    messages=[...]
)
```

When JSON mode is enabled, include the word "JSON" in the system prompt and specify the exact schema:

```
Respond with a JSON object matching this schema:
{"route": "<route_name>"}

where route_name is one of: haiku, sonnet, opus
```

JSON mode eliminates parsing failures from preamble or explanation text. Always prefer it for routing prompts.

## Function Calling as an Alternative

For stricter schema enforcement, use function calling instead of JSON mode:

```python
tools = [{
    "type": "function",
    "function": {
        "name": "route_request",
        "description": "Route the user request to the appropriate model tier",
        "parameters": {
            "type": "object",
            "properties": {
                "route": {
                    "type": "string",
                    "enum": ["haiku", "sonnet", "opus"],
                    "description": "The selected routing tier"
                }
            },
            "required": ["route"]
        }
    }
}]
```

Function calling constrains the output to the defined enum values, preventing invalid route names. Use `tool_choice={"type": "function", "function": {"name": "route_request"}}` to force the function call.

This is heavier than JSON mode but useful when route names must be exact.

## Few-Shot Example Formatting

Format examples as user/assistant turn pairs within the messages array:

```python
messages = [
    {"role": "system", "content": system_prompt},
    # Few-shot examples
    {"role": "user", "content": "What time does the store close?"},
    {"role": "assistant", "content": '{"route": "haiku"}'},
    {"role": "user", "content": "Compare microservices vs monolithic architecture for a 5-person startup."},
    {"role": "assistant", "content": '{"route": "sonnet"}'},
    {"role": "user", "content": "Design a distributed consensus algorithm that handles Byzantine faults."},
    {"role": "assistant", "content": '{"route": "opus"}'},
    # Actual request
    {"role": "user", "content": actual_query}
]
```

Each example is a separate user/assistant turn pair. The assistant turn contains only the JSON output — no reasoning, no preamble. This teaches the model the exact output pattern.

When using chain-of-thought, include reasoning in the assistant turn but clearly separate it from the JSON output:

```python
{"role": "assistant", "content": "The request asks for a simple factual lookup with no analysis needed.\n\n{\"route\": \"haiku\"}"}
```

GPT-5 is more concise by default than GPT-4o in few-shot responses — 3–5 examples is usually sufficient. Include boundary cases (requests that look like one route but belong to another) as these have the highest teaching value.

**Rendering reasoning and exclusions.** When `example_content` includes both `reasoning` and `exclusions`, combine them into the assistant turn's reasoning text (before the JSON output). The text should read as one coherent analytical passage — first explain why the assigned route applies, then explain why plausible alternative routes do not apply to this specific input. Do not format exclusions as a separate list; weave them into the reasoning narrative.

## Chain-of-Thought vs Reasoning Effort

GPT-5 has a built-in `reasoning_effort` parameter that controls internal chain-of-thought depth. For routing prompts, prefer using `reasoning_effort` over prompt-level CoT instructions:

| Approach | When to use |
|----------|-------------|
| `reasoning_effort: "low"` or `"minimal"` | Most routing tasks — fast, cheap, sufficient for clear-cut classifications |
| `reasoning_effort: "medium"` | Routing with subtle boundary cases or many overlapping routes |
| Explicit prompt-level CoT | Only when you need the reasoning visible in the output (e.g., for debugging or auditing) |

When you do need visible reasoning, keep the instructions concise:

```
For each request, briefly state:
1. The core task type
2. The complexity level
3. Which rule applies

Then output the JSON routing decision on the final line.
```

GPT-5 follows "brief" literally — it will not over-elaborate like GPT-4o did. Avoid open-ended reasoning prompts; they are unnecessary with GPT-5's improved instruction-following.

## Markdown Formatting in Output

GPT-5's API does not format responses in Markdown by default. For routing prompts this is desirable — you want raw JSON, not Markdown-wrapped output. Do **not** include Markdown formatting instructions in routing prompts.

If you ever need Markdown in the output for a non-routing use case, you must explicitly request it: "Use Markdown **only where semantically correct** (e.g., `inline code`, ```code fences```, lists, tables)." Note that Markdown adherence may degrade over long conversations.

## Verbosity Control

GPT-5 supports a `verbosity` parameter that controls answer length independently from reasoning depth. For routing prompts:

- Use low verbosity (or omit the parameter) — routing output should be a single JSON object.
- The prompt-level instruction "Respond with exactly one JSON object" is sufficient to keep output minimal, but `verbosity` provides an additional API-level guarantee.

## Classification Cookbook Pattern

GPT-5's recommended classification structure adapted for routing:

1. **System message:** Role + route definitions (Markdown headers or XML blocks) + ordered rules (numbered list, priority-first) + output format
2. **Few-shot turns:** 3–5 user/assistant pairs covering each route, including boundary cases
3. **Final user turn:** The actual request to classify
4. **Response format:** JSON mode enabled, or function calling for enum-constrained output
5. **Reasoning effort:** `low` or `minimal` for straightforward routing; `medium` for complex taxonomies

This message structure (system, examples-as-turns, query) with low reasoning effort is the recommended skeleton for all GPT-5 routing prompts.

## Practical Differences from Claude Prompts

When converting a routing prompt between providers:

| Aspect | Claude | GPT-5 |
|---|---|---|
| Structure | XML tags (`<routes>`, `<rules>`) | Markdown headers + optional XML for complex blocks |
| Examples | `<example>` blocks in system prompt | User/assistant turn pairs |
| Output control | Assistant prefill | JSON mode or function calling |
| Emphasis | `<important>` tags | **Bold** text |
| Reasoning | `<thinking>` tags | `reasoning_effort` parameter; inline CoT only when visible reasoning needed |
| Length tolerance | High — more detail helps | Moderate — concise, non-contradictory rules preferred |
| Contradictions | Handles gracefully | Burns reasoning tokens reconciling — must be eliminated |
