# Review Agent Design

## Overview

The Review Agent supervises the multi-candidate search process in Zone 4 (Refinement Loop), emitting localized block-level edit directives (TextGrad-style) rather than global rewrite suggestions, and deciding whether to promote, refine, or exit the search.

It is a hybrid agent: a **code-driven pre-processor** computes numerical analysis, and an **LLM critic** produces qualitative judgment. This follows the precedent set by the Eval Runner as the "code-driven exception" pattern.

## Position in the Pipeline

The Review Agent sits between eval completion and the next Prompt Builder iteration:

```
Prompt Builder generates candidate(s) vN
  → run_eval(vN) → ScoreReport
  → advance_round() → updated SearchState (Pareto math, stagnation)
  → Review Agent pre-processor (code) → ReviewBriefing
  → Review Agent LLM → ReviewResult
  → Prompt Builder reads ReviewResult for next round
     (or loop exits if Review Agent signals exit)
```

`advance_round()` runs **before** the Review Agent. The deterministic Pareto front and convergence check are already computed. The Review Agent can override or augment — e.g., override stagnation convergence to grant extra rounds for a promising macro edit, or signal exit due to diversity collapse even when `advance_round` says "not converged."

The Review Agent does **not** call `advance_round()` or mutate `SearchState` directly. It emits a `ReviewResult` that the orchestrator uses to decide next steps.

## Division of Labor

| Responsibility | Owner |
|---------------|-------|
| Pareto front management (quality + cost) | `advance_round()` (deterministic) |
| Stagnation counting, convergence flag | `advance_round()` (deterministic) |
| Multi-objective ranking (5 dimensions) | Review Agent LLM |
| Block-level edit directives | Review Agent LLM |
| Regression guards (rare-class recall, calibration) | Review Agent LLM |
| Promotion / refine / prune decisions | Review Agent LLM |
| Loop continuation override | Review Agent LLM |
| Numerical pre-processing (deltas, trends, diversity) | Review Agent code layer |

The deterministic Pareto math stays as a safety net. The Review Agent layers qualitative analysis on top.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Prompt structure | Convention-based Markdown with headers (`## Rules`, `## Examples`, `## Output Schema`) | Human-readable, diffable, enough structure for block-level feedback without schema migration |
| Exemplar bank | Holdout set (as Prompt Builder already uses) | Consistent with existing sourcing pattern |
| Mutation tracking | Prompt Builder emits MutationRecord + Review Agent tracks directive history | Closes the feedback loop: what was suggested → what was done → what happened |
| Pareto dimensions | 2D (quality + cost) in `advance_round`, richer analysis in Review Agent | Keeps deterministic layer simple and testable |
| Prompt similarity | `difflib` (stdlib) + section-level structural comparison | No external dependencies, sufficient for diversity detection |

### Prompt Section Convention

Prompts follow a Markdown convention with headers for top-level sections and numbered sub-items within:

```markdown
## Rules
1. When the user asks about X, route to model-A
2. Prefer tool-capable models when the query requires external data
3. ...

## Examples
### Example 1
Input: ...
Output: ...

### Example 2
Input: ...
Output: ...

## Output Schema
...
```

Edit directives reference sections by header name and sub-items by number: `block_type="rule"`, `block_identifier="Rule 2"` targets the second rule under `## Rules`. `block_type="example"`, `block_identifier="Example 3"` targets `### Example 3`. Section-level directives (e.g., "rewrite the output schema") use `block_identifier="Output Schema"`.

## Prerequisites

### Prompt Builder Contract Extension

The `MutationRecord` model defined in this spec is a new output contract for the Prompt Builder. The Prompt Builder spec must be updated to include `MutationRecord` emission as part of its output. The Review Agent depends on this for mutation tracking and directive effectiveness correlation.

### Eval Engine Metric Configuration

`OracleMetrics` requires that `cost_quality_reduction` is included in the eval `RunConfig.metrics` list. Without it, `oracle_cost_reduction` and `oracle_quality_reduction` will not be present in `ScoreReport.metrics`. The orchestrator must ensure this metric is configured for all eval runs within the refinement loop.

## Data Models

All models use Pydantic `BaseModel` for consistency with the existing codebase (`SearchState`, `Candidate`, `ScoreReport`, etc.).

### ReviewBriefing (Code Layer Output → LLM Input)

```python
class MetricDeltas(BaseModel):
    quality_delta: float
    cost_delta: float
    per_class_recall_deltas: dict[str, float]

class FrontComparison(BaseModel):
    front_candidate_version: str    # Version of the Pareto front candidate being compared against
    quality_delta: float
    cost_delta: float

class CandidateAnalysis(BaseModel):
    candidate_version: str
    parent_version: str | None
    mutation_description: str
    score_report: ScoreReport
    delta_vs_parent: MetricDeltas
    delta_vs_front: list[FrontComparison]

class ClassRecallEntry(BaseModel):
    recall: float
    support: int
    trend: list[float]          # Recall across last N rounds
    regression_flag: bool       # True if recall dropped vs previous round

class DiversityMetrics(BaseModel):
    example_overlap_ratio: float
    prompt_similarity: float    # Normalized edit distance across front (0.0 = identical, 1.0 = completely different)
    mutation_type_distribution: dict[str, int]

class DiminishingReturns(BaseModel):
    score_trajectory: list[float]
    improvement_trend: float
    stagnation_flag: bool

class MutationRecord(BaseModel):
    child_version: str
    parent_version: str
    mutation_type: str          # "example_swap" | "rule_edit" | "schema_change" | "rule_add" | "rule_remove" | "assembly_policy"
    description: str
    directive_ids: list[str] | None = None

class MutationHistory(BaseModel):
    effective_mutations: list[MutationRecord]
    ineffective_mutations: list[MutationRecord]
    untried_mutation_types: list[str]

class ExampleSummary(BaseModel):
    example_id: str
    route: str
    ambiguity_tags: list[str]

class OracleMetrics(BaseModel):
    oracle_cost_reduction: float        # From ScoreReport.metrics["oracle_cost_reduction"]
    oracle_quality_reduction: float     # From ScoreReport.metrics["oracle_quality_reduction"]
    candidate_cost_captured: float | None   # candidate_cost_reduction / oracle_cost_reduction (None if oracle is 0)
    candidate_quality_captured: float | None # candidate_quality_reduction / oracle_quality_reduction (None if oracle is 0)

class ReviewBriefing(BaseModel):
    round: int
    candidates: list[CandidateAnalysis]
    pareto_front: list[Candidate]
    per_class_recall: dict[str, ClassRecallEntry]
    diversity_metrics: DiversityMetrics
    diminishing_returns: DiminishingReturns
    mutation_history: MutationHistory
    oracle_metrics: OracleMetrics
    prompt_versions: dict[str, str]     # version → full prompt text
    holdout_examples: list[ExampleSummary]
```

### ReviewResult (LLM Output)

The LLM emits `ReviewResult` as a JSON object matching this schema. The system prompt instructs the LLM to produce valid JSON; the code layer parses and validates via Pydantic.

```python
class RankedCandidate(BaseModel):
    version: str
    rank: int
    rationale: str

class EditDirective(BaseModel):
    directive_id: str
    target_version: str
    block_type: str             # "rule" | "example" | "output_schema" | "assembly_policy"
    block_identifier: str       # "Rule 2" | "Example 5" | "Output Schema"
    granularity: str            # "macro" | "micro"
    directive: str
    priority: str               # "high" | "medium" | "low"

class PromotionDecision(BaseModel):
    version: str
    decision: str               # "promote" | "prune" | "refine"
    reason: str

class LoopSignal(BaseModel):
    action: str                 # "refine" | "exit"
    reason: str
    suggested_budget: int | None = None       # Additional rounds to grant (delta, not absolute)
    suggested_mutation_mode: str | None = None # "targeted" | "exploratory"

class RegressionFlag(BaseModel):
    version: str
    metric: str
    previous_value: float
    current_value: float
    severity: str               # "warning" | "block"

class DirectiveOutcome(BaseModel):
    prior_directive_id: str
    was_attempted: bool
    outcome: str                # "improved" | "no_effect" | "regressed"

class ReviewResult(BaseModel):
    candidate_ranking: list[RankedCandidate]
    edit_directives: list[EditDirective]
    promotion_decisions: list[PromotionDecision]
    loop_signal: LoopSignal
    regression_guards: list[RegressionFlag]
    directive_history_update: list[DirectiveOutcome]
```

### Precedence Rules

- `loop_signal` is authoritative for loop continuation. If `loop_signal.action = "refine"` but all candidates are "prune", the Prompt Builder must generate new candidates from the existing Pareto front (not from pruned candidates).
- `regression_guards` with `severity="block"` prevent promotion only. A blocked candidate can still be marked "refine" in `promotion_decisions`.
- `suggested_budget` is a delta: "grant N more rounds beyond what `advance_round` would allow." The orchestrator adds this to the remaining budget, capped by `max_rounds`.

## Code Pre-Processor Architecture

Lives in `odysseus/agents/review_preprocessor.py` — pure functions, no external dependencies beyond stdlib (`difflib` for text similarity).

### Computation Functions

| Function | Inputs | Output | Description |
|----------|--------|--------|-------------|
| `build_candidate_comparisons()` | ScoreReports for round candidates + Pareto front | `list[CandidateAnalysis]` | Cross-candidate and cross-front metric deltas |
| `extract_per_class_recall()` | Per-example results from current + historical ScoreReports | `dict[str, ClassRecallEntry]` | Per-route recall with trends and regression flags |
| `compute_diversity_metrics()` | Prompt texts for front candidates, mutation log | `DiversityMetrics` | Example overlap, prompt similarity (difflib), mutation type distribution. Pairwise comparison is O(N^2) on front size; expected front size is <15 candidates in 2D Pareto, so this is negligible. |
| `compute_diminishing_returns()` | Score trajectory from SearchState | `DiminishingReturns` | Improvement trend, stagnation flag |
| `correlate_mutations()` | Mutation log + score history | `MutationHistory` | Which mutation types helped, hurt, or haven't been tried |
| `compute_oracle_metrics()` | ScoreReport metrics (oracle_cost_reduction, oracle_quality_reduction, cost_reduction, quality_reduction) | `OracleMetrics` | Captured ratios vs theoretical ceiling. Returns `None` for captured ratios if oracle reduction is 0.0 (no routing benefit possible). |

### Orchestrator

```python
def build_review_briefing(
    search_state: SearchState,
    score_reports: dict[str, ScoreReport],          # Current round: version → report
    historical_reports: dict[int, dict[str, ScoreReport]],  # Past rounds: round_num → {version → report}
    prompt_texts: dict[str, str],
    mutation_log: list[MutationRecord],
    directive_history: list[DirectiveOutcome],
    holdout_examples: list[ExampleSummary],
) -> ReviewBriefing
```

`historical_reports` provides per-round ScoreReports needed for `ClassRecallEntry.trend` computation. The orchestrator accumulates these by persisting each round's reports to disk (see persistence layout below).

### File-Backed Persistence

```
outputs/<search_state_id>/
├── search_state.json           # Existing
├── pending_candidates.json     # Existing
├── directive_history.json      # NEW: list[DirectiveOutcome]
├── mutation_log.json           # NEW: list[MutationRecord]
└── round_reports/              # NEW: historical ScoreReports per round
    ├── round_1.json            # dict[str, ScoreReport] keyed by version
    ├── round_2.json
    └── ...
```

`holdout_examples` are loaded by the orchestrator from the rationale card set (via `holdout_rationale_card_set_path` in the pipeline context), projected to `ExampleSummary`.

## LLM Layer

### System Prompt

Located at `odysseus/agents/prompts/review_agent_system.md`, surfaced via MCP as `odysseus_review_agent()`.

**Prompt structure:**

1. **Role** — Prompt-program critic reviewing candidates from a routing optimization search
2. **Input contract** — ReviewBriefing field descriptions
3. **Output contract** — ReviewResult schema; LLM must emit valid JSON matching the schema
4. **Evaluation priorities** (ordered):
   1. Exploration vs exploitation balance — assess whether the search needs novelty or refinement (use diversity metrics, diminishing returns, oracle gap)
   2. Oracle gap analysis — how much headroom remains via captured ratios
   3. Per-candidate assessment — edit directives, regression flags, promotion/refine/prune
   4. Regression guards — block promotion only, not exploration
5. **Anti-patterns:**
   - Don't apply regression guards to block exploration — only block promotion
   - Don't suggest only micro-edits when diversity is collapsing or oracle gap is large
   - Don't re-suggest mutations from ineffective history
   - Don't exit if oracle captured ratios show significant remaining headroom and untried mutation types exist
   - Don't prune a structurally novel candidate just because it regressed — mark it for refinement with targeted fix directives
6. **Worked examples** — 2-3 ReviewBriefing → ReviewResult examples

### Edit Directive Granularity

| Granularity | Examples |
|------------|----------|
| **Macro** | Rewrite block, add/remove rule, change example set, swap assembly policy |
| **Micro** | Lexical pruning, shorter constraint wording, stronger output contract |

### Promotion Decisions

| Decision | Meaning | Regression tolerance |
|----------|---------|---------------------|
| **Promote** | Graduate to full-dev eval | None — no regressions allowed |
| **Refine** | Keep in search pool with specific fix directives | Tolerated — promising structure despite metric dips |
| **Prune** | Remove from search — dominated and no structural novelty | N/A |

## MCP Surface

| Type | Name | Description |
|------|------|-------------|
| Prompt | `odysseus_review_agent()` | Review Agent system prompt |
| Tool | `build_review_briefing_tool()` | Runs code pre-processor, returns ReviewBriefing |
| Tool | `record_directive_outcomes_tool()` | Updates directive history after Prompt Builder acts |
| Resource | `odysseus://agents/review-agent/guidelines` | Review criteria reference |

## Integration with Prompt Builder

### Prompt Builder Reads ReviewResult

The Prompt Builder receives from the ReviewResult:
- `edit_directives` — specific block-level instructions to follow
- `loop_signal.suggested_mutation_mode` — targeted or exploratory
- `promotion_decisions` — which candidates to use as parents (only "promote" or "refine")

The Prompt Builder interprets directives — it is not mechanically executing them. But it records what it actually did in the mutation log, enabling directive effectiveness tracking.

### Prompt Builder Emits MutationRecord

New output contract addition for the Prompt Builder (requires Prompt Builder spec update):

```python
class MutationRecord(BaseModel):
    child_version: str
    parent_version: str
    mutation_type: str          # "example_swap" | "rule_edit" | "schema_change" | "rule_add" | "rule_remove" | "assembly_policy"
    description: str
    directive_ids: list[str] | None = None  # Which Review Agent directives this addressed
```

### Directive History Update Flow

After each round's eval results:
1. Orchestrator matches `directive_ids` in MutationRecords to prior EditDirectives
2. Calls `record_directive_outcomes_tool()` with outcome per directive
3. Next ReviewBriefing includes updated `mutation_history` with effectiveness data

## Loop Control & Exit Conditions

### Decision Matrix

| `advance_round` says | Review Agent says | Result |
|---------------------|-------------------|--------|
| Not converged | Refine | Continue |
| Not converged | Exit (diversity collapse / oracle ceiling) | **Exit** — Review Agent overrides |
| Converged (stagnation) | Refine (untried macro edit) | **Continue** — Review Agent overrides, grants budget |
| Converged (max rounds) | Refine | **Exit** — hard cap not overridable |

### Exit Reasons

| Reason | Signal |
|--------|--------|
| `dominance_threshold_met` | Oracle captured ratios above threshold, diminishing returns |
| `diversity_collapse` | Front has converged, no novel mutations left |
| `budget_exhausted` | Review Agent's suggested budget rounds used up |
| `regression_deadlock` | Every mutation regresses, no viable path forward |

### On Exit

The Review Agent emits:
- Final candidate ranking with recommended winner
- Search summary (what worked, what didn't) — feeds into Final Reporting Agent
