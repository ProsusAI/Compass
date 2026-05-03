## Generalize Merge Discipline

The four `feat/generalize-*` branches form a star: `feat/generalize-pipeline` is the
shared trunk; `feat/generalize-{beam,emosa,sms-emoa}` are algorithm leaves that
periodically pull from pipeline. Algorithm code MUST NOT live on pipeline; if it
does, every propagation merge silently overwrites the recipient branch's
algorithm with whatever was on pipeline.

### Forbidden on `feat/generalize-pipeline`

| Pattern | Why |
|---|---|
| `_BRANCH_ALGORITHM = "beam" \| "emosa" \| "sms_emoa"` (any non-`"hill_climb"` value) | Pipeline is the shared base; the algorithm constant is set on the leaf branches |
| Files matching `odysseus/agents/prompts/*_overlay_{beam,emosa,sms_emoa,sms-emoa}.md` | Algorithm-specific overlays belong on their leaf branch |
| `def _populate_{beam,emosa,sms_emoa}_review_fields` in `preprocessor.py` | Algorithm-specific briefing population belongs on its leaf branch |
| `("beam", *), ("emosa", *), ("sms_emoa", *)` keys in `_overlay_map` (`odysseus/mcp/prompts.py`) | Only `hill_climb` keys live on pipeline; leaves add their own |

If a commit on pipeline introduces any of the above, revert it before merging
to any leaf. Use `git log feat/generalize-pipeline -- 'odysseus/agents/prompts/*_overlay_*.md' odysseus/agents/prompt_builder/search_ops.py` to audit.

### Pre-merge check before `feat/generalize-pipeline → feat/generalize-{leaf}`

Run before merging:

```
git fetch origin
git diff feat/generalize-pipeline...feat/generalize-<leaf> --name-only \
  | grep -E '(search_ops\.py|mcp/prompts\.py|review/preprocessor\.py|prompts/.*_overlay_)'
```

For each file listed, manually confirm: pipeline's version does NOT contain
the leaf's algorithm code. If it does, abort the merge and clean pipeline first.

During the merge, on conflict in `search_ops.py`, `mcp/prompts.py`, and
`review/preprocessor.py`: **always keep the leaf's `_BRANCH_ALGORITHM`,
`_overlay_map` keys, and `_populate_<algo>_review_fields`**. Pipeline's
version is wrong by definition.

### MCP cache after a corrective force-push

After force-pushing a leaf branch to undo contamination, any consumer using
`uvx --from git+...@<leaf>` MUST run `uv cache clean odysseus` (or restart
their MCP client) to drop the stale build. Otherwise the previous (wrong)
build of the branch keeps serving requests.

### Rationale

This rule exists because PR #120 (`88490de`) merged a beam-contaminated
pipeline into `feat/generalize-emosa`, silently flipping `_BRANCH_ALGORITHM`
from `"emosa"` to `"beam"` and replacing all `("emosa", *)` overlay keys.
The contamination originated from earlier commits `6c5665e` (`feat/generalize-beam`
→ `feat/generalize-pipeline`) and `0a5eedf` (`chore(beam): re-introduce
beam-specific layer atop cleaned pipeline`). Once algorithm code lives on
pipeline, propagation merges become destructive.

Apply alongside `generalize-fix-routing.md` (routes new fixes) and
`pr-base-branch.md` (guards merges to `main`).
