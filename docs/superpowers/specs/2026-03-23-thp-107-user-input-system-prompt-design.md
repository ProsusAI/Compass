# THP-107 — User Input Agent System Prompt

## Summary

Write a self-contained system prompt (`prompts/user_input_system.md`) that turns any MCP-connected LLM into the User Input agent — the pipeline's entry gate. The agent validates user submissions through conversation, applies defaults for optional fields, and produces a validated input report before downstream agents run.

## Context

The User Input agent is not a Python class. It is an LLM agent defined by its system prompt and the markdown reference files in `odysseus/agents/`. An MCP client (Claude Desktop, Cursor, etc.) loads the system prompt and becomes the agent. The MCP server provides tools; the prompt provides the reasoning instructions.

This is the final task in the THP-68 epic. All five dependency artifacts are complete:

- THP-69: `odysseus/agents/user_input_context.md` — domain context, field definitions, metrics
- THP-71: `odysseus/agents/user_input_defaults.md` — defaults table for optional fields
- THP-72: `odysseus/agents/user_input_report_template.md` — report template and rules
- THP-108: `odysseus/agents/user_input_taxonomy.md` — blocking/non-blocking gap classification
- THP-109: `odysseus/agents/user_input_clarification_guide.md` — clarification protocol

## Design

### Prompt structure

The system prompt is a single self-contained Markdown file. It inlines all necessary knowledge from the five dependency artifacts — distilled into actionable instructions, not copy-pasted verbatim. Sections:

1. **Role & mission** — The agent is the pipeline entry gate. Its job: validate the user's submission and produce a validated input report before any other agent runs.

2. **Domain context** — Distilled from `user_input_context.md`:
   - What cost-quality routing is (one paragraph).
   - Complete problem specification: two required fields (`routing_dataset`, `problem_description`) and four optional fields with defaults (`target_metrics`, `evaluation_threshold`, `data_split_ratio`, `max_iterations`).
   - Available metrics (accuracy, f1, confusion, cost_quality_reduction) with short descriptions and example specs.

3. **Validation logic** — Distilled from `user_input_taxonomy.md`:
   - Field-by-field classification: `routing_dataset` and `problem_description` are blocking; all others are non-blocking.
   - Decision rule: if any blocking gap exists, keep conversing; if only non-blocking gaps, apply defaults and produce report; if no gaps, produce report.

4. **Defaults table** — From `user_input_defaults.md`:
   - The four non-blocking defaults: `target_metrics` → `["f1/macro"]`, `evaluation_threshold` → `0.80`, `data_split_ratio` → `0.20`, `max_iterations` → `10`.
   - Each with its rationale and user-facing note.
   - Instruction: record each assumed default in the report's Assumed Defaults section.

5. **Clarification protocol** — Distilled from `user_input_clarification_guide.md`, modeled on the `superpowers:brainstorming` skill's conversational design pattern:
   - Comprehension-first: understand the routing problem before validating fields.
   - One question at a time, in priority order (problem_description first, then routing_dataset).
   - Prefer multiple-choice questions when possible; open-ended when needed.
   - Three question types: provide (missing field), choose (ambiguous input), fix (malformed input).
   - Conversational tone — build on user's words, accept natural language answers.
   - No attempt limit — keep asking until all blocking gaps are resolved.
   - Anti-patterns: don't dump all gaps at once, don't be robotic, don't ask about non-blocking gaps, don't re-ask what was already answered.
   - Reference: the `superpowers:brainstorming` skill's approach to one-question-at-a-time clarification, multiple-choice preference, and incremental validation should serve as the model for this protocol.

6. **Data Validation agent dispatch** — Instructions for future coordination:
   - When user provides a dataset, dispatch the Data Validation agent to assess quality.
   - Incorporate findings (insufficient examples, label imbalance, malformed records) as potential blocking gaps.
   - Surface data issues conversationally using the "fix" question type.
   - Note: this agent does not exist yet — include the dispatch protocol so the prompt is ready when it arrives.

7. **Output format** — From `user_input_report_template.md`:
   - The exact report template structure (Status, Confirmed Inputs, Gap Report, Assumed Defaults).
   - Two valid statuses: `proceed` and `proceed_with_defaults`. The `clarification_required` status is deprecated — the agent converses until gaps are resolved rather than producing an incomplete report.
   - Rules: when to include/omit Gap Report and Assumed Defaults sections, heading conventions, field identifiers.

### Agent flow

**Phase 1 — Conversation:**
1. Receive user input (dataset path, problem description, metrics, optional fields).
2. Comprehension check — make sure the agent understands the routing problem.
3. Validate all fields against the taxonomy.
4. If blocking gaps exist → enter clarification loop. One question at a time, conversational. No structured output during this phase.
5. Continue until all blocking gaps are resolved.

**Phase 2 — Report:**
1. Apply defaults for any missing optional fields.
2. Produce the validated input report in the exact template format.
3. Mention any assumed defaults conversationally alongside the report.

### Changes to existing code

**Deprecate `clarification_required` status:**

- `odysseus/agents/user_input_report.py`: Remove `STATUS_CLARIFICATION_REQUIRED` constant. Update `read_status()` to only accept `proceed` and `proceed_with_defaults`.
- `odysseus/agents/__init__.py`: Remove `STATUS_CLARIFICATION_REQUIRED` from exports.
- `odysseus/agents/user_input_report_template.md`: Remove `clarification_required` from the Status Values table and any references in the rules. Also fix the stale `target_metrics` default in the Field Reference section — change `["accuracy"]` to `["f1/macro"]` to match the canonical defaults table (THP-71).
- `odysseus/agents/user_input_taxonomy.md`: Update the Status Decision Logic section — remove the `clarification_required` outcome. Replace with: "If blocking gaps exist, the agent continues conversing until they are resolved."
- `odysseus/agents/user_input_clarification_guide.md`: Remove the two-attempt limit (lines 42-43). The agent keeps asking until all blocking gaps are resolved — it does not stop after a fixed number of attempts.
- `odysseus/agents/user_input_context.md`: Move `target_metrics` from the Required section to the Optional section. The taxonomy (THP-108) and defaults table (THP-71) both treat it as non-blocking with a default of `["f1/macro"]`, so the context document should align.

**No changes to:**
- `odysseus/mcp.py` — the system prompt is loaded by the MCP client, not the server.
- `odysseus/agents/base.py` — the User Input agent is not a Python class.
- `odysseus/agents/eval_runner.py` — unrelated agent.

### File inventory

| Action | File |
|---|---|
| Create | `prompts/user_input_system.md` |
| Modify | `odysseus/agents/user_input_report.py` |
| Modify | `odysseus/agents/__init__.py` |
| Modify | `odysseus/agents/user_input_report_template.md` |
| Modify | `odysseus/agents/user_input_taxonomy.md` |
| Modify | `odysseus/agents/user_input_clarification_guide.md` |
| Modify | `odysseus/agents/user_input_context.md` |

### Testing

- Unit tests for `read_status()` — verify it accepts `proceed` and `proceed_with_defaults`, rejects `clarification_required` and unknown values.
- Update any existing tests that reference `STATUS_CLARIFICATION_REQUIRED`.

## Out of scope

- `UserInputAgent` Python class — the agent is LLM-driven, not programmatic.
- Data Validation agent implementation — dispatch protocol is in the prompt, agent is built later.
- MCP server wiring for user input — the prompt is loaded by the MCP client directly.
- Override mechanism (re-submission flow) — documented in defaults, but the multi-turn session handling is an MCP client concern.
