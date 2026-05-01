Extends `review_agent_cold_start_base_system.md`.
**Loop phase.** `review`, round == 1.
**K.** 1.
Note: with K=1, the base flow's "K diverse strategies" collapses to one strategy; emit a single `ChildVariant`.
**Parent selection.** Set `parent_version = briefing.initial_parent_version` on every seed.
