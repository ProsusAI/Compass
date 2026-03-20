# THP-108: Gap Taxonomy Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the MD file that defines which missing user input fields block the pipeline and which get sensible defaults.

**Architecture:** A single Markdown file at `odysseus/agents/user_input_taxonomy.md` with three sections: taxonomy table, classification criteria, and status decision logic. No code — this is a reference document embedded into the system prompt by THP-107.

**Tech Stack:** Markdown

---

## File Structure

| File | Responsibility |
|---|---|
| Create: `odysseus/agents/user_input_taxonomy.md` | Gap taxonomy — classification rules, defaults, and decision logic |

---

## Chunk 1: Create the taxonomy file

### Task 1: Write the gap taxonomy document

**Files:**
- Create: `odysseus/agents/user_input_taxonomy.md`

**Reference docs:**
- Design spec: `docs/superpowers/specs/2026-03-20-thp108-gap-taxonomy-design.md`
- Field definitions: `odysseus/agents/THP-70.md`
- Default values: `odysseus/agents/THP-71.md`
- Output schema: `odysseus/agents/THP-72.md`
- Static context: `odysseus/agents/THP-69.md`

- [ ] **Step 1: Create the taxonomy file**

```markdown
# User Input Gap Taxonomy

Classification rules for missing input fields. Used by the User Input agent to determine
whether to proceed, apply defaults, or request clarification.

## Classification Criteria

- **Blocking**: Cannot be reasonably defaulted; no surrogate exists; downstream agents fail without it.
- **Non-blocking**: A principled domain default exists; the user can override the assumed value later.

## Taxonomy

| Field | Classification | Rationale | Default |
|---|---|---|---|
| `routing_dataset` | Blocking | No default can substitute real labeled routing data | — |
| `problem_description` | Blocking | Analysis agent cannot extract patterns without it | — |
| `target_metrics` | Non-blocking | Metrics are fixed in THP-69 context; F1 is a strong general-purpose default | F1 score |
| `evaluation_threshold` | Non-blocking | Conservative threshold consistent with routing literature | 0.80 |
| `data_split_ratio` | Non-blocking | 80/20 is a well-established standard | 0.20 |
| `max_iterations` | Non-blocking | Bounds cost while allowing convergence | 10 |

## Status Decision Logic

Based on the gaps identified, set the `status` field in the validated input report:

1. **Any blocking gap present** → `clarification_required` — halt pipeline, request missing fields.
2. **Only non-blocking gaps present** → `proceed_with_defaults` — apply defaults from table above, note them in the report.
3. **No gaps** → `proceed` — all fields present, continue pipeline.
```

- [ ] **Step 2: Verify the file renders correctly**

Run: `cat odysseus/agents/user_input_taxonomy.md`
Expected: All three sections visible, table renders with 6 rows.

- [ ] **Step 3: Commit**

```bash
git add odysseus/agents/user_input_taxonomy.md
git commit -m "feat(thp-108): add blocking vs non-blocking gap taxonomy"
```
