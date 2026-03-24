# Scenario 23: Classify Example — Simple Single-Hop Queries

**Date:** 2026-03-23
**Verdict:** PASS (14/14 criteria)

---

## Transcript

```
=== SCENARIO 23: Classify Example — Simple Single-Hop Queries ===

--- Turn 1 ---
User Simulator: I need you to classify three routing examples using the classify-example skill. Read `odysseus/skills/classify-example/SKILL.md` and `odysseus/skills/classify-example/references/vocabulary-registry-rules.md` first, then classify each example I give you.

The vocabulary registry is currently empty (no existing entries). Available routes are: haiku, sonnet, opus. Dataset size is 10.

Example rt-1:
- Query: 'What is the capital of France?'
- Ground-truth route: haiku

Please follow the skill procedure and produce the structured output.

Agent: I have read the skill procedure and the vocabulary registry rules. Let me classify example rt-1.

**Step 1 — Determine complexity_structure first**

Analysing the reasoning topology of "What is the capital of France?":

- **How many distinct reasoning steps?** One. The query asks for a single fact — the capital city of a specific country. A correct response requires retrieving one piece of well-known information.
- **Are steps independent or sequentially dependent?** Not applicable — there is only one step, so there are no dependencies.
- **Multiple disconnected constraints?** No. There is a single constraint: identify the capital of France.

This is a single-step factual retrieval with no chaining, no dependencies, and no parallel constraints. The vocabulary registry is empty, so no existing entry can match. I will propose a new complexity_structure entry: `single-step` — a query requiring exactly one reasoning or retrieval step with no dependencies.

Assigning `complexity_structure`: **single-step** (proposed)

**Step 2 — Classify intent_pattern**

With complexity established as single-step, I now classify the task type:

- **Primary goal:** The query asks for retrieval of a known fact. It is not asking for transformation, generation, analysis, or computation — it is purely a factual lookup.
- **Does complexity shift intent?** No. The single-step nature confirms this is a straightforward retrieval task, not an analytical or generative one.

The registry is empty, so I propose a new intent_pattern entry: `factual-lookup` — a query whose primary goal is retrieving a specific, well-known fact.

Assigning `intent_pattern`: **factual-lookup** (proposed)

**Step 3 — Vocabulary registry matching**

The registry is empty, so I must propose entries. The cluster threshold is max(3, ceil(0.05 * 10)) = max(3, 1) = 3. These proposals cannot be confirmed until at least 3 examples use them. I will note them as proposed.

**Cross-check:** The ground-truth route is haiku, which aligns with a single-step factual lookup — this is a trivial query that the smallest model handles well. No disagreement.

**Output:**

intent_pattern: factual-lookup
complexity_structure: single-step
proposed_entries:
  - field: complexity_structure
    name: single-step
    definition: Query requiring exactly one reasoning or retrieval step with no dependencies between sub-tasks.
    example_ids: [rt-1]
    justification: Registry is empty; no existing entry available for single-step queries.
  - field: intent_pattern
    name: factual-lookup
    definition: Query whose primary goal is retrieving a specific, well-known fact or piece of information.
    example_ids: [rt-1]
    justification: Registry is empty; no existing entry available for factual retrieval tasks.

--- Turn 2 ---
User Simulator: Now classify example rt-5:
- Query: 'What is 15% of 240?'
- Ground-truth route: haiku
Use the same vocabulary registry (still empty — proposed entries are not confirmed yet).

Agent: Classifying example rt-5.

**Step 1 — Determine complexity_structure first**

Analysing the reasoning topology of "What is 15% of 240?":

- **How many distinct reasoning steps?** One. The query asks for a single arithmetic computation: multiply 240 by 0.15. There is no chaining of results, no multi-step derivation.
- **Are steps independent or sequentially dependent?** Not applicable — one step only.
- **Multiple disconnected constraints?** No. A single operation is requested.

This has the same reasoning topology as rt-1: a single-step task with no dependencies. The proposed entry `single-step` ("query requiring exactly one reasoning or retrieval step with no dependencies between sub-tasks") fits exactly. Although that entry is not yet confirmed, I will reuse the same proposed label for consistency.

Assigning `complexity_structure`: **single-step** (proposed, reusing from rt-1)

**Step 2 — Classify intent_pattern**

With complexity established as single-step:

- **Primary goal:** The query asks for a numeric computation — calculating a percentage of a number. This is not retrieval of a known fact; it requires performing an arithmetic operation to produce the answer.
- **Does complexity shift intent?** No. The single-step nature confirms this is a simple, direct computation.

The proposed entry `factual-lookup` does not fit well here. "What is 15% of 240?" is not retrieving a stored fact — it requires an arithmetic operation. The distinction matters for routing because computation tasks have different error profiles than pure recall tasks (though both are trivially handled by haiku in this case).

I propose a new intent_pattern entry: `simple-computation` — a query whose primary goal is performing a straightforward arithmetic or formulaic calculation.

Assigning `intent_pattern`: **simple-computation** (proposed)

**Step 3 — Vocabulary registry matching**

Registry is still empty (proposals are unconfirmed). Updated proposals:

- `single-step` now covers example_ids: [rt-1, rt-5]
- `factual-lookup` still covers: [rt-1]
- `simple-computation` is new, covering: [rt-5]

None of these have reached the cluster threshold of 3 yet. They remain proposed.

**Cross-check:** The ground-truth route is haiku, consistent with a single-step simple computation — the smallest model handles basic arithmetic with near-perfect quality (0.99). No disagreement.

**Output:**

intent_pattern: simple-computation
complexity_structure: single-step
proposed_entries:
  - field: complexity_structure
    name: single-step
    definition: Query requiring exactly one reasoning or retrieval step with no dependencies between sub-tasks.
    example_ids: [rt-1, rt-5]
    justification: Registry is empty; no existing entry available for single-step queries.
  - field: intent_pattern
    name: simple-computation
    definition: Query whose primary goal is performing a straightforward arithmetic or formulaic calculation.
    example_ids: [rt-5]
    justification: Distinct from factual-lookup because the answer is derived through calculation, not recalled from known facts.

--- Turn 3 ---
User Simulator: Now classify example rt-10:
- Query: 'Define the word serendipity'
- Ground-truth route: haiku
Same empty registry.

Agent: Classifying example rt-10.

**Step 1 — Determine complexity_structure first**

Analysing the reasoning topology of "Define the word serendipity":

- **How many distinct reasoning steps?** One. The query asks for the definition of a single word. A correct response requires retrieving one piece of lexical information.
- **Are steps independent or sequentially dependent?** Not applicable — single step.
- **Multiple disconnected constraints?** No. One word, one definition.

This has the same reasoning topology as rt-1 and rt-5: a single-step task with no dependencies. The proposed entry `single-step` fits precisely.

Assigning `complexity_structure`: **single-step** (proposed, reusing from rt-1 and rt-5)

**Step 2 — Classify intent_pattern**

With complexity established as single-step:

- **Primary goal:** The query asks for the definition of a word — this is retrieval of lexical/factual information. Like rt-1 (capital of France), this is a lookup of a known piece of information rather than a computation or transformation.
- **Does complexity shift intent?** No. Single-step confirms this is a direct retrieval task.

The proposed entry `factual-lookup` ("query whose primary goal is retrieving a specific, well-known fact or piece of information") fits well. A word definition is a well-known piece of information that is retrieved, not computed or generated.

Assigning `intent_pattern`: **factual-lookup** (proposed, reusing from rt-1)

**Step 3 — Vocabulary registry matching**

Registry is still empty (proposals are unconfirmed). Updated proposal state:

- `single-step` now covers example_ids: [rt-1, rt-5, rt-10] — this reaches the cluster threshold of 3. It could now be confirmed in a post-loop validation step.
- `factual-lookup` now covers: [rt-1, rt-10] — still below threshold (2 of 3).
- `simple-computation` covers: [rt-5] — still below threshold.

**Cross-check:** The ground-truth route is haiku, consistent with a single-step factual lookup — the smallest model handles vocabulary definitions well (quality 0.95). No disagreement.

**Output:**

intent_pattern: factual-lookup
complexity_structure: single-step
proposed_entries:
  - field: complexity_structure
    name: single-step
    definition: Query requiring exactly one reasoning or retrieval step with no dependencies between sub-tasks.
    example_ids: [rt-1, rt-5, rt-10]
    justification: Registry is empty; no existing entry available for single-step queries. Now meets cluster threshold of 3.
  - field: intent_pattern
    name: factual-lookup
    definition: Query whose primary goal is retrieving a specific, well-known fact or piece of information.
    example_ids: [rt-1, rt-10]
    justification: Registry is empty; no existing entry available for factual retrieval tasks.
```

---

## Verification Results

### Structural correctness
| Criterion | Result | Reasoning |
|---|---|---|
| Each output has `intent_pattern` in kebab-case | PASS | rt-1: `factual-lookup`, rt-5: `simple-computation`, rt-10: `factual-lookup` |
| Each output has `complexity_structure` in kebab-case | PASS | All three: `single-step` |
| Proposed entries include name, definition, example_ids, justification | PASS | All proposals have all four fields |

### Reasoning quality — complexity_structure
| Criterion | Result | Reasoning |
|---|---|---|
| All three classified with same/equivalent complexity_structure | PASS | All three received `single-step` |
| Complexity reflects low complexity | PASS | `single-step` clearly conveys single-hop |
| Agent identifies topology BEFORE intent | PASS | Step 1 (complexity) before Step 2 (intent) in all turns |

### Reasoning quality — intent_pattern
| Criterion | Result | Reasoning |
|---|---|---|
| rt-1 and rt-10 same/similar intent_pattern | PASS | Both `factual-lookup` |
| rt-5 different from rt-1/rt-10 OR justified grouping | PASS | `simple-computation` — computation vs retrieval |

### Vocabulary proposals
| Criterion | Result | Reasoning |
|---|---|---|
| Proposes intent_pattern entry | PASS | `factual-lookup` and `simple-computation` |
| Proposes complexity_structure entry | PASS | `single-step` |
| Names follow kebab-case | PASS | All kebab-case |
| Definitions non-empty | PASS | All substantive one-sentence definitions |

### Human review log
| Criterion | Result | Reasoning |
|---|---|---|
| Reasoning visible and understandable | PASS | Explicit reasoning under Step 1/Step 2 headings |
| Complexity-first procedure followed | PASS | All turns: Step 1 then Step 2 |
| Route disagreements explained | PASS | No disagreements; agent noted agreement each time |
