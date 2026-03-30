# User Input Agent — Default Values

Lookup table for non-blocking gaps. When the User Input agent detects a missing optional
field, it applies the default from this table and records the assumption in the validated
input report.

## Defaults Table

| Field | Default value | Rationale | User-facing note |
|---|---|---|---|
| `target_metrics` | `["f1/macro"]` | F1 macro is a strong general-purpose metric for routing problems — it handles class imbalance well and reveals per-class performance, unlike accuracy which can mask poor routing on minority classes. | "No target metrics specified — defaulting to F1 macro average (`f1/macro`). You can specify metrics such as `accuracy >= 0.85` or `cost_reduction_with_overhead <= -0.30` in a follow-up." |
| `evaluation_threshold` | `0.80` | Conservative pass threshold consistent with routing literature — high enough to ensure meaningful quality, low enough to be achievable on most problems. | "No evaluation threshold specified — using 0.80 as the pass/fail threshold. You can adjust this in a follow-up." |
| `data_split_ratio` | `0.80` | 20/80 dev/holdout split keeps the iterative eval set small for fast feedback loops while reserving a large holdout for reliable final validation. | "No data split ratio provided — reserving 80% of data for holdout evaluation." |
| `max_iterations` | `10` | Bounds compute cost while allowing sufficient convergence — most routing problems converge within 5–8 rounds; 10 provides headroom without unbounded spending. | "No iteration limit provided — defaulting to 10 refinement rounds." |

## Override Mechanism

Users can override any assumed default by providing the corrected value in a follow-up
message within the same MCP session. The agent re-evaluates the submission with the
updated value and produces a new validated input report.

**How it works:**

1. The agent produces a `proceed_with_defaults` report listing all assumed values.
2. The MCP server surfaces the assumed defaults to the user (via the `assumed_defaults`
   section of the report).
3. If the user provides a corrected value (e.g. "use accuracy >= 0.90 instead"), the
   agent treats the follow-up as a partial re-submission.
4. The agent replaces the assumed default with the user-specified value, updates the
   gap report, and produces a new validated input report.
5. If all defaults are now user-confirmed, the status changes from `proceed_with_defaults`
   to `proceed`.

**Constraints:**

- Overrides apply only to non-blocking fields. Blocking gaps always require explicit
  user input — they cannot be defaulted or overridden.
- Each override replaces the full default value (no partial merges). For example, if the
  user specifies `accuracy >= 0.90`, the entire `target_metrics` default is replaced,
  not appended to.

## Propagation

Assumed defaults are flagged in the validated input report (THP-72) so downstream agents
know which values were user-specified and which were assumed.

**In the `assumed_defaults` array:**

Each assumed default produces an entry with:
- `field` — the field name.
- `assumed_value` — the default value applied.
- `user_note` — the user-facing note from the table above.

**In the `gap_report` array:**

Each non-blocking gap produces an entry with:
- `classification: "non-blocking"` — marks it as defaultable.
- `default_applied` — the value from this table.
- `rationale` — why this default was chosen.

**Downstream contract:**

Downstream agents (Data Validation, Routing Analysis, etc.) should treat assumed defaults
identically to user-specified values for processing purposes. The distinction exists for
transparency — so the user can review and override — not for differential treatment by
the pipeline.
