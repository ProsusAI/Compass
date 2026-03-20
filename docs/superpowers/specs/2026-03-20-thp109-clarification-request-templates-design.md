# THP-109 — Clarification Request Templates Design

**Date:** 2026-03-20
**Task:** [THP-109](https://prosus-thymo-thesis.atlassian.net/browse/THP-109) — Design clarification request templates
**Epic:** [THP-68](https://prosus-thymo-thesis.atlassian.net/browse/THP-68) — User Input Agent

## Overview

THP-109 defines a clarification protocol for the User Input agent — a structured guide embedded in the agent's system prompt that tells it how to conduct conversational clarifications when user input is incomplete, ambiguous, or malformed. The protocol is modeled on the superpowers brainstorming skill: it provides behavioral guidelines, question types, a process flow, and anti-patterns — not verbatim messages.

**Output file:** `odysseus/agents/user_input_clarification_guide.md` (new file) — embedded into the system prompt at THP-107.

**Format:** Structured markdown. This is a behavioral guide for an LLM, not a programmatic config.

**Target length:** ~600–900 words. Embedded in the system prompt alongside THP-69 (static context), THP-71 (defaults), THP-72 (output schema), and THP-108 (gap taxonomy). Must stay concise to preserve token budget.

## Deviations from Ticket

The THP-109 ticket specifies verbatim templates with "the exact message surfaced to the user" and asks for all blocking gaps to be presented in a single response. This spec departs from both requirements:

1. **Behavioral guidelines instead of verbatim templates.** The ticket asks for exact message text per blocking field. This spec provides behavioral guidance the agent uses to compose its own conversational messages. **Why:** The User Input agent is an LLM. Giving it rigid scripts produces robotic interactions. The superpowers brainstorming skill demonstrates that LLM agents perform better with process guidelines than scripted dialogue — they can adapt tone, build on prior context, and avoid redundant questions.

2. **One question at a time instead of all-at-once.** The ticket specifies presenting all blocking gaps in a single response to minimize round trips. This spec asks one question at a time. **Why:** A conversational flow (like the brainstorming skill uses) produces better answers. Dumping multiple questions overwhelms the user and leads to partial or shallow responses. The comprehension-first phase also means some gaps resolve naturally, so listing them all upfront would include questions that turn out to be unnecessary.

3. **`target_metrics` is non-blocking.** The ticket's examples treat `target_metrics` as blocking. Per THP-108's finalized taxonomy, `target_metrics` is classified as non-blocking with a default of F1 score. This spec follows THP-108's classification — `target_metrics` is not part of the blocking clarification protocol. The agent applies the default from THP-71 and mentions it to the user.

## Design Decisions

### Guidelines, not verbatim templates

The clarification guide tells the agent what to ask about and how to behave — not what to say word-for-word. The agent composes its own messages in a conversational tone, adapting to what the user has already said. This follows the same pattern as the superpowers brainstorming skill, which defines a process and principles rather than scripted dialogue.

### Comprehension-first flow

The agent's first job is to understand the user's routing problem, not to validate fields. Even if all fields pass validation, the agent should confirm it grasps the problem before proceeding. This mirrors how the brainstorming skill explores intent before execution. Comprehension follow-ups may naturally resolve formal gaps — if the problem description emerges during the understanding phase, the agent doesn't need to formally request it again.

### Data validation issues are surfaced conversationally

When the Data Validation agent (THP-73) finds issues with the dataset, the User Input agent wraps those findings in a single conversational message. There are no per-issue templates — the agent uses one generic pattern: explain what was found, what it means, and what the user can do. This keeps THP-109 decoupled from THP-73's error taxonomy.

### Format guidance is suggestive, not prescriptive

The agent hints at expected formats and offers examples to reduce ambiguity. But it accepts natural language answers. If a user replies "just use accuracy, 85% is fine" instead of `accuracy >= 0.85`, the agent should understand that and not reject it.

## Clarification Flow

```
Receive user submission
  → Comprehension check — does the agent understand the routing problem?
      → If unclear: conversational follow-ups until understood
  → Validate inputs against field definitions (THP-69/THP-70)
  → Dispatch Data Validation agent (if dataset present)
  → Collect all gaps (input validation + data validation findings)
  → If blocking gaps: enter clarification loop (priority order)
  → Apply defaults for non-blocking gaps, proceed
```

### Comprehension check

Before any field-level validation, the agent assesses whether it understands the routing problem. It should be able to articulate: what types of requests are being routed, what the available tiers/tools are, and what trade-offs matter. If it cannot, it asks targeted follow-ups — conversationally, not as formal gap requests.

This phase may naturally resolve blocking gaps. If the user's problem description was absent but emerges during the conversation, the agent does not re-request it.

### Clarification loop

When blocking gaps remain after the comprehension phase:

1. Order gaps by priority: problem description (1) → dataset (2)
2. Ask about the first unresolved gap — one at a time
3. When the user responds, validate the answer and mark the gap resolved
4. Move to the next gap, or re-ask if the answer was insufficient (explain why)
5. When all blocking gaps are resolved, proceed to re-submission

Data validation issues inherit their parent field's priority (dataset = priority 2).

### Re-submission flow

After all blocking gaps are resolved through the clarification loop:

1. The agent re-validates the full input set (original submission + clarification answers)
2. If new gaps are found (e.g. the user's dataset answer triggered a data validation issue), re-enter the clarification loop
3. If no blocking gaps remain, apply defaults for non-blocking gaps and produce the validated input report
4. The agent confirms to the user what it understood and what defaults were applied, then proceeds

The user does not need to explicitly "re-submit" — the agent treats the conversation as a continuous session. Each clarification answer is incorporated immediately.

## Question Types

The guide defines three behavioral modes the agent uses depending on the nature of the gap. These are not schema types — they're instructions on how to approach different situations.

### Provide

Used when a required field is entirely missing. The agent asks an open question, explains why the information matters, and offers examples of what a good answer looks like.

**Per-field guidance (blocking fields only):**

- **`problem_description`** (priority 1) — Ask about: what the user is routing, what tiers/tools are available, what trade-offs matter. Why it matters: the analysis agent uses this to extract routing patterns. Sufficient answer: a few sentences describing the routing context.
- **`routing_dataset`** (priority 2) — Ask about: labeled routing examples. Why it matters: the pipeline cannot analyze patterns or evaluate prompts without data. Sufficient answer: a JSONL file path or inline content with `input` and `expected` fields per record.

Note: `target_metrics` is classified as non-blocking by THP-108 (defaults to F1 score). The agent does not request it — it applies the default from THP-71 and mentions the assumed value to the user.

### Choose

Used when input is ambiguous and the agent can infer likely options. The agent presents options and lets the user pick or provide their own. Example: "You mentioned accuracy — did you want to optimize for `accuracy >= 0.85`, or do you have a different threshold in mind?"

### Fix

Used when a field is present but malformed or insufficient. The agent explains what's wrong, shows what a corrected version could look like, and accepts the user's correction in any reasonable format.

For data validation issues: the agent wraps the Data Validation agent's findings conversationally — "Your dataset was received, but the validation check found {issue}. {What it means}. {What the user can do}."

## Anti-Patterns

These are embedded in the guide as explicit instructions on what NOT to do:

- **Don't dump all gaps at once** — ask one at a time, in priority order
- **Don't repeat the full explanation** if the user partially answered — build on what they said
- **Don't reject natural language answers** that contain the needed information in a non-standard format
- **Don't ask about non-blocking gaps** — apply defaults and mention what was assumed
- **Don't be robotic** — adapt phrasing to the conversation, don't read from a script
- **Don't ask what was already answered** — if the comprehension phase resolved a gap, skip it

## Gap Report Integration

The clarification protocol produces two outputs:

1. **Conversational messages** — what the user sees, composed naturally by the agent
2. **Structured gap report entries** (THP-72 schema) — what downstream systems consume

The gap report entry per blocking gap:

```json
{
  "field": "<field name>",
  "classification": "blocking",
  "rationale": "<why this is blocking>",
  "clarification_request": "<summary of what was asked — for logging, not user-facing>",
  "source": "input_validation" | "data_validation"
}
```

**Proposed THP-72 schema changes** (requires THP-72 update):
- **`source` field** — new field distinguishing whether the gap was detected by input validation or forwarded from the Data Validation agent. Not in THP-72's current schema.
- **`clarification_request` semantics** — THP-72 currently describes this as "template text from THP-109" (literal user-facing message). This spec redefines it as a log summary of what was asked, since user-facing communication is conversational and unstructured. THP-72 should be updated to reflect this.

THP-72's three status values remain unchanged: `proceed`, `proceed_with_defaults`, `clarification_required`.

## What This Document Does NOT Cover

- **Which fields are blocking vs. non-blocking** — owned by THP-108
- **Default values for non-blocking gaps** — owned by THP-71
- **Data validation rules and error types** — owned by THP-73
- **The system prompt itself** — owned by THP-107, which assembles this guide with other components
- **The gap report schema** — owned by THP-72

## Dependencies

- **Blocked by** THP-108 (blocking gap taxonomy determines which fields trigger clarification)
- **Can be written in parallel with** THP-71 (defaults table)
- **THP-72** (output schema) — this spec proposes adding a `source` field and redefining `clarification_request` semantics; requires THP-72 update
- **THP-107** (final system prompt) embeds this guide and is blocked on it being finalized
- **THP-73** (Data Validation agent) — this design consumes its findings but does not depend on its implementation
