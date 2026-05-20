# Post-Cold-Start Review Override

This is the round-2 review — the first iterative review after the cold-start phase. The elite set this round contains every round-1 cold-start variant as a **protected parent**, regardless of Pareto dominance, so each initial strategy has exactly one data point. Your job this round is to give each strategy a second data point — one child per protected parent — before standard Pareto competition begins in round 3.

The rules below set the round-2 mandate. The iterative base that follows defines the per-child diagnostic workflow (identify failure mode → hypothesise → directive), and those steps still apply — but the parent-selection and merge sections of the iterative base are **overridden** by the rules in this file for this round only.

## Round-2 Protected Parents Mandate

You **must** emit exactly one `ChildVariant` per scored elite member, using that member as `parent_version`. Number of children = number of scored elite members this round.

- **One child per protected parent.** Do not allocate two children to the same parent.
- **No two-parent merges this round.** `secondary_parent_version` must be `null` on every variant.
- **Failed cold-start variants** (where `eval_status != "complete"` for that elite member) are skipped — do not emit a child for them.

For each protected parent, run the iterative diagnostic workflow (steps 1–4 of the iterative base) **scoped to that parent's score report and `top_confusion_cells`** — fetched via `get_score_report(version=parent)`, `get_confusion_cell(...)`, and `query_eval_results(version=parent, ...)` for per-example detail. Never read `results.jsonl` directly. Produce one bundled `ChildVariant` whose hypothesis is the highest-impact fix you can ground in that parent's data. Two different parents may target the same confusion cell — the per-parent diversity rule from the iterative base is auto-satisfied this round because each parent gets exactly one child.

Tool reminder: use the briefing + the MCP tools listed in base §2 only. Never call Bash, file reads, or `python3 -c` to inspect `report.json`, `results.jsonl`, or any other file under `outputs/`.

## Cell selection for the per-parent diagnostic

When picking the confusion cell to target for a given protected parent, rank that parent's `top_confusion_cells` by:

- **Threshold gap** against that parent's score report, when the user-declared threshold is NOT yet met.
- **Oracle gap** (per-cell `oracle_cost_change` / `oracle_quality_change`), when the threshold IS met — choose the cell whose fix closes the largest oracle residual without regressing below the threshold.

Pick the top-ranked cell for that parent. No per-parent diversity rule applies this round — each parent gets exactly one child.

## Parent Selection Override

The iterative base's "match parent to hypothesis" rule is suspended for round 2. Parents are fixed by the protected-parent mandate above. Within each parent's variant, the hypothesis must still be grounded in that parent's score report — pick the fix the parent most needs, not a generic improvement.

## Merge Override

`secondary_parent_version` must be `null` on every `ChildVariant` this round. Two-parent merges resume in round 3 once each strategy has two data points and Pareto competition begins.

## Loop Signal

Emit `LoopSignal.continue_search = true` for round 2 unconditionally — the round-2 mandate is a structured exploration step, not a convergence check. Stagnation and convergence detection resume in round 3 via the standard iterative path.
