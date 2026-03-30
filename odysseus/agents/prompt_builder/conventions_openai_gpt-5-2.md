# Prompt Builder — GPT-5.2 Addendum

This supplements the GPT-5 base conventions (`conventions-openai`). Only GPT-5.2-specific differences relevant to routing prompt generation are covered here. Read the base conventions first.

## Reasoning effort

GPT-5.2 adds two reasoning effort levels beyond the GPT-5 set:

| Level | GPT-5 | GPT-5.2 |
|---|---|---|
| `none` | — | New — no internal reasoning at all |
| `minimal` | Available | Available |
| `low` | Available | Available |
| `medium` | Default | Default |
| `high` | Available | Available |
| `xhigh` | — | New — deepest reasoning |

For routing classifiers, prefer `none` over `minimal`. The `none` level eliminates all internal reasoning overhead, making it the fastest and cheapest option for straightforward classification tasks. Use `minimal` or `low` only when routes are genuinely ambiguous.

## Instruction precision

GPT-5.2 follows instructions more literally than GPT-5. Implications for routing rules:

- **Tighter wording pays off more.** A precise 10-word rule outperforms a verbose 30-word explanation even more than with GPT-5.
- **Redundant rules hurt more.** If two rules cover the same case with slightly different wording, GPT-5.2 may treat them as distinct constraints and spend reasoning tokens reconciling. Remove all redundancy.
- **Implicit defaults are risky.** GPT-5.2 does not assume an obvious default — if no rule explicitly matches, it may hesitate or produce unexpected output. Always include an explicit default/fallback rule.

## Conservative grounding

GPT-5.2 has a stronger bias toward explicit reasoning and grounding than GPT-5. When routing rules are ambiguous or underspecified, GPT-5.2 tends to hedge rather than commit to a route. For routing prompts:

- **Every route must have a clear, non-overlapping trigger condition.** Vague descriptions like "complex tasks" cause hesitation.
- **Add an explicit default route rule** (e.g., "If no other rule applies, route to X"). Without this, GPT-5.2 may stall or produce malformed output on edge cases.
- **Avoid open-ended qualifying language** like "when appropriate" or "if needed" in route criteria — replace with concrete conditions.

## Scope discipline

GPT-5.2 may add unsolicited explanations, caveats, or reasoning to its output even when the prompt requests JSON only. This is more pronounced than with GPT-5. To enforce clean JSON output:

- **Reinforce the output constraint explicitly:** "Respond with exactly one JSON object. Do not include any text, reasoning, or explanation before or after the JSON."
- **In few-shot examples, ensure assistant turns contain only JSON** — no preamble, no trailing explanation. GPT-5.2 is highly pattern-sensitive to few-shot format.
- **Combine with JSON mode** (`response_format: {"type": "json_object"}`) as a hard constraint. The prompt-level instruction handles the content; JSON mode handles the format.
