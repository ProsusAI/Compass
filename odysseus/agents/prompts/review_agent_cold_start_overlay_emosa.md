Extends `review_agent_cold_start_base_system.md`.
**Loop phase.** `calibration`.
**K.** number of trajectories.
**Parent selection.** initial compiled prompt, pinned per trajectory.
**Pinning.** Each of the K seeds is bound to one `trajectory_id` / `weight_vector`. Each seed's step-2 hypothesis must target that trajectory's weight-vector binding axis. Diversity across the K is partially guaranteed by the weight vectors themselves; still enforce pairwise distinctness.
