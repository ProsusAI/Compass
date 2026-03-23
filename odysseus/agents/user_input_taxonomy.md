# User Input Gap Taxonomy

Classification rules for missing input fields. Used by the User Input agent to determine
whether to proceed, apply defaults, or request clarification.

## Classification Criteria

- **Blocking**: Cannot be reasonably defaulted; no surrogate exists; downstream agents fail without it.
- **Non-blocking**: A principled domain default exists; the user can override the assumed value later.

## Taxonomy

| Field | Classification | Rationale | Default |
|---|---|---|---|
| `routing_dataset` | Blocking | No default can substitute real labeled routing data | — |
| `problem_description` | Blocking | Analysis agent cannot extract patterns without it | — |
| `target_metrics` | Non-blocking | Metrics are fixed in THP-69 context; F1 is a strong general-purpose default | F1 score |
| `evaluation_threshold` | Non-blocking | Conservative threshold consistent with routing literature | 0.80 |
| `data_split_ratio` | Non-blocking | 80/20 is a well-established standard | 0.20 |
| `max_iterations` | Non-blocking | Bounds cost while allowing convergence | 10 |

## Status Decision Logic

Based on the gaps identified, set the `status` field in the validated input report:

1. **Any blocking gap present** → the agent continues conversing with the user until the gaps are resolved. No report is produced until all blocking gaps are filled.
2. **Only non-blocking gaps present** → `proceed_with_defaults` — apply defaults from table above, note them in the report.
3. **No gaps** → `proceed` — all fields present, continue pipeline.
