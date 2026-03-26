# Annotation Dispute System

Adds a feedback channel for surfacing potentially incorrect rationale card annotations to the human operator. The optimization loop remains unaffected — disputes are informational output collected across rounds and presented in the final report.

## Problem

The Routing Analysis Agent produces rationale cards before the optimization loop begins. During the loop, evaluation results may reveal that certain card annotations (intent_pattern, complexity_structure, ambiguity_tags, route_exclusions) don't accurately capture why an example routes the way it does. Today this signal is lost — the Review Agent sees misrouting patterns but has no mechanism to flag annotation quality issues.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Who resolves disputes? | Human | Cards are ground truth; automated mutation risks circular reasoning |
| When are disputes surfaced? | End-of-loop only | No need to interrupt the optimization loop |
| Effect on current loop? | None | Cards stay as-is; disputes are purely informational |
| What triggers a dispute? | Consistent misrouting + ambiguity signals, with confidence thresholds | Multiple independent signals reduce noise |
| Does the dispute suggest a fix? | No — flag only | Keeps the system in critic role; human decides the correction |
| Who produces disputes? | Final Reporting Agent | Review Agent stays focused on prompt critique and loop control |

## Architecture

### Data Flow

```
Each review round:
  results JSONL (per-example predictions) + holdout RationaleCardSet
      ↓
  compute_misroute_stats()          (review_preprocessor.py — reads results files)
      ↓
  save_misroute_stats()             (review_ops.py — JSON, keyed by round)

End of loop:
  misroute_stats.json + holdout RationaleCardSet
      ↓
  Final Reporting Agent             (LLM — reasons about which dimensions are suspect)
      ↓
  list[AnnotationDispute]           (section in final report)
      ↓
  Human operator                    (curates cards before next pipeline run)
```

### What Changes

| Component | Change |
|---|---|
| `review_preprocessor.py` | New `compute_misroute_stats` function, `ExampleMisrouteStats` model |
| `review_ops.py` | New `save_misroute_stats` / `load_all_misroute_stats` persistence pair |
| `odysseus/agents/annotation_dispute_models.py` | New file: `AnnotationDispute`, `DisputedDimension` models |
| Final Reporting Agent prompt | New section: consume misroute stats, produce annotation disputes |
| `docs/architecture.md` | New context dict key `misroute_stats_path`, update `holdout_rationale_card_set_path` consumers |
| Orchestrator | Call `compute_misroute_stats` + `save_misroute_stats` after each review round |

### What Doesn't Change

- **Review Agent** — no prompt modifications, no new fields in `ReviewBriefing` or `ReviewResult`
- **Rationale cards** — never mutated during the pipeline
- **Optimization loop** — completely unaffected, all cards remain ground truth
- **Analysis Agent** — no changes
- **Holdout isolation** — preserved; pre-processor reads holdout cards for misroute computation but nothing leaks to the Prompt Builder

## Data Models

### `ExampleMisrouteStats` (in `review_preprocessor.py`)

Pre-processor output — deterministic, threshold-filtered.

```python
class ExampleMisrouteStats(BaseModel):
    example_id: str
    assigned_route: str
    model_routes: dict[str, int]    # route -> count across candidates
    rounds_seen: list[int]
    ambiguity_tags: list[str]
    intent_pattern: str
    complexity_structure: str
    route_exclusions: list[RouteExclusion]
```

### Threshold Constants (in `review_preprocessor.py`)

```python
MIN_MISROUTE_CANDIDATES = 3   # Misrouted by at least 3 candidates
MIN_MISROUTE_ROUNDS = 2       # Across at least 2 rounds
```

Defaults — exposed as function parameters for configurability:

```python
def compute_misroute_stats(
    ...,
    min_misroute_candidates: int = MIN_MISROUTE_CANDIDATES,
    min_misroute_rounds: int = MIN_MISROUTE_ROUNDS,
) -> list[ExampleMisrouteStats]:
```

Only examples meeting both thresholds are included in the output.

### `DisputedDimension` / `AnnotationDispute` (in `odysseus/agents/annotation_dispute_models.py`)

Shared models consumed by the Final Reporting Agent. Separate file because they span the boundary between the review pre-processor (which produces the stats) and the reporting agent (which produces the disputes).

```python
class DisputedDimension(BaseModel):
    dimension: Literal["intent_pattern", "complexity_structure", "ambiguity_tags", "route_exclusions"]
    current_value: str | list[str]
    evidence: str                  # Why this seems wrong/incomplete

class AnnotationDispute(BaseModel):
    example_id: str
    assigned_route: str            # For context, not disputed
    disputed_dimensions: list[DisputedDimension]
    misroute_count: int
    rounds_observed: list[int]
```

`current_value` is `str | list[str]` to handle both scalar dimensions (`intent_pattern`, `complexity_structure`) and list dimensions (`ambiguity_tags`, `route_exclusions` serialized as a list of route strings).

## Pre-processor: `compute_misroute_stats`

Function in `review_preprocessor.py`. Not a pure function — reads results JSONL files from disk.

**Inputs:**
- `results_paths: dict[str, str]` — candidate version → path to results JSONL file (from `ScoreReport.results_path`). Each file contains per-example `EvalResult` records including the model's predicted route.
- `historical_results_paths: dict[int, dict[str, str]]` — round → (version → results path). Accumulated across rounds.
- `holdout_card_set: RationaleCardSet` — for card metadata and `assigned_route` ground truth.

**Why not `ScoreReport` directly?** `ScoreReport` carries only aggregate metrics and error breakdowns — not per-example predictions. The per-example route predictions live in the results JSONL files referenced by `ScoreReport.results_path`. This function reads those files to get the predicted route per example per candidate.

**Route extraction:** The predicted route lives at `EvalResult.output["route"]` (matching the convention in `odysseus/eval/metrics.py`). Records where `output` is `None` (failed calls) are skipped. Records where `output["route"]` does not match any known route are skipped (hallucinated routes — already handled in metrics).

**Logic:**
1. For each results file, load per-example `EvalResult` records and extract `output["route"]`
2. For each holdout example, count how many candidates routed it differently from `assigned_route`, tracking which rounds the misroutes appeared in
3. Filter to examples meeting both thresholds
4. For qualifying examples, extract all rationale dimensions from the holdout card

**Output:** `list[ExampleMisrouteStats]`

### Data dependency note

The orchestrator must accumulate `results_paths` across rounds (similar to how `historical_reports` accumulates `ScoreReport` dicts). The `results_path` field already exists on `ScoreReport` — the orchestrator just needs to track it per round.

`holdout_rationale_card_set_path` is currently consumed only by the Final Reporting Agent (per `docs/architecture.md`). The orchestrator / review pre-processor now also reads it for `compute_misroute_stats`. The architecture doc's "Consumed By" column must be updated.

## Persistence

### `save_misroute_stats` / `load_all_misroute_stats` (in `review_ops.py`)

Follows the existing `review_ops.py` pattern: `search_state_id` + `output_dir`, JSON format.

```python
def save_misroute_stats(
    search_state_id: str,
    round_num: int,
    stats: list[ExampleMisrouteStats],
    *,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
) -> None:
    """Write misroute stats for a round to {search_dir}/misroute_stats/round_{n}.json."""

def load_all_misroute_stats(
    search_state_id: str,
    *,
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
) -> dict[int, list[ExampleMisrouteStats]]:
    """Load all rounds' misroute stats, keyed by round number."""
```

Storage layout: `{output_dir}/{search_state_id}/misroute_stats/round_{n}.json` — one file per round, matching the `round_reports/round_{n}.json` pattern. Always writes even if the stats list is empty (records that the round was processed).

## Context Dict Addition

| Key | Type | Set By | Consumed By | Description |
|---|---|---|---|---|
| `misroute_stats_path` | `str` | Orchestrator (review round persistence) | Final Reporting Agent | Path to `misroute_stats/` directory containing per-round JSON files |

Update to existing key:

| Key | Consumed By (updated) |
|---|---|
| `holdout_rationale_card_set_path` | Final Reporting Agent, Review pre-processor (`compute_misroute_stats`) |

## Final Report Section

The Final Reporting Agent includes an "Annotation Review" section listing each dispute:

- Example ID and assigned route (for context)
- Which dimensions are disputed and why
- Misroute count and rounds observed
- The section is omitted if no examples meet the dispute thresholds

This is actionable input for the human before the next pipeline run.
