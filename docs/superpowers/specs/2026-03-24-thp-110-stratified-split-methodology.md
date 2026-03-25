# THP-110 — Stratified Split Methodology

Date: 2026-03-24
Wave: 1 (parallel with THP-82, THP-84, THP-86)
Epic: THP-74 — Routing Analysis Agent

---

## Summary

THP-110 defines the deterministic stratified split algorithm that divides an annotated routing dataset into `dev.jsonl` and `holdout.jsonl`. The split ensures proportional representation across routing-relevant dimensions so the downstream optimization loop works with a representative dev set.

This ticket does not introduce new skills, embeddings, or clustering. The two existing per-example skills (`classify-example`, `generate-routing-rationale`) provide all the annotation fields the split consumes.

---

## Scope Changes from Original Ticket

The original THP-110 spec included methodology selection, embedding model declaration, and skill sequencing. These are no longer needed:

| Original scope item | Disposition |
|---|---|
| Evaluate candidate extraction approaches | Dropped — extraction handled by existing skills |
| Skill sequencing | Dropped — two-skill sequence is fixed (`classify-example` → `generate-routing-rationale`) |
| Embedding model declaration | Dropped — no clustering step |
| Cluster ID generation | Dropped — THP-133 can define its own clustering when needed |
| Unit of analysis | Settled — per-example for annotation, full-set for split |

**Retained:** Stratified split methodology — the only remaining deliverable.

---

## Inputs

The split function receives two separate data structures and joins them internally:

| Input | Python type | Description |
|---|---|---|
| Original examples | `list[Example]` | Raw dataset examples with `id`, `input` (query text), and `expected.route` |
| Rationale card set | `RationaleCardSet` | Annotation output keyed by `example_id`, with `assigned_route`, `intent_pattern`, `complexity_structure`, `route_exclusions`, `ambiguity_tags` |
| Split ratio | `float` | Dev set proportion. Default `0.8` (holdout = `1 - dev_ratio`) |

The function joins examples with their rationale cards by `example_id`. Output records contain both the original example fields and the annotation fields.

**Preconditions:**
- The dataset must contain ≥ 2 examples. If fewer than 2 examples, emit all to `dev.jsonl` and an empty `holdout.jsonl` (degenerate case — no meaningful holdout is possible).
- Every example must have a corresponding rationale card in `RationaleCardSet.cards`, and vice versa. A mismatch is a pipeline error (raise, do not silently skip) — it means annotation did not complete successfully.

---

## Outputs

| Output | Description |
|---|---|
| `dev.jsonl` | Dev set examples — original fields + rationale card fields |
| `holdout.jsonl` | Holdout set examples — same schema as dev |
| `split_report.json` | Distribution summary per stratum for validation |

---

## Integration Context

The stratified split is a **deterministic Python function** invoked by the Routing Analysis Agent after the per-example annotation skills have completed. The agent pipeline is:

1. Run `classify-example` on each example → `intent_pattern`, `complexity_structure`
2. Run `generate-routing-rationale` on each example → `route_exclusions`, `ambiguity_tags`
3. **Invoke stratified split** on the full set of rationale cards
4. Receive `dev.jsonl` + `holdout.jsonl`

The split is not an LLM skill. It is a code step the agent delegates to entirely — no reasoning about how to split.

**Holdout enforcement:** The pipeline runner passes only `dev.jsonl` to refinement-loop agents downstream. `holdout.jsonl` is passed only to the final eval agent (THP-76 / THP-79). This is path-level control — agents never see a file whose path they are not given.

---

## Algorithm — Hierarchical Priority Stratification

### Step 1 — Build stratum key

For each example, compute the stratum key from the joined record:

```
stratum_key = (assigned_route, intent_pattern, complexity_structure)
```

Group all examples by stratum key.

### Step 2 — Handle small strata

- Strata with **≥ 2 members**: eligible for splitting
- Strata with **1 member**: assigned entirely to dev (singleton rule)

### Step 3 — Split eligible strata

For each stratum with ≥ 2 members, assign examples to dev and holdout at the target ratio (default 80/20).

Shuffling is deterministic: the random seed is the truncated hex string returned by `compute_dataset_hash()` (from the `list[Example]` input — see `odysseus.agents.routing_rationale_registry`), passed directly as a string to `random.Random(seed)`. Same dataset → same split.

Rounding: when stratum size does not divide cleanly, always round **in favor of dev** regardless of the configured ratio. Dev gets the extra example, ensuring holdout is never larger than intended.

**Edge case:** If all strata are singletons, all examples go to dev and holdout is empty. This is consistent with the algorithm but means holdout evaluation is not possible — the pipeline runner should warn when holdout is empty.

### Step 4 — Post-hoc ambiguity check

After the split, compute the distribution of `ambiguity_tags` across dev and holdout. Include this in `split_report.json` as a diagnostic. No rebalancing — ambiguity-tagged examples are most valuable in dev, and the singleton rule already biases rare cases that direction.

### Step 5 — Emit outputs

Write `dev.jsonl`, `holdout.jsonl`, and `split_report.json`.

---

## Stratification Priority

The stratum key dimensions are ordered by importance:

| Priority | Dimension | Rationale |
|---|---|---|
| 1 | `assigned_route` | Non-negotiable — if dev is missing a route, the optimization loop cannot learn to route to it |
| 2 | `intent_pattern` | Groups examples by task type within each route — important for few-shot diversity |
| 3 | `complexity_structure` | Captures reasoning difficulty — useful for balanced evaluation but recoverable if slightly imbalanced |

`ambiguity_tags` are not a stratification dimension. They are multi-label and sparse — using them in the stratum key would fragment strata beyond what the dataset can support. Their distribution is checked post-hoc in the split report.

---

## split_report.json Schema

```json
{
  "dataset_hash": "<truncated hex from compute_dataset_hash()>",
  "split_ratio": { "dev": 0.8, "holdout": 0.2 },
  "total_examples": 250,
  "dev_count": 205,
  "holdout_count": 45,
  "singleton_strata_count": 3,
  "strata": [
    {
      "key": ["<assigned_route>", "<intent_pattern>", "<complexity_structure>"],
      "total": 12,
      "dev": 10,
      "holdout": 2
    }
  ],
  "distributions": {
    "assigned_route": {
      "dev": { "<route>": 0.4 },
      "holdout": { "<route>": 0.42 }
    },
    "intent_pattern": {
      "dev": { "<pattern>": 0.25 },
      "holdout": { "<pattern>": 0.24 }
    },
    "complexity_structure": {
      "dev": { "<structure>": 0.3 },
      "holdout": { "<structure>": 0.31 }
    },
    "ambiguity_tags": {
      "dev": { "<TAG>": 12 },
      "holdout": { "<TAG>": 3 }
    }
  }
}
```

The `distributions` section shows normalized proportions for route, intent_pattern, and complexity_structure (for eyeballing divergence) and raw counts for ambiguity_tags (multi-label and sparse — counts may exceed set size since one example can have multiple tags).

---

## Impact on THP-74 Epic

This revised THP-110 removes several components from the THP-74 pipeline:

| Removed component | Original task(s) | Reason |
|---|---|---|
| Embedding / cluster-id-assignment code step | THP-155 | No clustering needed for split; THP-133 defines its own when needed |
| skill-2 (ambiguity-taxonomy) | THP-152 | Downstream agents reason over rationale cards directly |
| skill-3 (boundary-exemplar-tagging) | THP-153 | Downstream agents reason over rationale cards directly |
| skill-4 (confusion-narrative-generation) | THP-154 | Downstream agents reason over rationale cards directly |

Downstream consumers previously depending on these outputs:

| Consumer | Previous dependency | New approach |
|---|---|---|
| THP-133 (mixture-of-prompts) | `cluster_ids.json` | Defines its own clustering when picked up |
| THP-134 (context assembler) | `taxonomy.json`, `confusion_narratives.json` | Reasons over rationale cards directly |

---

## Dependencies

None — Wave 1 task.

---

## Blocks

- **THP-85** (skill orchestration framework — scope reduced to the two existing skills + split step)
- **THP-86** (inter-skill I/O schemas — scope reduced accordingly)
