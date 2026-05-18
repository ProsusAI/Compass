# Scenario: EMOSA — Steady-State Round (K=5 Trajectory Fanout)

## Setup
- Dataset: `tests/scenarios/data/emosa_toy_dataset.jsonl`
- Backend: `mock-echo`
- Search parameters: `num_trajectories=5`, `max_evals=50`
- Algorithm: `emosa`
- Pre-seeded `search_state.json`: `phase="search"`, `step_count=1`, K=5 trajectories with
  `current_solution` populated (`v_seed_0` through `v_seed_4`), `loop_phase="review"`,
  `temperature=0.95` (cooled once: `T_initial=1.0 * alpha^1`).
- System prompts: `odysseus_review_agent`, `odysseus_prompt_builder`
- MCP tools: `get_pipeline_status`, `get_search_state`, `build_review_briefing`,
  `register_candidate`, `run_batch_eval`, `advance_step`,
  `save_trajectory_child_variants_tool`, `record_directive_outcomes`

## Scenario Description

This scenario exercises one full EMOSA steady-state round starting from a post-calibration
state where all K=5 trajectories are seeded. It covers:

1. **Per-fork review (K=5)**: The pipeline dispatches five parallel Review Agent calls, one
   per trajectory. Each call invokes `build_review_briefing` with `trajectory_id=t`
   (0–4), so each agent receives the `weight_vector`, `binding_axis`, and `acceptance_history`
   specific to its sub-problem slot. Each Review Agent emits exactly one child directive
   targeting its seed solution.

2. **Build (K=5)**: The Prompt Builder registers one child candidate per trajectory via
   `register_candidate`, producing `v_child_0` through `v_child_4` with
   `parent_version=v_seed_t`.

3. **Batch evaluation**: `run_batch_eval` scores all 5 children concurrently.

4. **Advance step**: `advance_step` processes the scored children through the full
   steady-state loop:
   - Drift-cache refresh: recomputes current trajectory energies against updated ideal/nadir.
   - Per-trajectory Metropolis acceptance: each child is tested against its parent's energy
     under Tchebycheff with the trajectory's weight vector and updated ideal/nadir.
   - Neighborhood replacement: accepted solutions propagate to B=4 nearest neighbors.
   - Archive update and hypervolume computation.
   - Temperature cooling: `new_T = 0.95 * 0.95 = 0.9025`.
   - `step_count` increments to 2.
   - `total_evals` becomes 10.

The scenario validates:
- Each of the 5 Review Agent calls receives trajectory-specific EMOSA fields.
- All 5 children are built and evaluated.
- After `advance_step`, `step_count == 2` and `temperature ≈ T_initial * alpha^2 = 0.9025`.
- At least one trajectory has a non-empty `acceptance_history` with ≥ 2 entries.
- No `NotImplementedError` is raised.
- Archive size is unchanged or grew.

## User Simulator

You are a test harness operator driving one full EMOSA steady-state round with K=5 trajectory
fanout. You have complete knowledge of the expected flow and pre-seeded state.

**Your knowledge:**
- The run has `search_state_id="emosa_steady_state"` (or use the active run_id).
- Post-calibration state: K=5 trajectories seeded with `v_seed_0`–`v_seed_4`.
  `step_count=1`, `temperature=0.95`, `phase="search"`, `loop_phase="review"`.
- Weight vectors: `[(0.9, 0.1), (0.7, 0.3), (0.5, 0.5), (0.3, 0.7), (0.1, 0.9)]`.
- Expected flow:
  1. `get_pipeline_status` → confirms `loop_phase="review"`, EMOSA phase, K=5 pending forks.
  2. For each `t in [0, 1, 2, 3, 4]`:
     a. `build_review_briefing(run_id=..., trajectory_id=t)` — per-fork briefing.
     b. Review Agent (or inline) emits one child directive targeting `v_seed_t`.
     c. `register_candidate` registers `v_child_t` with `parent_version=v_seed_t`.
  3. `run_batch_eval` evaluates all 5 children.
  4. `advance_step` advances state; verify `step_count=2`, `temperature≈0.9025`.

**Behaviour:**
1. Call `get_pipeline_status` to confirm `loop_phase="review"` and `algorithm="emosa"`.
2. For trajectories 0 through 4 in order:
   a. Call `build_review_briefing` with `trajectory_id=<t>`.
   b. Confirm the returned briefing has `trajectory_id == t` and non-null `weight_vector`.
   c. Register one child candidate with `parent_version=v_seed_<t>` via `register_candidate`.
3. Call `run_batch_eval` to score all 5 children.
4. Call `advance_step`. Verify the result shows:
   - `algorithm_state.step_count == 2`
   - `algorithm_state.temperature ≈ 0.9025` (within 0.001)
   - No `NotImplementedError`
5. Call `get_search_state` and verify each trajectory has `acceptance_history` with
   at least one entry from the steady-state round (total length ≥ 2).
6. Confirm archive size is ≥ 1 (held or grew).

**Opening message:** "Please load the pre-seeded EMOSA run with `algorithm='emosa'`,
`num_trajectories=5`, `step_count=1`, `temperature=0.95`, and drive one full steady-state
round. Dataset: `tests/scenarios/data/emosa_toy_dataset.jsonl`. For each trajectory 0–4,
call `build_review_briefing` with `trajectory_id=<t>` and confirm it returns
trajectory-specific fields. After building and evaluating all 5 children, call
`advance_step` and verify `step_count` increments to 2 and `temperature ≈ 0.9025`."

## Verification Criteria

### Pre-round State
- [ ] `get_pipeline_status` returns `loop_phase="review"` and `algorithm="emosa"` before any
      child candidates are registered
- [ ] `algorithm_state.step_count == 1` at the start of the round
- [ ] `algorithm_state.temperature == 0.95` at the start of the round (post-calibration cool)
- [ ] All 5 trajectories in `algorithm_state.trajectories` have non-null `current_solution`

### Per-Fork Review (K=5 Briefings)
- [ ] `build_review_briefing` is called 5 times, once with `trajectory_id=0`, once with
      `trajectory_id=1`, once with `trajectory_id=2`, once with `trajectory_id=3`, and once
      with `trajectory_id=4`
- [ ] Each returned briefing JSON has `trajectory_id` equal to the requested value (0–4)
- [ ] Each returned briefing has a non-null `weight_vector` matching the trajectory's configured
      weight vector
- [ ] Each returned briefing has a non-null `stagnation_signal` with `temperature` and
      `review_exit` keys
- [ ] No `NotImplementedError` is raised during any `build_review_briefing` call

### Build and Eval
- [ ] Exactly 5 child candidates are registered (one per trajectory, `parent_version=v_seed_<t>`)
- [ ] `run_batch_eval` evaluates all 5 children and returns 5 scored results
- [ ] No `advance_step` call is made before all 5 children are scored

### Advance Step — Steady-State Update
- [ ] `advance_step` is called exactly once after all 5 children are scored
- [ ] After `advance_step`, `algorithm_state["step_count"] == 2`
- [ ] After `advance_step`, `algorithm_state["temperature"]` is within 0.001 of
      `T_initial * alpha^2 = 1.0 * 0.95^2 = 0.9025`
- [ ] After `advance_step`, `algorithm_state["total_evals"] == 10`
- [ ] After `advance_step`, `algorithm_state["phase"] == "search"` (not converged yet)
- [ ] No `NotImplementedError` raised during `advance_step`

### Per-Trajectory Post-Round State
- [ ] Each of the 5 entries in `algorithm_state["trajectories"]` has `acceptance_history`
      with at least 2 entries (calibration True + at least one steady-state decision)
- [ ] At least one trajectory's `acceptance_history` last entry is `True` (some acceptance
      occurred — mock-echo backend generates reproducible scores that admit improvement)
- [ ] Each trajectory's `current_solution` is either unchanged (rejection) or updated to the
      child candidate version (acceptance)

### Archive and Invariants
- [ ] `len(algorithm_state["trajectories"]) == 5` throughout the round
- [ ] Elite set (archive) size is ≥ 1 after `advance_step`
- [ ] `algorithm_state["ideal_point"]` and `algorithm_state["nadir_point"]` are present
      (may be updated if children improved upon seed scores)
- [ ] Top-level `loop_phase` after `advance_step` is `"review"` (next round ready)
