# Cross-Branch Pipeline Reconciliation — Remaining Work

## Status (2026-04-28)

The cross-branch generalization is **6 of 7 increments complete**. Increments 1–6 — unifying `Candidate`, `SearchState`+`RoundSummary`, the Stage 4 MCP tool surface, `ReviewBriefing`, pipeline guards, and Review Agent prompts (three-tier base + overlays) — are committed on `feat/generalize-pipeline` (published) and produce the canonical shared scaffolding. The original Increment 7 ("per-strategy residuals") was scoped as three small per-branch ports.

A 2026-04-28 audit of the actual feature branches changed the picture:

| Branch | Commits since baseline `bb7b258` | Files | Lines | G | S | D | R |
|---|---|---|---|---|---|---|---|
| `feature/parallel-beam-search` | ~181 (incl. shared ancestry) | 128 | +21k/-3k | 47 | 47 | 25 | 7 |
| `feature/sms-emoa` | 203 | 162 | +24k/-4k | 56 | 12 | 55 | 80 |
| `feature/emosa` | 187 | 122 | +23k/-3k | 80 | 9 (+6 AMOSA-baseline) | 64 | 28 |

G = general-purpose improvement (lands on main). S = strategy-specific. D = defunct, subsumed by Increments 1–6 — drop. R = cross-cutting, manual review per commit.

A pure strategy-only port would discard months of G work. The revised plan is **Option 2 — reconcile-then-port**, split across multiple sessions.

---

## Cross-branch shared topics (the bulk of G)

Most G work appears on multiple branches with parallel evolution. Pick one canonical version per topic; ship one PR each.

| Topic | parallel-beam (rep. SHAs) | sms-emoa (rep. SHAs) | emosa (rep. SHAs) | Recommended canonical | Approx LOC |
|---|---|---|---|---|---|
| Search-tree visualization (round slider, oracle bounds, route labels, refresh protocol, dark mode) | `9081815`, `f584f10` | `a7224c7`, `df4dc12`, `83ff12a`, `ae45589`, `e753e87`, `2fbd2fd`, `9081815` | `df4dc12`, `a7224c7`, `7282e6c`, `35008bb`, `e79b0c6` | sms-emoa or emosa (most evolved) | 800–2,200 |
| Batch eval / concurrent evaluation / progressive screening / eval_status filtering | (yes) | `aae3550`, `27f8852`, `e433896`, `919741f`, `f0184c2`, `5c94e0c`, `2b8c9ef`, `3bc0941` | `3dde351`, `aae3550`, `f1627c2`, `f106645`, `74ba14b`, `919741f`, `ee8d238`, `169c1b7` | sms-emoa | 600–1,500 |
| Oracle metrics + ceiling capture + scatter bounds | `7379488` | `7379488`, `210bdf5`, `8642f88`, `3f681a0`, `38d0009` | `3f681a0`, `8642f88`, `593b9b2`, `6a9e38e`, `df5b6c5`, `d3520ca`, `31210c6` | emosa | 300–700 |
| Confusion analysis + contrast pairs + signal-to-noise filters + cell-exhaustion tracking | (yes) | `d21e3d0`, `daeb969`, `17415fa`, `a569d54`, `7608cac`, `adf651c`, `0e27514`, `cbbeba4` | `d21e3d0`, `daeb969`, `adf651c`, `7608cac`, `17415fa`, `cbbeba4` | sms-emoa or emosa | 700–1,200 |
| Route validation / canonical normalization / wildcard / severity escalation | `4e4579d` | `433aaee`, `a1d1fd9`, `0338ffa`, `ecddefc`, `4e4579d` | `433aaee`, `4e4579d`, `b8018c1`, `a1d1fd9`, `279187a`, `599e1aa` | sms-emoa | 250–500 |
| Project-dir cache fix + metrics consolidation + run-specific prompt directories | `d354cdd`, `089ff41` | `d354cdd`, `6a9e38e`, `df5b6c5`, `1182b89`, `4f5c891`, `089ff41` | `1182b89`, `4f5c891`, `cdab117`, `24b42db`, `089ff41` | sms-emoa | 200–400 |
| Tooling: `query_misrouted_examples`, pagination, MCP cleanup | (yes) | `cdab117`, `2df60ae`, `764811b`, `856a85a` | (yes) | parallel-beam | ~500 |
| Cold-start prompt tightening / shallow-hypothesis rejection / target-driven scaffold | `8895b78`, `7cefacf`, `d41f2fd` | `eb10d13`, `fec025a`, `7c1c286`, `8895b78`, `7cefacf` | `2b8c9ef`, `3bc0941`, `2eaed8a`, `fde2c85`, `e3b3aa7`, `d5416f3`, `3f7fe50`, `d41f2fd`, `531d2d1`, `300b11f`, `51b3ca3`, `b07589e`, `1a9d11f`, `18b0a92`, `856a85a`, `4682749`, `210bdf5`, `a24d339` | emosa (most evolved) | 1,000–1,800 |
| Pipeline guards / dispatch markers / recovery phase | `e1da9b8`, `abcee7d`, `e9ae68d` | `91dfdbc`, `49f0bb7`, `4d58894`, `fe730bc`, `be2fd58` | `a52fa8e`, `08d4fda`, `d9ea800`, `27f8852`, `859010a`, `bd79c9e` | most are **D** (Increment 5 covers); small residual TBD | small |
| Review tool surface + child variants + secondary parent + preference resolution | (overlap) | `3c8cfb5`, `02019cd`, `f6a9712`, `41a3b98`, `fd69dca`, `41238fd`, `6f37cce` | `f54b92b`, `336433c`, `33ddf0e`, `febb931`, `41238fd`, `d1b9ba2`, `1f06f95` | mostly **D** (Increments 1, 4 cover); small residual | small |
| Documentation sync (architecture, search-strategy.md, narrative docs, design specs) | `2936fbb` | `e07eb3e`, `2936fbb`, `b8d9fc3`, `d121b73`, `106a9d2` | (yes) | merge across branches | ~500 |

## Per-branch unique G work

- **parallel-beam unique**: cold-start elite floor (`5e8fc0e`), beam-specific test infra. ~1 session.
- **sms-emoa unique**: warmup-specific test fixtures and helpers. ~0.5 session.
- **emosa unique**: small preprocessor pieces that bleed into S (handle in Phase C). ~0 sessions.

## Strategy-only residuals (Phase C)

After Phases A and B land, each feature branch's residual collapses to:

**parallel-beam** (~1 session)
- Files: `odysseus/agents/prompt_builder/search.py` (Pareto + crowding + HV + `prune_to_size` + `compute_pareto_front` + `update_elite_set`), `search_ops.py` (`advance_round` body with epsilon tightening, stagnation, cold-start floor)
- `algorithm_state` pocket: `beam_width`, `hypervolume`, `reference_point`, `epsilon_min`, `backtrack_threshold`
- Dispatcher: `_advance_beam` arm in `advance_step_tool`
- Preprocessor: populate `beam_rank`, `crowding_distance`, `hypervolume`, `reference_point`, and `stagnation_signal = {"hypervolume_delta", "backtrack_threshold"}`

**sms-emoa** (~1 session)
- Files: `odysseus/agents/prompt_builder/search.py` (`fast_non_dominated_sort`, `dynamic_reference_point`, `exclusive_hypervolume_contribution`, `reduce_population`), `search_ops.py` (`reduce_iteration`, `advance_warmup_batch`, termination)
- `algorithm_state` pocket: `mu`, `population`, `hypervolume_history`, `iteration`, `warm_up_complete`, `evaluation_budget`, `evaluations_used`, `reference_delta`, `stagnation_window`, `reference_point`
- Dispatcher: `_advance_sms_emoa` arm with two sub-arms (warmup vs steady-state); recognises `loop_phase ∈ {"warmup_seed", "warmup_build", "warmup_reduce", "review", "build"}`
- Preprocessor: populate `parent_a_version`, `parent_b_version`, and `stagnation_signal = {"hypervolume_history", "stagnation_window"}`
- SHAs to study for the algorithm port: `72eaf6e`, `a55f91d`, `e07eb3e`, `647e4ae`, `3c8cfb5`, `6aa6c69`, `022b811`, `91dfdbc`

**emosa** (~1.5 sessions)
- Files: `odysseus/agents/prompt_builder/annealing.py` (TrajectoryState, AnnealingState, `compute_tchebycheff_energy`, `compute_weight_vectors`, `normalize_objectives`, `metropolis_accept`, `compute_neighborhood`, `update_archive`); `search_ops.py` `advance_round` body with calibration handler
- Three EMOSA-specific commits to keep (the rest is AMOSA-baseline subsumed):
  - `c19ed6a` EMOSA refactor (Tchebycheff from ideal/nadir, plain archive, neighborhood replacement)
  - `9129f1f` ASF against per-trajectory reference points
  - `a15b608` recompute trajectory `current_energy` on ideal/nadir drift; `B = 4`
- `algorithm_state` pocket: `temperature`, `t_initial`, `t_min`, `alpha`, `num_trajectories`, `children_per_trajectory`, `trajectories: list[TrajectoryState]`, `ideal_point`, `nadir_point`, `neighborhood_size`, `phase`, `step_count`, `total_evals`, `max_evals`, `convergence_limit`, `epsilon`
- Dispatcher: `_advance_emosa` arm; calibration phase handler; **override `review_fanout_status`** with K-way per-trajectory fanout (the existing single-slot default in `odysseus/agents/pipeline/dispatch.py:review_fanout_status` is the override point)
- Preprocessor: populate `trajectory_id`, `weight_vector`, `binding_axis` (computed `argmax_i (λ_i · norm_i)`), `acceptance_history`, `stagnation_signal = {"temperature", "t_min", "review_exit"}`

## Defunct (drop, do not port)

Anything subsumed by Increments 1–6: `secondary_parent_version` on Candidate, `elite_set` rename, `RoundSummary` field renames, `ReviewBriefing` optional fields, build/review dispatch markers, three-tier review prompts, `advance_round_tool` → `advance_step_tool` rename. Specific D SHAs are catalogued in the per-branch triage reports (parallel-beam: 25, sms-emoa: 55, emosa: 64).

## Cross-cutting / R commits (manual decision per commit)

Not enumerable in advance. Triage them at the start of the relevant session — most resolve to G or S after a 1-minute read.

---

## Progress tracker (~15 sessions, 30–45h spread across whatever cadence suits)

Tick each session as you complete it. The first session must be **S0** (commit this plan to the branch); after that, Phase A sessions are independent and can run in any order, while Phase B → C → D must be sequential.

When a session completes, update its row with: `[x]` instead of `[ ]`, the commit SHA(s) it produced on `feat/generalize-pipeline`, and a one-line note if anything deviates from the plan. Keep the plan file in sync on the branch (amend the relevant tracking commit or push a fresh "progress: ..." commit).

### Phase 0 — Setup

- [ ] **S0** — Commit this plan to `feat/generalize-pipeline` at `docs/superpowers/plans/2026-04-28-reconcile-feature-branches.md`. Use the Haiku-subagent commit workflow. *(must run before any other session)*

### Phase A — Cross-branch G to main (8 sessions, any order after S0)

- [ ] **A1** — Search-tree visualization. Land canonical viz (recommended: sms-emoa or emosa). Verify viz renders in scenario tests.
- [ ] **A2** — Batch eval + concurrent evaluation. Add `run_batch_eval` MCP tool, progressive screening, eval_status filtering. Verify scenarios; new `test_batch_eval` covers screening.
- [ ] **A3** — Oracle metrics + ceiling capture. `OracleMetrics`, `oracle_quality_captured` fallback, scatter ceiling translation. Verify briefing carries oracle data on hill-climb.
- [x] **A4a** — Confusion analysis foundations: data models, preprocessor, briefing wiring. Ported `d21e3d0` + `daeb969` as `ec2a7fe` (add `ConfusionImpact`, `ContrastPairContent`, extend `EditDirective.block_type` literal with `contrast_pair`, add `ReviewBriefing.confusion_analysis`); `17415fa` as `299c31d` with **dedup-by-`example_id` extension** so `build_confusion_analysis` accepts results from N candidates without inflating per-cell counts (param renamed `best_candidate_results` → `eval_results`); `a569d54` + `7608cac` as `2bb6d09` with **strategy-owned selector lift**: `_select_confusion_candidates(state)` defaults to `[c.prompt_version for c in state.elite_set]` — no primary-metric fallback, strategies own confusion candidates via the elite_set contract (Increment 2). Briefing now carries populated `confusion_analysis` end-to-end; executive summary surfaces top 3 cells with structural/mixed/prompt-sensitive labels. Review Agent prompt unchanged in A4a (lands in A4b). **Decided A7-followup coupling: option (a)** — per-target `source_version` + `single_candidate_meets_all` flag. Confusion analysis stays decoupled from per-target source_version (different concerns: confusion uses elite_set; target_progress uses per-metric leaders). Verification: `1091 passed, 1 deselected` (`test_example_config_round_trip` pre-existing); ruff 5 / pyright 37 (both pre-existing baselines).
- [x] **A4b** — Confusion analysis Phase 2: signal-to-noise filters (`4e280cf`), prompt updates adapted to three-tier structure (`adf651c` + `279187a`), cell-exhaustion tracking (`0e27514` — adds 5 fields to `ConfusionImpact`, `ChildVariant.target_confusion_cell`, `cell_attempt_history.json` persistence, diversity allocation rule). Also: redirect `odysseus/mcp/resources.py:114` to a tier file and delete legacy `review_agent_system.md` (currently still referenced). Heads-up: the existing `0e27514` source has a latent bug where `last_attempted_round` is always `None` because `update_cell_attempt_history` doesn't write `"round"` into entries — fix during port. Cross-link with A7-followup (option (a) is the chosen design). **Ported SHAs**: `4e280cf` (signal-to-noise), `adf651c` (mostly superseded by three-tier rewrite), `279187a` (prompt builder fix), `0e27514` (cell-exhaustion tracking). **Bug fix landed**: `update_cell_attempt_history` now accepts `current_round` and writes `"round": current_round` in every entry — `last_attempted_round` is now correctly populated. Regression test added to `tests/test_cell_attempt_history.py`. **Scoped-down prompt port** (4 edits, not wholesale): documented 5 new `ConfusionImpact` fields + `effective_impact` sort + `attempt_count >= 2` switch-fix-type rule in `review_agent_iterative_base_system.md`; added `target_confusion_cell` to ChildVariant output schema and `contrast_pair_content` schema in `review_agent_base_system.md`; applied `279187a` verbatim to `prompt_builder_system.md`. Explicit diversity-allocation paragraph and anti-pattern #5 intentionally **dropped** — superseded by the base prompt's distinctness self-check. **MCP resource redirect**: `review_agent_guidelines` now returns `review_agent_base_system.md` + `"\n\n---\n\n"` + `review_agent_iterative_base_system.md` (algorithm-neutral). Legacy `review_agent_system.md` deleted. `docs/architecture.md` row 275 updated. **A7-followup decoupling preserved**: cell-exhaustion uses `state.elite_set` via A4a's `_select_confusion_candidates`; independent of `target_progress`'s per-metric leaders. **Verification**: `1120 passed, 1 failed` (pre-existing `test_example_config_round_trip`); ruff 5 / pyright 37 (both at pre-existing baselines).
- [ ] **A5** — Route validation + canonical normalization. Wildcard, severity escalation. Verify malformed routing contexts surface clear errors.
- [x] **A6** — Project-dir cache + metrics consolidation + run-specific paths. Ported `6a9e38e` (always compute accuracy/confusion/f1/cost_quality_change) and `d354cdd` (test fixture: reset `_cached`; align metric assertions). Reclassified `df5b6c5` and `1182b89` to A7 (review-tool surface, not project-dir/metrics/prompts) and deferred `4f5c891` to A7 (`get_prompt_text_tool` doesn't yet exist on this branch — comes with `1182b89`). Skipped `089ff41` (pure util consolidation; `odysseus/util.py` not present and not blocking). Result: `test_returns_cwd` flipped fail → pass; only `test_example_config_round_trip` remains pre-existing.
- [x] **A7** — Tooling + briefing scaffolding. Ported `1182b89` as `c543f7a` (replace mutation-centric schema with child-variant / batch-outcome model; add `query_holdout_examples_tool` + `get_prompt_text_tool`; merge `TargetSlack` into `UserTargetProgress`); `df5b6c5` as `bf53a03` (decompose `record_directive_outcomes_tool` params; allow null `parent_preference`); `4f5c891` + `cdab117` as `2ce1487` (run-specific prompt-dir fallback; require `run_id` on `get_prompt_text_tool`); `764811b` + `2df60ae` as `93aff90` (offset pagination; persistence-threshold contrast-pair text was already absent on this branch, so no prompt edit was needed; also fixed a B009 ruff regression introduced by `c543f7a`). **Deferred `856a85a`** (best-per-target metrics for `target_progress`): the source commit ships no `mixed_candidates` flag or per-metric `source_version`, and the Review Agent reads `target_progress` to emit `LoopSignal` consumed by `search_ops.py:378` for termination — silently mixing metrics across candidates can cause early stop on imaginary success. Tracked as new row A7-followup below. Verification: `1067 passed, 1 deselected` (only pre-existing `test_example_config_round_trip`); ruff back to baseline 5 errors; pyright unchanged at 37 pre-existing.
- [ ] **A7-followup** — Best-per-target metrics for `target_progress` (deferred from A7 / source `856a85a`). **Design fixed by A4a: option (a)** — add per-target `source_version` and a `single_candidate_meets_all` flag, plus prompt updates so the Review Agent can distinguish single-prompt success from cherry-picked mixes. (Option (b) was considered and rejected: keeping globally-best semantics with persistence/cell-exhaustion biases the agent toward declaring rounds done, raising the risk of early-exit on cherry-picked metrics.) Decoupled from confusion analysis: A4a's `_select_confusion_candidates` already uses `state.elite_set` (strategy-owned), independent of per-target leaders.
- [ ] **A8** — Cold-start prompt tightening + target-driven scaffold. Land emosa's most-evolved cold-start content as additions to `review_agent_cold_start_base_system.md`; integrate target-slack reading into preprocessor. Verify Increment 6 snapshot tests still pass.

### Phase B — Per-branch G residuals (sequential after Phase A)

- [ ] **B1** — parallel-beam unique G (cold-start floor `5e8fc0e`, beam test infra). ~1 session.
- [ ] **B2** — sms-emoa + emosa unique G (warmup test fixtures + minor emosa tweaks). ~0.5 session.

### Phase C — Strategy-only ports (sequential per branch, after Phase B)

- [ ] **C1** — parallel-beam residual port. Branch `feat/generalize-beam` off main. Add `_advance_beam`, beam algorithm module, preprocessor field population, init_state helper. Verify scenario runs beam to convergence; cross-branch diff small.
- [ ] **C2** — sms-emoa residual port. Branch `feat/generalize-sms-emoa` off main. Add `_advance_sms_emoa` (warmup + steady-state), `reduce_population` etc., preprocessor population. Verify warmup → steady-state transitions; (μ+1) eviction sound.
- [ ] **C3** — emosa residual port (first half). Branch `feat/generalize-emosa` off main. Land `annealing.py`, AnnealingState in pocket, `_advance_emosa` calibration arm, preprocessor `binding_axis`. Verify K=5 trajectories complete calibration round and write per-trajectory state.
- [ ] **C4** — emosa residual port (second half). Per-trajectory `review_fanout_status` override; `trajectory_fanout_missing`; multi-child Metropolis acceptance; neighborhood replacement. Verify K-way review fanout, per-trajectory acceptance, scenario runs to convergence.

### Phase D — Cross-branch verification (final)

- [ ] **D** — Diff audit. For each `feat/generalize-{beam,sms-emoa,emosa}`, run `git diff main..<branch> -- odysseus/`; confirm residual is one algorithm module + one dispatcher arm + preprocessor changes + (emosa only) per-trajectory fanout override. Update `docs/architecture.md` with the final cross-branch matrix. Decide whether to replace/rebase the legacy `feature/parallel-beam-search`, `feature/sms-emoa`, `feature/emosa` branches.

### Completed prior to this plan revision (for context)

- [x] **Increment 1** — Unify `Candidate`. Commit `8e55ed8`.
- [x] **Increment 2** — Unify `SearchState` + `RoundSummary`. Commit `398c5e3`.
- [x] **Increment 3** — Unify Stage 4 MCP tool surface (`advance_round_tool` → `advance_step_tool`). Commit `fe62325`.
- [x] **Increment 4** — Unify `ReviewBriefing`. Commit `a4a9bfc`.
- [x] **Increment 5** — Unify pipeline guards & dispatch markers. Commit `9425121`.
- [x] **Increment 6** — Review Agent prompts (three-tier base + 8 overlays). Commit `925e2e6`.

## Per-session verification

Each session ends with:
```
uv run ruff check odysseus/ tests/
uv run pyright
uv run pytest tests/ -x
```

The two pre-existing failures (`tests/test_models.py::test_example_config_round_trip`, `tests/test_project_dir.py::TestGetProjectDir::test_returns_cwd`) remain pre-existing throughout. Phase C ports also run an MCP scenario test that exercises the strategy end-to-end on a small dev set. Phase D runs the cross-branch diff audit.
