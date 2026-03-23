# THP-82 — Routing Rationale Schema

Date: 2026-03-23
Wave: 1 (parallel with THP-110, THP-84, THP-86)
Epic: THP-74 — Routing Analysis Agent

---

## Summary

Define the structured routing rationale schema that powers clustering, retrieval, and boundary analysis. Each routing example in a dataset is annotated as a rationale card with 4 fields, supported by a dynamic vocabulary registry and a 2-skill annotation pipeline.

---

## Reference: Existing Few-Shot Prompt

**File:** `../../prompt-routing/prompts/fewshot_v16_reduce_overrouting.md`
(absolute: `/Users/thymo.fieten/Documents/prompt-routing/prompts/fewshot_v16_reduce_overrouting.md`)

Contains the full tier decision framework (tiers 0, 1, 2), 9 decision heuristics, and 22 labeled examples with natural-language reasoning narratives. These narratives are the raw material the schema formalizes.

| Narrative pattern | Maps to schema field |
|---|---|
| "single-entity factual lookup" / "generation task" / "constraint satisfaction" | `intent_pattern` |
| "single-hop" / "2-hop chain" / "3+ sequential dependency" / "parallel constraints" | `complexity_structure` |
| "NOT tier 2 just because..." / "tier 0 fails the first hop" | `tier_disqualifiers` |
| "torn between 1 and 2" / "could go either way" | `ambiguity_tags` |

---

## Rationale Card Schema

Each routing example gets annotated with a rationale card containing 4 fields.

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `intent_pattern` | `string` | yes | The task type the query represents. Value drawn from the vocabulary registry. |
| `complexity_structure` | `string` | yes | The reasoning topology required to answer. Value drawn from the vocabulary registry. |
| `tier_disqualifiers` | `list[{route: string, reason: string}]` | yes | Why specific routes are ruled out for this example. `route` matches the `expected.route` value from THP-80 (e.g., `"opus"`, `"sonnet"`, `"haiku"` or `"0"`, `"1"`, `"2"`). |
| `ambiguity_tags` | `list[string]` | yes | Tags from the ambiguity registry that apply. Empty list if the example is clear-cut. |

### Constraints

- **Disqualifier coverage:** Every route *not* assigned to the example must have at least one disqualifier entry. If the example's route is `"1"`, there must be entries for `"0"` and `"2"`.
- **Disqualifier content:** Each `reason` must reference an observable property of the query, not a capability assumption about the model. Write "query requires joining 3 independent sources" not "this route's model isn't smart enough."
- **Ambiguity tags:** Only tags present in the finalized (post-pruning) registry are valid.

### Example

```yaml
# Example 20 — Eurostat sequential filtering (route "2")
rationale_card:
  intent_pattern: "data-filtering"
  complexity_structure: "sequential-dependency"
  tier_disqualifiers:
    - route: "0"
      reason: "query requires precise numerical thresholds (50M tonnes, 20%) not common knowledge"
    - route: "1"
      reason: "3 sequential filtering steps where each output feeds the next"
  ambiguity_tags:
    - "AMBIGUOUS_COMPLEXITY"
```

### Fields Considered and Dropped

| Field | Reason for dropping |
|---|---|
| `required_capability` | Absorbed by `intent_pattern` + `complexity_structure`. These two fields jointly capture what the model must do. A separate capability field overlapped with both and was hard to annotate consistently. |
| `tool_dependency` | Zero signal in the current dataset (fewshot_v16 contains no tool-dependent queries). Available as an optional extension for future datasets that include tool routing. |
| `risk_level` | Self-assessed confidence is unreliable when produced by the same agent making the routing decision. Replaced by `ambiguity_tags`, which express boundary-case status through observable properties rather than declared confidence. |
| `tie_breaker` / `decisive_signal` | For clear-cut examples, redundant with `intent_pattern` + `complexity_structure` + `tier_disqualifiers`. For ambiguous examples, the ambiguity tags + disqualifiers already capture what made the decision hard and what resolved it. Including it risks over-specifying the routing logic per example. |

---

## Vocabulary Registry

All three dynamic vocabularies (`intent_pattern`, `complexity_structure`, `ambiguity_tags`) follow a unified registry pattern.

### Structure

```yaml
vocabulary_registry:
  intent_pattern:
    entries:
      - name: "factual-lookup"
        definition: "Query asks for a single factual answer — a name, date, place, or title"
        example_ids: ["ex_1", "ex_5", "ex_9", "ex_14"]  # IDs are illustrative
      - name: "data-filtering"
        definition: "Query applies filtering criteria to a named dataset or source"
        example_ids: ["ex_2", "ex_6", "ex_11", "ex_13"]  # IDs match dataset record IDs
  complexity_structure:
    entries:
      - name: "single-hop"
        definition: "Answer requires one retrieval step with no dependencies"
        example_ids: ["ex_1", "ex_4", "ex_6"]
  ambiguity_tags:
    entries:
      - name: "AMBIGUOUS_COMPLEXITY"
        definition: "Complexity signals point to different tiers"
        example_ids: ["ex_20", "ex_12", "ex_5"]
```

### Registry Rules

1. **Minimum cluster size:** An entry is only included if it applies to at least `max(3, ceil(0.05 * dataset_size))` examples. This threshold applies uniformly to all entries — seed and new alike.
2. **Seed values are suggestions, not guarantees.** They are evaluated against the threshold like any other entry. A seed value that applies to fewer examples than the threshold is excluded from the output.
3. **New entries require:** a name, a one-sentence definition, the list of example IDs, and a justification for why existing entries don't cover the pattern.
4. **No semantic overlap:** A new entry must not duplicate an existing one. The agent must explain why existing entries are insufficient before proposing a new entry.
5. **Append-only across runs:** Subsequent runs on the same dataset receive the previous run's registry as input. Existing entries must be reused. New entries can be added, but existing entries cannot be renamed or removed. This ensures consistency across runs.
6. **Dataset identity:** By default, dataset identity is determined by content hash — same content produces the same hash and inherits the previous registry. When the dataset changes (examples added, labels corrected), use `--inherit-registry-from <path>` to explicitly chain from a previous run's registry. A dataset with no matching hash and no explicit inheritance starts fresh with only seed values as suggestions.
7. **Naming convention:** `intent_pattern` and `complexity_structure` use `kebab-case`. `ambiguity_tags` use `SCREAMING_SNAKE_CASE`.

### Seed Values

Only `ambiguity_tags` has seed values. These tags describe properties of the annotation process (boundary cases, mislabels, conflicting signals) that generalize across any routing dataset regardless of domain.

`intent_pattern` and `complexity_structure` have **no seeds** — these vocabularies are fully derived from the dataset. The values that emerge from a model-tier routing dataset will differ from those in a customer-support or content-moderation routing dataset.

| Vocabulary | Seeds |
|---|---|
| `intent_pattern` | *(none — fully derived from dataset)* |
| `complexity_structure` | *(none — fully derived from dataset)* |
| `ambiguity_tags` | `AMBIGUOUS_COMPLEXITY`, `AMBIGUOUS_DOMAIN`, `POTENTIAL_MISLABEL`, `BOUNDARY_CASE` |

---

## Annotation Guidance

The routing analysis agent populates rationale cards using 2 sequential skills, followed by a post-loop validation step.

### Skill 1: `classify_example`

**Purpose:** Jointly determine `intent_pattern` and `complexity_structure`.

**Input:** Query text, ground-truth route assignment, vocabulary registry.

**Process:**
1. Identify the reasoning topology first — count the hops, check for dependencies between steps, look for source-joining. This determines `complexity_structure`.
2. Classify the task type, using `complexity_structure` to disambiguate. A query mentioning multiple data sources with `sequential-dependency` structure is `cross-source-join`, not `data-filtering`.
3. Check proposed values against the vocabulary registry. If neither existing entries fit, flag the example for potential new vocabulary entry.

**Output:** `intent_pattern` value, `complexity_structure` value. Optionally, a `proposed_entries` list when no existing vocabulary entry fits — each proposal includes a name, one-sentence definition, and justification for why existing entries are insufficient. Proposals are collected across all examples and evaluated against the cluster threshold during post-loop validation.

**Why these fields are grouped:** They inform each other — intent classification depends on understanding the complexity structure, and misclassifying one leads to misclassifying the other. Joint reasoning prevents lock-in from a strict sequential approach.

### Skill 2: `generate_routing_rationale`

**Purpose:** Produce `tier_disqualifiers` and propose `ambiguity_tags`.

**Input:** Query text, ground-truth route assignment, `intent_pattern` and `complexity_structure` from Skill 1, vocabulary registries.

**Process:**
1. For each route *not* assigned to the example, generate a disqualifier. For ordered tiers (e.g., 0/1/2), work upward: "why not 0?" → "why not 1?" → "why not 2?". For unordered routes (e.g., model names), iterate through all non-assigned routes.
2. Write each disqualifier as a single concise sentence referencing an observable query property.
3. Evaluate whether ambiguity tags apply: if disqualifiers were hard to write for a particular route, or if `intent_pattern` and `complexity_structure` pulled toward different routes, that signals an ambiguity tag.
4. Propose applicable tags from the registry. Tags are candidates at this stage — the minimum cluster threshold is enforced during post-loop validation.

**Output:** `tier_disqualifiers` list, `ambiguity_tags` candidate list.

**Why these fields are grouped:** Disqualifiers are the heavy reasoning step and benefit from full focus. Ambiguity tags depend on observing difficulty during disqualifier generation — "was it hard to explain why tier X doesn't work?" is the primary signal.

### Post-Loop Validation

Runs once after all examples in the dataset are annotated. Not a skill — a validation step.

**Per-card checks:**

| Check | Rule |
|---|---|
| Required fields present | All 4 fields must exist on every card |
| Vocabulary membership | `intent_pattern` and `complexity_structure` values must exist in the registry |
| Disqualifier coverage | Every route ≠ assigned route has at least one disqualifier entry |
| Disqualifier format | Each entry has `route` (string, matching a valid `expected.route` value) and `reason` (non-empty string) |
| Ambiguity tag membership | All tags on the card must exist in the finalized registry |

**Dataset-level checks:**

| Check | Rule |
|---|---|
| Cluster threshold | Every registry entry across all 3 vocabularies meets `max(3, ceil(0.05 * dataset_size))` |
| Pruning cleanup | Cards referencing pruned entries have those values removed |
| Orphaned examples | If pruning removes a vocabulary entry from `intent_pattern` or `complexity_structure`, the agent automatically re-runs Skill 1 (`classify_example`) on affected examples using the pruned registry. This is a retry, not a human-in-the-loop step. If reclassification fails (no surviving entry fits), the example is flagged for human review. |
| Registry consistency | No two entries in the same vocabulary have identical or near-identical definitions. This is an LLM-judgment check: the agent compares each pair of definitions within a vocabulary and flags any that describe the same observable pattern using different wording. Not automated via embedding similarity — the agent reads the definitions and decides. |

### Common Annotation Mistakes

- **Confusing verbosity with complexity.** Long queries with many parallel constraints are often `parallel-constraints` + `constraint-satisfaction`, not `sequential-dependency`.
- **Writing disqualifiers about model capability.** Disqualifiers describe what the query requires, not what the model can't do.
- **Over-tagging ambiguity.** Tags require the minimum cluster threshold. Individual annotator uncertainty is not sufficient — the pattern must recur across examples.

---

## Deliverables

1. Routing rationale schema (this document — the card structure and field definitions)
2. Vocabulary registry with seed values and expansion rules
3. Annotation guidance as 2 agent skills (`classify_example`, `generate_routing_rationale`)
4. Validation checks for per-card consistency and dataset-level coverage

---

## Dependencies

None — Wave 1 task.

---

## How It Links with the Codebase

| Touch point | Detail |
|---|---|
| THP-80 | Rationale cards are a **separate artifact** keyed by THP-80 record `id`, not embedded in THP-80 records. The base dataset format is untouched; rationale cards reference records by ID. |
| THP-81 | Missing signal detection in the output report uses the rationale schema to identify what is absent (e.g., no examples with `cross-source-join` intent). |
| THP-86 | Serialization format builds on this logical schema. The vocabulary registry is persisted as part of THP-86's output artifact. THP-86 owns the formal machine-readable schema (JSON Schema / Pydantic model); THP-82 is the logical-level spec. |
| THP-106 | Final system prompt embeds the 2 annotation skills so the agent can produce structured rationale cards. |
| THP-74 | Rationale cards feed into Phase 1 (clustering, boundary analysis) and Phase 2 (stratified splitting via ambiguity tags). |

---

## Success Criteria

- Each routing example can be represented as a structured rationale card using the 4-field schema
- The schema adapts to arbitrary routing datasets through the vocabulary registry expansion mechanism
- The vocabulary registry maintains consistency across multiple runs via append-only semantics
- Rationale fields are extractable reproducibly from labeled examples using the 2-skill annotation pipeline
- The schema is directly usable by exemplar optimization and mixture-of-prompts workflows
