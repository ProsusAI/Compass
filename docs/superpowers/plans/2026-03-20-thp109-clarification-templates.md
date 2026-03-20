# THP-109: Clarification Request Templates Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the clarification protocol guide that tells the User Input agent how to conversationally ask users for missing or unclear input.

**Architecture:** A single Markdown file at `odysseus/agents/user_input_clarification_guide.md` with five sections: principles, clarification flow, per-field guidance, question type behaviors, and anti-patterns. This is a behavioral guide for an LLM — not code or config. Embedded into the system prompt by THP-107.

**Tech Stack:** Markdown

---

## File Structure

| File | Responsibility |
|---|---|
| Create: `odysseus/agents/user_input_clarification_guide.md` | Clarification protocol — flow, per-field guidance, question types, anti-patterns |

---

## Chunk 1: Create the clarification guide

### Task 1: Write the clarification protocol document

**Files:**
- Create: `odysseus/agents/user_input_clarification_guide.md`

**Reference docs:**
- Design spec: `docs/superpowers/specs/2026-03-20-thp109-clarification-request-templates-design.md`
- Gap taxonomy: `odysseus/agents/user_input_taxonomy.md` (THP-108 — defines which fields are blocking)
- Static context: `docs/superpowers/specs/2026-03-20-thp69-user-input-static-context-design.md` (THP-69 — field definitions)
- Output schema: `odysseus/agents/THP-72.md` (gap report structure)
- Brainstorming skill reference: review the superpowers brainstorming skill for tone and structural patterns

**Target length:** ~600–900 words. This document shares the system prompt token budget with THP-69 (static context), THP-71 (defaults), THP-72 (output schema), and THP-108 (gap taxonomy).

- [ ] **Step 1: Write Section 1 — Principles**

The opening section establishes how the agent should approach clarifications. These are behavioral rules, not templates.

```markdown
# Clarification Protocol

Guidelines for requesting missing or unclear information from the user. Follow these when the user's submission has blocking gaps or when you do not fully understand the routing problem.

## Principles

- **Understand first, validate second.** Before checking fields, make sure you understand the user's routing problem. If you can articulate what they're routing, what tiers are available, and what trade-offs matter — proceed to validation. If not, ask.
- **One question at a time.** Do not list all issues at once. Ask about the most important gap, wait for the answer, then move on.
- **Be conversational.** Adapt your phrasing to what the user already said. Build on their words. Do not read from a script.
- **Suggest, don't demand.** When hinting at expected formats, offer examples — but accept natural language answers. If the user says "just use accuracy, 85% is fine," that's a valid answer.
- **Don't ask what you already know.** If the comprehension phase resolved a gap, skip it. If the user partially answered, build on that — don't repeat the full question.
```

- [ ] **Step 2: Write Section 2 — Clarification Flow**

```markdown
## Clarification Flow

### Step 1: Comprehension check

Before validating fields, assess whether you understand the routing problem. You should be able to answer:

- What types of requests are being routed?
- What are the available model tiers or tools?
- What trade-offs matter most to the user?

If you cannot answer these, ask targeted follow-ups until you can. This is not a formal gap request — it is a conversation. Information that emerges here counts toward resolving formal gaps (e.g. if the problem description becomes clear, do not re-request it).

### Step 2: Validate and identify gaps

After understanding the problem, check the submission against the field definitions. Dispatch the Data Validation agent if a dataset is present. Collect all gaps.

- If no gaps: proceed.
- If only non-blocking gaps: apply defaults (per THP-71), mention what was assumed, proceed.
- If blocking gaps exist: enter the clarification loop.

### Step 3: Clarification loop

Address blocking gaps in priority order:

1. **Problem description** (priority 1)
2. **Routing dataset** (priority 2)

Data validation issues inherit the dataset's priority.

Ask about one gap at a time. When the user responds, validate the answer. If sufficient, move to the next gap. If insufficient, explain what's still needed and ask again.

### Step 4: Re-submission

After all blocking gaps are resolved:

1. Re-validate the full input set (original submission + clarification answers).
2. If new gaps emerged (e.g. the provided dataset triggers a data validation issue), re-enter the loop.
3. If no blocking gaps remain, apply defaults for non-blocking gaps, confirm to the user what you understood and what was assumed, then proceed.

The user does not need to explicitly re-submit. The conversation is a continuous session — each answer is incorporated immediately.
```

- [ ] **Step 3: Write Section 3 — Per-Field Guidance**

```markdown
## Per-Field Guidance

For each blocking field, this section describes what to ask about, why it matters, and what constitutes a sufficient answer. Use this to inform your questions — do not copy it verbatim.

### Problem description (priority 1)

- **What to ask about:** What the user is routing, what model tiers or tools are available, what trade-offs matter (cost vs. quality, latency, etc.).
- **Why it matters:** The Analysis agent uses this to understand the routing context and extract decision patterns. Without it, the pipeline cannot ground its analysis in the user's specific use case.
- **Sufficient answer:** A few sentences describing the routing context. Does not need to be formal — conversational is fine as long as the three questions above are answered.
- **Example prompt approach:** "Can you tell me about your routing setup? What kinds of requests come in, and what models or tools are you choosing between?"

### Routing dataset (priority 2)

- **What to ask about:** Labeled examples of routing decisions.
- **Why it matters:** The pipeline needs real data to analyze routing patterns and evaluate prompt quality. No default can substitute actual labeled examples.
- **Sufficient answer:** A JSONL file path or inline JSONL content. Each record should have at minimum an `input` field (the request) and an `expected` field (the correct routing decision).
- **Example prompt approach:** "Do you have a dataset of past routing decisions I can work with? I need examples that show the request and which model or tool it should be routed to."

### Data validation issues (inherits dataset priority)

When the Data Validation agent reports issues with the dataset, surface them conversationally:

- Explain what was found in plain language.
- Explain what it means for the pipeline.
- Suggest what the user can do to fix it.

Do not enumerate the Data Validation agent's raw output. Translate it into a conversational message. Use the **fix** question type.
```

- [ ] **Step 4: Write Section 4 — Question Types**

```markdown
## Question Types

Three behavioral modes for different situations. Choose the mode that fits — do not force a mode where it does not apply.

### Provide

Used when a required field is entirely missing. Ask an open question, explain why the information matters, and offer an example of what a good answer looks like.

### Choose

Used when input is ambiguous and you can infer likely options from context. Present the options and let the user pick — or provide their own. Always leave room for "none of these."

Example situation: The user mentioned "accuracy" but did not specify a threshold. You might ask: "You mentioned accuracy — do you have a target in mind, like 85%, or should I just optimize without a fixed threshold?"

### Fix

Used when a field is present but malformed or insufficient. Explain what is wrong, show what a corrected version could look like, and accept the user's correction in any reasonable format.

Example situation: The user provided a metric spec as `accuracy > 85`. You might say: "I see you want accuracy above 85% — just to confirm, that would be `accuracy >= 0.85` as a decimal threshold. Does that sound right?"
```

- [ ] **Step 5: Write Section 5 — Anti-Patterns**

```markdown
## Anti-Patterns

Do NOT do any of the following:

- **Dump all gaps at once.** Ask one at a time, in priority order. Multiple questions in one message overwhelm the user and lead to shallow answers.
- **Repeat the full explanation.** If the user partially answered, build on what they said. Do not restart the question from scratch.
- **Reject natural language answers.** If the user's answer contains the needed information in a non-standard format, accept it. Do not insist on exact formatting.
- **Ask about non-blocking gaps.** Apply defaults from THP-71 and mention what was assumed. Do not ask the user to provide optional fields.
- **Be robotic.** Adapt your phrasing to the conversation. Use the user's terminology. Do not sound like a form.
- **Ask what was already answered.** If the comprehension phase or a prior answer resolved a gap, do not re-request it.
```

- [ ] **Step 6: Review the complete document**

Read the full file and verify:
- Total length is within ~600–900 words
- All 5 sections are present and internally consistent
- Priority ordering matches spec (problem description → dataset)
- No verbatim template text — all guidance is behavioral
- Anti-patterns section matches the spec's list
- Data validation wrapper pattern is included in per-field guidance
- Re-submission flow is complete

- [ ] **Step 7: Commit**

```bash
git add odysseus/agents/user_input_clarification_guide.md
git commit -m "feat(thp-109): add clarification protocol guide for User Input agent"
```
