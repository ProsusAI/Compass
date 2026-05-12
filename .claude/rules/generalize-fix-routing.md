## Generalize Branch Fix Routing

Fixes targeting the multi-algorithm generalize workstream MUST land on the correct branch based on scope:

| Fix scope | Target branch | Propagation |
|---|---|---|
| General / pipeline-wide (affects all algorithms — pipeline orchestration, MCP surface, shared utilities, cross-cutting infra) | `feat/generalize-pipeline` | After landing, `git cherry-pick` the commit(s) onto each `feat/generalize-{hill_climb,beam,emosa,sms-emoa}` branch. Follow the "Pipeline → leaf propagation procedure" in `generalize-merge-discipline.md`. **Never merge** pipeline into a leaf. |
| Algorithm-specific (only affects one algorithm: e.g. hill-climb step logic, EMOSA trajectory logic, beam scoring, SMS-EMOA hypervolume) | The matching `feat/generalize-{hill_climb,beam,emosa,sms-emoa}` branch | Do NOT propagate to other algorithm branches. Do NOT land on `feat/generalize-pipeline`. If an algorithm-agnostic part of the same change should be shared, lift it out as a separate commit and follow the "Authoring an algorithm-agnostic improvement" flow in `generalize-merge-discipline.md`. |

Rationale: `feat/generalize-pipeline` is the shared base; algorithm branches consume from it. Routing fixes correctly keeps shared logic in one place and prevents algorithm-specific code from leaking across branches.

When in doubt about scope, ask the user before committing.

Apply alongside `pr-base-branch.md` — base-branch rule still governs the merge-to-main step (none of these branches PR to main without explicit user confirmation).
