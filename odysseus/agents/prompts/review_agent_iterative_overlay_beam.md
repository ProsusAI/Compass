# Iterative overlay — parallel beam

Extends `review_agent_iterative_base_system.md`.

**Loop phase.** `review`, round ≥ 2.
**Total child count per round.** `beam_width` (read from `briefing.beam_width`).

**Round 2 — diversity sweep.** Parent allocation is fixed: emit **exactly one child per round-1 elite**. With `beam_width = 3` and 3 round-1 elites, that is 3 children, one each. This guarantees every initial elite gets at least one round-2 descendant before the beam contracts.

**Round ≥ 3 — agent-chosen allocation.** Emit `beam_width` children total, distributed across 1, 2, or 3 elites at your discretion. Spend the budget on whichever elite-set members **look most promising for reaching the user's threshold** — or, once the threshold is met, **for moving past the oracle point**. Allocation modes:

- **Concentrate** (3 from 1): one elite looks clearly most promising toward the threshold (or oracle, post-threshold).
- **Split** (2 + 1): two elites look comparably promising; give the stronger one two children.
- **Spread** (1 + 1 + 1): several elites look promising and you want a child from each.

Use judgement — these are not rigid rules.

**Step-1 ranking of confusion cells.** Same two-phase pattern as hill-climb; the ranking criterion changes with progress against the user's thresholds:

- **Threshold NOT yet met.** Rank confusion cells by **threshold gap** against the selected parent. Pick the top-ranked cell.
- **Threshold met.** Rank by **oracle gap** — `oracle_cost_change` / `oracle_quality_change` per cell. Pick the cell whose fix closes the largest oracle residual without regressing below the threshold.

When emitting multiple children from one parent, target **different** confusion cells (top-N from the same ranked list) — never duplicate cells within one parent.

**Strategy-specific read.** `beam_rank`, `crowding_distance` per elite; `stagnation_signal.hypervolume_delta`; `beam_width`.
**Stagnation cue.** `stagnation_signal.hypervolume_delta < backtrack_threshold` → the current line of attack has stalled; reconsider which elite(s) look most promising and pick a different confusion cell (lower on the threshold-gap or oracle-gap ranked list).
