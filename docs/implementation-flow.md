# Implementation Flow

Last updated: 2026-03-23

---

## Status Overview

| Epic | Title | Status |
|------|-------|--------|
| [THP-75](https://prosus-thymo-thesis.atlassian.net/browse/THP-75) | Eval Framework Code | ✅ Done |
| [THP-76](https://prosus-thymo-thesis.atlassian.net/browse/THP-76) | Eval Runner Agent | ✅ Done |
| [THP-132](https://prosus-thymo-thesis.atlassian.net/browse/THP-132) | Prompt-program Optimizer & Search Controller | ✅ Done (scope absorbed into THP-77/78) |
| [THP-68](https://prosus-thymo-thesis.atlassian.net/browse/THP-68) | User Input Agent | 🔄 In Progress (2 tasks in review) |
| [THP-73](https://prosus-thymo-thesis.atlassian.net/browse/THP-73) | Data Validation Agent | ⬜ To Do |
| [THP-74](https://prosus-thymo-thesis.atlassian.net/browse/THP-74) | Routing Analysis Agent | ⬜ To Do |
| [THP-77](https://prosus-thymo-thesis.atlassian.net/browse/THP-77) | Prompt-program Compiler and Search Optimizer | ⬜ To Do |
| [THP-78](https://prosus-thymo-thesis.atlassian.net/browse/THP-78) | Review Agent | ⬜ To Do |
| [THP-79](https://prosus-thymo-thesis.atlassian.net/browse/THP-79) | Final Reporting Agent | ⬜ To Do |
| [THP-133](https://prosus-thymo-thesis.atlassian.net/browse/THP-133) | Mixture-of-Prompts Routing | ⬜ To Do |
| [THP-134](https://prosus-thymo-thesis.atlassian.net/browse/THP-134) | Context Assembler & Dynamic Context Engineering | ⬜ To Do |

---

## Epic Ordering

```
Phase 0 (done):    THP-75, THP-76, THP-132
Phase 1 (current): THP-68 (in progress) || THP-73
Phase 2 (analysis):THP-74             ← needs THP-68 + THP-73
Phase 3 (loop):    THP-77 || THP-78   ← parallel, both need THP-74; loop with THP-76
Phase 4 (output):  THP-79             ← needs everything
Phase 5 (advanced):THP-133 || THP-134 ← parallel advanced features
```

| Phase | Epic | Depends on |
|-------|------|-----------|
| 0 | [THP-75](https://prosus-thymo-thesis.atlassian.net/browse/THP-75) — Eval Framework Code | — |
| 0 | [THP-76](https://prosus-thymo-thesis.atlassian.net/browse/THP-76) — Eval Runner Agent | — |
| 0 | [THP-132](https://prosus-thymo-thesis.atlassian.net/browse/THP-132) — Prompt-program Optimizer | — |
| 1 | [THP-68](https://prosus-thymo-thesis.atlassian.net/browse/THP-68) — User Input Agent | — |
| 1 | [THP-73](https://prosus-thymo-thesis.atlassian.net/browse/THP-73) — Data Validation Agent | — |
| 2 | [THP-74](https://prosus-thymo-thesis.atlassian.net/browse/THP-74) — Routing Analysis Agent | THP-68, THP-73 |
| 3 | [THP-77](https://prosus-thymo-thesis.atlassian.net/browse/THP-77) — Prompt-program Compiler and Search Optimizer | THP-74 |
| 3 | [THP-78](https://prosus-thymo-thesis.atlassian.net/browse/THP-78) — Review Agent | THP-74 |
| 4 | [THP-79](https://prosus-thymo-thesis.atlassian.net/browse/THP-79) — Final Reporting Agent | THP-77, THP-78, THP-76 |
| 5 | [THP-133](https://prosus-thymo-thesis.atlassian.net/browse/THP-133) — Mixture-of-Prompts Routing | THP-74, THP-77 |
| 5 | [THP-134](https://prosus-thymo-thesis.atlassian.net/browse/THP-134) — Context Assembler | THP-74, THP-77 |

---

## Task Breakdown Per Epic

### THP-68 — User Input Agent 🔄 In Progress

```
Wave 1 (parallel, in review): THP-69, THP-108
Wave 2 (parallel):             THP-71 (needs 108), THP-109 (needs 108)
Wave 3:                        THP-72 (needs 69+71)
Wave 4:                        THP-107 (needs all above)
Wave 5:                        THP-146 (needs 107)
```

| Wave | Task | Status | Depends on |
|------|------|--------|-----------|
| 1 | [THP-69](https://prosus-thymo-thesis.atlassian.net/browse/THP-69) Define agent static knowledge context | 🔄 In Review | — |
| 1 | [THP-108](https://prosus-thymo-thesis.atlassian.net/browse/THP-108) Define blocking vs. non-blocking gap taxonomy | 🔄 In Review | — |
| 2 | [THP-71](https://prosus-thymo-thesis.atlassian.net/browse/THP-71) Define default values for non-blocking gaps | ⬜ To Do | THP-108 |
| 2 | [THP-109](https://prosus-thymo-thesis.atlassian.net/browse/THP-109) Design clarification request templates | ⬜ To Do | THP-108 |
| 3 | [THP-72](https://prosus-thymo-thesis.atlassian.net/browse/THP-72) Define validated input report schema | ⬜ To Do | THP-69, THP-71 |
| 4 | [THP-107](https://prosus-thymo-thesis.atlassian.net/browse/THP-107) Write final system prompt | ⬜ To Do | all above |
| 5 | [THP-146](https://prosus-thymo-thesis.atlassian.net/browse/THP-146) Write full integration test | ⬜ To Do | THP-107 |

---

### THP-73 — Data Validation Agent

```
Wave 1:            THP-80
Wave 2:            THP-81 (needs THP-80)
Wave 3 (parallel): THP-145, THP-106 (needs THP-81)
```

| Wave | Task | Status | Depends on |
|------|------|--------|-----------|
| 1 | [THP-80](https://prosus-thymo-thesis.atlassian.net/browse/THP-80) Define data format | ⬜ To Do | — |
| 2 | [THP-81](https://prosus-thymo-thesis.atlassian.net/browse/THP-81) Define output format and code generation context | ⬜ To Do | THP-80 |
| 3 | [THP-145](https://prosus-thymo-thesis.atlassian.net/browse/THP-145) Implement full dataset validation logic | ⬜ To Do | THP-80, THP-81 |
| 4 | [THP-106](https://prosus-thymo-thesis.atlassian.net/browse/THP-106) Add final prompt | ⬜ To Do | all above |

> Note: THP-83 (Create context for generating data analysis code) was merged into THP-81. THP-82 and THP-84 were reassigned to THP-74.

---

### THP-74 — Routing Analysis Agent

```
Wave 1 (parallel): THP-110, THP-85, THP-86, THP-82, THP-84
Wave 2 (parallel): THP-111 (needs 110+85), THP-112 (needs 110)
Wave 3:            THP-105 (needs all above)
```

| Wave | Task | Status | Depends on |
|------|------|--------|-----------|
| 1 | [THP-110](https://prosus-thymo-thesis.atlassian.net/browse/THP-110) Define routing pattern extraction methodology | ⬜ To Do | — |
| 1 | [THP-85](https://prosus-thymo-thesis.atlassian.net/browse/THP-85) Expand reasoning framework into boundary and cluster analysis framework | ⬜ To Do | — |
| 1 | [THP-86](https://prosus-thymo-thesis.atlassian.net/browse/THP-86) Expand output format into structured routing analysis artifact spec and split manifest | ⬜ To Do | — |
| 1 | [THP-82](https://prosus-thymo-thesis.atlassian.net/browse/THP-82) Expand analysis dimensions into routing rationale schema | ⬜ To Do | — |
| 1 | [THP-84](https://prosus-thymo-thesis.atlassian.net/browse/THP-84) Create context for routing dataset quality | ⬜ To Do | — |
| 2 | [THP-111](https://prosus-thymo-thesis.atlassian.net/browse/THP-111) Define few-shot examples of reasoning document output | ⬜ To Do | THP-110, THP-85 |
| 2 | [THP-112](https://prosus-thymo-thesis.atlassian.net/browse/THP-112) Define how patterns translate into prompt-ready heuristics | ⬜ To Do | THP-110 |
| 3 | [THP-105](https://prosus-thymo-thesis.atlassian.net/browse/THP-105) Create final prompt (Phase 1 only) | ⬜ To Do | all above |

> Note: THP-82 and THP-84 were reassigned here from THP-73. THP-74 now receives the full dataset (no pre-existing split) and produces two outputs: the routing analysis artifact and a `split_manifest.json`. THP-86 owns both the artifact format spec and the Phase 2 stratified split algorithm. THP-105 covers the Phase 1 prompt only; Phase 2 is deterministic (no prompt required).

---

### THP-77 — Prompt-program Compiler and Search Optimizer

```
Wave 1 (parallel): THP-100, THP-101, THP-118, THP-119
Wave 2 (parallel): THP-102, THP-117, THP-148 (needs THP-147 from THP-78, THP-135, THP-118)
Wave 3:            THP-103 (needs all above)
```

| Wave | Task | Status | Depends on |
|------|------|--------|-----------|
| 1 | [THP-100](https://prosus-thymo-thesis.atlassian.net/browse/THP-100) Create context management | ⬜ To Do | — |
| 1 | [THP-101](https://prosus-thymo-thesis.atlassian.net/browse/THP-101) Demote model-specific cookbooks to supporting backend layer | ⬜ To Do | — |
| 1 | [THP-118](https://prosus-thymo-thesis.atlassian.net/browse/THP-118) Define prompt versioning scheme | ⬜ To Do | — |
| 1 | [THP-119](https://prosus-thymo-thesis.atlassian.net/browse/THP-119) Define heuristic injection format | ⬜ To Do | — |
| 2 | [THP-102](https://prosus-thymo-thesis.atlassian.net/browse/THP-102) Expand prompting guidelines into prompt-program search space | ⬜ To Do | — |
| 2 | [THP-117](https://prosus-thymo-thesis.atlassian.net/browse/THP-117) Expand few-shot selection into exemplar optimization engine | ⬜ To Do | — |
| 2 | [THP-148](https://prosus-thymo-thesis.atlassian.net/browse/THP-148) Define block-level edit operator taxonomy and directive consumption protocol | ⬜ To Do | THP-147, THP-135, THP-118 |
| 3 | [THP-103](https://prosus-thymo-thesis.atlassian.net/browse/THP-103) Create final prompt | ⬜ To Do | all above |

> Note: THP-102 and THP-117 were reassigned here from THP-132. THP-135 (Define prompt-program block schema, no parent epic) is a prerequisite for THP-148.

---

### THP-78 — Review Agent

```
Wave 1 (parallel): THP-120, THP-121, THP-147, THP-123, THP-94, THP-95
Wave 2:            THP-122 (needs THP-147, THP-123)
Wave 3:            THP-99 (needs all above)
```

| Wave | Task | Status | Depends on |
|------|------|--------|-----------|
| 1 | [THP-120](https://prosus-thymo-thesis.atlassian.net/browse/THP-120) Define accept/revert decision criteria | ⬜ To Do | — |
| 1 | [THP-121](https://prosus-thymo-thesis.atlassian.net/browse/THP-121) Define diminishing returns detection logic | ⬜ To Do | — |
| 1 | [THP-147](https://prosus-thymo-thesis.atlassian.net/browse/THP-147) Define localized edit directive schema | ⬜ To Do | THP-135 |
| 1 | [THP-123](https://prosus-thymo-thesis.atlassian.net/browse/THP-123) Define changelog awareness mechanism | ⬜ To Do | — |
| 1 | [THP-94](https://prosus-thymo-thesis.atlassian.net/browse/THP-94) Expand review steps into search-controller review policy | ⬜ To Do | — |
| 1 | [THP-95](https://prosus-thymo-thesis.atlassian.net/browse/THP-95) Expand continuation criteria into search-controller stopping policy | ⬜ To Do | — |
| 2 | [THP-122](https://prosus-thymo-thesis.atlassian.net/browse/THP-122) Define insight ranking methodology | ⬜ To Do | THP-147, THP-123 |
| 3 | [THP-99](https://prosus-thymo-thesis.atlassian.net/browse/THP-99) Create final prompt | ⬜ To Do | all above |

> Note: THP-94 and THP-95 were reassigned here from THP-132.

---

### THP-79 — Final Reporting Agent

```
Wave 1 (parallel): THP-96, THP-97, THP-124, THP-125, THP-126, THP-127
Wave 2:            THP-98 (needs all above)
```

| Wave | Task | Status | Depends on |
|------|------|--------|-----------|
| 1 | [THP-96](https://prosus-thymo-thesis.atlassian.net/browse/THP-96) Create reporting structure | ⬜ To Do | — |
| 1 | [THP-97](https://prosus-thymo-thesis.atlassian.net/browse/THP-97) Create writing style guide | ⬜ To Do | — |
| 1 | [THP-124](https://prosus-thymo-thesis.atlassian.net/browse/THP-124) Define confidence assessment methodology | ⬜ To Do | — |
| 1 | [THP-125](https://prosus-thymo-thesis.atlassian.net/browse/THP-125) Define iteration history table schema | ⬜ To Do | — |
| 1 | [THP-126](https://prosus-thymo-thesis.atlassian.net/browse/THP-126) Define deployment guidance template | ⬜ To Do | — |
| 1 | [THP-127](https://prosus-thymo-thesis.atlassian.net/browse/THP-127) Define threshold not reached failure path | ⬜ To Do | — |
| 2 | [THP-98](https://prosus-thymo-thesis.atlassian.net/browse/THP-98) Create final prompt | ⬜ To Do | all above |

---

### THP-133 — Mixture-of-Prompts Routing

```
Wave 1:            THP-136 (needs cluster IDs from THP-74)
Wave 2 (parallel): THP-137, THP-138 (both need THP-136)
Wave 3:            THP-139 (needs THP-137 + THP-138)
```

| Wave | Task | Status | Depends on |
|------|------|--------|-----------|
| 1 | [THP-136](https://prosus-thymo-thesis.atlassian.net/browse/THP-136) Specialise routing region clusters from THP-74 analysis artifact | ⬜ To Do | THP-74 |
| 2 | [THP-137](https://prosus-thymo-thesis.atlassian.net/browse/THP-137) Optimize specialist prompt-programs per routing cluster | ⬜ To Do | THP-136 |
| 2 | [THP-138](https://prosus-thymo-thesis.atlassian.net/browse/THP-138) Build lightweight meta-router prompt for cluster assignment | ⬜ To Do | THP-136 |
| 3 | [THP-139](https://prosus-thymo-thesis.atlassian.net/browse/THP-139) Validate mixture-of-prompts against universal prompt baseline | ⬜ To Do | THP-137, THP-138 |

> Note: THP-136 consumes THP-74's cluster IDs and specialises them for the mixture-of-prompts context — it does not re-derive clusters from scratch.

---

### THP-134 — Context Assembler & Dynamic Context Engineering

```
Wave 1 (parallel): THP-140, THP-141, THP-142
Wave 2:            THP-143 (needs all above)
```

| Wave | Task | Status | Depends on |
|------|------|--------|-----------|
| 1 | [THP-140](https://prosus-thymo-thesis.atlassian.net/browse/THP-140) Build rule relevance selector and context budget policy | ⬜ To Do | — |
| 1 | [THP-141](https://prosus-thymo-thesis.atlassian.net/browse/THP-141) Implement per-request example retrieval using hybrid skill-card scoring | ⬜ To Do | — |
| 1 | [THP-142](https://prosus-thymo-thesis.atlassian.net/browse/THP-142) Add conditional failure-mode appendix injection | ⬜ To Do | — |
| 2 | [THP-143](https://prosus-thymo-thesis.atlassian.net/browse/THP-143) Validate context assembler: static vs dynamic context ablation | ⬜ To Do | THP-140, THP-141, THP-142 |

> Note: THP-134 depends on THP-74 (for ambiguity taxonomy and confusion narratives) in addition to THP-77. This dependency is reflected in the Epic Ordering table above.

---

## Orphan Tasks

| Task | Status | Notes |
|------|--------|-------|
| [THP-135](https://prosus-thymo-thesis.atlassian.net/browse/THP-135) Define prompt-program block schema | ⬜ To Do | No parent epic; prerequisite for THP-147 (THP-78) and THP-148 (THP-77) |
| [THP-144](https://prosus-thymo-thesis.atlassian.net/browse/THP-144) Implement multi-candidate generation and minibatch triage | ⬜ To Do | Parent: THP-132 (Done epic); logically belongs to THP-77 wave 2 |
