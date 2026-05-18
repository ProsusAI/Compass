# Scenario: EMOSA — Calibration Round (K=5 Trajectory Seeding)

## Setup
- Dataset: `tests/scenarios/data/emosa_toy_dataset.jsonl`
- Backend: `mock-echo`
- Search parameters: `num_trajectories=5`, `max_evals=50`
- Algorithm: `emosa`
- Initial `loop_phase`: `"calibration"`
- Weight vectors: `[(0.9, 0.1), (0.7, 0.3), (0.5, 0.5), (0.3, 0.7), (0.1, 0.9)]`
- Initial `ideal_point`: `(1.0, 0.0)` (placeholder — refreshed after calibration_complete)
- Initial `nadir_point`: `(0.0, 1.0)` (placeholder — refreshed after calibration_complete)
- System prompts: `odysseus_review_agent_cold_start`, `odysseus_prompt_builder`
- MCP tools: `get_pipeline_status`, `get_search_state`, `init_search_state`,
  `register_candidate`, `run_batch_eval`, `advance_step`,
  `build_review_briefing`, `record_directive_outcomes`

## Scenario Description

This scenario exercises the EMOSA cold-start calibration round from an empty state through to
trajectory seeding, covering:

1. **Calibration phase**: The cold-start Review Agent (`odysseus_review_agent_cold_start` with
   the `emosa` overlay) receives an empty briefing and emits exactly K=5 diverse child
   directives — one per trajectory. The Prompt Builder realises all five seeds via
   `register_candidate` (round=0, no parents). Batch evaluation scores all five
   candidates.

2. **Advance step**: `advance_step` is called to consolidate the scored seeds.
   `calibration_complete` seeds each trajectory with its corresponding candidate:
   `current_solution`, `current_quality`, `current_cost`, and `current_energy` are
   populated. The algorithm pocket's `phase` flips to `"search"` and the top-level
   `loop_phase` flips to `"review"`. `step_count` increments to 1. `total_evals` becomes 5.

The scenario validates:
- The cold-start Review Agent emits ≥ K=5 child variants in a single response.
- Batch evaluation scores all 5 candidates.
- After `advance_step`, each of the 5 trajectories has non-null
  `current_solution`, `current_quality`, `current_cost`, and `current_energy`.
- `algorithm_state.phase` flips from `"calibration"` to `"search"`.
- Top-level `loop_phase` flips to `"review"`.
- `algorithm_state.step_count == 1`.
- `algorithm_state.total_evals == 5`.

## User Simulator

You are a test harness operator driving the EMOSA calibration round in a minimal toy run.
You have full knowledge of the expected flow and will verify state after each tool call.

**Your knowledge:**
- The dataset is `tests/scenarios/data/emosa_toy_dataset.jsonl` (10 examples, 3 tiers).
- The search is initialised with `algorithm="emosa"`, `num_trajectories=5`, `max_evals=50`,
  `backend="mock-echo"`.
- K=5 weight vectors: `[(0.9, 0.1), (0.7, 0.3), (0.5, 0.5), (0.3, 0.7), (0.1, 0.9)]`.
- All trajectories start with `current_solution=None` (calibration phase).
- You know the EMOSA calibration loop: cold-start review → build (K=5 seeds) → batch eval →
  advance_step (seeds trajectories, flips phase to "search" + loop_phase to "review").

**Behaviour:**
1. Start by calling `get_pipeline_status` to confirm Stage 4 calibration phase is active and
   `activate_prompt == "odysseus_review_agent_cold_start"` (with `algorithm="emosa"`).
2. Invoke the cold-start Review Agent. Confirm it emits ≥ 5 child directives.
3. Call `get_pipeline_status` again and confirm phase transitions to `warmup_build` or
   `calibration` build dispatch.
4. Invoke the Prompt Builder and register all 5 seed candidates via `register_candidate`.
5. Call `run_batch_eval` to score all 5 candidates concurrently.
6. Call `advance_step`. Confirm the result shows:
   - `algorithm_state.phase == "search"`
   - `loop_phase == "review"`
   - `step_count == 1`
   - `total_evals == 5`
7. Call `get_search_state` and verify each trajectory in `algorithm_state.trajectories`
   has non-null `current_solution`, `current_quality`, `current_cost`, and `current_energy`.

**Opening message:** "Please initialise a new search state with `algorithm='emosa'`,
`num_trajectories=5`, `max_evals=50`, and `backend='mock-echo'`, then drive the EMOSA
calibration round. Dataset: `tests/scenarios/data/emosa_toy_dataset.jsonl`. After calibration
completes, verify all 5 trajectories are seeded and `loop_phase` has flipped to `'review'`."

## Verification Criteria

### Calibration Phase — Review Agent
- [ ] `get_pipeline_status` returns an instruction activating `odysseus_review_agent_cold_start`
      (with `algorithm="emosa"`) before any seeds are registered
- [ ] The cold-start Review Agent emits ≥ 5 child variant directives (one per trajectory) in a
      single response
- [ ] No steady-state Review Agent overlay (`odysseus_review_agent_iterative`) is invoked during
      the calibration round

### Calibration Phase — Build and Eval
- [ ] The Prompt Builder registers exactly 5 seed candidates (one per trajectory, round=0, no
      parents)
- [ ] `run_batch_eval` evaluates all 5 candidates concurrently and returns 5 scored results
- [ ] No `advance_step` call is made before all 5 candidates are scored

### Advance Step — Trajectory Seeding
- [ ] `advance_step` is called once after all 5 candidates are scored
- [ ] After `advance_step`, `algorithm_state["phase"] == "search"`
- [ ] After `advance_step`, top-level `loop_phase == "review"`
- [ ] After `advance_step`, `algorithm_state["step_count"] == 1`
- [ ] After `advance_step`, `algorithm_state["total_evals"] == 5`

### Per-Trajectory State
- [ ] Each of the 5 entries in `algorithm_state["trajectories"]` has:
  - `current_solution` is not null (set to the scored candidate's `prompt_version`)
  - `current_quality` is not null (float)
  - `current_cost` is not null (float)
  - `current_energy` is not null (float — Tchebycheff energy at calibration)
  - `acceptance_history == [True]` (calibration acceptance is unconditional)

### Invariants
- [ ] `len(algorithm_state["trajectories"]) == 5` before and after `advance_step`
- [ ] No top-level `trajectories`, `temperature`, or `step_count` fields appear on the
      SearchState root — they live inside `algorithm_state`
- [ ] `algorithm_state["ideal_point"]` and `algorithm_state["nadir_point"]` are updated from
      the scored calibration candidates (not the placeholder `(1.0, 0.0)` / `(0.0, 1.0)`)
