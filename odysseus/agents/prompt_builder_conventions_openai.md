# Prompt Builder — OpenAI Conventions

OpenAI-specific conventions for routing prompts. Distilled from OpenAI's prompt engineering guide and cookbook patterns.

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

## Markdown Structure

OpenAI models parse Markdown headers and lists natively. Use them for organization:

- `##` headers to separate prompt sections (Routes, Rules, Examples, Output Format)
- **Bold** for route names and critical terms
- Numbered lists for ordered rules (the ordering signals priority)
- Bullet lists for unordered attributes of a route

Do not use XML tags — OpenAI models treat them as literal text rather than structural markers.

## Emphasis

Use **bold** and numbered lists to highlight critical rules. For must-not-violate constraints, use bold within a dedicated section:

```markdown
## Critical Rules

1. **Never route safety-critical requests to haiku.** Medical, legal, and financial advice must go to opus.
2. **When uncertain, prefer the cheaper route.** Only escalate when criteria are clearly met.
```

Avoid ALL CAPS. Bold is the strongest reliable emphasis mechanism for OpenAI models.

## JSON Mode for Structured Output

Enable JSON mode to guarantee valid JSON responses:

```python
response = client.chat.completions.create(
    model="gpt-4o",
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

## Chain-of-Thought

For OpenAI models, request reasoning inline rather than in tagged blocks:

```
For each request, briefly state:
1. The core task type
2. The complexity level
3. Which rule applies

Then output the JSON routing decision on the final line.
```

Keep reasoning instructions concise — OpenAI models tend to be verbose when given open-ended reasoning prompts, which adds latency. Asking for "brief" reasoning controls output length.

## Classification Cookbook Pattern

OpenAI's recommended classification structure adapted for routing:

1. **System message:** Role + route definitions (Markdown headers) + ordered rules (numbered list) + output format
2. **Few-shot turns:** 3–6 user/assistant pairs covering each route, including boundary cases
3. **Final user turn:** The actual request to classify
4. **Response format:** JSON mode enabled, or function calling for enum-constrained output

This three-part message structure (system, examples-as-turns, query) is the recommended skeleton for all OpenAI routing prompts.

## Practical Differences from Claude Prompts

When converting a routing prompt between providers:

| Aspect | Claude | OpenAI |
|---|---|---|
| Structure | XML tags (`<routes>`, `<rules>`) | Markdown headers, bold, lists |
| Examples | `<example>` blocks in system prompt | User/assistant turn pairs |
| Output control | Assistant prefill | JSON mode or function calling |
| Emphasis | `<important>` tags | **Bold** text |
| Reasoning | `<thinking>` tags | Inline reasoning before JSON |
| Length tolerance | High — more detail helps | Moderate — concise rules preferred |
