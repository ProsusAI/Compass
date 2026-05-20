# EMOSA: Decomposition-Based Multi-Objective Simulated Annealing

This file is the source of truth for anyone touching the search engine. The algorithm is a clean adaptation of **EMOSA** (Li & Landa-Silva 2011) for LLM-driven prompt search: decomposition-based multi-objective SA with Tchebycheff scalarization, K parallel trajectories, per-trajectory Metropolis acceptance, EMOSA's neighborhood replacement, and a plain non-dominated archive. When reading or modifying `compass/agents/prompt_builder/annealing.py`, `search_ops.py`, `compass/agents/review/preprocessor.py`, or the Review Agent prompts, consult this document first.

---

## Algorithm at a glance

| Component | Technique | Primary reference |
|-----------|-----------|-------------------|
| Sub-problem decomposition | Tchebycheff scalarization with K weight vectors | Zhang & Li 2007 (MOEA/D); Li & Landa-Silva 2011 (EMOSA) |
| Per-sub-problem state | K parallel current-solutions with independent energies | Li & Landa-Silva 2011 |
| Acceptance criterion | Per-trajectory Metropolis on Tchebycheff energy delta | Kirkpatrick et al. 1983; Li & Landa-Silva 2011 |
| Neighborhood replacement | Every generated child (accepted or not) replaces any neighbor whose current is scalarized-worse; no Metropolis gate | Li & Landa-Silva 2011 |
| Archive | Plain non-dominated set; dominance filter only; no size limits | Li & Landa-Silva 2011 |
| Mutation operator | LLM Review Agent + Prompt Builder pipeline (per-sub-problem-aware) | This codebase |
| Convergence | Temperature floor, eval budget, Review Agent LoopSignal exit | — |

---

## Tchebycheff decomposition

The scalar energy for a solution `x` under weight vector `λ = (λ_q, λ_c)` is:

```
E(x; λ) = max(
    λ_q · norm_q(x),
    λ_c · norm_c(x)
)
```

where:
- `norm_q(x) = (nadir_q − quality(x)) / (nadir_q − ideal_q)` — 0 at the ideal, 1 at the nadir
- `norm_c(x) = (cost(x) − ideal_c) / (nadir_c − ideal_c)` — 0 at the ideal, 1 at the nadir
- `ideal_q`, `ideal_c` are the best quality and lowest cost seen across all evaluations
- `nadir_q`, `nadir_c` are the worst quality and highest cost seen

Energy `E = 0` is the ideal corner; higher is worse. A solution's **binding axis** is the index `i` where `λ_i × norm_i` is largest — the term that dominates the `max`. Equivalently:

```
binding_axis = argmax_i ( λ_i · (f_i − ideal_i) / (nadir_i − ideal_i) )
```

**Why Tchebycheff instead of weighted sum:** A weighted-sum scalarization `E = λ_q · g_q + λ_c · g_c` cannot produce solutions on concave regions of the Pareto front regardless of the weight choice. The Tchebycheff aggregation `E = max(λ_q · g_q, λ_c · g_c)` can reach any point on the Pareto front — convex or concave — by varying `λ`. This property is critical when the quality/cost tradeoff surface is not convex.

**Normalization:** `normalize_objectives` (in `annealing.py`) maps raw quality and cost into `[0, 1]` relative to `ideal_point` and `nadir_point`. After normalization, `norm_q = 0` means the candidate equals the best-ever quality; `norm_q = 1` means it equals the worst-ever quality. Cost is analogous.

**Concrete example:** Suppose `ideal = (0.90 quality, 0.02 cost)`, `nadir = (0.70, 0.10)`. A candidate with quality 0.80 and cost 0.06 gives `norm_q = (0.90 − 0.80)/(0.90 − 0.70) = 0.50`, `norm_c = (0.06 − 0.02)/(0.10 − 0.02) = 0.50`. For trajectory 0 (`λ = (0.9, 0.1)`): `E = max(0.9 × 0.50, 0.1 × 0.50) = max(0.45, 0.05) = 0.45`; binding axis = quality. For trajectory 4 (`λ = (0.1, 0.9)`): `E = max(0.1 × 0.50, 0.9 × 0.50) = max(0.05, 0.45) = 0.45`; binding axis = cost. For a cost-efficient candidate (quality 0.72, cost 0.03): `norm_q = 0.90`, `norm_c = 0.125`; trajectory 0 energy = `max(0.81, 0.013) = 0.81`; trajectory 4 energy = `max(0.09, 0.113) = 0.113`. Trajectory 4 sees it as much better.

**Implementation:** `compute_tchebycheff_energy` in `compass/agents/prompt_builder/annealing.py`. The function normalizes objectives via `normalize_objectives`, then applies the max aggregation using `ideal_point` and `nadir_point` from `AnnealingState`.

**Citations:** Zhang, Q. & Li, H. (2007). *MOEA/D*. IEEE TEC 11(6):712–731. Li, H. & Landa-Silva, D. (2011). *EMOSA*. Evolutionary Computation 19(4):561–595.

---

## Weight vectors and trajectories

`compute_weight_vectors(num_trajectories)` in `annealing.py` generates K evenly-spaced weight vectors spanning `λ_q ∈ [0.1, 0.9]` with `λ_c = 1 − λ_q`. Quality-focused trajectories (`λ_q` close to 0.9) are listed first. For `num_trajectories = 1`, the single vector is `(0.5, 0.5)`; for `num_trajectories = 2`, vectors are `(0.9, 0.1)` and `(0.1, 0.9)`.

For the default `num_trajectories = 5`, the generated weight vectors are:

| Trajectory ID | λ_q | λ_c | Sub-problem emphasis |
|---------------|-----|-----|----------------------|
| 0 | 0.9 | 0.1 | Heavy quality focus |
| 1 | 0.7 | 0.3 | Quality-leaning |
| 2 | 0.5 | 0.5 | Balanced (knee region) |
| 3 | 0.3 | 0.7 | Cost-leaning |
| 4 | 0.1 | 0.9 | Heavy cost focus |

Each trajectory maintains its own `current_solution` (the `prompt_version` of the candidate it currently holds) and `current_energy` (the Tchebycheff energy of that candidate under its weight vector). These are stored in `TrajectoryState` inside `AnnealingState`. This design runs K independent SA chains in parallel, one per sub-problem — characteristic of EMOSA and MOEA/D extended with per-sub-problem SA.

The `acceptance_history` field in `TrajectoryState` records the last 5 accept/reject decisions for that trajectory, enabling the Review Agent to detect when a trajectory is stuck (consistently rejecting moves).

The number of trajectories (`num_trajectories`) is configured in `init_annealing_state` (called by `init_search_state_tool`). The default is 5; higher values increase Pareto front coverage at the cost of more evaluations per round.

---

## Per-sub-problem SA acceptance

Each trajectory applies the standard SA acceptance rule to its own Tchebycheff energy:

```
if Δ_E ≤ 0:
    accept  # improvement always accepted
else:
    accept with probability exp(−Δ_E / T)
```

**Implementation:** `metropolis_accept(delta_e, temperature)` in `annealing.py`. Applied inside `_advance_emosa_search` in `search_ops.py` for each trajectory independently against that trajectory's own `temperature`. When a trajectory generates M children (`children_per_trajectory > 1`), the acceptance rule is applied to each child separately and the accepted child with the lowest energy is kept ("Metropolis-then-best-of-accepted" semantics).

**Per-trajectory adaptive cooling:** each trajectory holds its own `temperature` and `alpha` on `TrajectoryState`. After Metropolis (and neighborhood replacement) each round, every trajectory that attempted a step adjusts its temperature via `adaptive_cool` based on its recent acceptance rate against a target band:

- if rate > `target_acceptance_high` (default 0.6) → `T ← T × α^cooling_exp_fast` (cool faster, default exp 1.5)
- if rate < `target_acceptance_low` (default 0.4) → `T ← T × α^cooling_exp_slow` (cool slower, default exp 0.5)
- otherwise → `T ← T × α` (default geometric step)

`α` is fixed per trajectory at calibration via `compute_cooling_rate(t_initial, t_min, max_steps)`. The adaptive rule modifies the *exponent* applied each round, not `α` itself. This matches Li & Landa-Silva 2011 §3.4. Convergence on `temperature_floor` requires ALL trajectories to be below `t_min`.

**Default `t_initial = 0.2`**: chosen so that for the empirically observed median worsening Δ_E ≈ 0.07 (across the run at `outputs/d92011e7/`), P(accept) at the start of search is ≈ 0.7 — exploration without random-walk. The previous default of 1.0 left SA in random-walk regime for the first 60% of the budget, with acceptance histories of 5/5 True confirming the gate did nothing useful.

**Citations:**
- Kirkpatrick, S., Gelatt, C. D. & Vecchi, M. P. (1983). *Optimization by simulated annealing*. Science, 220(4598):671–680.
- Li, H. & Landa-Silva, D. (2011). *EMOSA*. Evolutionary Computation 19(4):561–595.

---

## Neighborhood replacement

Every generated child is offered to its originating trajectory's neighborhood, regardless of whether the originating trajectory's Metropolis accepted it. The originators themselves are excluded from the replacement target set — Metropolis owns that decision. For each neighbor trajectory `j` (in `B(i)` and not in the originating set):

```
if compute_tchebycheff_energy(child, λ_j) < neighbor_j.current_energy:
    neighbor_j.current_solution ← child
    neighbor_j.current_energy   ← energy under λ_j
```

This replacement is **unconditional** — there is no Metropolis random gate on the neighbor step. If the child is better than the neighbor's current under the neighbor's weight, the neighbor adopts it. This is the core EMOSA mechanism that prevents over-specialization: a child generated for one sub-problem can strengthen adjacent sub-problems without any explicit cross-trajectory logic in the Review Agent. Critically, this includes children that the originating trajectory's Metropolis rejected — they are still offered to neighbors, matching the canonical algorithm.

**Default:** B = 4 for K = 5 (each trajectory sees every other trajectory's accepted children). B is a config field in `AnnealingState`.

**Citations:** Li & Landa-Silva 2011 (EMOSA neighborhood replacement); Zhang & Li 2007 (MOEA/D neighborhood structure as precedent).

---

## External archive

The global non-dominated archive (`elite_set` in `SearchState`) accumulates Pareto-optimal candidates across all trajectories. Archive management is a plain dominance filter:

- **Dominance filter:** `update_archive` in `annealing.py` rejects any new candidate dominated by an existing archive member and removes existing members dominated by the new candidate.
- **No size limits:** the archive grows monotonically, bounded only by the total evaluation budget. There is no soft limit, no hard limit, and no pruning step.

The archive is shared across all trajectories: any trajectory can add a Pareto-improving candidate regardless of which trajectory generated it.

**Citation:** Li & Landa-Silva 2011.

---

## Ideal and nadir point updates

The Tchebycheff normalization depends on `ideal_point` and `nadir_point`. These are updated incrementally in `_advance_emosa_search`: after collecting scored candidates, the ideal and nadir are expanded to include any new extremes discovered this round. The ideal point never regresses (quality only increases, cost only decreases); the nadir can expand in either direction.

This incremental update means early rounds operate with a narrow reference interval (small difference between ideal and nadir), which compresses the energy values toward zero. As more of the tradeoff surface is explored, the normalization spreads out and energy differences become more informative.

To keep the Metropolis Δ_E comparison range-consistent, each trajectory caches the raw `(current_quality, current_cost)` of its `current_solution`. At the top of `advance_round`, after the new ideal/nadir are computed, every trajectory's `current_energy` is **recomputed** under the new normalization before the Metropolis gate runs. Without this refresh, stored energies from rounds with narrower normalization are systematically lower than newly-computed energies under expanded normalization — the Metropolis Δ_E is positive even when the child strictly dominates under the current weight, biasing the gate toward keeping the held current and stranding trajectories on early picks.

---

## Initial seeding / Calibration phase

Before the main search loop begins, the algorithm runs a **calibration phase** to seed each trajectory with an initial current solution and energy.

**Steps (`calibration_complete` in `search_ops.py`):**
1. The Review Agent cold-start produces K diverse hypotheses (one per trajectory) without axis pre-commitment. See `review_agent_cold_start_system.md`.
2. The Prompt Builder compiles and evaluates one candidate per hypothesis.
3. The ideal and nadir points are initialized from the calibration candidates: `ideal_q = max quality seen`, `ideal_c = min cost seen`, `nadir_q = min quality seen`, `nadir_c = max cost seen`.
4. Each trajectory's `current_solution` and `current_energy` are seeded 1:1 in generation order: variant 0 → trajectory 0, variant 1 → trajectory 1, and so on. The assignment is arbitrary by design.
5. The archive is initialized with all non-dominated calibration candidates.
6. `AnnealingState.phase` transitions from `"calibration"` to `"search"`.

**Alignment via neighborhood replacement:** The initial 1:1 assignment makes no attempt to match hypotheses to weight-vector axes. Alignment between each trajectory's current solution and its weight vector emerges naturally during the first several rounds via neighborhood replacement — trajectories that receive a well-aligned child quickly converge on it; misaligned starting seeds are superseded. This is consistent with EMOSA's design and is not a defect.

The calibration phase corresponds to what the cold-start prompt calls "round 0". The `amosa_calibration_step_tool` wraps `calibration_complete` for MCP-level invocation.

---

## LLM Review Agent as mutation operator

EMOSA is operator-agnostic: it specifies the acceptance criterion and neighborhood replacement, but not how candidate mutations are generated. In this codebase, the Review Agent + Prompt Builder pipeline realizes the per-sub-problem-aware mutation slot. Each round, the Review Agent for trajectory `i` proposes directives targeted at reducing the term dominating the Tchebycheff max on that trajectory's binding axis — a semantically richer mutation than random perturbation. The Prompt Builder compiles the directives into a concrete candidate prompt for evaluation.

Neighborhood replacement prevents over-specialization: a strong cross-axis child generated under one trajectory's mandate can propagate to neighboring trajectories if it scalarizes better there. The Review Agent does not need to anticipate this; it focuses on its own trajectory's binding axis.

---

## Convergence

The search converges when any of the following conditions is met:

| Condition | `convergence_reason` value |
|-----------|---------------------------|
| Temperature falls below `t_min` | `"temperature_floor"` |
| `total_evals >= max_evals` | `"eval_budget"` |
| Review Agent emits `LoopSignal(action="exit")` | `"review_exit"` |

All convergence checks happen inside `advance_round`. The round summary's `converged` field is `True` on the terminal round; `AnnealingState.phase` transitions to `"converged"`. The Prompt Builder Agent reads phase to decide whether to call `advance_round_tool` again or close out the run.

---

## Pointers for future changes

- **Changing the scalarization** (e.g., to PBI — Penalty-Boundary Intersection, per Zhang & Li 2007): edit `compute_tchebycheff_energy` in `compass/agents/prompt_builder/annealing.py` and update the "Tchebycheff decomposition" section above. PBI is a natural next extension; EMOSA's original paper discusses it as an alternative.
- **Adding an axis** (e.g., latency): update `classify_user_target` in `preprocessor.py`, add weight-vector logic in `compute_weight_vectors`, extend `compute_tchebycheff_energy` to K-objective form, and extend this document's "Tchebycheff decomposition" and "Weight vectors and trajectories" sections.
- **Changing neighborhood size B**: edit the `neighborhood_size` field in `AnnealingState` (default 4, set when constructing the `algorithm_state` pocket on `init_search_state`) and update the "Neighborhood replacement" section above.
- **Changing archive behavior** (e.g., adding crowding-distance-based pruning if archive grows too large): edit `update_archive` in `annealing.py` and update the "External archive" section above.
- **Changing convergence detection**: edit the convergence checks in `_advance_emosa_search` in `search_ops.py` and update the "Convergence" section above.
- **Tuning the adaptive cooling band**: adjust `target_acceptance_low`/`target_acceptance_high`/`cooling_exp_fast`/`cooling_exp_slow` defaults on `AnnealingState` in `annealing.py`. The defaults (0.4 / 0.6 / 1.5 / 0.5) follow Li & Landa-Silva 2011 §3.4. Lower bands push trajectories to cool faster overall.

---

## References

Kirkpatrick, S., Gelatt, C. D. & Vecchi, M. P. (1983). Optimization by simulated annealing. *Science*, 220(4598):671–680.

Li, H. & Landa-Silva, D. (2011). An adaptive evolutionary multi-objective approach based on simulated annealing. *Evolutionary Computation*, 19(4):561–595. *(Primary reference — EMOSA.)*

Zhang, Q. & Li, H. (2007). MOEA/D: A multiobjective evolutionary algorithm based on decomposition. *IEEE Transactions on Evolutionary Computation*, 11(6):712–731. *(Tchebycheff decomposition and neighborhood structure.)*
