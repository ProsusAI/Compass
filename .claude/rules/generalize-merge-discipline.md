## Generalize Merge Discipline

The `feat/generalize-*` branches form a star: `feat/generalize-pipeline` is the
shared trunk; `feat/generalize-{hill_climb,beam,emosa,sms-emoa}` are algorithm leaves
that periodically pull from pipeline. Algorithm code MUST NOT live on pipeline; if it
does, every propagation overwrites the recipient branch's
algorithm with whatever was on pipeline.

### Propagation flow (read this first)

Both directions across the star are **cherry-pick only**. Plain `git merge`
between pipeline and any leaf is forbidden because it replays decontamination
commits (or contamination merges) as destructive changes on the recipient.

| Direction | Mechanism | Why |
|---|---|---|
| Leaf → pipeline | `git cherry-pick <sha>` of an algorithm-agnostic commit only | Prevents pipeline contamination at the source. Never `git merge feat/generalize-<leaf>` into pipeline |
| Pipeline → leaf | `git cherry-pick <sha>` of explicitly-listed algorithm-agnostic commits | Prevents decontamination commits from being replayed as deletions on the leaf. Never `git merge feat/generalize-pipeline` into a leaf |
| Leaf → leaf | Forbidden | Share via pipeline using the two cherry-pick steps above |

#### Authoring an algorithm-agnostic improvement

1. Develop on whichever branch is most convenient (often a leaf, where you
   already have the running pipeline).
2. Once it lands on the leaf, identify the SHA(s) that are purely
   algorithm-agnostic (do not reference any `*_overlay_<algo>.md`,
   `_populate_<algo>_review_fields`, `("<algo>", …)` overlay keys, or
   algorithm-specific modules like `annealing.py` / `emosa_trace.py`).
3. `git checkout feat/generalize-pipeline && git cherry-pick <sha>` for each.
4. Push pipeline.
5. From each leaf, follow "Pipeline → leaf propagation procedure" below.

#### Pipeline → leaf propagation procedure

1. `git fetch origin`.
2. `git log feat/generalize-pipeline ^feat/generalize-<leaf>` to enumerate
   candidate commits.
3. For each commit, classify:
   - **Algorithm-agnostic** → cherry-pick.
   - **Decontamination / leaf-specific / contamination revert** → skip.
4. `git cherry-pick <sha>` per kept commit, in order.
5. Spot-check the leaf's invariants before pushing: `_BRANCH_ALGORITHM` is
   unchanged, the algorithm's overlays and `_populate_<algo>_review_fields`
   are still present, and no algorithm-specific files were deleted.
6. Run tests; push.

### Forbidden on `feat/generalize-pipeline`

| Pattern | Why |
|---|---|
| `_BRANCH_ALGORITHM = "hill_climb" \| "beam" \| "emosa" \| "sms_emoa"` (any non-`"__unset__"` value) | Pipeline trunk uses the `"__unset__"` sentinel; leaf branches set the concrete value |
| Files matching `compass/agents/prompts/*_overlay_{hill_climb,beam,emosa,sms_emoa,sms-emoa}.md` | Algorithm-specific overlays belong on their leaf branch |
| `def _populate_{hill_climb,beam,emosa,sms_emoa}_review_fields` in `preprocessor.py` | Algorithm-specific briefing population belongs on its leaf branch |
| `("hill_climb", *), ("beam", *), ("emosa", *), ("sms_emoa", *)` keys in `_overlay_map` (`compass/mcp/prompts.py`) | Leaf branches add their own overlay keys; pipeline has none |

If a commit on pipeline introduces any of the above, revert it before merging
to any leaf. Use `git log feat/generalize-pipeline -- 'compass/agents/prompts/*_overlay_*.md' compass/agents/prompt_builder/search_ops.py` to audit.

### Conflict-resolution rule (when a cherry-pick conflicts on a leaf)

On conflict in `search_ops.py`, `mcp/prompts.py`, or `review/preprocessor.py`
during a pipeline → leaf cherry-pick: **always keep the leaf's
`_BRANCH_ALGORITHM`, `_overlay_map` keys, and `_populate_<algo>_review_fields`**.
Pipeline's version is wrong by definition.

Heuristic for individual hunks:
- Hunk *adds* algorithm-agnostic perf/feature machinery → take it.
- Hunk *removes* an algorithm-named symbol, file, key, or function → drop the
  deletion (keep the leaf side).
- Hunk does both → manually merge: apply the additive change while preserving
  the algorithm code.

### MCP cache after a corrective force-push

After force-pushing a leaf branch to undo contamination, any consumer using
`uvx --from git+...@<leaf>` MUST run `uv cache clean compass` (or restart
their MCP client) to drop the stale build. Otherwise the previous (wrong)
build of the branch keeps serving requests.

### Rationale

This rule exists because of two recurring incidents:

- **PR #120 (`88490de`)** merged a beam-contaminated pipeline into
  `feat/generalize-emosa`, silently flipping `_BRANCH_ALGORITHM` from
  `"emosa"` to `"beam"` and replacing all `("emosa", *)` overlay keys. The
  contamination originated from earlier commits `6c5665e` (`feat/generalize-beam`
  → `feat/generalize-pipeline`) and `0a5eedf` (`chore(beam): re-introduce
  beam-specific layer atop cleaned pipeline`).
- **PR #131** propagated pipeline into emosa with a body advertising one
  algorithm-agnostic commit (`5b10983`) but a diff that also included two
  trunk-decontamination commits (`db269df`, `359ff64`). Merging it would
  have deleted ~7,000 lines of emosa code. Resolution: closed PR #131,
  cherry-picked `5b10983` and `2f54e1b` directly onto emosa.

Once algorithm code lives on pipeline, propagation merges become
destructive — and the corrective decontamination commits become equally
destructive when replayed onto a leaf. The cherry-pick-only flow above
breaks both halves of that cycle.

Apply alongside `generalize-fix-routing.md` (routes new fixes) and
`pr-base-branch.md` (guards merges to `main`).
