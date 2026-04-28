# Iterative overlay — hill-climb (main)

Extends `review_agent_iterative_base_system.md`.

**Loop phase.** `review`, round ≥ 2.
**Parent selection.** Single parent = elite with highest quality (tiebreak: lowest cost).
**Child count.** 1.

**Step-1 ranking of confusion cells.** You always pick from `confusion_analysis` — only the **ranking criterion** changes with progress against the user's thresholds:

- **Threshold NOT yet met.** Rank confusion cells by **threshold gap** — how much the cell's fix would reduce the distance between the parent's current metrics and the unmet user target(s). Pick the top-ranked cell.
- **Threshold met.** Rank confusion cells by **oracle gap** — read `oracle_cost_change` / `oracle_quality_change` per cell from `candidate_analysis`. The oracle represents the cheapest-correct routing; the gap is how much cost (or, more rarely, quality) the parent leaves on the table compared to the oracle on that cell. Pick the cell whose fix closes the largest oracle residual without regressing below the user threshold.

Same tool, same data source — the only thing that changes once the user's bar is cleared is which column of numbers you sort on.

**Strategy-specific read.** `SearchState.mutation_mode`:
  - `"targeted"`: pick the top-ranked cell under the current ranking.
  - `"exploratory"`: pick a cell the search has been ignoring under the current ranking (i.e. a lower-ranked-but-non-trivial cell), not a random one.
**Stagnation cue.** `stagnation_signal.count ≥ stagnation_limit - 1` → next round is the last chance in this mode; prefer a bolder hypothesis mechanism.
