# Prompt Builder — Claude Sonnet 5 Addendum

This supplements the base conventions (`conventions-claude`). Only Sonnet-5-specific differences relevant to routing prompt generation are covered here. Read the base conventions first.

## Adaptive thinking is on by default

Unlike Claude Sonnet 4.6, Sonnet 5 runs with adaptive thinking on by default and manual extended-thinking budgets (`thinking: {type: "enabled", budget_tokens: N}`) are no longer supported. Thinking depth is controlled by the `effort` parameter instead: `low`, `medium`, `high` (default), `xhigh`, `max`.

For routing classifiers, `low` or `medium` effort is usually sufficient — routing is a short, well-scoped task, not the "hardest coding and agentic" case `xhigh` is meant for. If a routing prompt covers many overlapping or ambiguous routes, raise effort to `medium` rather than adding more prompt-level reasoning scaffolding.

## More literal instruction following

Sonnet 5 interprets rules literally, especially at `low` effort — it does not silently generalize a rule stated for one example to similar-but-unstated cases. When writing routing rules:

- State the scope of a rule explicitly rather than relying on the model to infer it applies broadly. ("Apply this to every route, not just the first" rather than assuming it's obvious.)
- This literalism is an advantage for routing prompts, which depend on predictable, narrow rule application — but it means an under-specified rule set is more likely to leave genuine gaps than on prior Sonnet models.

## Response length

Sonnet 5 calibrates response length to task complexity rather than a fixed verbosity. This has little effect on routing prompts, since the output is a fixed-shape single JSON object — the `<output_format>` / output-format section constraint is sufficient and does not need extra brevity instructions specific to this model.

## API-level note (not prompt text)

`temperature`, `top_p`, and `top_k` are rejected with a 400 error on Sonnet 5. This doesn't affect prompt content, but if a backend profile sets a sampling parameter for determinism in evals, it must be removed for Sonnet 5 backends.
