# Review Agent: Replace Assembly Policy with Vocabulary Directives

## Context

The review agent can currently emit directives targeting four block types: `rule`, `example`, `output_schema`, and `assembly_policy`. In practice, `assembly_policy` is a blunt instrument — it changes prompt structure globally (section ordering, example selection strategy), making it hard to attribute improvement or regression to a specific change. Meanwhile, the review agent has no way to address a common failure mode: route confusion caused by ambiguous or overlapping route descriptions.

This change removes `assembly_policy` from the review agent's allowed directives and adds `vocabulary` — letting the review agent refine route and dimension descriptions to sharpen classification boundaries. Section ordering and structural assembly decisions become the sole responsibility of the Prompt Builder agent.

## Changes

### 1. `odysseus/agents/review/models.py`

**MutationType** (line 87-94): Replace `"assembly_policy"` with `"vocabulary_edit"`.

```python
MutationType = Literal[
    "example_swap",
    "rule_edit",
    "schema_change",
    "rule_add",
    "rule_remove",
    "vocabulary_edit",  # was: "assembly_policy"
]
```

**EditDirective.block_type** (line 217): Replace `"assembly_policy"` with `"vocabulary"`.

```python
block_type: Literal["rule", "example", "output_schema", "vocabulary"]
```

No new fields needed. The existing `block_identifier` and `directive` fields are sufficient:
- `block_identifier`: `"route:<name>"` or `"dimension:<name>"` (e.g., `"route:billing"`, `"dimension:complexity"`)
- `directive`: Natural language description of the refinement

Note: `"vocabulary_edit"` (MutationType) and `"vocabulary"` (block_type) follow the existing naming convention where MutationType describes the action and block_type describes the target (cf. `"schema_change"` vs `"output_schema"`).

### 2. `odysseus/agents/prompts/review_agent_system.md`

**Remove** all seven `assembly_policy` occurrences:
- Line 126: JSON schema template (`"block_type": "<rule | example | output_schema | assembly_policy>"`)
- Line 217: Block type documentation in Edit Directive Guidelines
- Line 223: Granularity table example mentioning "swap assembly policy" as a macro example
- Line 341: Example 2 briefing summary mentioning untried mutation types
- Lines 356-357: Example 2 directive JSON
- Line 368: Example 2 `loop_signal` reason
- Line 379: Example 2 reasoning paragraph

**Add** `vocabulary` block type documentation in the Edit Directive Guidelines section:

- `block_type = "vocabulary"` targets route or dimension descriptions in the routing context
- `block_identifier` format: `"route:<route_name>"` or `"dimension:<dimension_name>"`
- The directive describes how to refine the description to sharpen classification boundaries
- Constraints:
  - Cannot rename routes — only refine descriptions
  - Cannot add or remove routes or dimensions
  - Must cite a specific confusion pattern from eval metrics (e.g., "route X and Y are confused in 30% of cases")
  - `granularity` is always `"micro"` (vocabulary edits are targeted refinements, not structural changes)

**Add** a worked example replacing the old assembly_policy example:

```json
{
  "directive_id": "d1",
  "target_version": "v7",
  "block_type": "vocabulary",
  "block_identifier": "route:billing",
  "granularity": "micro",
  "directive": "Sharpen the billing route description to exclude account-level access issues. Current description conflates payment disputes with account lockouts, causing 28% confusion with the account_management route. Emphasize that billing covers only payment methods, charges, refunds, and invoices.",
  "priority": "high"
}
```

**Update** convergence/plateau guidance: where the prompt currently suggests exploring `assembly_policy` as an untried mutation type, replace with `vocabulary_edit`.

### 3. `odysseus/agents/prompts/prompt_builder_system.md`

**Add** vocabulary directive handling in the compilation section:

When vocabulary directives are present in the edit directives, the Prompt Builder must use the refined descriptions instead of the original `routing_context` descriptions when compiling the Categories and Decision Logic sections. The `block_identifier` maps to a specific route or dimension by name.

**Add** explicit statement: section ordering (Objective, Categories, Decision Logic, Examples, Output Format) is the Prompt Builder's sole structural decision. No external directive controls section ordering or assembly strategy.

Note: `prompt_builder_system.md` has zero existing `assembly_policy` references, so there is nothing to remove — only additions are needed.

### 4. `odysseus/agents/review/preprocessor.py`

**Update** `_ALL_MUTATION_TYPES` (line 331-338): Replace `"assembly_policy"` with `"vocabulary_edit"`.

```python
_ALL_MUTATION_TYPES = [
    "example_swap",
    "rule_edit",
    "schema_change",
    "rule_add",
    "rule_remove",
    "vocabulary_edit",  # was: "assembly_policy"
]
```

### 5. Test updates

**`tests/test_review_models.py`:**
- Line 222: `valid_types` list in `test_all_mutation_types_valid` — replace `"assembly_policy"` with `"vocabulary_edit"`
- Lines 252, 255: `untried_mutation_types` in `TestMutationHistory.test_basic_construction` — replace `"assembly_policy"` with `"vocabulary_edit"`
- Line 472: `test_all_block_types_valid` — replace `"assembly_policy"` with `"vocabulary"` (note: this tests `EditDirective.block_type`, not `MutationType`)

**`tests/test_review_preprocessor.py`:**
- Lines 448-454: `all_mutation_types` list in `correlate_mutations` test — replace `"assembly_policy"` with `"vocabulary_edit"`
- Line 815: `untried_mutation_types=["assembly_policy"]` in `_make_briefing` helper — replace with `"vocabulary_edit"`
- Line 881: `assert "assembly_policy" in summary` in `test_lists_untried_mutations` — replace with `"vocabulary_edit"`

### 6. No changes needed

- `odysseus/agents/routing_context.py` — RoutingContext model stays immutable
- `odyssey/agents/review/ops.py` — Generic JSON serialization, no block_type filtering
- `odysseus/eval/` — Eval engine doesn't inspect directive types
- Cold-start logic — Only emits example directives

## Edge cases

The Prompt Builder should skip vocabulary directives whose `block_identifier` references a route or dimension name not present in the current `RoutingContext`. Add this as an instruction in `prompt_builder_system.md`: "If a vocabulary directive references an unrecognized route or dimension name, ignore it."

No model-level validation is added — this is consistent with the project's agent-driven architecture where prompt-level guards are preferred over schema enforcement.

## Verification

1. Run `uv run pyright` — type check passes with updated Literal types
2. Run `uv run pytest` — all tests pass with updated values
3. Run `uv run ruff check .` — no lint issues
4. Verify the review agent prompt renders correctly and examples are valid JSON
5. Check that `_ALL_MUTATION_TYPES` in preprocessor matches `MutationType` literal values
