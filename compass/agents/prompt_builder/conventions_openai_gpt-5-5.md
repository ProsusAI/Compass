# Prompt Builder — GPT-5.5 Addendum

This supplements the base conventions (`conventions-openai`). Only GPT-5.5-specific differences relevant to routing prompt generation are covered here. Read the base conventions first.

## Treat as a new model family, not a drop-in replacement

OpenAI's explicit guidance: don't carry over prompt instructions tuned for gpt-5.2 or gpt-5.4 unchanged. When compiling a routing prompt for GPT-5.5:

- Start from the smallest prompt that preserves the routing contract (routes, rules, output format) rather than porting over every instruction accumulated for an earlier GPT-5.x model.
- Tune `reasoning_effort`, verbosity, and output-format wording against representative examples for this model specifically — do not assume settings that worked well on gpt-5.2/gpt-5.4 transfer directly.

## Practical implication for the Prompt Builder Agent

When rerunning or reoptimizing an existing prompt for a GPT-5.5 backend (via the rerun flow), treat carried-over rules and examples as a starting hypothesis to re-validate through the eval loop, not as settled content — this model family is more likely than a same-generation point release to need rule wording adjusted, not just re-scored.
