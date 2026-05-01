## Generalize Branch Fix Routing

Fixes targeting the multi-algorithm generalize workstream MUST land on the correct branch based on scope:

| Fix scope | Target branch | Propagation |
|---|---|---|
| General / pipeline-wide (affects all algorithms — pipeline orchestration, MCP surface, shared utilities, cross-cutting infra) | `feat/generalize-pipeline` | After landing, open a PR from `feat/generalize-pipeline` into each `feat/generalize-{beam,emosa,sms-emoa}` branch to propagate. |
| Algorithm-specific (only affects one algorithm: e.g. EMOSA trajectory logic, beam scoring, SMS-EMOA hypervolume) | The matching `feat/generalize-{beam,emosa,sms-emoa}` branch | Do NOT propagate to other algorithm branches. Do NOT land on `feat/generalize-pipeline`. |

Rationale: `feat/generalize-pipeline` is the shared base; algorithm branches consume from it. Routing fixes correctly keeps shared logic in one place and prevents algorithm-specific code from leaking across branches.

When in doubt about scope, ask the user before committing.

Apply alongside `pr-base-branch.md` — base-branch rule still governs the merge-to-main step (none of these branches PR to main without explicit user confirmation).
