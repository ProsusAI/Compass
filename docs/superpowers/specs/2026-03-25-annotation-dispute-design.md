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
  eval results + holdout RationaleCardSet
      ↓
  compute_misroute_stats()          (review_preprocessor.py — pure function)
      ↓
  save_misroute_stats()             (review_ops.py — append to misroute_stats.jsonl)

End of loop:
  misroute_stats.jsonl + holdout RationaleCardSet
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
| New shared models | `AnnotationDispute`, `DisputedDimension` (not review-specific) |
| Final Reporting Agent prompt | New section: consume misroute stats, produce annotation disputes |
| `docs/architecture.md` | New context dict key `misroute_stats_path` |
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
```

### Threshold Constants (in `review_preprocessor.py`)

```python
MIN_MISROUTE_CANDIDATES = 3   # Misrouted by at least 3 candidates
MIN_MISROUTE_ROUNDS = 2       # Across at least 2 rounds
```

Only examples meeting both thresholds are persisted.

### `DisputedDimension` / `AnnotationDispute` (shared models)

Final Reporting Agent output — includes LLM-generated evidence.

```python
class DisputedDimension(BaseModel):
    dimension: Literal["intent_pattern", "complexity_structure", "ambiguity_tags", "route_exclusions"]
    current_value: str
    evidence: str                  # Why this seems wrong/incomplete

class AnnotationDispute(BaseModel):
    example_id: str
    assigned_route: str            # For context, not disputed
    disputed_dimensions: list[DisputedDimension]
    misroute_count: int
    rounds_observed: list[int]
```

## Pre-processor: `compute_misroute_stats`

Pure function in `review_preprocessor.py`.

**Inputs:**
- Current round's eval results (per-example predictions from `ScoreReport`)
- Historical eval results (accumulated across rounds)
- Holdout `RationaleCardSet` (for card metadata)

**Logic:**
1. For each holdout example, count how many candidates routed it differently from `assigned_route` across current + historical rounds
2. Filter to examples meeting both thresholds (`MIN_MISROUTE_CANDIDATES`, `MIN_MISROUTE_ROUNDS`)
3. For qualifying examples, extract the card's rationale dimensions into `ExampleMisrouteStats`

**Output:** `list[ExampleMisrouteStats]`

Derived from `historical_reports` already available in `build_review_briefing` — no new data dependencies. Stateless: recomputed each round from accumulated eval results.

## Persistence

### `save_misroute_stats` / `load_all_misroute_stats` (in `review_ops.py`)

- `save_misroute_stats(run_dir: Path, round: int, stats: list[ExampleMisrouteStats])` — writes to `{run_dir}/misroute_stats.jsonl`, one JSON object per stat entry with round number
- `load_all_misroute_stats(run_dir: Path) -> dict[int, list[ExampleMisrouteStats]]` — reads all entries, grouped by round

Consistent with existing `review_ops.py` patterns (directive history, round reports).

## Context Dict Addition

| Key | Type | Set By | Consumed By | Description |
|---|---|---|---|---|
| `misroute_stats_path` | `str` | Orchestrator (review round persistence) | Final Reporting Agent | Path to accumulated `misroute_stats.jsonl` |

## Final Report Section

The Final Reporting Agent includes an "Annotation Review" section listing each dispute:

- Example ID and assigned route (for context)
- Which dimensions are disputed and why
- Misroute count and rounds observed
- The section is omitted if no examples meet the dispute thresholds

This is actionable input for the human before the next pipeline run.
