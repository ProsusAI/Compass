# Prompt Builder — Claude Fable 5 Addendum

This supplements the base conventions (`conventions-claude`). Only Fable-5-specific differences relevant to routing prompt generation are covered here. Read the base conventions first.

## Override: do not ask Fable 5 to reproduce reasoning in the response

**This overrides the base conventions' Chain-of-Thought section.** The base `conventions-claude` file recommends visible `<thinking>` tags in the response, with the reasoning rendered as part of the completion text before the JSON output. On Fable 5, prompts that ask the model to echo, transcribe, or explain its internal reasoning as response text can trigger the `reasoning_extraction` refusal category, causing the request to fall back or fail instead of returning a route.

For routing prompts targeting Fable 5:

- Do not include a `<thinking>` block in the expected output format, and do not instruct the model to "show your reasoning" or "explain your decision" in the response.
- If reasoning visibility is genuinely needed (e.g. for eval/debugging), read the model's structured `thinking` output field from adaptive thinking instead of asking for it inline in the completion text.
- The output format section should request the JSON route object only — this is actually simpler than the base file's CoT pattern, not an added constraint.

## Effort levels

Fable 5 exposes the same `effort` parameter as other current Claude models (`low`, `medium`, `high` default, `xhigh`, `max`). For routing classification, `medium` or `low` is appropriate for most taxonomies; reserve `high`/`xhigh` for routing decisions with many overlapping or genuinely ambiguous categories.

## Strong instruction following favors brevity

Fable 5's instruction-following is strong enough that a short, explicit rule set outperforms an exhaustively enumerated one — matching the base conventions' existing preference for full sentences over shorthand, but taken further: prefer a small number of precise, non-overlapping route-selection rules over a long list covering every conceivable edge case. Add boundary-case few-shot examples for the edge cases instead of more prose rules.
