# Scenario 24: Classify Example — Complex Multi-Step Queries

**Date:** 2026-03-23
**Verdict:** PASS (17/17 criteria)

---

## Transcript

```
=== SCENARIO 24: Classify Example — Complex Multi-Step Queries ===

--- Turn 1 ---
User Simulator: [Provides rt-2 with pre-populated registry containing factual-lookup, arithmetic-computation, single-hop]

Agent:

**Step 1 — Determine complexity_structure first**

The query has two distinct phases connected by a sequential dependency:
1. **Compare** the economic policies of Keynesianism and monetarism — requires understanding both frameworks across multiple dimensions.
2. **Evaluate which framework better explains the 2008 financial crisis** — depends on step 1, because evaluation requires applying the compared features to a specific historical event.

These are not parallel constraints. Step 2 genuinely depends on step 1. This is a sequential dependency chain (compare -> then evaluate).

Checking existing registry: `single-hop` clearly does not fit — rt-2 requires at least two dependent reasoning stages.

**No existing complexity_structure entry fits.** Proposing `sequential-dependency`.

**Step 2 — Classify intent_pattern**

The query asks to compare two theoretical frameworks and make an evaluative judgment. Neither `factual-lookup` nor `arithmetic-computation` fits.

Proposing `comparative-evaluation`.

**Output:**
intent_pattern: comparative-evaluation
complexity_structure: sequential-dependency
proposed_entries:
  - field: complexity_structure
    name: sequential-dependency
    definition: "Answer requires multiple reasoning steps where later steps depend on the output of earlier steps"
    example_ids: ["rt-2", "rt-6", "rt-8"]
    justification: "single-hop covers only single-step retrieval or computation. rt-2 requires compare then evaluate — a genuine sequential dependency."
  - field: intent_pattern
    name: comparative-evaluation
    definition: "Query asks to compare multiple entities or frameworks and make an evaluative judgment about their relative merit"
    example_ids: ["rt-2"]
    justification: "factual-lookup and arithmetic-computation cover single-answer tasks. Neither captures synthesis and judgment for comparing frameworks."

--- Turn 2 ---
User Simulator: [Provides rt-6: persuasive essay with counterarguments, rebuttals, citations → opus]

Agent:

**Step 1 — Determine complexity_structure first**

The query requires:
1. Construct a persuasive argument for renewable energy
2. Incorporate counterarguments (depends on step 1)
3. Write rebuttals to counterarguments (depends on step 2)
4. Cite recent studies (woven throughout)

Steps 2 and 3 are sequentially dependent on step 1. The proposed `sequential-dependency` fits well.

**complexity_structure: sequential-dependency**

**Step 2 — Classify intent_pattern**

The query asks to **generate** a structured persuasive text. Distinct from:
- factual-lookup: No single factual answer
- arithmetic-computation: No calculation
- comparative-evaluation: Primary goal is text generation, not comparative judgment

Proposing `structured-generation`.

**Output:**
intent_pattern: structured-generation
complexity_structure: sequential-dependency
proposed_entries:
  - field: intent_pattern
    name: structured-generation
    definition: "Query asks to produce a structured written artifact with explicit compositional requirements"
    example_ids: ["rt-6"]
    justification: "None of existing or proposed entries capture multi-part persuasive text generation with prescribed structural elements."

--- Turn 3 ---
User Simulator: [Provides rt-8: identify patterns, rank by impact, recommend improvements → opus]

Agent:

**Step 1 — Determine complexity_structure first**

Three distinct phases with sequential dependencies:
1. **Identify recurring complaint patterns** — pattern recognition across data
2. **Rank by business impact** — depends on step 1 (can't rank without identified patterns)
3. **Recommend three process improvements** — depends on steps 1 and 2

Three-stage sequential dependency chain: identify -> rank -> recommend.

**complexity_structure: sequential-dependency**

**Step 2 — Classify intent_pattern**

The query asks to perform **data-driven analysis** — pattern identification, ranking, and recommendations. Distinct from all existing and proposed entries.

Proposing `multi-phase-analysis`.

**Output:**
intent_pattern: multi-phase-analysis
complexity_structure: sequential-dependency
proposed_entries:
  - field: intent_pattern
    name: multi-phase-analysis
    definition: "Query requires analysing data to identify patterns, ranking findings, and producing actionable recommendations"
    example_ids: ["rt-8"]
    justification: "None of existing entries capture pattern extraction from data followed by impact ranking and recommendation generation."

Summary:
| Example | complexity_structure | intent_pattern |
|---------|---------------------|----------------|
| rt-2 | sequential-dependency | comparative-evaluation |
| rt-6 | sequential-dependency | structured-generation |
| rt-8 | sequential-dependency | multi-phase-analysis |
```

---

## Verification Results

### Structural correctness
| Criterion | Result |
|---|---|
| All outputs have `intent_pattern` in kebab-case | PASS |
| All outputs have `complexity_structure` in kebab-case | PASS |
| Proposed entries have all required fields | PASS |

### Reasoning quality — complexity_structure
| Criterion | Result |
|---|---|
| All three different from `single-hop` | PASS — all `sequential-dependency` |
| Sequential dependencies recognized | PASS — each turn identifies dependency chains |
| rt-2 identified as sequential/dependent | PASS — "compare -> then evaluate" |
| rt-8 identified as multiple dependent phases | PASS — "identify -> rank -> recommend" |

### Reasoning quality — intent_pattern
| Criterion | Result |
|---|---|
| Not classified as factual-lookup or arithmetic-computation | PASS — all new proposals |
| New entries proposed | PASS — 3 new entries |
| Different types distinguished | PASS — comparison vs generation vs analysis |

### Vocabulary proposals
| Criterion | Result |
|---|---|
| New complexity_structure proposed | PASS — `sequential-dependency` |
| New intent_pattern proposed | PASS — 3 entries |
| Justifications explain why existing insufficient | PASS — each references existing entries |
| Names follow kebab-case | PASS |

### Human review log
| Criterion | Result |
|---|---|
| Registry entries checked before proposals | PASS |
| Complexity-first procedure | PASS |
| Simple vs complex distinction evident | PASS |
