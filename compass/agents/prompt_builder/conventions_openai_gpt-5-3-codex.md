# Prompt Builder — GPT-5.3-Codex Addendum

This supplements the base conventions (`conventions-openai`). Only GPT-5.3-Codex-specific differences relevant to routing prompt generation are covered here. Read the base conventions first.

## Scope note

GPT-5.3-Codex is a coding/agentic-specialized variant of the GPT-5 family, tuned for autonomous multi-step coding work rather than short classification tasks. It has no publicly documented routing- or classification-specific prompting guidance beyond the base GPT-5 conventions — this addendum is intentionally short. If a backend targets this model for routing, the base `conventions-openai` file's classification cookbook pattern applies unchanged.

## Reasoning effort

GPT-5.3-Codex supports the standard `low`/`medium`/`high`/`xhigh` reasoning effort levels. `medium` is the recommended balanced default for interactive use; the model uses fewer thinking tokens per task than prior Codex-line models at a given effort level. For routing classifiers, `low` or `medium` is sufficient — `high`/`xhigh` are intended for the model's core use case (hard, long-horizon coding tasks) and are unlikely to improve routing accuracy enough to justify the cost.
