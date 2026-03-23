# THP-146 — Integration Tests for User Input Agent

## Summary

Integration tests for the User Input agent that run as real multi-turn conversations inside Claude Code. Each test is a self-contained Markdown scenario file that Claude Code reads and executes by orchestrating three sub-agents: a User Input Agent, a User Simulator, and a Verification Agent. Tests use real LLM API calls against the pre-configured Odysseus MCP server.

## Context

The User Input agent (THP-107) is not a Python class — it is an LLM agent defined by its system prompt (`prompts/user_input_system.md`), loaded via the `odysseus_routing_input` MCP prompt. An MCP client activates the prompt and becomes the agent, with access to MCP tools including `submit_input_report` for pipeline handoff. This means traditional unit tests with mocked method calls cannot test the actual agent behavior. Instead, we test the agent by running real conversations and verifying the outcomes.

### Dependencies

| Artifact | Status | Role |
|---|---|---|
| THP-107 | Complete | System prompt — defines the agent under test |
| THP-72 | Complete | Validated input report schema — verification target |
| THP-108 | Complete | Blocking/non-blocking taxonomy — drives scenario design |
| THP-109 | Complete | Clarification protocol — tested by multi-turn scenarios |
| THP-69 | Complete | Static domain context — inlined in system prompt |
| THP-71 | Complete | Defaults table — verified in report output |

## Architecture

### Three sub-agents

Each test scenario is executed by three sub-agents orchestrated by Claude Code:

**User Input Agent** — The agent under test. Activated via the `odysseus_routing_input` MCP prompt (which loads `prompts/user_input_system.md`). Has access to the pre-configured Odysseus MCP tools including `submit_input_report` for pipeline handoff. Receives user messages, reasons about completeness, asks clarifications, and eventually produces a validated input report and calls `submit_input_report` to hand off to the next pipeline stage.

**User Simulator** — Plays the role of a user described in the scenario. Given a persona, available information, and behavioral constraints. Responds naturally to whatever the User Input Agent asks — not scripted, reactive. Has no MCP connection.

**Verification Agent** — Runs after the conversation concludes. Receives the full conversation transcript and the final validated input report. Checks each verification criterion and reports structured pass/fail results with reasoning.

### Turn-by-turn orchestration

```
Claude Code reads scenario MD
  → spins up User Simulator (## User Simulator section)
  → spins up User Input Agent (odysseus_routing_input MCP prompt + MCP tools)
  → gets initial user message from simulator

  LOOP:
    → passes user message to User Input Agent
    ← receives agent response
    → if agent called submit_input_report tool → exit loop (primary signal)
    → if response contains "# Validated Input Report" → exit loop (fallback)
    → passes agent response to User Simulator
    ← receives simulator's next message

  → spins up Verification Agent (## Verification Criteria + transcript + report)
  ← receives pass/fail results
```

The conversation terminates when the User Input Agent calls the `submit_input_report` MCP tool (the primary completion signal). The system prompt instructs the agent to call this tool after producing the validated input report and getting user confirmation. As a fallback, the orchestration also exits if it detects `# Validated Input Report` in the agent's response. The agent may include conversational text before or after the report (e.g., mentioning assumed defaults) — Claude Code scans the full response.

### Safety valve

The orchestration loop has a maximum of **20 turns**. If the conversation has not produced a validated input report within 20 turns, the test fails with "conversation did not converge." This prevents infinite loops when the simulator and agent talk past each other.

### Preconditions

- The Odysseus MCP server is pre-configured and connected to Claude Code before tests run.
- No server startup or connection management is needed in the test flow.

## Scenario file structure

Each scenario is a single self-contained Markdown file in `tests/scenarios/`:

```markdown
# Scenario: <name>

## Setup
- Synthetic data files needed (paths relative to tests/scenarios/data/)
- Any preconditions specific to this scenario

## Scenario Description
Plain language description of the test situation — shared context for all three agents.

## User Simulator
Instructions for the sub-agent playing the user:
- Persona and background
- What information they have and will provide
- What information they are missing or will not provide
- How they should behave (reactive, not scripted)
- For multi-turn scenarios: what they know but haven't shared yet

**Opening message:** The exact first message the simulator sends to the User Input Agent.
This anchors the conversation start — subsequent messages are generated reactively.

## Verification Criteria
Checklist for the verification agent — each item is a pass/fail assertion:
- [ ] Criterion 1
- [ ] Criterion 2
- ...
```

The User Simulator section gives the agent a **character with knowledge**, not a script. It responds naturally to whatever the User Input Agent asks, which tests real conversational dynamics.

### Verification Agent input format

The Verification Agent receives:

1. **Conversation transcript** — interleaved `User:` / `Agent:` messages, one per turn, in chronological order. MCP tool calls made by the agent are included inline as `[Tool call: tool_name(args)]` / `[Tool result: ...]` blocks within the agent's turn.
2. **Final validated input report** — extracted from the agent's final message (the Markdown content after `# Validated Input Report`).
3. **Verification criteria** — the `## Verification Criteria` section from the scenario MD.

A scenario passes only if **all** verification criteria pass. The Verification Agent reports each criterion individually with pass/fail and reasoning, plus an overall verdict.

**Note on premature reports:** The orchestration loop exits whenever `# Validated Input Report` appears — it does not check whether the report is valid or complete. Correctness checking is intentionally delegated to the Verification Agent. If the agent produces a report before resolving all blocking gaps (e.g., in scenario 11), the loop will exit and the verification criteria will catch it as a failure.

## File layout

```
tests/scenarios/
  data/
    valid_dataset.jsonl
    no_expected_field.jsonl
  01_complete_submission.md
  02_missing_optional_defaults.md
  03_missing_required_clarification.md
  04_multiple_blocking_gaps.md
  05_mixed_blocking_nonblocking.md
  06_malformed_dataset.md
  07_vague_problem_description.md
  08_ambiguous_tiers.md
  09_contradictory_metrics.md
  10_domain_mismatch.md
  11_persistent_clarification.md
  12_natural_language_answers.md
```

### Synthetic test data

Two dataset files are provided. `valid_dataset.jsonl` is used by all active scenarios; `no_expected_field.jsonl` is reserved for scenario 6 when THP-73 lands.

**`valid_dataset.jsonl`** — 5 well-formed cost-quality routing records (used by scenarios 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12):

```jsonl
{"id": "1", "input": {"query": "What is 2+2?"}, "expected": {"route": "haiku"}}
{"id": "2", "input": {"query": "Explain quantum entanglement in detail with examples"}, "expected": {"route": "opus"}}
{"id": "3", "input": {"query": "Translate 'hello' to French"}, "expected": {"route": "haiku"}}
{"id": "4", "input": {"query": "Write a nuanced essay on the ethics of AI regulation"}, "expected": {"route": "opus"}}
{"id": "5", "input": {"query": "Summarize this paragraph in one sentence"}, "expected": {"route": "sonnet"}}
```

Simple queries route to the cheap tier (haiku), complex ones to the expensive tier (opus), middle-ground to sonnet. All the same function — answering questions — routed by complexity to different cost tiers.

**`no_expected_field.jsonl`** — Same 5 records with `expected` field stripped (used by scenario 6).

## Test scenarios

### 1. Complete submission — proceed

**What it tests:** Happy path — all fields provided, no clarification needed.

**User Simulator:** A data analyst who provides everything upfront: dataset path (`tests/scenarios/data/valid_dataset.jsonl`), a clear problem description ("Route customer queries to haiku/sonnet/opus tiers based on complexity — simple factual questions to haiku, moderate tasks to sonnet, complex reasoning to opus"), target metrics (`accuracy >= 0.90`), evaluation threshold (`0.85`), data split ratio (`0.25`), max iterations (`5`).

**Verification Criteria:**
- [ ] Report status is `proceed`
- [ ] Confirmed Inputs contains the dataset path
- [ ] Confirmed Inputs contains the problem description
- [ ] Confirmed Inputs lists `accuracy >= 0.90` as target metric
- [ ] Confirmed Inputs includes evaluation threshold, data split ratio, and max iterations
- [ ] No `## Gap Report` heading appears in the report
- [ ] No `## Assumed Defaults` heading appears in the report
- [ ] Single turn — agent produced the report without asking clarification questions
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description

### 2. Missing optional fields — proceed with defaults

**What it tests:** All optional fields omitted — agent applies defaults without asking.

**User Simulator:** A data analyst who provides only the dataset path and problem description. Does not mention metrics, threshold, split ratio, or iterations. When the agent mentions the assumed defaults and asks if they are acceptable, confirms they are fine.

**Verification Criteria:**
- [ ] Report status is `proceed_with_defaults`
- [ ] Confirmed Inputs contains dataset path and problem description
- [ ] Confirmed Inputs does NOT have subsections for Target Metrics, Evaluation Threshold, Data Split Ratio, or Max Iterations (these were all defaulted, so they belong in Assumed Defaults)
- [ ] Gap Report lists `target_metrics` as `non-blocking` with default `["f1/macro"]`
- [ ] Gap Report lists `evaluation_threshold` as `non-blocking` with default `0.80`
- [ ] Gap Report lists `data_split_ratio` as `non-blocking` with default `0.20`
- [ ] Gap Report lists `max_iterations` as `non-blocking` with default `10`
- [ ] Assumed Defaults table contains all four defaults with correct values
- [ ] Agent did NOT ask about optional fields before producing the report — applied defaults rather than treating them as blocking
- [ ] Agent conversationally mentioned the assumed defaults alongside the report
- [ ] Agent asked whether the assumed defaults are acceptable or if the user wants to adjust them
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description

### 3. Missing required field — clarification loop

**What it tests:** Dataset is missing — agent enters clarification loop, asks for it, user provides it.

**User Simulator:** A data analyst who describes their routing problem clearly but forgets to provide the dataset. Does not mention any optional fields (metrics, threshold, split ratio, iterations). When asked about the dataset, provides the path `tests/scenarios/data/valid_dataset.jsonl`. When the agent mentions assumed defaults and asks if they are acceptable, confirms they are fine.

**Verification Criteria:**
- [ ] Agent asked about the dataset (not all gaps at once)
- [ ] Agent did not ask about optional fields
- [ ] Conversation took at least 2 turns before the report was produced
- [ ] Final report status is `proceed_with_defaults`
- [ ] Confirmed Inputs contains the dataset path provided in the follow-up
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description

### 4. Multiple blocking gaps

**What it tests:** Both required fields missing — agent asks one at a time in priority order.

**User Simulator:** A user who only says "I want to optimize my routing" with no dataset and no real problem description. When asked about the problem, describes a model-tier routing setup. When asked about the dataset, provides the path. When the agent mentions assumed defaults and asks if they are acceptable, confirms they are fine.

**Verification Criteria:**
- [ ] Agent did NOT dump both gaps in a single message
- [ ] Agent asked about the problem description before the dataset (priority order)
- [ ] Each turn focused on a single gap (not multiple unrelated questions)
- [ ] Final report status is `proceed_with_defaults`
- [ ] Confirmed Inputs contains both the problem description and dataset path
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description

### 5. Mixed blocking and non-blocking gaps

**What it tests:** One blocking gap (dataset) plus all optional fields missing — agent only asks about the blocking gap.

**User Simulator:** A user who provides a clear problem description but no dataset and no optional fields. Provides dataset when asked. When the agent mentions assumed defaults and asks if they are acceptable, confirms they are fine.

**Verification Criteria:**
- [ ] Agent asked about the dataset (blocking gap)
- [ ] Agent never asked about optional fields (non-blocking — defaults applied)
- [ ] Final report status is `proceed_with_defaults`
- [ ] Gap Report contains both blocking-resolved and non-blocking entries
- [ ] Assumed Defaults table lists all four optional field defaults
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description

### 6. Malformed dataset

**What it tests:** Dataset is provided but structurally invalid — agent surfaces the issue using the "fix" question type.

**User Simulator:** A user who provides everything including dataset path `tests/scenarios/data/no_expected_field.jsonl`. When the agent points out the structural issue, provides the corrected path `tests/scenarios/data/valid_dataset.jsonl`.

**Verification Criteria:**
- [ ] Agent identified that the dataset is missing the `expected` field
- [ ] Agent used a "fix" style question — explained the issue, showed what's needed
- [ ] Agent did not reject the submission outright — guided the user to fix it
- [ ] Final report references the corrected dataset path
- [ ] Final report status is `proceed_with_defaults`
- [ ] Agent called `submit_input_report` tool with the report, corrected dataset path, and problem description

**Note:** This scenario depends on the Data Validation agent (THP-73), which is not yet implemented. The system prompt says: "Until then, accept the dataset path as-is." **This scenario is deferred until THP-73 is complete.** The agent will currently accept the malformed dataset without flagging issues, so the test would not produce meaningful results. When THP-73 lands, un-defer this scenario and verify the full fix flow.

### 7. Vague problem description — needs refinement

**What it tests:** Comprehension-first behavior — agent doesn't accept a vague description, asks to understand the routing problem.

**User Simulator:** A user who provides the dataset and says "I want to route stuff to the right place." Has actual context they can share when asked: they're routing customer support queries to haiku/sonnet/opus based on complexity, where cost matters more than perfect accuracy for simple queries. Does not provide optional fields. When the agent mentions assumed defaults and asks if they are acceptable, confirms they are fine.

**Verification Criteria:**
- [ ] Agent did not accept "route stuff to the right place" as a valid problem description
- [ ] Agent asked at least one clarifying question about the routing context (what types of requests, what tiers, what trade-offs)
- [ ] Final report contains a refined, specific problem description — not the original vague input
- [ ] The refined description mentions concrete tiers or tools
- [ ] The refined description reflects the information the user provided during clarification
- [ ] Final report status is `proceed_with_defaults`
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description

### 8. Ambiguous tiers — choose question type

**What it tests:** The "choose" question type — agent presents options when input is ambiguous.

**User Simulator:** A user who provides the dataset and says "I need to route queries between my cheap and expensive models." Does not name specific tiers. Does not provide optional fields. When presented with options, selects one (e.g., "the first option — haiku and opus"). When the agent mentions assumed defaults and asks if they are acceptable, confirms they are fine.

**Verification Criteria:**
- [ ] Agent recognized the ambiguity in "cheap and expensive models"
- [ ] Agent presented multiple-choice options (e.g., "Are these tiers like Haiku/Sonnet/Opus, or custom endpoints, or something else?")
- [ ] Options included a "none of these" or open-ended escape
- [ ] Final problem description in the report includes the concrete tier names the user selected
- [ ] Final report status is `proceed_with_defaults`
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description

### 9. Contradictory metrics — invalid optimization target

**What it tests:** Agent catches a metric that can't be used as an optimization target.

**User Simulator:** A user who provides dataset, a clear problem description, and says "I want to optimize for the confusion matrix." Does not provide other optional fields. When the agent explains that confusion is diagnostic only, switches to "okay, then let's go with accuracy, at least 85%." When the agent mentions assumed defaults and asks if they are acceptable, confirms they are fine.

**Verification Criteria:**
- [ ] Agent identified that `confusion` is not suitable as an optimization target
- [ ] Agent explained why (diagnostic only, no single scalar to optimize)
- [ ] Agent suggested valid alternatives
- [ ] Final report lists a valid optimization metric (not confusion)
- [ ] Agent handled this conversationally, not as a hard error
- [ ] Final report status is `proceed_with_defaults`
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description

### 10. Domain mismatch — not a routing problem

**What it tests:** Agent recognizes when the described problem isn't cost-quality routing.

**User Simulator:** A user who provides the dataset but describes a sentiment analysis problem: "I want to classify customer reviews as positive, negative, or neutral." When the agent surfaces the mismatch, either reframes as routing ("actually I want to route sentiment requests to different model tiers by difficulty") or acknowledges the mismatch.

**Verification Criteria:**
- [ ] Agent recognized that sentiment classification is not cost-quality routing
- [ ] Agent surfaced the mismatch — did not silently proceed
- [ ] Agent either helped reframe the problem as routing or clearly explained why this isn't a routing problem
- [ ] If reframed: final report has a valid routing problem description
- [ ] If not reframed: no report was produced, conversation ended with a clear explanation
- [ ] If reframed: agent called `submit_input_report` tool with the report, dataset path, and problem description
- [ ] If not reframed: agent did NOT call `submit_input_report`

### 11. Persistent clarification — unhelpful answers

**What it tests:** The agent persists when the user gives unhelpful or off-topic answers — it never gives up or produces a premature report.

**User Simulator:** A user who wants to optimize routing but gives vague, off-topic, or unhelpful answers for the first 2-3 turns (e.g., "just make it work", "I don't know, figure it out"). Eventually provides a real problem description and dataset path when the agent rephrases its question. When the agent mentions assumed defaults and asks if they are acceptable, confirms they are fine.

**Verification Criteria:**
- [ ] Agent did not give up after unhelpful answers
- [ ] Agent did not produce a report without the required fields
- [ ] Agent rephrased or approached the question differently after each unhelpful answer
- [ ] Agent remained conversational and patient — not robotic or repetitive
- [ ] Final report was eventually produced with status `proceed_with_defaults`
- [ ] Conversation took at least 4 turns
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description

### 12. Natural language answers — non-standard format

**What it tests:** The agent accepts information provided in natural, conversational language rather than requiring structured field values.

**User Simulator:** A user who provides all required information but in a rambling, conversational way. For example: "So basically we have this JSONL file at tests/scenarios/data/valid_dataset.jsonl and what we're trying to do is figure out which queries should go to the cheap model and which ones need the expensive one, you know? Like simple stuff goes to haiku and the hard questions go to opus. Oh and we care about accuracy, like at least 90%." When the agent mentions assumed defaults and asks if they are acceptable, confirms they are fine.

**Verification Criteria:**
- [ ] Agent extracted the dataset path from the conversational message
- [ ] Agent extracted the problem description from the natural language
- [ ] Agent extracted the metric spec (`accuracy >= 0.90`) from informal phrasing
- [ ] Agent did not ask the user to reformat or re-provide information already given
- [ ] Final report contains the extracted information in clean, structured form
- [ ] Final report status is `proceed_with_defaults` (user provided dataset, problem description, and target metric, but not threshold, split ratio, or iterations — those get defaults)
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
- [ ] Agent called `submit_input_report` tool with the report, dataset path, and problem description

## Out of scope

- **Automated test runner** — these tests are run manually via Claude Code, not via `pytest`.
- **Data Validation agent integration** — scenario 6 tests what validation the agent can do now; full integration comes with THP-73.
- **Performance testing** — no latency or token-usage assertions.
- **Prompt regression testing** — if the system prompt changes, tests may need updating. This is expected.
- **Override mechanism** — testing re-submission after the report is produced is a separate concern.
