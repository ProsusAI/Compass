# Parallel Beam Search Refinement — Design Spec

**Date:** 2026-04-02
**Status:** Draft

## Overview

This spec redesigns the Stage 4 refinement loop from single-candidate hill-climbing to multi-parent beam search with concurrent evaluation and adaptive beam width. The core change is that each round produces K candidates in parallel (one per directive batch, each potentially branching from a different Pareto front member), evaluates them concurrently, and feeds the full batch outcome back to the Review Agent.

Stages 1–3 and 5, Pareto dominance logic, the eval engine internals (except `RunDependencies`), the orchestrator dispatch pattern, and file-backed persistence are all unchanged.

## Changed / New Components

| Component | File | Change |
|---|---|---|
| `SearchState` | `odysseus/agents/prompt_builder/search.py` | Add `beam_width`, `min_beam_width`, `max_beam_width`, `active_evals` |
| `Candidate` | `odysseus/agents/prompt_builder/search.py` | Add `eval_status`, `mutation_strategy`, `source_directive_batch_id` |
| `DirectiveBatch` | `odysseus/agents/review/models.py` | New model |
| `ReviewResult` | `odysseus/agents/review/models.py` | Replace `edit_directives` with `directive_batches` |
| `ReviewBriefing` | `odysseus/agents/review/models.py` | Add `beam_width`, `batch_outcomes` |
| `BatchOutcome` | `odysseus/agents/review/models.py` | New model |
| `LoopSignal` | `odysseus/agents/review/models.py` | Add `suggested_beam_width` |
| `run_batch_eval` | `odysseus/mcp/prompt_building_tools.py` | New tool (replaces `run_eval` in `_BUILD_TOOLS`) |
| `BatchEvalCandidate` | `odysseus/mcp/prompt_building_tools.py` | New input model |
| `BatchEvalResult` / `CandidateEvalOutcome` | `odysseus/mcp/prompt_building_tools.py` | New output models |
| `_detect_stage_4_phase` | `odysseus/agents/pipeline/status.py` | Add `build_recovering` phase |
| `STAGE_4_BUILD_RECOVERING_INSTRUCTION` | `odysseus/agents/pipeline/instructions.py` | New template |
| `STAGE_REGISTRY` | `odysseus/mcp/server.py` | Add `run_batch_eval` to `"prompt_building"` entry |
| Review Agent system prompt | `odysseus/agents/prompts/review_agent_system.md` | New schema, branching section, diversity rule |
| `save_edit_directives` / `load_edit_directives` | `odysseus/agents/review/ops.py` | Renamed to `save_directive_batches` / `load_directive_batches`, format changes from `list[EditDirective]` to `list[DirectiveBatch]` |
| `advance_round` | `odysseus/agents/prompt_builder/search_ops.py` | Add `active_evals` guard, `eval_status` filtering, beam width calculation, stagnation-on-all-fail handling |
| `register_candidate` | `odysseus/agents/prompt_builder/search_ops.py` | Accept new `eval_status`, `mutation_strategy`, `source_directive_batch_id` parameters |
| `RunDependencies` | `odysseus/eval/controller.py` | Accept optional shared `TokenBucketRateLimiter` for concurrent eval runs |
| `STAGE_4_BUILD_INSTRUCTION` | `odysseus/agents/pipeline/instructions.py` | Replace `run_eval` with `run_batch_eval` in sub-agent tools list |
| Prompt Builder system prompt | `odysseus/agents/prompts/prompt_builder_system.md` | New `run_batch_eval` tool usage, directive batch consumption, pipelined generation flow |

---

## Section 1: Search State & Beam Width

### `SearchState` Extensions

Add four fields to `SearchState` in `odysseus/agents/prompt_builder/search.py`:

```python
class SearchState(BaseModel):
    # ... existing fields ...
    beam_width: int = 2
    min_beam_width: int = 2
    max_beam_width: int = 5
    active_evals: list[str] = Field(default_factory=list)
```

| Field | Type | Default | Purpose |
|---|---|---|---|
| `beam_width` | `int` | `2` | Candidates to generate and evaluate per round |
| `min_beam_width` | `int` | `2` | Floor for adaptive calculation |
| `max_beam_width` | `int` | `5` | Ceiling for adaptive calculation |
| `active_evals` | `list[str]` | `[]` | Prompt versions currently being evaluated (in-flight tracking for crash recovery) |

### Adaptive Beam Width Calculation

Computed in `advance_round` after each round completes. Evaluated top-to-bottom; first matching row wins.

| Condition | `beam_width` |
|---|---|
| `mutation_mode == "exploratory"` AND `stagnation_count >= 2` | `max_beam_width` (5) |
| `mutation_mode == "exploratory"` | 4 |
| `mutation_mode == "targeted"` AND `stagnation_count == 0` | `min_beam_width` (2) |
| `mutation_mode == "targeted"` | 3 |

If `LoopSignal.suggested_beam_width` is present, it overrides the table result (clamped to `[min_beam_width, max_beam_width]`). See Section 5.

Note: The table uses post-round values: the newly computed `mutation_mode` and `stagnation_count` (i.e., the values that will be persisted), not the pre-round state.

### `advance_round` Beam Width Logic

After computing `new_mutation_mode` and `new_stagnation_count`:

```python
# 1. Compute from adaptive table
if new_mutation_mode == 'exploratory' and new_stagnation_count >= 2:
    new_beam_width = state.max_beam_width
elif new_mutation_mode == 'exploratory':
    new_beam_width = 4
elif new_mutation_mode == 'targeted' and new_stagnation_count == 0:
    new_beam_width = state.min_beam_width
else:
    new_beam_width = 3

# 2. Apply Review Agent override if present
if signal and signal.suggested_beam_width is not None:
    new_beam_width = signal.suggested_beam_width

# 3. Clamp
new_beam_width = max(state.min_beam_width, min(state.max_beam_width, new_beam_width))
```

The computed `beam_width` is included in the `model_copy(update={...})` dict alongside the other state updates.

### `active_evals` Lifecycle

`active_evals` tracks prompt versions with in-flight evaluations. Versions are added when `run_batch_eval` launches each eval, and removed when the result is recorded. On restart, a non-empty `active_evals` signals the `build_recovering` phase (Section 4). The list is persisted in `search_state.json` and is the source of truth for crash recovery.

---

## Section 2: Multi-Parent Branching & Directive Model

### New Model: `DirectiveBatch`

```python
class DirectiveBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directive_batch_id: str
    parent_version: str                    # Pareto front member to branch from
    directives: list[EditDirective]        # Edits to apply to this parent
    mutation_strategy: Literal["targeted", "exploratory", "structural"]
    priority: int                          # Execution order hint (lower = first)
```

Each batch produces exactly one candidate. The Prompt Builder applies `directives` to the prompt at `parent_version` to generate a new candidate.

`mutation_strategy` categorizes the type of change:
- `targeted` — focused edits to specific blocks (rule tweaks, example refinements). Used when the search is making progress.
- `exploratory` — broader changes that explore new directions (new rules, example swaps, assembly policy changes). Used to escape local optima.
- `structural` — fundamental reorganization of the prompt (section reordering, schema overhaul, major example replacement). Reserved for when both targeted and exploratory approaches stagnate.

Note: `SearchState.mutation_mode` (two-valued: `targeted | exploratory`) controls the overall search posture and drives beam width adaptation. `DirectiveBatch.mutation_strategy` (three-valued) is a per-batch instruction. The Review Agent can assign `structural` strategy to individual batches regardless of the current `mutation_mode`.

### `ReviewResult` Change

Replace the flat `edit_directives` field with `directive_batches`:

```python
# Before
class ReviewResult(BaseModel):
    edit_directives: list[EditDirective]
    ...

# After
class ReviewResult(BaseModel):
    directive_batches: list[DirectiveBatch]
    ...
```

The `candidate_ranking`, `promotion_decisions`, `loop_signal`, `regression_guards`, and `directive_history_update` fields are unchanged.

### `Candidate` Model Additions

```python
class Candidate(BaseModel):
    # ... existing fields ...
    eval_status: Literal["registered", "evaluating", "scored", "failed"] = "registered"
    mutation_strategy: Literal["targeted", "exploratory", "structural"] | None = None
    source_directive_batch_id: str | None = None
```

| Field | Type | Default | Purpose |
|---|---|---|---|
| `eval_status` | `Literal[...]` | `"registered"` | Tracks candidate lifecycle (see Section 4) |
| `mutation_strategy` | `Literal[...] \| None` | `None` | Strategy inherited from source batch |
| `source_directive_batch_id` | `str \| None` | `None` | Traceability link: batch → candidate → score |

### Diversity Enforcement

When `beam_width >= 3`, at least one `DirectiveBatch` in `ReviewResult.directive_batches` must have `mutation_strategy == "exploratory"`. This is validated in `record_directive_outcomes`.

**Violation handling:** If the rule is violated, `record_directive_outcomes` rejects the `ReviewResult` with a validation error describing the constraint. The Review Agent must re-emit with at least one exploratory batch. This avoids the need for synthetic directive generation.

When the Pareto front has a single member, all batches necessarily share the same `parent_version`. Diversity enforcement still applies (requiring one exploratory mutation strategy) but multi-parent branching provides no additional benefit until the front has >= 2 members.

### Directive Batch Persistence

`record_directive_outcomes` (in `odysseus/mcp/review_tools.py`) currently accepts a flat `edit_directives: list[dict]` parameter and persists via `save_edit_directives`. This changes to accept `directive_batches: list[dict]` instead (parameter renamed from `edit_directives` to `directive_batches`). The underlying persistence functions `save_edit_directives` and `load_edit_directives` in `odysseus/agents/review/ops.py` are renamed to `save_directive_batches` and `load_directive_batches` respectively. Persistence path remains `outputs/<run_id>/search/edit_directives.json` but the serialization format changes from `list[EditDirective]` to `list[DirectiveBatch]`.

`get_edit_directives` is updated to return `list[DirectiveBatch]` instead of `list[EditDirective]`. The Prompt Builder consumes these batches directly.

Cold-start v1 does not use `get_edit_directives` (it generates from seed examples), so no backward compatibility shim is needed.

### Review Agent System Prompt Updates

The Review Agent system prompt (`odysseus/agents/prompts/review_agent_system.md`) requires three additions:

1. **Updated output schema** — replace the `edit_directives` array with `directive_batches`, including a JSON example showing `directive_batch_id`, `parent_version`, `directives`, `mutation_strategy`, `priority`.
2. **"Multi-parent branching" section** — explains that each batch targets a specific Pareto front member as `parent_version`, enabling independent exploration of different front members in parallel.
3. **Diversity enforcement anti-pattern** — explicit rule: "When `beam_width >= 3`, you MUST include at least one batch with `mutation_strategy == 'exploratory'`. Emitting only `targeted` batches is a contract violation."
4. **Batch count contract** — "Emit exactly `beam_width` directive batches. Each batch produces one candidate. `beam_width` is provided in `ReviewBriefing.beam_width`."

---

## Section 3: Pipelined Generation + Concurrent Eval

### Before (sequential per-candidate)

```
for each directive:
    generate candidate
    register_candidate
    run_eval
    record_eval_result
advance_round
```

### After (pipelined)

```
candidates = []
for each directive_batch (sorted by priority):
    generate candidate from batch.parent_version + batch.directives
    candidates.append(candidate)

batch_result = run_batch_eval(run_id, candidates)
advance_round
```

Generation remains sequential (LLM-driven, fast) so each candidate can reference the previous one's version number if needed. Evaluation is fully concurrent.

### New Tool: `run_batch_eval`

Replaces `run_eval` as the eval entry-point for normal build rounds. See Section 6 for the full tool spec.

### Rate Limiting

The current `TokenBucketRateLimiter` is instantiated per `controller.run()` call. With concurrent eval runs, each would get an independent limiter, multiplying the actual API rate. `run_batch_eval` must create a single shared `TokenBucketRateLimiter` and inject it into all concurrent eval runs via `RunDependencies`. This requires a minor change to `RunDependencies` to accept an optional pre-built rate limiter instead of always constructing one internally.

This is the one change to eval engine internals required by this design.

---

## Section 4: Stage Guards, Pipeline Status & Recovery

### `Candidate.eval_status` Lifecycle

```
registered → evaluating → scored
                       → failed
```

Registered: `register_candidate` called, no eval started.
Evaluating: `run_batch_eval` has launched the eval coroutine.
Scored: eval completed successfully, result recorded.
Failed: eval raised an exception or returned an error.

### Phase Detection (`_detect_stage_4_phase` in `status.py`)

Extended to detect `build_recovering` when `active_evals` is non-empty:

| Files / State | Sub-phase | Action |
|---|---|---|
| No `directive_history.json` AND no `search_state.json` | `cold_start` | Spawn Review Agent (seed examples) |
| No v1 prompt | `build_v1` | Spawn Prompt Builder |
| `loop_phase == "build"` AND `active_evals == []` | `build` | Spawn Prompt Builder |
| `loop_phase == "build"` AND `active_evals != []` | `build_recovering` | Spawn Prompt Builder with recovery flag |
| `loop_phase == "review"` | `review` | Spawn Review Agent |

Note: Convergence (`converged == true`) is detected upstream by `_check_stage_4`, which returns `"complete"` status before `_detect_stage_4_phase` is ever called. The phases above only apply when the search is still active.

Detection reads `active_evals` from `search_state.json`. Empty list (`[]`) and absent field both resolve to the non-recovering `build` phase.

Implementation: `_detect_stage_4_phase` in `status.py` currently reads `loop_phase` from the raw JSON dict. The change: after determining `loop_phase == "build"`, also read `data.get("active_evals", [])`. If non-empty, return `"build_recovering"` instead of `"build"`. Add `"build_recovering"` to the `phase_config` dict in `_next_action_for_stage_4` mapping to `STAGE_4_BUILD_RECOVERING_INSTRUCTION`.

### Crash Recovery Flow

1. Pipeline detects `active_evals` non-empty → `build_recovering` phase.
2. Orchestrator spawns Prompt Builder with `STAGE_4_BUILD_RECOVERING_INSTRUCTION`.
3. Prompt Builder calls `run_batch_eval` in recovery mode (empty `candidates` list).
4. Recovery mode: load `pending_candidates.json`, triage by `eval_status`:
   - `scored` → skip (already complete)
   - `evaluating` → resume via fingerprint-based resume (existing eval-engine mechanism)
   - `registered` → start fresh
5. Execute remaining evals concurrently with `asyncio.gather`.
6. Once all resolved, call `advance_round` normally.

### Transition Guards

**Build → Review** (`advance_round`): All candidates in `pending_candidates` must have `eval_status` in `{"scored", "failed"}`, and `active_evals` must be empty. `advance_round` filters pending candidates: only `eval_status == "scored"` candidates are passed to `update_pareto_front`. Failed candidates (which retain sentinel values `quality_score=0.0, cost=0.0`) are excluded from the Pareto update but their versions are still logged in `round_history.candidates_evaluated`. If no candidates are scored, the round is treated as a stagnation event. If either the eval_status or active_evals condition fails, `advance_round` raises.

**Review → Build** (`record_directive_outcomes`): `directive_batches` count must equal `beam_width`. Diversity rule must be satisfied. Only then does `loop_phase` flip to `"build"`.

**Stage 4 → Stage 5 exit**: `converged == true` AND `active_evals` empty AND `pending_candidates` empty (or all scored/failed).

### New Instruction Template

Add `STAGE_4_BUILD_RECOVERING_INSTRUCTION` to `odysseus/agents/pipeline/instructions.py`:

```python
STAGE_4_BUILD_RECOVERING_INSTRUCTION: str = (
    "<HARD_STOP>\n"
    "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the <stage_system_prompt> below as its system prompt.\n\n"
    "PRE-DISPATCH: Call start_stage(run_id='{run_id}', stage='prompt_building') "
    "BEFORE spawning the sub-agent.\n\n"
    "RECOVERY MODE: active_evals is non-empty. The sub-agent must call run_batch_eval "
    "with an empty candidates list to resume in-flight evaluations before calling "
    "advance_round.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state, get_edit_directives, "
    "init_search_state, register_candidate, record_eval_result, "
    "advance_round_tool, run_batch_eval\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call get_pipeline_status.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>\n\n"
    "<stage_system_prompt></stage_system_prompt>"
)
```

---

## Section 5: Review Agent Briefing & Beam Width Feedback Loop

### `ReviewBriefing` Additions

```python
class ReviewBriefing(BaseModel):
    # ... existing fields ...
    beam_width: int = 2
    batch_outcomes: list[BatchOutcome] = Field(default_factory=list)
```

`beam_width` defaults to 2 (matching `SearchState.beam_width` default) to ensure `ReviewBriefing` can be constructed during cold-start when no beam width has been explicitly calculated yet.

`beam_width` tells the Review Agent exactly how many `directive_batches` to emit. `batch_outcomes` provides per-batch performance feedback so the agent can reason about which mutation strategies and parent selections were effective.

Note: On cold-start (first review round, seed example selection), `batch_outcomes` is an empty list and `beam_width` defaults to 2. The `directive_batches` contract (emit exactly `beam_width` batches) applies only from the first normal review round onward — the cold-start Review Agent emits seed examples using the existing flow, not directive batches.

### New Model: `BatchOutcome`

```python
class BatchOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directive_batch_id: str
    parent_version: str
    mutation_strategy: Literal["targeted", "exploratory", "structural"]
    candidate_version: str | None       # None if generation failed before registration
    eval_status: Literal["scored", "failed"] | None
    quality_delta_vs_parent: float | None
    made_pareto_front: bool
```

Built by the `build_review_briefing` preprocessor by joining `directive_batches` (from `directive_history.json`) with scored/failed candidates via `source_directive_batch_id`. `quality_delta_vs_parent` is `candidate.quality_score - parent.quality_score` where both are available; `None` otherwise.

### `LoopSignal` Addition

```python
class LoopSignal(BaseModel):
    # ... existing fields ...
    suggested_beam_width: int | None = Field(
        default=None,
        description=(
            "Override the adaptive beam width for the next round. "
            "Clamped to [min_beam_width, max_beam_width] by advance_round."
        ),
    )
```

When `suggested_beam_width` is present in the `LoopSignal` consumed by `advance_round`, it replaces the adaptive table result before clamping.

### Preprocessor Changes

`build_review_briefing` (in `odysseus/agents/review/preprocessor.py`) gains two responsibilities:

1. Read `beam_width` from `SearchState` and include it in `ReviewBriefing`.
2. Build `batch_outcomes` by iterating the most recent round's directive batches and joining each to its corresponding scored/failed candidate via `source_directive_batch_id`. Compute `quality_delta_vs_parent` inline.

---

## Section 6: `run_batch_eval` Tool

### Tool Signature

```python
async def run_batch_eval(
    run_id: str,
    candidates: list[BatchEvalCandidate],
) -> BatchEvalResult:
    ...
```

### Input Model

```python
class BatchEvalCandidate(BaseModel):
    prompt_version: str
    parent_version: str | None
    mutation_strategy: Literal["targeted", "exploratory", "structural"]
    source_directive_batch_id: str
    example_ids: list[str]
```

### Output Models

```python
class CandidateEvalOutcome(BaseModel):
    prompt_version: str
    quality_score: float | None
    cost: float | None
    error: str | None
    score_report_path: str | None

class BatchEvalResult(BaseModel):
    succeeded: list[CandidateEvalOutcome]
    failed: list[CandidateEvalOutcome]
```

### Internal Flow (Normal Mode)

1. For each candidate in `candidates`:
   - Call `register_candidate` with `eval_status="registered"`, `mutation_strategy`, `source_directive_batch_id`.
   - Set `eval_status = "evaluating"` and add `prompt_version` to `SearchState.active_evals`.
   - Persist `search_state.json` and `pending_candidates.json`.
2. `asyncio.gather(*[_run_single_eval(c) for c in candidates], return_exceptions=True)`
3. Collect all results from `asyncio.gather`. Process sequentially in a loop:
   - On success: record result, set `eval_status = "scored"`, remove from `active_evals`, persist.
   - On exception: set `eval_status = "failed"`, remove from `active_evals`, log error, persist.
   
   Results are processed sequentially after all evals complete to avoid concurrent writes to `search_state.json` and `pending_candidates.json`. The eval coroutines themselves run concurrently (the expensive part), but the state bookkeeping is serialized.
4. Return `BatchEvalResult` with succeeded and failed lists populated.

**Error handling:**
- Failed candidates are excluded from `advance_round`'s Pareto update but are logged in `round_history.candidates_evaluated`.
- Round proceeds as long as at least one candidate succeeds.
- All fail → stagnation event. `advance_round` increments `stagnation_count`. Review Agent receives an error briefing with all `BatchOutcome.eval_status == "failed"` and is expected to diagnose (e.g., version conflict, invalid directive).

### Recovery Mode (empty `candidates` list)

When called with `candidates=[]` and `active_evals` is non-empty:

1. Load `pending_candidates.json`.
2. For each pending candidate:
   - `eval_status == "scored"` → skip.
   - `eval_status == "evaluating"` → resume via fingerprint-based resume (existing eval-engine path; the fingerprint is derived from `prompt_version` + `example_ids`).
   - `eval_status == "registered"` → start fresh eval.
3. Execute concurrently, same error handling as normal mode.
4. Return `BatchEvalResult`.

### Tool Registration

`run_batch_eval` replaces `run_eval` in `_BUILD_TOOLS` (in `status.py`). The individual `register_candidate` and `record_eval_result` tools remain registered for backward compatibility with cold-start v1 generation, which uses a simpler single-candidate flow.

`run_batch_eval` must also be added to `STAGE_REGISTRY["prompt_building"]` in `odysseus/mcp/server.py`, which gates tool availability per stage. Without this, the tool will be invisible to sub-agents during the build phase. `_RERUN_TOOLS` is unchanged and retains `run_eval` (rerun mode is single-candidate).

---

## Section 7: Prompt Builder Agent Flow Change

### Before (sequential)

```
for each directive:
    generate candidate
    register_candidate          # tool call
    run_eval                    # tool call
    record_eval_result          # tool call
advance_round                   # tool call
```

Four tool calls per candidate; N*3+1 calls for N candidates.

### After (pipelined)

```
for each directive_batch (sorted by priority):
    generate candidate from batch.parent_version + batch.directives
    # no tool calls during generation loop

batch_result = run_batch_eval(run_id, candidates)    # 1 tool call
advance_round(run_id)                                 # 1 tool call
```

Two tool calls for the eval+advance cycle regardless of beam width. Generation is LLM-driven reasoning only (no tool calls), keeping the context window cost flat.

The Prompt Builder reads `beam_width` from `get_search_state` at the start of each build phase to know how many candidates to generate.

### Prompt Builder System Prompt Updates

The Prompt Builder system prompt (`odysseus/agents/prompts/prompt_builder_system.md`) requires updates:

1. **Tool usage** — replace the sequential `register_candidate` → `run_eval` → `record_eval_result` pattern with the new `run_batch_eval` tool, including its input format (`BatchEvalCandidate`).
2. **Directive consumption** — `get_edit_directives` now returns `list[DirectiveBatch]` instead of `list[EditDirective]`. The system prompt must instruct the agent to iterate over batches, applying each batch's `directives` to its `parent_version`.
3. **Recovery mode** — instruct the agent that if `active_evals` is non-empty in the search state, it should call `run_batch_eval` with an empty candidates list to resume.
4. **Generation loop** — the prompt should emphasize generating all candidates before calling `run_batch_eval` (two tool calls for the eval+advance cycle).

---

## Section 8: End-to-End Round Flow

### Normal Round Trace (beam_width = 3)

```
1. Orchestrator calls get_pipeline_status
   → loop_phase="review", active_evals=[], dispatches Review Agent

2. Review Agent:
   a. call build_review_briefing
      → receives ReviewBriefing{beam_width=3, batch_outcomes=[...prior round outcomes...]}
   b. analyzes candidates, pareto front, diminishing returns
   c. emits ReviewResult{directive_batches=[
        DirectiveBatch{id="b1", parent_version="v5", mutation_strategy="targeted", priority=1},
        DirectiveBatch{id="b2", parent_version="v3", mutation_strategy="exploratory", priority=2},
        DirectiveBatch{id="b3", parent_version="v5", mutation_strategy="targeted", priority=3},
      ]}
   d. call record_directive_outcomes
      → validates: 3 batches == beam_width=3 ✓
      → validates: at least 1 exploratory ✓ (b2)
      → flips loop_phase to "build"

3. Orchestrator dispatches Prompt Builder

4. Prompt Builder:
   a. call get_search_state  → beam_width=3
      call get_edit_directives  → directive_batches=[b1, b2, b3]
   b. generate v8 from v5 + b1.directives
   c. generate v9 from v3 + b2.directives
   d. generate v10 from v5 + b3.directives
   e. call run_batch_eval(run_id, [
        BatchEvalCandidate{prompt_version="v8", parent="v5", strategy="targeted", batch_id="b1"},
        BatchEvalCandidate{prompt_version="v9", parent="v3", strategy="exploratory", batch_id="b2"},
        BatchEvalCandidate{prompt_version="v10", parent="v5", strategy="targeted", batch_id="b3"},
      ])
      → registers v8, v9, v10; active_evals=["v8","v9","v10"]
      → asyncio.gather(eval_v8, eval_v9, eval_v10)
      → v10 fails (invalid directive output)
      → v8 scored 0.82, v9 scored 0.79
      → active_evals=[]
      → returns BatchEvalResult{succeeded=[v8,v9], failed=[v10]}
   f. call advance_round
      → processes v8, v9 against pareto front
      → v8 joins front; v9 dominated
      → stagnation_count stays 0 (improvement found)
      → recalculates beam_width: targeted + stagnation=0 → 2
      → flips loop_phase to "review"

5. Loop continues
```

### Crash Recovery Trace

```
1. Prompt Builder is mid-eval when process crashes
   search_state.json: {loop_phase="build", active_evals=["v8","v9","v10"]}
   pending_candidates.json: [
     {version="v8", eval_status="scored"},
     {version="v9", eval_status="evaluating"},
     {version="v10", eval_status="evaluating"},
   ]

2. Pipeline restarts, orchestrator calls get_pipeline_status
   _detect_stage_4_phase: loop_phase="build", active_evals=["v8","v9","v10"] (non-empty)
   → sub-phase: "build_recovering"
   → dispatches Prompt Builder with STAGE_4_BUILD_RECOVERING_INSTRUCTION

3. Prompt Builder:
   a. call get_search_state → sees active_evals non-empty
   b. call run_batch_eval(run_id, candidates=[])  # recovery mode
      → loads pending_candidates
      → v8: scored → skip
      → v9: evaluating → resume via fingerprint
      → v10: evaluating → resume via fingerprint
      → asyncio.gather(resume_v9, resume_v10)
      → v9 scored 0.79, v10 fails
      → active_evals=[]
   c. call advance_round  → normal processing

4. Pipeline continues normally
```

---

## What Doesn't Change

The following are explicitly out of scope for this design:

- **Pareto dominance logic** (`dominates`, `update_pareto_front` in `search.py`) — unchanged
- **Eval engine internals** (`odysseus/eval/`) — unchanged; `run_batch_eval` is a wrapper, not a replacement
- **Rate limiter** — the `TokenBucketRateLimiter` implementation is unchanged, but `RunDependencies` gains an optional parameter to accept a pre-built shared limiter (see Section 3)
- **Stages 1–3 and 5** — unaffected
- **Orchestrator dispatch pattern** — `start_stage`/`complete_stage` bookkeeping unchanged; only the instruction template for `build_recovering` is new
- **File-backed persistence approach** — `search_state.json` and `pending_candidates.json` remain the source of truth; `run_batch_eval` writes incrementally as results arrive (same pattern as existing `record_eval_result`)
