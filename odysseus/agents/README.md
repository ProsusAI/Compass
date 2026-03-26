# `odysseus/agents/`

This directory contains two distinct layers:

1. **LLM-driven agents** — system prompts in [`prompts/`](prompts/) surfaced via the MCP server's prompt mechanism. Claude acts as the agent by following those instructions.
2. **Python support code** — domain models, validation functions, and registry operations that MCP tools call into. These are not agents in the execution sense; they are the typed contracts and pure-Python logic that back the agents.

The one exception is [`EvalRunnerAgent`](#evalrunneragent-eval_runnerpy) — a code-driven Python class that orchestrates eval runs programmatically.

---

## Agent Prompts (`prompts/`)

One system prompt per LLM-driven agent, as Markdown files:

| File | Agent | Description |
|------|-------|-------------|
| [`prompts/user_input_system.md`](prompts/user_input_system.md) | User Input Agent | |
| [`prompts/data_validation_system.md`](prompts/data_validation_system.md) | Data Validation Agent | |
| [`prompts/eval_runner_system.md`](prompts/eval_runner_system.md) | Eval Runner Agent | |
| [`prompts/backend_setup_system.md`](prompts/backend_setup_system.md) | Backend Setup Agent | Guides user through selecting or creating a backend before first eval run |

The MCP server registers these as named prompts. When an MCP client (e.g. Claude Desktop, Cursor) calls the `optimize_routing_prompt` tool, Claude is given the appropriate system prompt and acts as that agent.

---

## `EvalRunnerAgent` — [`eval_runner.py`](eval_runner.py)

The one code-driven agent. Subclasses `BaseAgent` and orchestrates a full evaluation run against the dev split without requiring an internal LLM call.

**Role:** Extracts parameters from the pipeline context, loads a run config, wires dependencies, delegates to `odysseus.eval.controller`, and returns a structured `ScoreReport`.

### Context keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `prompt_version` | `str` | `"latest"` | Prompt version to evaluate |
| `data_source` | `str` | `""` | Path to the JSONL dataset |
| `backend` | `str` | `"default"` | Backend label matching a profile in `backends/` |
| `config_path` | `str` | `"outputs/run_config.yaml"` | Path to the YAML run config |

### Outputs

On success: `{ScoreReport.CONTEXT_KEY: ScoreReport}`.

On failure: `{"error": {"category": str, "detail": str}}` where `category` is one of `not_found`, `validation_error`, `permission_denied`, `run_error`.

The data split is always `"dev"` — holdout evaluation is a separate MCP tool.

---

## `base.py` — Abstract base class

Defines `BaseAgent`, the abstract interface all pipeline agents conform to.

| Member | Description |
|--------|-------------|
| `name` (property) | Agent identifier string |
| `run(context)` (async) | Execute the agent; takes a pipeline context dict, returns a dict of outputs to merge back in |

---

## `user_input_report.py` — Validated input report contract

Defines the pipeline contract for the User Input Agent's output. The report itself is a Markdown file produced by the agent following the template in [`user_input_report_template.md`](user_input_report_template.md).

| Symbol | Type | Description |
|--------|------|-------------|
| `CONTEXT_KEY` | `str` | Pipeline context key (`"validated_input_report_path"`) pointing to the report file |
| `STATUS_PROCEED` | `str` | Status value `"proceed"` — all required inputs were provided |
| `STATUS_PROCEED_WITH_DEFAULTS` | `str` | Status value `"proceed_with_defaults"` — missing inputs filled with defaults |
| `read_status(path)` | `str` | Reads the `**Status:**` line from the Markdown report; raises `ValueError` if absent or unrecognized |

---

## `data_validation_checks.py` — Data quality validation

Provides typed Pydantic models and pure validation functions used by the Data Validation Agent. All functions operate on raw parsed JSONL rows (`list[dict]`).

### Models

| Model | Description |
|-------|-------------|
| `DataQualityReport` | Top-level report; wraps all check sections plus a `summary` string |
| `SchemaFinding` | Result of one schema conformance check: `field`, `status`, `severity`, `violation`, `row_indices` |
| `LabelDistribution` | Per-tier label distribution stats: counts, percentages, imbalanced tiers |
| `TierDistribution` | Single-tier stats inside `LabelDistribution` |
| `VolumeAssessment` | Volume adequacy verdict across all tiers (`overall_verdict`: `"pass"` / `"fail"`) |
| `TierVolume` | Single-tier volume verdict: `"adequate"` / `"insufficient"` / `"absent"` |
| `QueryLengthDistribution` | Character length stats (min, max, mean, p95) of the `input` field |

### Check functions

| Function | Signature | Description |
|----------|-----------|-------------|
| `check_schema_conformance` | `(rows) → list[SchemaFinding]` | Validates required keys, types, `route`-in-`routes`, non-empty routes, consistent model set, unique IDs, null fields |
| `check_label_distribution` | `(rows, min_tier_percentage) → LabelDistribution` | Computes per-tier counts and flags under-represented tiers |
| `check_volume_adequacy` | `(rows, min_per_tier) → VolumeAssessment` | Flags tiers below the minimum example count |
| `check_query_length_distribution` | `(rows) → QueryLengthDistribution` | Computes length stats over the `input` field |
| `run_all_checks` | `(rows) → DataQualityReport` | Runs all four checks with default thresholds; sets `summary=""` for the LLM agent to fill |

Default thresholds: `min_tier_percentage=0.10`, `min_per_tier=5`.

---

## `routing_rationale_models.py` — Routing rationale domain models

Foundational Pydantic models for structured annotation of routing examples.

### Core annotation models

| Model | Description |
|-------|-------------|
| `RationaleCard` | Structured annotation for one routing example. Fields: `example_id`, `assigned_route`, `intent_pattern` (kebab-case), `complexity_structure` (kebab-case), `route_exclusions`, `ambiguity_tags` (SCREAMING_SNAKE_CASE) |
| `RouteExclusion` | One ruled-out route on a card. Fields: `route` (non-empty), `reason` (non-empty) |
| `RationaleCardSet` | A complete set of cards for a dataset. Fields: `cards` (dict of `example_id → RationaleCard`), `dataset_hash`, `registry`, `created_at`, `inherited_from` |

### Vocabulary models

| Model | Description |
|-------|-------------|
| `VocabularyEntry` | One term in a vocabulary dimension. Fields: `name`, `definition`, `example_ids`, `justification` |
| `VocabularyRegistry` | Dynamic registry for all annotation dimensions. Three lists of `VocabularyEntry`: `intent_pattern` (kebab-case names), `complexity_structure` (kebab-case names), `ambiguity_tags` (SCREAMING_SNAKE_CASE names) |

### Routing context models

| Model | Description |
|-------|-------------|
| `RoutingContext` | Domain-agnostic routing config. Fields: `domain`, `routes`, `routing_dimensions`, `route_ordering`, `seed_vocabulary` |
| `RouteDefinition` | A single route target: `name`, `description` |
| `RoutingDimension` | A dimension routes differ along (e.g. cost, capability): `name`, `direction` (`"lower_is_better"` / `"higher_is_better"`), `description` |
| `RouteOrdering` | Optional ordering of routes along one dimension: `dimension`, `order` |
| `SeedVocabulary` | Optional seed vocab for bootstrapping annotation: same three lists as `VocabularyRegistry` but defaults to empty |

### Naming conventions enforced by validators

| Field | Convention |
|-------|-----------|
| `intent_pattern` | `kebab-case` |
| `complexity_structure` | `kebab-case` |
| `ambiguity_tags` | `SCREAMING_SNAKE_CASE` |

---

## `routing_rationale_checks.py` — Rationale card validation

Validation functions that operate on `RationaleCard` / `RationaleCardSet` instances and return typed `RationaleCheckResult` objects.

### Result model

`RationaleCheckResult`: `passed`, `check_name`, `severity` (`"critical"` / `"warning"` / `"info"`), `details`, `affected_ids`.

### Per-card checks

| Function | Severity | Description |
|----------|----------|-------------|
| `check_required_fields(card, registry)` | critical | All four required fields present and non-empty (`assigned_route`, `intent_pattern`, `complexity_structure`, `route_exclusions`). Empty `ambiguity_tags` is allowed. |
| `check_vocabulary_membership(card, registry)` | critical | `intent_pattern` and `complexity_structure` exist in the registry |
| `check_exclusion_coverage(card, available_routes)` | critical | Every route other than `assigned_route` has a `RouteExclusion` |
| `check_exclusion_format(card)` | critical | Each `RouteExclusion` has non-empty `route` and `reason` |
| `check_ambiguity_tag_membership(card, registry)` | warning | All `ambiguity_tags` on the card are in the registry |

### Dataset-level checks

| Function | Severity | Description |
|----------|----------|-------------|
| `check_card_completeness(card_set, dataset_size)` | critical | Card set contains exactly one card per dataset example |
| `check_cluster_thresholds(registry, dataset_size)` | warning | Every registry entry has at least `max(3, ceil(0.05 * dataset_size))` example IDs |
| `check_pruning_cleanup(card_set)` | critical | No card references a vocabulary entry absent from the registry (stale references after pruning) |
| `find_orphaned_examples(card_set)` | warning | No card's `example_id` is absent from all registry `example_ids` lists |
| `check_registry_consistency(registry, judge_fn)` | warning | Async LLM-judged check for semantic overlap between all pairs in each vocabulary dimension |

### Top-level runner

`validate_rationale_card_set(card_set, routing_context, dataset_size, judge_fn) → list[RationaleCheckResult]`

Runs dataset-level checks first (to ensure vocabulary is post-pruning), then per-card checks for every card in the set.

---

## `routing_rationale_registry.py` — Registry persistence and lifecycle

Manages hashing, seed creation, persistence, and merge/prune operations for `VocabularyRegistry` instances.

### Functions

| Function | Description |
|----------|-------------|
| `compute_dataset_hash(examples)` | SHA-256 hash (16-char hex) over sorted `(id, input, expected.route)` tuples — order-independent |
| `create_seed_registry()` | Empty registry pre-seeded with 4 canonical ambiguity tags: `AMBIGUOUS_COMPLEXITY`, `AMBIGUOUS_DOMAIN`, `POTENTIAL_MISLABEL`, `BOUNDARY_CASE` |
| `save_registry(registry, path)` | Serialize to YAML; creates parent directories |
| `load_registry(path)` | Deserialize from YAML |
| `resolve_registry(dataset_hash, registry_dir, inherit_from)` | Look up registry for a hash (exact match first, then `inherit_from`, then `None` for fresh start) |
| `merge_registry(existing, proposed)` | Validate proposed does not remove any existing entries; raises `RegistryMergeError` on violation |
| `prune_registry(registry, dataset_size)` | Remove entries below threshold `max(3, ceil(0.05 * dataset_size))`; returns `(pruned_registry, removed_names_by_dimension)` |

### `RegistryMergeError`

Raised by `merge_registry` when a proposed registry illegally removes or renames existing entries.

---

## Shared model relationships

```
RoutingContext
  └── routes: list[RouteDefinition]
  └── routing_dimensions: list[RoutingDimension]
  └── route_ordering: RouteOrdering | None
  └── seed_vocabulary: SeedVocabulary | None

RationaleCardSet
  └── cards: dict[example_id, RationaleCard]
  │     └── route_exclusions: list[RouteExclusion]
  │     └── ambiguity_tags: list[str]  ← must be in registry
  │     └── intent_pattern: str        ← must be in registry
  │     └── complexity_structure: str  ← must be in registry
  └── registry: VocabularyRegistry
        └── intent_pattern: list[VocabularyEntry]
        └── complexity_structure: list[VocabularyEntry]
        └── ambiguity_tags: list[VocabularyEntry]

DataQualityReport
  └── schema_findings: list[SchemaFinding]
  └── label_distribution: LabelDistribution
  │     └── tiers: list[TierDistribution]
  └── volume_assessment: VolumeAssessment
  │     └── tiers: list[TierVolume]
  └── query_length: QueryLengthDistribution | None
```

`RationaleCardSet` ties `RationaleCard` instances to their shared `VocabularyRegistry`. `RoutingContext` provides the authoritative set of route names used by `check_exclusion_coverage`. `DataQualityReport` is independent — it belongs to the data validation pipeline, not the rationale annotation pipeline.
