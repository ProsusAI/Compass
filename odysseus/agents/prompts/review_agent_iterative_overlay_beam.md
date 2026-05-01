# Iterative overlay — parallel beam

Extends `review_agent_iterative_base_system.md`.

**Loop phase.** `review`, round ≥ 2.
**Parent selection.** Single parent. Prefer isolated elites (high `crowding_distance`) when `stagnation_signal.hypervolume_delta` is below `backtrack_threshold`; otherwise prefer the highest-quality elite.
**Child count.** 1.

**Step-1 ranking of confusion cells.** Same two-phase pattern as hill-climb — the only thing that changes with progress against the user's thresholds is the ranking criterion:

- **Threshold NOT yet met.** Rank confusion cells by **threshold gap** against the selected parent. Pick the top-ranked cell.
- **Threshold met.** Rank confusion cells by **oracle gap** — read `oracle_cost_change` / `oracle_quality_change` per cell from `candidate_analysis`. Pick the cell whose fix closes the largest oracle residual without regressing below the user threshold.

**Strategy-specific read.** `beam_rank`, `crowding_distance` per elite; `stagnation_signal.hypervolume_delta`.
**Stagnation cue.** `stagnation_signal.hypervolume_delta < backtrack_threshold` → the bundle should revisit a cell the beam stopped exploring (picked under whichever ranking applies — threshold-gap or oracle-gap — but from lower down the ranked list).
