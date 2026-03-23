# THP-146 Integration Tests Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create 12 Markdown scenario files and 2 synthetic datasets that test the User Input agent's multi-turn conversation behavior through Claude Code orchestration.

**Architecture:** Each scenario is a self-contained MD file with three sections (User Simulator, Scenario Description, Verification Criteria). Claude Code reads a scenario, orchestrates three sub-agents (User Input Agent, User Simulator, Verification Agent), and reports pass/fail. No Python code — all files are Markdown or JSONL.

**Tech Stack:** Markdown scenario files, JSONL datasets, Claude Code sub-agent orchestration, pre-configured Odysseus MCP server.

**Spec:** `docs/superpowers/specs/2026-03-23-thp-146-integration-tests-design.md`

---

## Chunk 0: Orchestration documentation

### Task 0: Create tests/scenarios/README.md

**Files:**
- Create: `tests/scenarios/README.md`

- [ ] **Step 1: Write the orchestration README**

Write to `tests/scenarios/README.md`:

```markdown
# Integration Test Scenarios

Test scenarios for the User Input agent. Each `.md` file in this directory is a self-contained test scenario executed by Claude Code.

## Prerequisites

- The Odysseus MCP server must be pre-configured and connected to Claude Code before running tests.
- Real LLM API calls are made — ensure `ANTHROPIC_API_KEY` is set.

## How to run a scenario

Tell Claude Code:

> Run the integration test in `tests/scenarios/01_complete_submission.md`

Claude Code will:

1. Read the scenario file and parse its sections.
2. Spin up a **User Simulator** sub-agent with the `## User Simulator` section as its instructions.
3. Spin up a **User Input Agent** sub-agent with `prompts/user_input_system.md` as its system prompt, connected to the MCP tools.
4. Get the opening message from the User Simulator.
5. Broker the conversation turn-by-turn:
   - Pass user message → User Input Agent
   - Receive agent response
   - If response contains `# Validated Input Report` → conversation done, go to step 6
   - Otherwise pass agent response → User Simulator → get next message → loop
6. Spin up a **Verification Agent** with the transcript, report, and criteria.
7. Report pass/fail results.

## Safety valve

Maximum **20 turns**. If the conversation has not produced a validated input report within 20 turns, the test fails with "conversation did not converge."

## Verification Agent input format

The Verification Agent receives:

1. **Conversation transcript** — interleaved messages in this format:
   ```
   User: <message>
   Agent: <message>
   [Tool call: tool_name(args)]
   [Tool result: ...]
   User: <next message>
   ...
   ```
2. **Final validated input report** — the Markdown content after `# Validated Input Report` in the agent's final message.
3. **Verification criteria** — the `## Verification Criteria` checklist from the scenario file.

A scenario passes only if **all** verification criteria pass. The Verification Agent reports each criterion individually with pass/fail and reasoning, plus an overall verdict.

## Scenario file structure

Each scenario follows this template:

- `## Setup` — data files and preconditions
- `## Scenario Description` — plain language context
- `## User Simulator` — persona, knowledge, behavior, opening message
- `## Verification Criteria` — pass/fail checklist

See the design spec at `docs/superpowers/specs/2026-03-23-thp-146-integration-tests-design.md` for full details.
```

- [ ] **Step 2: Commit**

```bash
git add tests/scenarios/README.md
git commit -m "docs(thp-146): add orchestration README for integration test scenarios"
```

---

## Chunk 1: Synthetic data and foundational scenarios

### Task 1: Create synthetic test datasets

**Files:**
- Create: `tests/scenarios/data/valid_dataset.jsonl`
- Create: `tests/scenarios/data/no_expected_field.jsonl`

- [ ] **Step 1: Create the directory structure**

```bash
mkdir -p tests/scenarios/data
```

- [ ] **Step 2: Create `valid_dataset.jsonl`**

Write to `tests/scenarios/data/valid_dataset.jsonl`:

```jsonl
{"id": "1", "input": {"query": "What is 2+2?"}, "expected": {"route": "haiku"}}
{"id": "2", "input": {"query": "Explain quantum entanglement in detail with examples"}, "expected": {"route": "opus"}}
{"id": "3", "input": {"query": "Translate 'hello' to French"}, "expected": {"route": "haiku"}}
{"id": "4", "input": {"query": "Write a nuanced essay on the ethics of AI regulation"}, "expected": {"route": "opus"}}
{"id": "5", "input": {"query": "Summarize this paragraph in one sentence"}, "expected": {"route": "sonnet"}}
```

- [ ] **Step 3: Create `no_expected_field.jsonl`**

Write to `tests/scenarios/data/no_expected_field.jsonl` — same records with `expected` stripped:

```jsonl
{"id": "1", "input": {"query": "What is 2+2?"}}
{"id": "2", "input": {"query": "Explain quantum entanglement in detail with examples"}}
{"id": "3", "input": {"query": "Translate 'hello' to French"}}
{"id": "4", "input": {"query": "Write a nuanced essay on the ethics of AI regulation"}}
{"id": "5", "input": {"query": "Summarize this paragraph in one sentence"}}
```

- [ ] **Step 4: Validate JSONL is well-formed**

```bash
python -c "import json; [json.loads(l) for l in open('tests/scenarios/data/valid_dataset.jsonl')]; print('valid_dataset OK')"
python -c "import json; [json.loads(l) for l in open('tests/scenarios/data/no_expected_field.jsonl')]; print('no_expected_field OK')"
```

Expected: Both print OK.

- [ ] **Step 5: Commit**

```bash
git add tests/scenarios/data/valid_dataset.jsonl tests/scenarios/data/no_expected_field.jsonl
git commit -m "feat(thp-146): add synthetic test datasets for integration scenarios"
```

---

### Task 2: Scenario 01 — Complete submission (proceed)

**Files:**
- Create: `tests/scenarios/01_complete_submission.md`

- [ ] **Step 1: Write the scenario file**

Write to `tests/scenarios/01_complete_submission.md`:

```markdown
# Scenario: Complete Submission

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides all required and optional fields in a single message. The agent should produce a validated input report immediately with status `proceed` — no clarification needed, no defaults applied.

## User Simulator
You are a data analyst at a tech company. You are setting up a routing optimization pipeline and have all the information ready.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl` — 5 labeled routing examples mapping queries to haiku/sonnet/opus tiers by complexity.
- Problem description: "Route customer queries to haiku/sonnet/opus tiers based on complexity — simple factual questions to haiku, moderate tasks to sonnet, complex reasoning to opus."
- Target metrics: `accuracy >= 0.90`
- Evaluation threshold: `0.85`
- Data split ratio: `0.25`
- Max iterations: `5`

**Behavior:** Provide all of the above in your opening message. Be clear and direct. Do not withhold any information.

**Opening message:** "Hi, I'd like to set up routing optimization. Here's what I have: my dataset is at `tests/scenarios/data/valid_dataset.jsonl` — it has 5 labeled examples mapping queries to haiku, sonnet, or opus tiers based on complexity. The problem is to route customer queries to the right tier: simple factual questions go to haiku, moderate tasks to sonnet, and complex reasoning to opus. I want to optimize for accuracy with a threshold of at least 90% (`accuracy >= 0.90`). Use an evaluation threshold of 0.85, a data split ratio of 0.25, and cap it at 5 iterations."

## Verification Criteria
- [ ] Report status is `proceed`
- [ ] Confirmed Inputs contains the dataset path `tests/scenarios/data/valid_dataset.jsonl`
- [ ] Confirmed Inputs contains the problem description about routing queries to haiku/sonnet/opus by complexity
- [ ] Confirmed Inputs lists `accuracy >= 0.90` as target metric
- [ ] Confirmed Inputs includes evaluation threshold (0.85), data split ratio (0.25), and max iterations (5)
- [ ] No `## Gap Report` heading appears in the report
- [ ] No `## Assumed Defaults` heading appears in the report
- [ ] Single turn — agent produced the report without asking clarification questions
```

- [ ] **Step 2: Commit**

```bash
git add tests/scenarios/01_complete_submission.md
git commit -m "feat(thp-146): add scenario 01 — complete submission (proceed)"
```

---

### Task 3: Scenario 02 — Missing optional fields (proceed with defaults)

**Files:**
- Create: `tests/scenarios/02_missing_optional_defaults.md`

- [ ] **Step 1: Write the scenario file**

Write to `tests/scenarios/02_missing_optional_defaults.md`:

```markdown
# Scenario: Missing Optional Fields — Proceed with Defaults

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides both required fields (dataset and problem description) but omits all optional fields (target metrics, evaluation threshold, data split ratio, max iterations). The agent should apply defaults for the missing optional fields, mention them conversationally, and ask the user if the defaults are acceptable before finalizing.

## User Simulator
You are a data analyst who knows the routing problem well but hasn't thought about metrics or thresholds yet.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- Problem description: "We route incoming customer queries to either haiku, sonnet, or opus depending on how complex the query is. Simple lookups go to haiku, multi-step tasks go to sonnet, and open-ended reasoning goes to opus."
- You have NO preferences for metrics, thresholds, split ratios, or iteration limits.

**Behavior:**
- Provide the dataset and problem description in your opening message.
- Do NOT mention metrics, thresholds, split ratios, or iterations.
- If the agent mentions assumed defaults and asks whether they are acceptable, confirm that they are fine.

**Opening message:** "Hi, I want to optimize my routing setup. My dataset is at `tests/scenarios/data/valid_dataset.jsonl` — it has labeled examples of queries routed to haiku, sonnet, or opus tiers. The routing logic is based on complexity: simple lookups go to haiku, multi-step tasks to sonnet, and open-ended reasoning to opus."

## Verification Criteria
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
```

- [ ] **Step 2: Commit**

```bash
git add tests/scenarios/02_missing_optional_defaults.md
git commit -m "feat(thp-146): add scenario 02 — missing optional fields (defaults)"
```

---

### Task 4: Scenario 03 — Missing required field (clarification loop)

**Files:**
- Create: `tests/scenarios/03_missing_required_clarification.md`

- [ ] **Step 1: Write the scenario file**

Write to `tests/scenarios/03_missing_required_clarification.md`:

```markdown
# Scenario: Missing Required Field — Clarification Loop

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides a clear problem description but forgets to include the dataset. The agent should detect the missing required field, ask for it (without dumping all gaps at once), and produce the report after the user provides it.

## User Simulator
You are a data analyst who has been thinking about the routing problem but forgot to attach the dataset.

**Your knowledge:**
- Problem description: "We have a three-tier model routing system — haiku for cheap/fast queries, sonnet for moderate complexity, opus for deep reasoning tasks. We want to optimize the routing decisions to minimize cost while maintaining quality."
- Dataset path (provide when asked): `tests/scenarios/data/valid_dataset.jsonl`
- You have NO preferences for optional fields (metrics, threshold, split ratio, iterations).

**Behavior:**
- In your opening message, describe the routing problem clearly but do NOT mention any dataset.
- When the agent asks about the dataset, provide the path.
- Do NOT volunteer optional field values at any point.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I'm working on a routing optimization project. We have a three-tier model routing system — haiku for cheap/fast queries, sonnet for moderate complexity, and opus for deep reasoning tasks. We want to optimize the routing decisions to minimize cost while maintaining quality."

## Verification Criteria
- [ ] Agent asked about the dataset (not all gaps at once)
- [ ] Agent did not ask about optional fields
- [ ] Conversation took at least 2 turns before the report was produced
- [ ] Final report status is `proceed_with_defaults`
- [ ] Confirmed Inputs contains the dataset path provided in the follow-up
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
```

- [ ] **Step 2: Commit**

```bash
git add tests/scenarios/03_missing_required_clarification.md
git commit -m "feat(thp-146): add scenario 03 — missing required field (clarification)"
```

---

### Task 5: Scenario 04 — Multiple blocking gaps

**Files:**
- Create: `tests/scenarios/04_multiple_blocking_gaps.md`

- [ ] **Step 1: Write the scenario file**

Write to `tests/scenarios/04_multiple_blocking_gaps.md`:

```markdown
# Scenario: Multiple Blocking Gaps

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides a vague opening with neither a real problem description nor a dataset. Both required fields are missing. The agent should ask one question at a time in priority order: problem description first (priority 1), then dataset (priority 2).

## User Simulator
You are a manager who heard about the routing optimizer and wants to try it, but hasn't prepared any details yet.

**Your knowledge:**
- Problem description (provide when asked): "We route user requests to different Claude model tiers — haiku, sonnet, and opus — based on the complexity of the task. Simple questions go to haiku, moderate analysis to sonnet, and complex creative or reasoning tasks to opus."
- Dataset path (provide when asked): `tests/scenarios/data/valid_dataset.jsonl`
- You have NO preferences for optional fields.

**Behavior:**
- Your opening message is vague — you want to optimize routing but don't provide specifics.
- When the agent asks about the problem, describe the model-tier routing setup.
- When the agent asks about the dataset, provide the path.
- Do NOT volunteer information before being asked.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I want to optimize my routing."

## Verification Criteria
- [ ] Agent did NOT dump both gaps in a single message
- [ ] Agent asked about the problem description before the dataset (priority order)
- [ ] Each turn focused on a single gap (not multiple unrelated questions)
- [ ] Final report status is `proceed_with_defaults`
- [ ] Confirmed Inputs contains both the problem description and dataset path
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
```

- [ ] **Step 2: Commit**

```bash
git add tests/scenarios/04_multiple_blocking_gaps.md
git commit -m "feat(thp-146): add scenario 04 — multiple blocking gaps"
```

---

### Task 6: Scenario 05 — Mixed blocking and non-blocking gaps

**Files:**
- Create: `tests/scenarios/05_mixed_blocking_nonblocking.md`

- [ ] **Step 1: Write the scenario file**

Write to `tests/scenarios/05_mixed_blocking_nonblocking.md`:

```markdown
# Scenario: Mixed Blocking and Non-Blocking Gaps

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides a clear problem description but no dataset and no optional fields. The agent should ask only about the blocking gap (dataset) and silently apply defaults for the non-blocking optional fields.

## User Simulator
You are a data scientist who has the routing problem well understood but forgot the dataset and hasn't specified any optional parameters.

**Your knowledge:**
- Problem description: "Our system routes API requests to haiku, sonnet, or opus based on task complexity. Straightforward lookups and translations go to haiku, summarization and moderate analysis to sonnet, and complex multi-step reasoning to opus. We want to optimize this routing for cost efficiency."
- Dataset path (provide when asked): `tests/scenarios/data/valid_dataset.jsonl`
- You have NO preferences for optional fields.

**Behavior:**
- Provide only the problem description in your opening message — no dataset, no optional fields.
- When the agent asks about the dataset, provide the path.
- Do NOT volunteer optional field preferences.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I need help optimizing our model routing. Our system routes API requests to haiku, sonnet, or opus based on task complexity. Straightforward lookups and translations go to haiku, summarization and moderate analysis to sonnet, and complex multi-step reasoning to opus. We want to optimize this routing for cost efficiency."

## Verification Criteria
- [ ] Agent asked about the dataset (blocking gap)
- [ ] Agent never asked about optional fields (non-blocking — defaults applied)
- [ ] Final report status is `proceed_with_defaults`
- [ ] Gap Report contains both blocking-resolved and non-blocking entries
- [ ] Assumed Defaults table lists all four optional field defaults
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
```

- [ ] **Step 2: Commit**

```bash
git add tests/scenarios/05_mixed_blocking_nonblocking.md
git commit -m "feat(thp-146): add scenario 05 — mixed blocking and non-blocking gaps"
```

---

### Task 7: Scenario 06 — Malformed dataset (deferred)

**Files:**
- Create: `tests/scenarios/06_malformed_dataset.md`

- [ ] **Step 1: Write the scenario file**

Write to `tests/scenarios/06_malformed_dataset.md`:

```markdown
# Scenario: Malformed Dataset

> **DEFERRED:** This scenario depends on the Data Validation agent (THP-73), which is not yet implemented. The system prompt currently says "accept the dataset path as-is," so this test would not produce meaningful results. Un-defer when THP-73 lands.

## Setup
- Malformed dataset: `tests/scenarios/data/no_expected_field.jsonl`
- Corrected dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides all fields including a dataset, but the dataset is structurally invalid — records are missing the `expected` field. The agent should detect the structural issue (via the Data Validation agent), surface it using the "fix" question type, and guide the user to provide a corrected dataset.

## User Simulator
You are a data analyst who accidentally exported the dataset without the label column.

**Your knowledge:**
- Original (broken) dataset: `tests/scenarios/data/no_expected_field.jsonl`
- Corrected dataset path (provide when told about the issue): `tests/scenarios/data/valid_dataset.jsonl`
- Problem description: "Route queries to haiku, sonnet, or opus based on complexity."

**Behavior:**
- Provide the broken dataset path and problem description in your opening message.
- When the agent explains the structural issue, acknowledge the mistake and provide the corrected dataset path.

**Opening message:** "Hi, I'd like to optimize my routing. My dataset is at `tests/scenarios/data/no_expected_field.jsonl` and the problem is routing queries to haiku, sonnet, or opus based on complexity."

## Verification Criteria
- [ ] Agent identified that the dataset is missing the `expected` field
- [ ] Agent used a "fix" style question — explained the issue, showed what's needed
- [ ] Agent did not reject the submission outright — guided the user to fix it
- [ ] Final report references the corrected dataset path `tests/scenarios/data/valid_dataset.jsonl`
- [ ] Final report status is `proceed_with_defaults`
```

- [ ] **Step 2: Commit**

```bash
git add tests/scenarios/06_malformed_dataset.md
git commit -m "feat(thp-146): add scenario 06 — malformed dataset (deferred for THP-73)"
```

## Chunk 2: Comprehension and refinement scenarios

### Task 8: Scenario 07 — Vague problem description

**Files:**
- Create: `tests/scenarios/07_vague_problem_description.md`

- [ ] **Step 1: Write the scenario file**

Write to `tests/scenarios/07_vague_problem_description.md`:

```markdown
# Scenario: Vague Problem Description — Needs Refinement

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides a dataset but only a vague problem description. The agent should recognize that "route stuff to the right place" is insufficient, engage in comprehension-first questioning to understand the routing problem, and produce a report with a refined description.

## User Simulator
You are a product manager who knows the routing system well but described it vaguely because you assumed the tool would figure it out.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- Actual routing context (share when asked): You route customer support queries to three Claude model tiers — haiku for simple FAQ-style questions, sonnet for moderately complex troubleshooting, and opus for deep technical investigations. Cost matters more than perfect accuracy for simple queries — you'd rather occasionally misroute a simple query to sonnet than pay opus prices for everything.
- You have NO preferences for optional fields.

**Behavior:**
- Opening message is deliberately vague about the problem.
- When the agent asks clarifying questions about tiers, request types, or trade-offs, share the details from your knowledge.
- Respond naturally and conversationally — don't recite a spec.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "Hey, I've got a dataset at `tests/scenarios/data/valid_dataset.jsonl` and I want to route stuff to the right place. Can you help me optimize this?"

## Verification Criteria
- [ ] Agent did not accept "route stuff to the right place" as a valid problem description
- [ ] Agent asked at least one clarifying question about the routing context (what types of requests, what tiers, what trade-offs)
- [ ] Final report contains a refined, specific problem description — not the original vague input
- [ ] The refined description mentions concrete tiers or tools (haiku, sonnet, opus)
- [ ] The refined description reflects the information the user provided during clarification
- [ ] Final report status is `proceed_with_defaults`
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
```

- [ ] **Step 2: Commit**

```bash
git add tests/scenarios/07_vague_problem_description.md
git commit -m "feat(thp-146): add scenario 07 — vague problem description"
```

---

### Task 9: Scenario 08 — Ambiguous tiers (choose question type)

**Files:**
- Create: `tests/scenarios/08_ambiguous_tiers.md`

- [ ] **Step 1: Write the scenario file**

Write to `tests/scenarios/08_ambiguous_tiers.md`:

```markdown
# Scenario: Ambiguous Tiers — Choose Question Type

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user mentions "cheap and expensive models" without specifying concrete tier names. The agent should recognize the ambiguity and use the "choose" question type — presenting multiple-choice options for what the tiers might be, with an open-ended escape option.

## User Simulator
You are a developer who thinks in terms of "cheap model" and "expensive model" but hasn't mapped these to specific product names.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- When presented with options: you're using haiku as the cheap tier and opus as the expensive tier. Select that option.
- You have NO preferences for optional fields.

**Behavior:**
- Opening message mentions cheap/expensive models without naming them.
- When the agent presents options, pick the one that matches haiku/opus (or describe it if it's "none of these").
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I have a dataset at `tests/scenarios/data/valid_dataset.jsonl`. I need to route queries between my cheap and expensive models. Cheap for the easy stuff, expensive for the hard stuff."

## Verification Criteria
- [ ] Agent recognized the ambiguity in "cheap and expensive models"
- [ ] Agent presented multiple-choice options (e.g., "Are these tiers like Haiku/Sonnet/Opus, or custom endpoints, or something else?")
- [ ] Options included a "none of these" or open-ended escape
- [ ] Final problem description in the report includes the concrete tier names the user selected
- [ ] Final report status is `proceed_with_defaults`
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
```

- [ ] **Step 2: Commit**

```bash
git add tests/scenarios/08_ambiguous_tiers.md
git commit -m "feat(thp-146): add scenario 08 — ambiguous tiers (choose question)"
```

---

### Task 10: Scenario 09 — Contradictory metrics

**Files:**
- Create: `tests/scenarios/09_contradictory_metrics.md`

- [ ] **Step 1: Write the scenario file**

Write to `tests/scenarios/09_contradictory_metrics.md`:

```markdown
# Scenario: Contradictory Metrics — Invalid Optimization Target

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user requests optimization for the confusion matrix, which is diagnostic only and not suitable as an optimization target. The agent should catch this, explain why, suggest alternatives, and guide the user to a valid metric.

## User Simulator
You are a data scientist who is familiar with confusion matrices from sklearn but hasn't thought about what makes a good optimization target vs. a diagnostic tool.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- Problem description: "We route user queries to haiku, sonnet, or opus based on task complexity. Simple questions go to haiku, moderate to sonnet, complex to opus."
- Initial metric preference: confusion matrix (you think it gives the most complete picture)
- Fallback metric (use when agent explains the issue): "okay, then let's go with accuracy, at least 85%"
- You have NO preferences for other optional fields.

**Behavior:**
- Provide dataset, problem description, and your metric preference in the opening message.
- When the agent explains that confusion is diagnostic only, accept the explanation and switch to accuracy.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I want to optimize my routing. Dataset is at `tests/scenarios/data/valid_dataset.jsonl`. We route queries to haiku, sonnet, or opus by complexity — simple to haiku, moderate to sonnet, complex to opus. I want to optimize for the confusion matrix since it gives the fullest picture of how the routing is performing."

## Verification Criteria
- [ ] Agent identified that `confusion` is not suitable as an optimization target
- [ ] Agent explained why (diagnostic only, no single scalar to optimize)
- [ ] Agent suggested valid alternatives
- [ ] Final report lists a valid optimization metric (not confusion)
- [ ] Agent handled this conversationally, not as a hard error
- [ ] Final report status is `proceed_with_defaults`
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
```

- [ ] **Step 2: Commit**

```bash
git add tests/scenarios/09_contradictory_metrics.md
git commit -m "feat(thp-146): add scenario 09 — contradictory metrics"
```

---

### Task 11: Scenario 10 — Domain mismatch

**Files:**
- Create: `tests/scenarios/10_domain_mismatch.md`

- [ ] **Step 1: Write the scenario file**

Write to `tests/scenarios/10_domain_mismatch.md`:

```markdown
# Scenario: Domain Mismatch — Not a Routing Problem

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user describes a sentiment classification problem, not a cost-quality routing problem. The agent should recognize the mismatch and surface it rather than silently proceeding.

## User Simulator
You are a product analyst who confused this tool with a general ML classifier. You have a dataset but your problem is sentiment analysis, not model-tier routing.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- Your actual problem: "I want to classify customer reviews as positive, negative, or neutral."
- If the agent points out this isn't a routing problem: you realize the confusion. You can either:
  - Reframe: "Oh wait, actually what I really need is to route sentiment analysis requests to different model tiers by difficulty — simple positive/negative to haiku, nuanced mixed-sentiment reviews to opus."
  - OR acknowledge: "Ah, you're right, this isn't what I need. Thanks for clarifying."
- Choose whichever response feels more natural in the conversation.

**Behavior:**
- Opening message describes a sentiment classification problem.
- Respond naturally to the agent's feedback about the mismatch.
- If you reframe, provide the routing-specific details.

**Opening message:** "Hi, I have a dataset at `tests/scenarios/data/valid_dataset.jsonl` and I want to classify customer reviews as positive, negative, or neutral. Can you help me set this up?"

## Verification Criteria
- [ ] Agent recognized that sentiment classification is not cost-quality routing
- [ ] Agent surfaced the mismatch — did not silently proceed
- [ ] Agent either helped reframe the problem as routing or clearly explained why this isn't a routing problem
- [ ] If reframed: final report has a valid routing problem description
- [ ] If not reframed: no report was produced, conversation ended with a clear explanation
```

- [ ] **Step 2: Commit**

```bash
git add tests/scenarios/10_domain_mismatch.md
git commit -m "feat(thp-146): add scenario 10 — domain mismatch"
```

---

### Task 12: Scenario 11 — Persistent clarification

**Files:**
- Create: `tests/scenarios/11_persistent_clarification.md`

- [ ] **Step 1: Write the scenario file**

Write to `tests/scenarios/11_persistent_clarification.md`:

```markdown
# Scenario: Persistent Clarification — Unhelpful Answers

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user gives vague, unhelpful, or off-topic answers for the first several turns. The agent should persist — rephrasing questions, approaching from different angles — without giving up or producing a premature report.

## User Simulator
You are a busy executive who wants results but doesn't want to spend time on details. You will eventually cooperate but need the agent to earn your engagement.

**Your knowledge:**
- Problem description (provide on turn 4+): "We route incoming API requests to haiku, sonnet, or opus based on how complex the query is. Simple stuff to haiku, hard stuff to opus."
- Dataset path (provide on turn 5+): `tests/scenarios/data/valid_dataset.jsonl`
- You have NO preferences for optional fields.

**Behavior:**
- Turn 1 (opening): Be vague — you want to optimize something.
- Turn 2: Deflect — "just make it work" or "I don't have time for this, can't you figure it out?"
- Turn 3: Give a slightly more useful but still insufficient answer — "it's about routing queries" without specifying tiers or trade-offs.
- Turn 4+: Start cooperating. Provide the problem description when the agent asks in a way that resonates.
- Turn 5+: Provide the dataset path when asked.
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "I need to optimize something. Can you help?"

## Verification Criteria
- [ ] Agent did not give up after unhelpful answers
- [ ] Agent did not produce a report without the required fields
- [ ] Agent rephrased or approached the question differently after each unhelpful answer
- [ ] Agent remained conversational and patient — not robotic or repetitive
- [ ] Final report was eventually produced with status `proceed_with_defaults`
- [ ] Conversation took at least 4 turns
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
```

- [ ] **Step 2: Commit**

```bash
git add tests/scenarios/11_persistent_clarification.md
git commit -m "feat(thp-146): add scenario 11 — persistent clarification"
```

---

### Task 13: Scenario 12 — Natural language answers

**Files:**
- Create: `tests/scenarios/12_natural_language_answers.md`

- [ ] **Step 1: Write the scenario file**

Write to `tests/scenarios/12_natural_language_answers.md`:

```markdown
# Scenario: Natural Language Answers — Non-Standard Format

## Setup
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`

## Scenario Description
The user provides all required information in a single rambling, conversational message rather than in structured field-value format. The agent should extract the relevant information without asking the user to reformat or re-provide anything.

## User Simulator
You are a chatty colleague who explains everything in a stream-of-consciousness style.

**Your knowledge:**
- Dataset: `tests/scenarios/data/valid_dataset.jsonl`
- Problem: routing queries to haiku/opus by complexity
- Metric: accuracy, at least 90%
- No preferences for other optional fields.

**Behavior:**
- Provide everything in one big rambling message.
- If the agent asks you to reformat or re-provide information, push back: "I already told you all of that."
- When the agent mentions assumed defaults and asks if they are acceptable, confirm they are fine.

**Opening message:** "So basically we have this JSONL file at `tests/scenarios/data/valid_dataset.jsonl` and what we're trying to do is figure out which queries should go to the cheap model and which ones need the expensive one, you know? Like simple stuff goes to haiku and the hard questions go to opus. Oh and we care about accuracy, like at least 90%."

## Verification Criteria
- [ ] Agent extracted the dataset path from the conversational message
- [ ] Agent extracted the problem description from the natural language
- [ ] Agent extracted the metric spec (`accuracy >= 0.90`) from informal phrasing
- [ ] Agent did not ask the user to reformat or re-provide information already given
- [ ] Final report contains the extracted information in clean, structured form
- [ ] Final report status is `proceed_with_defaults` (user provided dataset, problem description, and target metric, but not threshold, split ratio, or iterations — those get defaults)
- [ ] Agent mentioned the assumed defaults and asked whether they are acceptable
```

- [ ] **Step 2: Commit**

```bash
git add tests/scenarios/12_natural_language_answers.md
git commit -m "feat(thp-146): add scenario 12 — natural language answers"
```

---

### Task 14: Final commit — update THP-146.md

**Files:**
- Modify: `odysseus/agents/THP-146.md`

- [ ] **Step 1: Update the ticket to reflect the new design**

Update `odysseus/agents/THP-146.md` to reflect that integration tests are now scenario-based MD files in `tests/scenarios/` driven by Claude Code orchestration with real API calls, not pytest-based mocked tests. Mark status as "Done."

- [ ] **Step 2: Commit**

```bash
git add odysseus/agents/THP-146.md
git commit -m "docs(thp-146): update ticket to reflect scenario-based integration test design"
```
