## PR Base Branch

When opening a pull request from a `feat/generalize-*` branch, the base MUST NOT be `main` unless the user has explicitly confirmed in the same turn that testing is complete and the merge to `main` is intended.

| Head branch pattern | Required behavior |
|---|---|
| `feat/generalize-*` | Pass `--base <other-generalize-branch-or-integration-branch>` explicitly to `gh pr create`. If no clear target, ASK the user. Do not default to `main`. |
| any other | Repo default (`main`) is acceptable. Standard flow. |

Rationale: the `feat/generalize-*` branches are kept self-contained while their algorithm-specific implementations are still under test. Accidentally targeting `main` risks merging work that has not yet been validated end-to-end across all four algorithm branches (`beam`, `emosa`, `pipeline`, `sms-emoa`).

Apply to: `gh pr create`, `gh pr edit --base`, and any scripted/agent PR creation flow. When in doubt, ask before opening.
