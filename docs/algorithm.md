# Beam Search over Prompt Candidates

This file is the source of truth for anyone touching the Stage-4 search engine.
The algorithm is a **multi-objective beam search**: each round expands the current elite set
into `beam_width` new prompt candidates, evaluates them on the dev split, and keeps the
non-dominated (quality, cost) front — pruned for spread by NSGA-II crowding distance. The
mutation operator is the LLM Review Agent + Prompt Builder pipeline, not a random perturbation.

When reading or modifying [`compass/agents/prompt_builder/search.py`](../compass/agents/prompt_builder/search.py),
[`compass/agents/prompt_builder/search_ops.py`](../compass/agents/prompt_builder/search_ops.py),
[`compass/agents/review/preprocessor.py`](../compass/agents/review/preprocessor.py), or the
Review Agent prompts, consult this document first.

> The search strategy is chosen by two constants in `search_ops.py` (see
> [Configuration](#configuration)); this repo sets them to beam search, which is what this
> document describes. Using a different strategy means changing those constants and adding
> its own `advance_round` implementation.

---

## Algorithm at a glance

| Component | Technique | Where |
|-----------|-----------|-------|
| Expansion | `beam_width` children per round, allocated across elite parents by the Review Agent | `review_agent_iterative_overlay_beam.md` |
| Mutation operator | LLM Review Agent (identify failure → hypothesise → directive) + Prompt Builder compile | `compass/agents/review/`, `compass/agents/prompts/prompt_builder_system.md` |
| Selection | Pareto dominance on (quality ↑, cost ↓) | `dominates`, `compute_pareto_front` in `search.py` |
| Diversity / pruning | NSGA-II crowding distance, prune to `2·beam_width + 1`, endpoints protected | `crowding_distance`, `prune_to_size` in `search.py` |
| Progress metric | 2-D hypervolume of the front vs a worst-seen reference point | `compute_hypervolume` in `search.py` |
| Stagnation | relative hypervolume improvement ≤ `epsilon` | `advance_round_beam` in `search_ops.py` |
| Convergence | eval budget spent **and** stagnation ≥ `convergence_limit`, or `max_rounds`, or Review Agent `LoopSignal(action="exit")` | `advance_round_beam` |

---

## Configuration

Two module-level constants in `search_ops.py` select the strategy. In this repo:

```python
_BRANCH_ALGORITHM: AlgorithmType = "beam"
_BRANCH_ALGORITHM_STATE: dict[str, Any] = {"beam_width": 3}
```

`init_search_state` copies `_BRANCH_ALGORITHM_STATE` into `SearchState.algorithm_state`.
`advance_step` (MCP tool) dispatches to `advance_round` → `advance_round_beam`.

`SearchState` fields that govern the loop (defaults from `search.py`):

| Field | Default | Meaning |
|---|---|---|
| `algorithm_state["beam_width"]` | `3` | children generated per round |
| `evaluation_budget` | `60` | total candidate evaluations before convergence is allowed |
| `max_rounds` | `50` | hard round cap |
| `stagnation_limit` | `3` | rounds without hypervolume progress before `mutation_mode` may flip / backtrack cues fire |
| `convergence_limit` | `5` | consecutive stagnant rounds required to converge (must be `> stagnation_limit`) |
| `epsilon` | `0.001` | minimum *relative* hypervolume improvement that counts as progress |
| `algorithm_state["epsilon_min"]` | `0.0005` | floor for `epsilon` after tightening |
| `algorithm_state["backtrack_threshold"]` | `2` | stagnation count at which the round summary sets `backtracking = True` |
| `mutation_mode` | `"targeted"` | `targeted` (faithful edits) vs `exploratory` (structural rewrite) |

`search_state.json` is auto-created at Stage 4 entry by `_ensure_stage4_search_state`
(called from `_next_action_for_stage_4` in `status.py`), so cold-start sub-agents always find
a real `SearchState` on disk.

---

## The candidate tree

Every candidate is a `Candidate` record (`search.py`):

```python
prompt_version: str                 # "v1", "v2", … (monotonic, from SearchState.next_variant_seq)
parent_version: str | None          # "base" for cold-start seeds, else a prior vN
secondary_parent_version: str | None # set only for two-parent merges (round ≥ 3)
quality_score: float                # = metrics "quality_change": signed fraction vs the baseline route
cost: float                         # = metrics "cost_change_with_overhead": signed fraction vs baseline
round_introduced: int
example_ids: list[str]              # few-shot ids embedded in this prompt
eval_status: "pending" | "running" | "complete" | "failed" | None
```

The root is the sentinel string `"base"` (`INITIAL_PARENT_VERSION` in
`compass/agents/review/models.py`). `parent_version` / `secondary_parent_version` edges form
the search tree (a DAG once merges appear). Lineage of dominated / evicted candidates is
preserved in the append-only `outputs/<run_id>/search/candidate_archive.json`; the live tree is
rendered to `outputs/<run_id>/search/viz.html` after every state mutation.

**Scores are deltas, not accuracy.** `quality_score` and `cost` are signed fractions relative
to the dataset's baseline route, produced by `compute_cost_quality_change` in
[`compass/eval/metrics.py`](../compass/eval/metrics.py). Classifier accuracy is reported in the
score report and shown in the viz tooltip, but it is not the optimization objective.

---

## Round structure

Each round follows the fixed Prompt Builder tool sequence
(`compass/agents/prompts/prompt_builder_system.md`):

> `register_candidate` (per candidate) → `run_batch_eval` (once) → `record_eval_result`
> (per succeeded entry) → `advance_step`. Never reorder. Never reuse a version number.

`run_batch_eval` evaluates all of a round's candidates concurrently under one shared rate
limiter (`compass/eval/batch_eval.py`).

### Round 1 — cold start

Overlay: `review_agent_cold_start_overlay_beam.md`.

The Review Agent produces **K = `beam_width`** diverse seed candidates with no eval data yet.
Seeds must span confusion cells *and* cost regions. All seeds have `parent_version = "base"`.

`advance_round_beam` special-cases round 1: `update_elite_set(..., is_cold_start_round=True)`
**bypasses Pareto filtering and crowding-distance pruning** — every scored seed is retained so
each initial strategy gets a second data point in round 2. `validate_elite_set` is skipped for
the same reason. Stagnation count is forced to 0.

### Round 2 — post-cold-start

Overlay: `review_agent_post_coldstart_overlay_beam.md`.

The elite set this round holds every scored round-1 seed as a **protected parent**. The Review
Agent must emit **exactly one `ChildVariant` per scored elite member**, using that member as
`parent_version`:

- one child per protected parent — no doubling up;
- `secondary_parent_version` must be `null` (no merges yet);
- failed cold-start seeds (`eval_status != "complete"`) are skipped;
- `LoopSignal.continue_search = true` unconditionally — round 2 is a structured exploration
  step, not a convergence check.

Standard Pareto competition begins in round 3.

### Round ≥ 3 — steady-state iterative

Overlay: `review_agent_iterative_overlay_beam.md`.

The Review Agent emits `beam_width` children total, **allocated at its discretion** across 1–3
members of the current elite set:

- **Concentrate** (3 → 1): one elite is clearly most promising toward the threshold (or, once
  the threshold is met, toward the oracle point);
- **Split** (2 + 1): two elites look comparably promising;
- **Spread** (1 + 1 + 1): a child from each of three elites.

Per-child workflow (from `review_agent_iterative_base_system.md`): **identify failure mode →
hypothesise from data → create directive(s)**. The hypothesis is grounded in specific example
ids or metric patterns. Confusion cells are ranked by **threshold gap** while the user
threshold is unmet, and by **oracle gap** (`oracle_quality_change` / `oracle_cost_change` per
cell) once it is met. Multiple children off one parent must target *different* cells. Two-parent
merges (`secondary_parent_version`) are allowed from round 3 on.

The Prompt Builder compiles each `ChildVariant`'s `EditDirective`s (`block_type` ∈ `rule`,
`example`, `output_schema`, `vocabulary`, `contrast_pair`) into a concrete prompt in the fixed
section order Objective → Categories → Decision Logic → Examples → Output Format.

---

## Selection: elite set update

`advance_round_beam` calls `update_elite_set(current_elite, scored_pending, max_size = 2*beam_width + 1)`:

1. Combine the current elite with the newly scored candidates; drop placeholder `(0.0, 0.0)`
   entries; dedupe by `prompt_version`.
2. `compute_pareto_front` — keep only non-dominated candidates. `dominates(a, b)` is true when
   `a.quality_score >= b.quality_score` **and** `a.cost <= b.cost` with at least one strict
   inequality.
3. `prune_to_size(front, 2*beam_width + 1)` — while the front exceeds the cap, repeatedly
   remove the non-endpoint candidate with the smallest **NSGA-II crowding distance**. The two
   endpoints (highest quality, lowest cost) are protected every iteration.

`crowding_distance` gives endpoints `inf` and each interior point the sum over the quality and
cost axes of the normalized gap between its two neighbours — the standard NSGA-II diversity
measure. With `beam_width = 3` the elite set holds at most **7** candidates.

`validate_elite_set` recomputes the front defensively after every round except round 1 and logs
if it had to drop a dominated member.

---

## Progress and stagnation

After updating the elite set, `advance_round_beam`:

1. Builds a **worst-seen reference point** from all elite + scored candidates this round:
   `ref = (worst_quality * 0.9 or -0.1, worst_cost * 1.1 or 0.1)` — a lower-left corner below
   every point seen.
2. Computes `new_hypervolume = compute_hypervolume(new_elite, ref)` — the 2-D area the front
   dominates, via a sweepline over quality.
3. Stagnation (skipped on round 1):
   ```
   relative_improvement = (new_hypervolume - hypervolume_prev) / hypervolume_prev   # or new_hypervolume if prev == 0
   new_stagnation_count  = 0 if relative_improvement > state.epsilon else state.stagnation_count + 1
   ```
4. **Epsilon tightening (one-time):** when all user targets are first met by the elite set,
   `epsilon ← max(epsilon / 2, epsilon_min)`, the stagnation count resets to 0, and a flag is
   set so this never repeats. This raises the bar for "progress" once the loop is in
   refinement territory.
5. **Backtracking flag:** `backtracking = new_stagnation_count >= backtrack_threshold` (2). The
   iterative overlay surfaces `stagnation_signal.hypervolume_delta` to the Review Agent as a
   cue to change which elite(s) it expands and pick a different confusion cell.

Hypervolume, previous hypervolume, and the reference point are stored back into
`algorithm_state` for the next round; the per-round values are also recorded on the
`RoundSummary` (`hypervolume`, `reference_point`, `backtracking`, `target_improvement`,
`front_quality_spread`, `stagnation_count`).

---

## Convergence

```
total_evaluated = sum(len(r.candidates_evaluated) for r in round_history) + len(this_round)
budget_reached  = total_evaluated >= evaluation_budget                     # default 60
converged       = (budget_reached and new_stagnation_count >= convergence_limit)   # default 5
                  or new_round >= max_rounds                               # default 50
```

`convergence_reason` is `"max_rounds"` when the round cap is hit, otherwise `"stagnation"`.
On the terminal round `RoundSummary.converged` is `True`, `SearchState.converged` is set, and
`loop_phase` flips to `"build"` (the Prompt Builder closes the run out instead of dispatching
another review).

The Review Agent can also end the loop early by emitting `LoopSignal(action="exit")`. Per
`review_agent_iterative_base_system.md`, this is only safe when `single_candidate_meets_all` is
true — one candidate meets *every* declared user target.

After `advance_round_beam` returns, scored candidates are appended to
`candidate_archive.json`, `pending_candidates.json` is cleared, and `viz.html` is regenerated.

---

## Mutation modes

`SearchState.mutation_mode` toggles between:

- **`targeted`** — faithful paraphrase / reorder / example swap against the parent prompt;
- **`exploratory`** — structural rewrite with different example sets.

The mode flips toward `exploratory` when the search stalls (stagnation), giving the Review
Agent licence to propose larger changes. See `prompt_builder_system.md` for how each mode
constrains the compiled prompt.

---

## Pointers for future changes

- **Change the beam width:** edit `_BRANCH_ALGORITHM_STATE` in `search_ops.py`. The elite-set
  cap (`2*beam_width + 1`) and per-round child count both follow from it; the iterative overlay
  reads `briefing.beam_width`.
- **Change the selection objective** (e.g. add latency as a third axis): extend `Candidate`,
  `dominates`, `compute_pareto_front`, `crowding_distance`, and `compute_hypervolume` in
  `search.py` to K objectives, and update `classify_user_target` in
  `compass/agents/review/preprocessor.py`.
- **Change pruning** (e.g. reference-point-based instead of crowding distance): edit
  `prune_to_size` / `crowding_distance` in `search.py`.
- **Change convergence detection:** edit the `converged` / `budget_reached` logic in
  `advance_round_beam` in `search_ops.py` and update the "Convergence" section above.
- **Tune stagnation sensitivity:** `epsilon`, `epsilon_min`, `stagnation_limit`,
  `convergence_limit`, `backtrack_threshold`. Note the `convergence_limit > stagnation_limit`
  invariant enforced by a `model_validator` on `SearchState`.

---

## References

Deb, K., Pratap, A., Agarwal, S. & Meyarivan, T. (2002). *A fast and elitist multiobjective
genetic algorithm: NSGA-II.* IEEE Transactions on Evolutionary Computation, 6(2):182–197.
*(Crowding-distance diversity operator used in `prune_to_size`.)*

Zitzler, E. & Thiele, L. (1999). *Multiobjective evolutionary algorithms: a comparative case
study and the strength Pareto approach.* IEEE Transactions on Evolutionary Computation,
3(4):257–271. *(Hypervolume indicator used as the progress metric.)*
