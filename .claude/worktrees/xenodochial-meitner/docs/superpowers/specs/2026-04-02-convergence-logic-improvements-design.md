# Convergence Logic Improvements

## Context

Project Odysseus uses a two-tier convergence system for its prompt optimization loop:

1. **Mechanical tier** (`search_ops.py:advance_round`): Tracks stagnation via Pareto-binary progress, triggers convergence at configurable limits.
2. **Intelligent tier** (Review Agent LLM): Analyzes oracle gaps, diversity, diminishing returns, mutation history. Emits `loop_signal` to override mechanical decisions.

An audit identified 7 issues across both tiers — from semantic bugs to missing signal dimensions. This spec addresses all of them through additive changes that enrich the mechanical tier's signals while preserving the Review Agent as the convergence authority.

## Issues Addressed

| # | Issue | Severity | Category |
|---|-------|----------|----------|
| 1 | Stagnation is purely Pareto-binary — near-miss progress ignored | Design gap | Mechanical tier |
| 2 | `suggested_budget` treated as replacement, not additive delta | Bug | Mechanical tier |
| 3 | Diminishing returns window too small (3 rounds) — noisy signal | Design gap | Preprocessor |
| 4 | Exit path skips `round_history` — final round data lost | Bug | Review tools |
| 5 | No cost tracking for reporting | Missing feature | Reporting |
| 6 | Diversity collapse invisible to mechanical tier | Design gap | Mechanical tier |
| 7 | Hardcoded 0.005 stagnation threshold — not relative | Design gap | Preprocessor |

## Design

### 1. Fix `suggested_budget` as additive delta

**File:** `odysseus/agents/prompt_builder/search_ops.py` (line 374)

Current code replaces `convergence_limit`:
```python
new_convergence_limit = max(signal.suggested_budget, state.stagnation_limit + 1)
```

Change to additive:
```python
new_convergence_limit = max(
    state.convergence_limit + signal.suggested_budget,
    state.stagnation_limit + 1,
)
```

Also update `LoopSignal.suggested_budget` field description in `odysseus/agents/review/models.py` to explicitly document "delta (additional rounds), not absolute."

**Test impact:** The existing test in `test_prompt_builder_search_ops.py` (line ~461) asserts the old replacement semantics (`convergence_limit == 4`). This test must be updated to expect the new additive result.

### 2. Exit path records final RoundSummary

**File:** `odysseus/mcp/review_tools.py` (lines 220-227)

When `loop_signal.action == "exit"`, the current code sets `converged=True` directly, bypassing `advance_round`. The final round never appears in `round_history`.

Fix: before setting `converged=True`, append a terminal `RoundSummary`. Requires adding `_load_pending` to the imports from `search_ops`.

**New import:**
```python
from odysseus.agents.prompt_builder.search_ops import (
    _load_pending,
    _load_state,
    _save_loop_signal,
    _save_state,
)
```

**Updated exit path:**
```python
if parsed_signal.action == "exit":
    with contextlib.suppress(FileNotFoundError):
        state = _load_state(run_id, out)
        pending = _load_pending(run_id, out)
        # Build terminal round summary
        summary = RoundSummary(
            round=state.round,
            candidates_evaluated=[c.prompt_version for c in pending],
            new_pareto_points=0,
            front_size=len(state.pareto_front),
            mutation_mode=state.mutation_mode,
            stagnation_count=state.stagnation_count,
            converged=True,
            convergence_reason="review_exit",
        )
        updated = state.model_copy(update={
            "converged": True,
            "round_history": [*state.round_history, summary],
        })
        _save_state(run_id, updated, out)
```

Note: the terminal summary will have default values for `front_improvement`, `front_quality_spread`, and `round_routing_cost` (all `0.0`) since it bypasses the full `advance_round` computation. This is acceptable — the Review Agent has already analyzed these metrics before emitting "exit."

### 3. Widen diminishing returns window + add stddev

**File:** `odysseus/agents/review/preprocessor.py` (lines 253-280)

Change window from `min(4, len)` to `min(7, len)` — up to 6 deltas instead of 3.

Add `improvement_stddev` computation:
```python
import statistics
stddev = statistics.pstdev(deltas) if len(deltas) >= 2 else 0.0
```

**File:** `odysseus/agents/review/models.py`

New field on `DiminishingReturns`:
```python
improvement_stddev: float = 0.0
```

This lets the Review Agent distinguish "noisy plateau" (high stddev, low trend) from "genuine convergence" (low stddev, low trend).

### 4. Relative stagnation threshold

**File:** `odysseus/agents/review/preprocessor.py`

In `build_review_briefing`, compute relative threshold before calling `compute_diminishing_returns`. Update the call site (currently around line 574-576):

```python
# Compute relative threshold
best_score = max(score_trajectory) if score_trajectory else 0.0
effective_threshold = max(0.005, 0.01 * best_score)

diminishing_returns = compute_diminishing_returns(
    score_trajectory=score_trajectory,
    stagnation_threshold=effective_threshold,
)
```

**File:** `odysseus/agents/review/models.py`

New field on `DiminishingReturns`:
```python
effective_threshold: float = 0.005
```

The `compute_diminishing_returns` function must populate this field with the threshold it actually used.

At score 0.95, threshold becomes 0.0095 (harder to call "stagnant"). At score 0.50, stays at the floor of 0.005.

### 5. Epsilon-progress replaces binary stagnation

**File:** `odysseus/agents/prompt_builder/search.py`

New field on `SearchState`:
```python
epsilon: float = 0.001
```

New function — uses **quality only** to avoid mixing scales (quality is 0-1, cost is arbitrary):
```python
def compute_front_improvement(
    old_front: list[Candidate],
    new_front: list[Candidate],
) -> float:
    """Measure improvement as best quality gain across the front.

    Uses quality dimension only to avoid scale mixing with cost.
    Returns 0.0 if no improvement or fronts are empty.
    """
    if not old_front or not new_front:
        return 0.0
    old_best_quality = max(c.quality_score for c in old_front)
    new_best_quality = max(c.quality_score for c in new_front)
    return max(0.0, new_best_quality - old_best_quality)
```

**File:** `odysseus/agents/prompt_builder/search_ops.py` (line 354)

Replace binary stagnation:
```python
# Before:
new_stagnation_count = 0 if new_pareto_points > 0 else state.stagnation_count + 1

# After:
improvement = compute_front_improvement(state.pareto_front, new_front)
new_stagnation_count = 0 if improvement > state.epsilon else state.stagnation_count + 1
```

New field on `RoundSummary`:
```python
front_improvement: float = 0.0
```

**Design note:** Using quality-only avoids the problem of summing quality (0-1 scale) with cost (arbitrary dollar scale). The Pareto front update already handles cost improvements by adding cost-dominant candidates. The epsilon check answers: "did the best achievable quality improve this round?"

### 6. Near-miss candidates on ReviewBriefing

**File:** `odysseus/agents/review/models.py`

New model:
```python
class NearMissCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    domination_gap_quality: float  # Quality deficit to nearest dominator
    domination_gap_cost: float     # Cost excess over nearest dominator
```

New field on `ReviewBriefing`:
```python
near_miss_candidates: list[NearMissCandidate] = []
```

**File:** `odysseus/agents/review/preprocessor.py`

New function `compute_near_misses`:
```python
def compute_near_misses(
    candidates: list[Candidate],
    front: list[Candidate],
) -> list[NearMissCandidate]:
    """For each dominated candidate, find its minimum domination gap to the front.

    A candidate is a near-miss if it is dominated by at least one front member.
    The gap is the minimum (quality_deficit, cost_excess) pair across all dominators.
    Candidates that are incomparable with the entire front (not dominated, not on front)
    are excluded — they represent unexplored trade-off regions, not near-misses.
    """
    front_versions = {c.prompt_version for c in front}
    near_misses = []
    for candidate in candidates:
        if candidate.prompt_version in front_versions:
            continue
        # Find all front members that dominate this candidate
        min_gap_quality = float("inf")
        min_gap_cost = float("inf")
        dominated_by_any = False
        for f in front:
            if f.quality_score >= candidate.quality_score and f.cost <= candidate.cost:
                if f.quality_score > candidate.quality_score or f.cost < candidate.cost:
                    dominated_by_any = True
                    gap_q = f.quality_score - candidate.quality_score
                    gap_c = candidate.cost - f.cost
                    if gap_q + gap_c < min_gap_quality + min_gap_cost:
                        min_gap_quality = gap_q
                        min_gap_cost = gap_c
        if dominated_by_any:
            near_misses.append(NearMissCandidate(
                version=candidate.prompt_version,
                domination_gap_quality=min_gap_quality,
                domination_gap_cost=min_gap_cost,
            ))
    return near_misses
```

Called in `build_review_briefing` with the current round's pending candidates and the updated Pareto front.

### 7. Front quality spread on RoundSummary

**File:** `odysseus/agents/prompt_builder/search.py`

New field on `RoundSummary`:
```python
front_quality_spread: float = 0.0
```

**File:** `odysseus/agents/prompt_builder/search_ops.py`

In `advance_round`, after updating the front:
```python
if len(new_front) > 1:
    qualities = [c.quality_score for c in new_front]
    front_quality_spread = max(qualities) - min(qualities)
else:
    front_quality_spread = 0.0
```

This is a health signal, not a convergence trigger. Low spread with multiple candidates indicates the front is collapsing to similar quality levels.

### 8. Routing cost tracking for reporting

**File:** `odysseus/agents/prompt_builder/search.py`

New field on `SearchState`:
```python
total_routing_cost: float = 0.0
```

New field on `RoundSummary`:
```python
round_routing_cost: float = 0.0
```

**File:** `odysseus/agents/prompt_builder/search_ops.py`

In `advance_round`:
```python
round_cost = sum(c.cost for c in pending)
new_total_cost = state.total_routing_cost + round_cost
```

Persist `total_routing_cost` on the updated state. Not used as a convergence trigger — reporting only.

**Naming note:** Uses `routing_cost` (not `eval_cost`) because `Candidate.cost` represents the routing cost metric from evaluation, not the cost of running the eval infrastructure.

### 9. Convergence reason on RoundSummary

**File:** `odysseus/agents/prompt_builder/search.py`

New field on `RoundSummary`:
```python
convergence_reason: str | None = None
```

**File:** `odysseus/agents/prompt_builder/search_ops.py`

Set based on which condition triggered convergence:
```python
if converged:
    if new_round >= state.max_rounds:
        convergence_reason = "max_rounds"
    elif new_stagnation_count >= new_convergence_limit:
        convergence_reason = "stagnation"
    else:
        convergence_reason = None  # Should not happen
```

The exit path fix (change #2) uses `convergence_reason="review_exit"`.

## Files Modified

| File | Changes |
|------|---------|
| `odysseus/agents/prompt_builder/search.py` | New fields on `SearchState` (`epsilon`, `total_routing_cost`) and `RoundSummary` (`front_improvement`, `front_quality_spread`, `round_routing_cost`, `convergence_reason`). New `compute_front_improvement()` function. |
| `odysseus/agents/prompt_builder/search_ops.py` | Fix `suggested_budget` semantics. Replace binary stagnation with epsilon-progress. Compute front quality spread, round cost, convergence reason. |
| `odysseus/agents/review/preprocessor.py` | Widen diminishing returns window. Compute relative threshold and pass to `compute_diminishing_returns`. Compute near-miss candidates via new `compute_near_misses()` function. |
| `odysseus/agents/review/models.py` | New fields on `DiminishingReturns` (`improvement_stddev`, `effective_threshold`). New `NearMissCandidate` model with `extra="forbid"`. New field on `ReviewBriefing` (`near_miss_candidates`). Update `LoopSignal.suggested_budget` description. |
| `odysseus/mcp/review_tools.py` | Add `_load_pending` import. Fix exit path to record final `RoundSummary`. |
| `odysseus/agents/prompts/review_agent_system.md` | Document new briefing fields (`near_miss_candidates`, `improvement_stddev`, `effective_threshold`) in the briefing fields table so the Review Agent knows how to use them. |

## Backward Compatibility

**`search.py` models** (`SearchState`, `RoundSummary`, `Candidate`): No `extra="forbid"` — new fields with defaults deserialize cleanly from old JSON. Fully backward compatible.

**`review/models.py` models** (`DiminishingReturns`, `ReviewBriefing`): Have `extra="forbid"`. New fields must be declared on the model class (they are). Old JSON without these fields deserializes correctly because Pydantic uses defaults. However, new JSON with these fields cannot be read by old code — this is a **forward-compatibility** one-way door. Acceptable since we don't run mixed versions.

## Verification

1. **Unit tests**: Test `compute_front_improvement` with known fronts (no improvement, small improvement, large improvement). Test additive budget fix with various starting states. Test diminishing returns with 6+ round trajectories. Test `compute_near_misses` with dominated, near-miss, and incomparable candidates.
2. **Test updates**: Update the existing `suggested_budget` test in `test_prompt_builder_search_ops.py` to expect additive semantics.
3. **Integration**: Run a full pipeline and verify `round_history` is complete (including final round on review exit). Check `convergence_reason` is populated on the terminal round.
4. **Regression**: Run `uv run pytest` — existing tests should pass except the `suggested_budget` test which requires the expected-value update.
