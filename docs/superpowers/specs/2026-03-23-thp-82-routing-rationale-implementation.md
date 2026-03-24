# THP-82 — Routing Rationale Schema Implementation Design

Date: 2026-03-23
Wave: 1 (parallel with THP-110, THP-84, THP-86)
Epic: THP-74 — Routing Analysis Agent
Logical spec: `docs/superpowers/specs/2026-03-23-thp-82-routing-rationale-schema.md`

---

## Summary

Implement the routing rationale schema as Python code: Pydantic models, validation functions, vocabulary registry management, and two annotation skills. Schema-first approach — models first, then validation, then registry, then skills.

---

## Decisions from Brainstorming

| Decision | Choice | Rationale |
|---|---|---|
| Scope | Models + validation + registry + skills (full THP-82) | Annotation skills belong to routing analysis agent, not THP-106 |
| Skills format | SKILL.md packages under `odysseus/skills/` | Follow project skill conventions with frontmatter, references, progressive disclosure |
| Skills domain scope | Domain-independent | Skills describe reasoning process; vocabulary registry handles domain adaptation |
| Registry storage | Working YAML file + snapshot in THP-86 output | Working file for inspection and `--inherit-registry-from`; THP-86 captures frozen state |
| LLM-judged consistency check | Injectable `judge_fn` callable | Keeps validation testable with mock judges in unit tests |
| In-memory representation | `RationaleCardSet` container with metadata | Holds cards dict + dataset hash, registry, timestamp — natural target for THP-86 serialization |
| Approach | Schema-first (bottom-up) | Matches existing codebase pattern (THP-81), each layer independently testable |

---

## File Layout

```
odysseus/
  agents/
    routing_rationale_models.py    # Pydantic models
    routing_rationale_checks.py    # Validation functions
    routing_rationale_registry.py  # Registry I/O, hashing, merge, prune
  skills/
    classify-example/
      SKILL.md
      references/
        vocabulary-registry-rules.md
    generate-routing-rationale/
      SKILL.md
      references/
        disqualifier-guidelines.md
tests/
  test_routing_rationale_models.py
  test_routing_rationale_checks.py
  test_routing_rationale_registry.py
```

---

## Section 1: Pydantic Models

File: `odysseus/agents/routing_rationale_models.py`

### Models

```python
class TierDisqualifier(BaseModel):
    route: str          # matches Expected.route values (opaque string)
    reason: str         # observable query property, not capability claim

class RationaleCard(BaseModel):
    example_id: str     # foreign key to Example.id
    assigned_route: str # the ground-truth route for this example (from Expected.route)
    intent_pattern: str
    complexity_structure: str
    tier_disqualifiers: list[TierDisqualifier]
    ambiguity_tags: list[str]  # empty list if clear-cut

class VocabularyEntry(BaseModel):
    name: str
    definition: str
    example_ids: list[str]
    justification: str | None = None  # required for new entries, None for seeds

class VocabularyRegistry(BaseModel):
    intent_pattern: list[VocabularyEntry]
    complexity_structure: list[VocabularyEntry]
    ambiguity_tags: list[VocabularyEntry]

class RationaleCardSet(BaseModel):
    cards: dict[str, RationaleCard]  # keyed by example_id
    dataset_hash: str
    registry: VocabularyRegistry
    created_at: datetime
    inherited_from: str | None = None  # path to parent registry
```

### Validators

- `RationaleCard.intent_pattern` and `complexity_structure`: enforce `kebab-case` (regex: `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`)
- `RationaleCard.ambiguity_tags` values: enforce `SCREAMING_SNAKE_CASE` (regex: `^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$`)
- `VocabularyRegistry` model validator: entries in `intent_pattern` and `complexity_structure` lists must have kebab-case names; entries in `ambiguity_tags` must have SCREAMING_SNAKE_CASE names. Validation lives at the registry level because `VocabularyEntry` does not know which vocabulary it belongs to.
- `TierDisqualifier.reason`: non-empty string
- `RationaleCard.example_id`: non-empty string
- `RationaleCard.assigned_route`: non-empty string

---

## Section 2: Validation Functions

File: `odysseus/agents/routing_rationale_checks.py`

### Result Type

```python
class RationaleCheckResult(BaseModel):
    passed: bool
    check_name: str
    severity: Literal["critical", "warning", "info"]  # consistent with SchemaFinding
    details: str
    affected_ids: list[str]  # example IDs or entry names involved
```

### Per-Card Checks

| Function | Signature | Rule |
|---|---|---|
| `check_required_fields` | `(card: RationaleCard, registry: VocabularyRegistry) -> RationaleCheckResult` | All 4 fields present and non-empty (`ambiguity_tags` can be `[]`) |
| `check_vocabulary_membership` | `(card: RationaleCard, registry: VocabularyRegistry) -> RationaleCheckResult` | `intent_pattern` and `complexity_structure` values exist in registry entries |
| `check_disqualifier_coverage` | `(card: RationaleCard, available_routes: set[str]) -> RationaleCheckResult` | Every route != `card.assigned_route` has at least one disqualifier |
| `check_disqualifier_format` | `(card: RationaleCard) -> RationaleCheckResult` | Each entry has non-empty `route` and `reason` |
| `check_ambiguity_tag_membership` | `(card: RationaleCard, registry: VocabularyRegistry) -> RationaleCheckResult` | All tags on card exist in finalized ambiguity_tags registry |

### Dataset-Level Checks

| Function | Signature | Rule |
|---|---|---|
| `check_cluster_thresholds` | `(registry: VocabularyRegistry, dataset_size: int) -> RationaleCheckResult` | Every entry meets `max(3, ceil(0.05 * dataset_size))` minimum |
| `check_pruning_cleanup` | `(card_set: RationaleCardSet) -> RationaleCheckResult` | No cards reference entries absent from the registry |
| `find_orphaned_examples` | `(card_set: RationaleCardSet) -> RationaleCheckResult` | Returns IDs of examples whose vocabulary entries were pruned |
| `check_registry_consistency` | `(registry: VocabularyRegistry, judge_fn: Callable) -> Awaitable[RationaleCheckResult]` | No semantic overlap between entries in same vocabulary (LLM-judged) |

### Top-Level Runner

```python
async def validate_rationale_card_set(
    card_set: RationaleCardSet,
    available_routes: set[str],
    dataset_size: int,
    judge_fn: Callable[[str, str], Awaitable[bool]],
) -> list[RationaleCheckResult]:
```

Runs dataset-level checks first (including pruning and threshold enforcement), then per-card checks against the pruned registry. This ordering ensures that `check_ambiguity_tag_membership` validates against the finalized (post-pruning) registry as required by the logical spec.

**Scope note:** `find_orphaned_examples` is detection-only — it returns the IDs of examples that need re-annotation after pruning. The actual re-annotation (re-running Skill 1) is the responsibility of the routing analysis agent orchestration layer, not the validation module.

---

## Section 3: Registry Management

File: `odysseus/agents/routing_rationale_registry.py`

### Content Hashing

```python
def compute_dataset_hash(examples: list[Example]) -> str:
```

Deterministic SHA-256 over sorted `(id, input, expected.route)` tuples. Truncated to 16 hex chars.

### Persistence

```python
def save_registry(registry: VocabularyRegistry, path: Path) -> None:
def load_registry(path: Path) -> VocabularyRegistry:
def resolve_registry(
    dataset_hash: str,
    registry_dir: Path,
    inherit_from: Path | None = None,
) -> VocabularyRegistry | None:
```

`resolve_registry` looks up `registry_dir/<hash>.yaml` first, falls back to `inherit_from` path, returns `None` for fresh start (seed-only initialization).

### Append-Only Merge

```python
def merge_registry(
    existing: VocabularyRegistry,
    proposed: VocabularyRegistry,
) -> VocabularyRegistry:
```

Validates no existing entries are removed or renamed. Only new entries appended. Raises `RegistryMergeError` on violations.

### Pruning

```python
def prune_registry(
    registry: VocabularyRegistry,
    dataset_size: int,
) -> tuple[VocabularyRegistry, dict[str, list[str]]]:
```

Removes entries below `max(3, ceil(0.05 * dataset_size))`. Returns pruned registry + removed entries categorized by vocabulary (dict keyed by `"intent_pattern"`, `"complexity_structure"`, `"ambiguity_tags"` → list of removed entry names). This categorization is needed because removing an `intent_pattern` or `complexity_structure` entry requires re-running Skill 1 on affected examples, while removing an `ambiguity_tags` entry only requires stripping the tag from cards.

### Seed Initialization

```python
def create_seed_registry() -> VocabularyRegistry:
```

Returns registry with empty `intent_pattern` and `complexity_structure` lists. `ambiguity_tags` contains 4 seed entries: `AMBIGUOUS_COMPLEXITY`, `AMBIGUOUS_DOMAIN`, `POTENTIAL_MISLABEL`, `BOUNDARY_CASE` — each with a definition, empty `example_ids`, and no justification.

---

## Section 4: Skills

### `odysseus/skills/classify-example/`

```
classify-example/
├── SKILL.md
└── references/
    └── vocabulary-registry-rules.md
```

**SKILL.md frontmatter:**

```yaml
---
name: classify-example
description: >
  Jointly determine intent_pattern and complexity_structure for a routing
  example. Use when annotating dataset examples with routing rationale cards.
  Takes query text, ground-truth route, and vocabulary registry as input.
  Outputs field values and optionally proposes new vocabulary entries when
  no existing entry fits.
---
```

**SKILL.md body** — domain-independent annotation procedure:

1. Read the query and identify the reasoning topology — count the steps, check for dependencies between steps, look for parallel vs sequential structure. This determines `complexity_structure`.
2. Classify what task the query is asking for, using the complexity structure to disambiguate. This determines `intent_pattern`.
3. Match against the vocabulary registry. If an existing entry fits, use it. If not, propose a new entry with name (kebab-case), one-sentence definition, affected example IDs, and justification for why existing entries are insufficient.
4. Output: `intent_pattern` value, `complexity_structure` value, optionally `proposed_entries` list.

Common mistakes:
- Long queries are not necessarily complex — multiple parallel constraints differ from sequential dependencies
- Do not assume domain-specific intent categories — let them emerge from the data
- Joint reasoning prevents lock-in: intent classification depends on complexity structure

**references/vocabulary-registry-rules.md:**
- Naming: `intent_pattern` and `complexity_structure` use kebab-case; `ambiguity_tags` use SCREAMING_SNAKE_CASE
- Cluster threshold: `max(3, ceil(0.05 * dataset_size))`
- No semantic overlap: new entry must not duplicate existing; justify why existing entries are insufficient
- Append-only: existing entries cannot be renamed or removed across runs

### `odysseus/skills/generate-routing-rationale/`

```
generate-routing-rationale/
├── SKILL.md
└── references/
    └── disqualifier-guidelines.md
```

**SKILL.md frontmatter:**

```yaml
---
name: generate-routing-rationale
description: >
  Produce tier_disqualifiers and propose ambiguity_tags for a routing example.
  Use after classify-example has determined intent and complexity. Takes query
  text, ground-truth route, classification output, and vocabulary registry.
  Outputs disqualifier list covering all non-assigned routes and candidate
  ambiguity tags.
---
```

**SKILL.md body** — domain-independent annotation procedure:

1. For each route not assigned to this example, write a disqualifier. If routes have a natural ordering, work from lowest to highest. If unordered, iterate all non-assigned routes.
2. Write each disqualifier as a single concise sentence referencing an observable property of the query.
3. Assess ambiguity: if a disqualifier was hard to write, or if the classification pulled toward a different route, that signals an ambiguity tag.
4. Propose applicable tags from the registry. Tags are candidates — minimum cluster threshold is enforced during post-loop validation, not here.
5. Output: `tier_disqualifiers` list, `ambiguity_tags` candidate list.

**references/disqualifier-guidelines.md:**
- DO reference observable query properties: "query requires joining 3 independent sources", "query has a single unambiguous answer"
- DON'T reference route target capabilities: "this route's model can't handle it", "too complex for this tier"
- The `route` field value must exactly match the dataset's `expected.route` values — treat these as opaque strings
- Each `reason` is a single sentence, non-empty
- Coverage requirement: every non-assigned route must have at least one disqualifier entry

### Skill Consumption Model

Both skills are LLM-consumed markdown only — they are loaded into the routing analysis agent's context as annotation instructions. No Python skill loader is needed; the agent reads SKILL.md and reference files to guide its annotation reasoning. Pydantic models enforce structural constraints on the output; the skills guide the reasoning process.

---

## Section 5: Integration

### Touch Points

| Existing file | Change |
|---|---|
| `odysseus/agents/__init__.py` | Export new models and check functions |
| `odysseus/eval/models.py` | No changes — `Example.id` and `Expected.route` used as foreign keys |
| THP-80 records | No changes — rationale cards are separate artifacts keyed by ID |
| THP-81 code | No changes — may later use rationale schema for missing signal detection |
| THP-86 code | Will import models when building serialization layer |

### Testing Strategy

- `tests/test_routing_rationale_models.py` — Pydantic validation, naming convention enforcement, serialization round-trips
- `tests/test_routing_rationale_checks.py` — all per-card and dataset-level checks; mock `judge_fn` for consistency check
- `tests/test_routing_rationale_registry.py` — content hashing determinism, YAML save/load round-trips, merge append-only enforcement, pruning threshold logic, seed initialization
- Integration test scenarios in `tests/scenarios/` following existing markdown runbook pattern

---

## Success Criteria

- Each routing example can be represented as a `RationaleCard` using the 4-field schema
- Pydantic validators enforce naming conventions and structural constraints
- Validation functions catch all per-card and dataset-level violations
- Registry persists as YAML, supports append-only merge and content-hash lookup
- Skills are domain-independent SKILL.md packages usable by the routing analysis agent
- All unit tests pass with no dependency on external LLM calls (mock judge)
