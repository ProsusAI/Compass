# Final Reporting Agent Design

## Overview

The Final Reporting Agent is the terminal agent in the Odysseus pipeline. It synthesises all upstream artifacts into a structured 8-section report that explains what the final prompt does, why it works, how it was arrived at, and how much confidence to place in the results. The report is written to serve two audiences: a technical practitioner deploying the prompt, and a non-technical stakeholder reviewing the outcome.

The agent is **hybrid**: a code pre-processor assembles a `ReportBriefing` from all upstream artifacts (including triggering and consuming the holdout evaluation), and an LLM writer receives the briefing and produces the final Markdown report. This follows the same pattern as the Review Agent.

## Position in Pipeline

```
Review Agent signals exit (loop_signal.action = "exit")
  → optimize_routing_prompt orchestration logic stores LoopHistory in context
  → Final Reporting Agent activated via odysseus_final_reporting_agent() prompt
      LLM calls build_report_briefing_tool():
        1. Filter holdout dataset (exclude few-shot examples via filter_holdout_dataset())
        2. Run holdout evaluation via EvalRunnerAgent directly
        3. Compute per-class results, threshold assessment, confidence factors
        4. Assemble and return ReportBriefing
      LLM writes 8-section Markdown report → outputs/final_report.md
      LLM surfaces executive summary in conversation
  → Pipeline complete
```

The agent does not mutate `SearchState` and is read-only with respect to all upstream pipeline state.

## Prerequisites

### 1. Prompt Builder Contract Extension

The Prompt Builder must emit `few_shot_example_ids: list[str]` as a new pipeline context key alongside `prompt_version`. This lists the example IDs embedded in the current prompt version as few-shot examples. The code layer uses this to call `filter_holdout_dataset()` before running holdout evaluation, preventing leakage.

This key must be set for every round so the Run Controller can record it in `LoopIteration`. The final round's value is used by the Reporting Agent.

### 2. User Input Agent Contract Extension

The User Input Agent must set two new direct pipeline context keys: `target_metric: str` and `target_value: float`. These are extracted from the user's problem description during the input conversation and stored alongside `validated_input_report_path`. They are required for deterministic threshold assessment in the code layer.

This is a minimal extension to the User Input Agent's context writes — no file format changes are required.

### 3. `run_holdout_eval` MCP Tool Replacement

The existing `run_holdout_eval` stub in `mcp.py` is superseded by `build_report_briefing_tool()`, which handles holdout filtering and evaluation as part of briefing assembly. The `run_holdout_eval` stub should be **removed** to avoid confusion — it exposes incomplete functionality (no filtering step) that would produce contaminated results if called directly. Any MCP client that previously referenced `run_holdout_eval` should use `build_report_briefing_tool()` instead.

### 4. `LoopSignal.reason` Controlled Vocabulary

`LoopSignal.reason` in the Review Agent spec is currently a free-text `str`. To enable reliable `loop_exit_reason` population in `ConfidenceFactors`, `LoopSignal.reason` must use a controlled vocabulary. The Review Agent spec's Exit Reasons table defines four values — these must be promoted to a `Literal` type constraint:

```python
reason: Literal[
    "dominance_threshold_met",
    "budget_exhausted",
    "diversity_collapse",
    "regression_deadlock",
]
```

The Review Agent spec must be updated to enforce this.

## Loop History Accumulation

`loop_history: list[LoopIteration]` is accumulated by the **orchestration logic inside `optimize_routing_prompt` in `mcp.py`** — not by a new agent or class. At the end of each refinement round, after the Review Agent emits its `ReviewResult`, the orchestration logic appends a `LoopIteration` to a local list. When the loop exits, it stores the list as `loop_history` in the pipeline context before invoking the Reporting Agent.

## Context Keys

### Consumed

| Key | Type | Set By |
|-----|------|--------|
| `loop_history` | `list[LoopIteration]` | `optimize_routing_prompt` orchestration (new) |
| `few_shot_example_ids` | `list[str]` | Prompt Builder (new contract) |
| `target_metric` | `str` | User Input Agent (new contract) |
| `target_value` | `float` | User Input Agent (new contract) |
| `holdout_jsonl_path` | `str` | Routing Analysis Agent |
| `holdout_rationale_card_set_path` | `str` | Routing Analysis Agent |
| `dev_jsonl_path` | `str` | Routing Analysis Agent |
| `split_report_path` | `str` | Routing Analysis Agent |
| `validated_input_report_path` | `str` | User Input Agent |
| `data_quality_report` | `DataQualityReport` | Data Validation Agent |
| `routing_context` | `RoutingContext` | Data Validation Agent |
| `backend` | `str` | MCP tool param |
| `config_path` | `str` | MCP tool param |

### Written

| Key | Type | Description |
|-----|------|-------------|
| `final_report_path` | `str` | Path to the written Markdown report |

## Data Models

All models use Pydantic `BaseModel` for consistency with the existing codebase.

### `LoopIteration` (accumulated in `loop_history`)

One entry per refinement round, appended by `optimize_routing_prompt` orchestration after each `ReviewResult`.

```python
class LoopIteration(BaseModel):
    round: int
    prompt_version: str
    few_shot_example_ids: list[str]       # from Prompt Builder context key at time of round
    score_report: ScoreReport
    review_result: ReviewResult
    key_mutation_description: str         # short summary of the change made this round
```

### `ReportBriefing` (Code Layer Output → LLM Input)

```python
class PerClassResult(BaseModel):
    route: str
    recall: float
    precision: float | None
    support: int

class HoldoutSummary(BaseModel):
    score_report: ScoreReport
    filtered_example_count: int           # example count after few-shot filtering
    per_class_results: list[PerClassResult]

class ThresholdAssessment(BaseModel):
    target_metric: str
    target_value: float
    achieved_value: float
    threshold_met: bool
    gap: float                            # achieved - target (negative = missed)

class ConfidenceFactors(BaseModel):
    holdout_sample_size: int              # = HoldoutSummary.filtered_example_count
    dev_holdout_gap: float                # holdout primary metric - best dev primary metric
    loop_exit_reason: str                 # taken verbatim from last LoopIteration.review_result.loop_signal.reason
                                          # expected values: "dominance_threshold_met" | "budget_exhausted" |
                                          #                  "diversity_collapse" | "regression_deadlock"
    data_quality_warnings: list[str]      # extracted from DataQualityReport

class IterationRow(BaseModel):
    round: int
    prompt_version: str
    primary_metric: float
    delta_vs_previous: float | None       # None for round 1
    loop_signal: str                      # "refine" | "exit"
    key_change: str

class ReportBriefing(BaseModel):
    # Identity
    final_prompt_version: str
    final_prompt_text: str
    total_rounds: int

    # Upstream artifacts (content, not paths)
    validated_input_report: str           # Markdown content read from validated_input_report_path
    routing_context: RoutingContext
    data_quality_report: DataQualityReport

    # Performance
    best_dev_score_report: ScoreReport    # LoopIteration with highest primary_metric score
    holdout_summary: HoldoutSummary
    threshold_assessment: ThresholdAssessment

    # History and confidence
    iteration_history: list[IterationRow]
    confidence_factors: ConfidenceFactors

    # Reproducibility
    backend: str
    metric_configs: list[MetricConfig]    # from RunConfig.from_yaml(config_path).metrics
    dev_split_path: str                   # = dev_jsonl_path from context
    holdout_split_path: str               # the filtered path used for holdout eval
    run_timestamp: datetime
```

There is no structured output model — the LLM writes Markdown directly to disk.

## Code Preprocessor

Lives in `odysseus/agents/reporting_preprocessor.py`. Pure functions, no external dependencies beyond stdlib. The `build_report_briefing_tool()` MCP tool is the orchestrator that invokes these functions and calls `EvalRunnerAgent` directly — the preprocessor functions themselves do not invoke MCP tools.

### Functions

| Function | Inputs | Output | Notes |
|----------|--------|--------|-------|
| `filter_holdout_dataset()` | `holdout_jsonl_path: str`, `exclude_ids: list[str]` | `str` (filtered path) | **Already implemented** in `odysseus/agents/prompt_builder_holdout_filter.py`. Called by `build_report_briefing_tool()` before running holdout eval. |
| `compute_per_class_results()` | holdout `ScoreReport`, holdout JSONL path | `list[PerClassResult]` | Reads `ScoreReport.results_path` + expected routes from JSONL; computes per-route recall, precision, support |
| `compute_threshold_assessment()` | `target_metric: str`, `target_value: float`, holdout `ScoreReport` | `ThresholdAssessment` | Looks up `achieved_value` from `ScoreReport.metrics[target_metric]`; computes gap |
| `compute_confidence_factors()` | `holdout_summary: HoldoutSummary`, best dev `ScoreReport`, `list[LoopIteration]`, `DataQualityReport` | `ConfidenceFactors` | `holdout_sample_size = holdout_summary.filtered_example_count`; dev/holdout gap from primary metric; exit reason from last `LoopIteration.review_result.loop_signal.reason` |
| `build_iteration_history()` | `list[LoopIteration]`, `target_metric: str` | `list[IterationRow]` | Flattens loop history into table rows; `primary_metric = score_report.metrics[target_metric]`; `delta_vs_previous = None` for round 1 |
| `select_best_dev_score_report()` | `list[LoopIteration]`, `target_metric: str` | `ScoreReport` | Returns the `ScoreReport` from the `LoopIteration` with the highest `score_report.metrics[target_metric]` value |

### `build_report_briefing_tool()` Orchestration (in `mcp.py`)

`build_report_briefing_tool()` is the single MCP-exposed entry point. Its internal sequence:

```python
async def build_report_briefing_tool(context: dict) -> ReportBriefing:
    # 1. Filter holdout dataset to exclude few-shot examples
    filtered_holdout_path = filter_holdout_dataset(
        holdout_jsonl_path=context["holdout_jsonl_path"],
        exclude_ids=context["few_shot_example_ids"],
    )

    # 2. Run holdout evaluation via EvalRunnerAgent directly
    eval_context = {**context, "data_source": filtered_holdout_path, "data_split": "holdout"}
    eval_result = await EvalRunnerAgent().run(eval_context)
    holdout_score_report: ScoreReport = eval_result[ScoreReport.CONTEXT_KEY]

    # 3. Assemble HoldoutSummary
    per_class = compute_per_class_results(holdout_score_report, filtered_holdout_path)
    filtered_count = sum(1 for _ in open(filtered_holdout_path))
    holdout_summary = HoldoutSummary(
        score_report=holdout_score_report,
        filtered_example_count=filtered_count,
        per_class_results=per_class,
    )

    # 4. Assemble remaining briefing fields
    loop_history: list[LoopIteration] = context["loop_history"]
    target_metric: str = context["target_metric"]
    target_value: float = context["target_value"]

    return ReportBriefing(
        final_prompt_version=context["prompt_version"],
        final_prompt_text=FilePromptManager(...).load(context["prompt_version"]),
        total_rounds=len(loop_history),
        validated_input_report=Path(context["validated_input_report_path"]).read_text(),
        routing_context=context["routing_context"],
        data_quality_report=context["data_quality_report"],
        best_dev_score_report=(best_dev := select_best_dev_score_report(loop_history, target_metric)),
        holdout_summary=holdout_summary,
        threshold_assessment=compute_threshold_assessment(target_metric, target_value, holdout_score_report),
        iteration_history=build_iteration_history(loop_history, target_metric),
        confidence_factors=compute_confidence_factors(holdout_summary, best_dev, loop_history, context["data_quality_report"]),
        backend=context["backend"],
        metric_configs=RunConfig.from_yaml(context["config_path"]).metrics,
        dev_split_path=context["dev_jsonl_path"],
        holdout_split_path=filtered_holdout_path,
        run_timestamp=datetime.now(UTC),
    )
```

## Report Structure

The LLM writes all 8 sections in a single pass from the `ReportBriefing`.

| # | Section | Primary Audience | Driven By |
|---|---------|-----------------|-----------|
| 1 | **Executive Summary** | Non-technical | `ThresholdAssessment`, final primary metric, total rounds, loop exit reason |
| 2 | **Data Profile** | Both | `DataQualityReport`, dev/holdout sample sizes from `HoldoutSummary.filtered_example_count` and dev split |
| 3 | **Routing Logic Summary** | Technical | `final_prompt_text`, `RoutingContext.routes` — plain-English explanation of what the prompt does |
| 4 | **Iteration History** | Technical | `iteration_history` → rendered as Markdown table: round, version, score, delta, decision, key change |
| 5 | **Holdout Performance** | Technical | `HoldoutSummary.per_class_results`, failure cases from `ScoreReport.errors`, dev vs holdout comparison |
| 6 | **Confidence Assessment** | Both | `ConfidenceFactors` — explicit reasoning about trust level given sample size, dev/holdout gap, exit reason, data quality warnings |
| 7 | **Deployment Guidance** | Technical | Failure patterns from section 5, `DataQualityReport` warnings, `RoutingContext.routes` — known failure modes, monitoring recommendations, future data collection priorities |
| 8 | **Reproducibility Block** | Technical | `backend`, `metric_configs`, `final_prompt_version`, `dev_split_path`, `holdout_split_path`, `run_timestamp` |

### Threshold Not Reached

If `ThresholdAssessment.threshold_met = False`:
- Section 1 **opens** with an explicit statement of the shortfall (achieved value, target value, gap) before any other content
- Section 6 explains the contributing factors (exit reason, dev/holdout gap, data quality warnings)
- The shortfall is not mentioned in sections 2, 3, 4, 5, 7, or 8

## LLM Layer

### System Prompt

Located at `odysseus/agents/prompts/reporting_system.md`, surfaced via MCP as `odysseus_final_reporting_agent()`.

**Prompt structure:**

1. **Role** — Report writer synthesising a completed routing optimisation run into a structured audit document
2. **Input contract** — `ReportBriefing` field descriptions
3. **Output contract** — Write Markdown to `outputs/final_report.md`; surface section 1 (Executive Summary only) in the conversation response; emit `final_report_path` as the context output
4. **Section-by-section instructions** — purpose, target audience, required inputs, and conditional rules per section
5. **Writing style** — see below
6. **Worked example** — one abbreviated `ReportBriefing` → report excerpt illustrating section 1 and section 6

### Writing Style

Embedded in the system prompt and applies across all sections:

- **Accurate** — state results as they are, neither undersell nor oversell
- **Direct** — plain language for sections 1, 2, 6; technical precision for sections 4, 5, 8
- **Honest about limitations** — surface any concern a practitioner would need to know: low-support routes, large dev/holdout gap, data quality issues, failure modes
- **Single mention** — each concern is raised once, with the specific number or factor that drives it, then not repeated
- **No hedging** — uncertainty is stated explicitly ("confidence is limited because holdout n=42") rather than softened
- **Not pessimistic** — if results are good, say so plainly; raise concerns where present without amplifying them

System prompt instruction: *"Do not soften concerns. Do not amplify them. State each limitation once, with the specific number or factor that drives it, and move on."*

## MCP Surface

| Type | Name | Description |
|------|------|-------------|
| Prompt | `odysseus_final_reporting_agent()` | Reporting Agent system prompt |
| Tool | `build_report_briefing_tool()` | Runs code pre-processor + holdout eval; returns `ReportBriefing` |

## Error Handling

Errors follow the `EvalRunnerAgent` pattern: `{"error": {"category": ..., "detail": ...}}`.

### Code Layer Errors

| Category | Condition | Behaviour |
|----------|-----------|-----------|
| `missing_context_key` | `loop_history`, `few_shot_example_ids`, `target_metric`, or `target_value` absent | Return error immediately, pipeline stops |
| `holdout_eval_failed` | `EvalRunnerAgent.run()` failed or returned error | Return error, surface partial context for debugging |
| `target_metric_not_in_scores` | `target_metric` key absent from `ScoreReport.metrics` | Return error; indicates metric config mismatch |
| `report_write_failed` | Could not write to `outputs/final_report.md` | Return error with any partial output captured |

### LLM Layer Failures

If the LLM produces an incomplete report, the agent surfaces the partial output path and an error message. There is no retry loop — this is a terminal agent.

## Testing

### Unit Tests (`tests/`)

The preprocessor functions are pure and unit-testable with fixtures:

- `test_compute_per_class_results` — given mock holdout JSONL and EvalResults, asserts correct per-route recall/precision/support
- `test_compute_threshold_assessment` — threshold met case (gap ≥ 0) and threshold missed case (gap < 0)
- `test_compute_confidence_factors` — various exit reason + gap + sample size combinations
- `test_build_iteration_history` — verifies `delta_vs_previous = None` for round 1, correct deltas for subsequent rounds
- `test_select_best_dev_score_report` — returns the iteration with highest primary metric, not just the last round

### Integration Test Scenarios (`tests/scenarios/`)

**`54_reporting_threshold_met.md`** — Happy path. The loop exited on `dominance_threshold_met`. The report should confirm the threshold was met in section 1, include a complete iteration history table, and present holdout performance with per-class breakdown.

Verification criteria:
- [ ] `build_report_briefing_tool` was called with correct context keys including `few_shot_example_ids`
- [ ] `filter_holdout_dataset` was called with non-empty `exclude_ids` before holdout eval
- [ ] Holdout eval was run on the filtered path (not the original `holdout_jsonl_path`)
- [ ] Section 1 states the threshold was met with the achieved metric value
- [ ] Section 4 contains a Markdown table with one row per loop iteration
- [ ] Section 8 contains the exact backend, prompt version, and data split used
- [ ] `final_report_path` is written to context

**`55_reporting_threshold_missed.md`** — Loop hit `budget_exhausted` without meeting the target. The report must open section 1 with an explicit shortfall statement, and section 6 must explain the contributing confidence factors.

Verification criteria:
- [ ] Section 1 opens with an explicit shortfall statement containing the achieved value, target value, and gap
- [ ] Section 6 contains explicit confidence reasoning referencing `budget_exhausted` as the exit reason
- [ ] The shortfall is not mentioned in sections 2, 3, 4, 5, 7, or 8
- [ ] Report is otherwise complete with all 8 sections present
- [ ] `final_report_path` is written to context
