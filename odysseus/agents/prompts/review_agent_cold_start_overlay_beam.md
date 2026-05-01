Extends `review_agent_cold_start_base_system.md`.
**Loop phase.** `review`, round == 1.
**K.** `beam_width`.
**Parent selection.** Set `parent_version = briefing.initial_parent_version` on every seed. Diversity must span confusion cells *and* cost regions — the beam uses crowding distance in later rounds.
