# Scenario: SMS-EMOA — Warm-Up Then Steady-State Iterations

## Setup
- Dataset: `tests/scenarios/data/sms_emoa_toy_dataset.jsonl`
- Backend: `mock-echo`
- Search parameters: `mu=4`, `evaluation_budget=8`
- Algorithm: `sms_emoa`
- System prompts: `odysseus_review_agent_warmup`, `odysseus_prompt_builder`, `odysseus_review_agent`
- MCP tools: `get_pipeline_status`, `get_search_state_tool`, `init_search_state_tool`,
  `register_candidate_tool`, `run_eval`, `record_eval_result_tool`, `signal_eval_complete_tool`,
  `advance_step_tool`, `build_review_briefing_tool`,
  `record_directive_outcomes_tool`, `run_batch_eval`

## Scenario Description

This scenario exercises the complete SMS-EMOA optimisation loop from an empty state through to
budget termination, covering:

1. **Warm-up phase**: The warm-up Review Agent (`odysseus_review_agent_warmup`) emits μ=4 diverse
   seed prompt directives in a single response. The Prompt Builder realises all four seeds via
   `register_candidate_tool` (round=0, no parents). Batch evaluation scores all four seeds.
   `advance_step_tool` is then called to consolidate the scored seeds into the initial
   population (`algorithm_state.warm_up_complete = True`).

2. **Steady-state iteration 1**: The iterative Review Agent (`odysseus_review_agent`) receives the
   review briefing showing two sampled parents (parent_a, parent_b) from the population, the
   current Pareto front shape, and the HV trend. It emits one child directive describing a
   recombination hypothesis. The Prompt Builder emits exactly one child candidate, which is
   evaluated. `advance_step_tool` is called to apply SMS-EMOA selection (μ+1 → μ).

3. **Steady-state iteration 2**: Same as iteration 1 — one child, one eval, one advance_step_tool call.

4. **Termination**: After warm-up uses 4 evaluations and 2 iterations use 2 more (total 6), the
   budget of 8 is not yet exhausted. A third or fourth iteration should cause `advance_step_tool`
   to return `terminated=True` with `termination_reason="budget"` when
   `algorithm_state.evaluations_used >= 8`.

The scenario validates:
- `state.algorithm_state["population"]` has exactly μ=4 entries after warm-up completes.
- `algorithm_state.warm_up_complete` flips to `True` after the warm-up `advance_step_tool` call.
- `|population| == 4` invariant holds after each steady-state `advance_step_tool` call.
- `algorithm_state.hypervolume_history` length grows by one per steady-state `advance_step_tool` call.
- `loop_phase` is `"review"` when `get_pipeline_status` surfaces `odysseus_review_agent` and
  `"build"` when it surfaces `odysseus_prompt_builder`.
- Termination fires with `termination_reason == "budget"` when `evaluations_used >= 8`.

## User Simulator

You are a test harness operator driving the SMS-EMOA optimisation loop in a minimal toy run.
You have full knowledge of the expected flow and will verify state after each tool call.

**Your knowledge:**
- The dataset is `tests/scenarios/data/sms_emoa_toy_dataset.jsonl` (20 examples, 3 tiers).
- The search is initialised with `algorithm="sms_emoa"`, `mu=4`, `evaluation_budget=8`,
  `backend="mock-echo"`.
- You know the SMS-EMOA loop: warm-up (μ seeds → batch eval → advance_step_tool) →
  steady-state (review → build → eval → advance_step_tool, repeat).

**Behaviour:**
1. Start by calling `get_pipeline_status` to confirm Stage 4 warm-up seed phase is active and
   `activate_prompt == "odysseus_review_agent_warmup"`.
2. After warm-up seeds are emitted, call `get_pipeline_status` again and confirm
   `activate_prompt == "odysseus_prompt_builder"` and the phase is `warmup_build`.
3. After batch eval completes, call `get_pipeline_status` and confirm phase is `warmup_reduce`.
4. Call `advance_step_tool`. Confirm `algorithm_state.warm_up_complete == True` and
   `len(algorithm_state.population) == 4`.
5. For each steady-state iteration, call `get_pipeline_status` and confirm `loop_phase` cycles
   `review → build → review` correctly. After each `advance_step_tool` call, read the
   result and confirm `population_size == 4` and `algorithm_state.hypervolume_history` grew.
6. Continue until `advance_step_tool` returns `terminated=True`.

**Opening message:** "Please initialise a new search state with `algorithm='sms_emoa'`, `mu=4`,
`evaluation_budget=8`, and `backend='mock-echo'`, then drive the SMS-EMOA warm-up phase. Dataset:
`tests/scenarios/data/sms_emoa_toy_dataset.jsonl`. After warm-up completes, run two steady-state
iterations and continue until the evaluation budget is exhausted."

## Verification Criteria

### Warm-Up Phase
- [ ] `get_pipeline_status` returns `activate_prompt: "odysseus_review_agent_warmup"` before any
      seeds are registered
- [ ] The warm-up Review Agent emits exactly 4 seed directives (μ=4) in its response
- [ ] After seeds are built and evaluated, `advance_step_tool` is called successfully
- [ ] After the warm-up `advance_step_tool`, `state.algorithm_state["warm_up_complete"] == True`
- [ ] After the warm-up `advance_step_tool`, `len(state.algorithm_state["population"]) == 4`
- [ ] `get_pipeline_status` transitions from `warmup_seed` → `warmup_build` → `warmup_reduce`
      as the warm-up progresses

### Steady-State Iterations
- [ ] After warm-up, `get_pipeline_status` returns `activate_prompt: "odysseus_review_agent"` with
      `loop_phase == "review"` (not `odysseus_review_agent_warmup` or any post-coldstart variant)
- [ ] The iterative Review Agent receives a briefing containing `parent_a` and `parent_b` fields
      (two distinct parents sampled from the population)
- [ ] The Prompt Builder emits exactly one child candidate per iteration (not a batch)
- [ ] `advance_step_tool` is called after each single-child evaluation
- [ ] After each steady-state `advance_step_tool` call, `len(state.algorithm_state["population"]) == 4`
- [ ] `len(state.algorithm_state["hypervolume_history"])` increases by 1 after each
      steady-state `advance_step_tool` call
- [ ] `loop_phase` is `"build"` when `get_pipeline_status` surfaces `odysseus_prompt_builder` and
      `"review"` when it surfaces `odysseus_review_agent`

### Termination
- [ ] `advance_step_tool` eventually returns `terminated=True`
- [ ] Termination `termination_reason == "budget"` when `evaluations_used >= 8`
- [ ] `state.algorithm_state["evaluations_used"] >= state.algorithm_state["evaluation_budget"]`
      at termination

### Invariants
- [ ] `len(state.algorithm_state["population"])` is always exactly `mu=4`
      (never grows beyond, never shrinks below)
- [ ] No top-level `population`, `warm_up_complete`, or `hypervolume_history` fields appear
      on the SearchState root — they live inside `algorithm_state`
