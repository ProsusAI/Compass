# Prompt Builder — GPT-5.6 Sol Addendum

Identical to `conventions_openai_gpt-5-6.md` — kept as a separate file because backends may specify either the `gpt-5.6` alias or the canonical `gpt-5.6-sol` model ID, and the two normalize to different filenames. If updating this content, update both files.

This supplements the base conventions (`conventions-openai`). Only GPT-5.6-specific differences relevant to routing prompt generation are covered here. Read the base conventions first.

## Outcome-first prompting

GPT-5.6's official guidance: describe the destination rather than prescribing every step. Define the outcome, constraints, and completion bar, then leave room for the model to choose an efficient path. This reinforces — even more strongly than on gpt-5.2/gpt-5.4 — the base conventions' pattern of keeping the output format section as the sole authority on response shape: state the exact JSON schema and stop, rather than adding procedural instructions about how to arrive at the answer.

## Trim harder than on prior GPT-5.x models

GPT-5.6 "follows prompt contracts closely": conflicting or overlapping instructions cause more instability than missing detail, more so than on earlier GPT-5.x models. When compiling or reoptimizing a routing prompt for this model, actively remove:

- Repeated style rules that say the same thing more than once in different words.
- Examples that don't change model behavior (i.e., examples the model would already get right without them).
- Absolute directives like "always" / "never" where a case could plausibly conflict with another rule — prefer explicit, scoped conditions instead (matching the base conventions' existing priority-ordering guidance, taken further).

OpenAI's internal testing found leaner prompts improved eval scores by roughly 10–15% while cutting tokens 41–66% and cost 33–67% — trimming is not just a cost optimization on this model, it measurably improves correctness.

## Verbosity parameter

Use the `text.verbosity` API parameter to control output length globally instead of prose "be brief" / "respond concisely" instructions in the prompt — it supersedes that pattern from the base conventions for GPT-5.6 specifically. Keep the routing output-format section's schema instruction; drop any separate verbosity prose if migrating an existing prompt.

## Not applicable to Compass routing prompts

GPT-5.6 introduces Programmatic Tool Calling (writing code to coordinate and filter tool outputs). This does not apply to Compass's routing prompts, which have no tool use in the target completion — noted here only so it isn't mistaken for a missing convention.
