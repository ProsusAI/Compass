## Compass Stage-4 Review Agent Dispatch

When dispatching a Stage-4 Review sub-agent (any session driving the Compass MCP where pipeline phase is `review` or an `Agent` call is being made with description like "Stage 4 / Review …"), the sub-agent's system prompt MUST be fetched from the Compass MCP — never hand-written. Pass the returned text verbatim.

| `SearchState.warm_up_complete` | MCP prompt to fetch | Phase |
|---|---|---|
| `False` | `compass_review_agent_cold_start(algorithm=<branch_algorithm>)` | Warm-up / seeding |
| `True`  | `compass_review_agent_iterative(algorithm=<branch_algorithm>)` | Iterative loop (round ≥ 2) |

`<branch_algorithm>` is the leaf's `_BRANCH_ALGORITHM` (e.g. `sms_emoa`, `emosa`, `beam`, `hill_climb`). Both prompts are defined in [`compass/mcp/prompts.py`](../../compass/mcp/prompts.py) and assemble three layers (shared base + phase base + algorithm overlay) via `assemble_review_prompt`.

### How to use the returned text

Pass it as-is as the `prompt` argument to the `Agent` tool (or equivalent sub-agent dispatch mechanism). The orchestrator MAY prepend a brief 1–3 sentence dispatch envelope carrying runtime context (e.g. `run_id`, `round_number`, `selection_hint` for algorithms that fan out per-trajectory). The orchestrator MUST NOT modify, summarise, paraphrase, or "add context to" the canonical prompt body.

### Forbidden in any dispatch prompt

Do NOT restate any of the following — the canonical prompt owns them, and any restatement drifts silently until validation fires:

- `EditDirective` field names (`directive_id`, `target_version`, `block_type`, `block_identifier`, `granularity`, `directive`, `priority`, optional `example_content` / `contrast_pair_content`).
- `ChildVariant` field names.
- The block-type vocabulary (`rule`, `example`, `output_schema`, `vocabulary`, `contrast_pair`).
- Per-algorithm child-count rules (e.g. SMS-EMOA's strict `1`, EMOSA's K-per-trajectory, beam's multi-child generation).
- Loop-phase logic (when to emit `loop_signal.action = "exit"` vs `"continue"`).

### Rationale

Run `d04da214` (SMS-EMOA, round 0) tripped a Pydantic `ValidationError` from `record_directive_outcomes` ([`compass/mcp/review_tools.py:406`](../../compass/mcp/review_tools.py)) when its Stage-4 sub-agent — dispatched with a hand-rolled prompt — submitted directives shaped `{"type": "directive_text", "body": "..."}`. The validator `EditDirective` is declared with `model_config = ConfigDict(extra="forbid")` ([`compass/agents/review/models.py:272-286`](../../compass/agents/review/models.py)); the hand-rolled shape matches zero required fields and two forbidden extras. The error message named `ChildVariant`; lacking any recovery path, the LLM started filesystem-hunting (`find … | xargs grep -l ChildVariant`) to read the schema off disk — directly violating the no-Bash invariant the canonical prompt establishes at [`compass/agents/prompts/review_agent_base_system.md:13-15`](../../compass/agents/prompts/review_agent_base_system.md).

Hand-rolling is most tempting on algorithms with sparse overlays — SMS-EMOA's iterative overlay fits the entire child-emission rule in ~7 lines, making the canonical prompt feel skippable. Those are precisely the cases where drift is silent until validation fails. This rule closes the door uniformly across all four algorithm leaves.

Apply alongside [`generalize-fix-routing.md`](generalize-fix-routing.md), [`generalize-merge-discipline.md`](generalize-merge-discipline.md), and [`pr-base-branch.md`](pr-base-branch.md).
