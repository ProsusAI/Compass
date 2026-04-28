# Iterative overlay — SMS-EMOA

Extends `review_agent_iterative_base_system.md`.

**Loop phase.** `review`, and `SearchState.warm_up_complete == True`. If `warm_up_complete == False`, stop — the warmup overlay is the correct prompt.
**Parent selection.** **Recombination.** Read `parent_a_version` and `parent_b_version` from the briefing (already chosen by the algorithm). Set both `parent_version = parent_a_version` and `secondary_parent_version = parent_b_version` on the child. The hypothesis (step 2) names what A and B each do that the recombination child should combine.
**Child count.** Exactly 1 (strict (μ+1) steady state).
**Binding axis.** The dimension along which A and B differ most; if they are close, pick the dimension that is farthest from the user target.
**Strategy-specific read.** `hypervolume_history` (last `stagnation_window` entries).
**Stagnation cue.** HV values within `reference_delta / 100` over `stagnation_window` → bias the hypothesis toward opening a new region of the front, not tightening one point.
