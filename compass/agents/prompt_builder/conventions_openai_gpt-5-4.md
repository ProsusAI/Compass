# Prompt Builder — GPT-5.4 Addendum

This supplements the base conventions (`conventions-openai`). Only GPT-5.4-specific differences relevant to routing prompt generation are covered here. Read the base conventions first.

## Scope note

Public prompting guidance for GPT-5.4 focuses on frontend/design generation rather than classification tasks. No routing-specific deltas from the base GPT-5 conventions are documented — this addendum is intentionally short and mainly exists to confirm GPT-5.4 has been evaluated against the base conventions rather than silently falling through.

## Specificity over vagueness

The one generalizable takeaway relevant to routing prompts: GPT-5.4 responds well to a fully-specified output contract stated up front, and to starting from a low reasoning effort and stepping up only if evals show it's needed — consistent with the base conventions' existing guidance to prefer `low`/`minimal` reasoning effort for routing classifiers.
