# MCP Stage-Scoped Tool Filtering & Code Reorganization — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce orchestrator tool surface from 23 to 4 via session-scoped MCP filtering, and reorganize code into stage-aligned modules.

**Architecture:** Split monolithic `mcp.py` into stage-specific tool files under `mcp/`. Reorganize flat `agents/` into subdirectories matching pipeline stages. Add session-scoped `active_stage` to MCP server that gates `tools/list` responses.

**Tech Stack:** Python 3.11+, FastMCP, uv, pytest, ruff, pyright

**Spec:** `docs/specs/2026-03-30-mcp-stage-scoping-and-code-reorganization-design.md`

---

## Chunk 1: Reorganize `agents/` into subdirectories

### Task 1: Create `agents/pipeline/` subdirectory

**Files:**
- Move: `odysseus/agents/pipeline_status.py` → `odysseus/agents/pipeline/status.py`
- Move: `odysseus/agents/pipeline_guards.py` → `odysseus/agents/pipeline/guards.py`
- Create: `odysseus/agents/pipeline/__init__.py`

- [ ] **Step 1: Create directory and `__init__.py`**

```bash
mkdir -p odysseus/agents/pipeline
```

Create `odysseus/agents/pipeline/__init__.py`:
```python
"""Pipeline orchestration — status detection and artifact guards."""

from __future__ import annotations

from odysseus.agents.pipeline.guards import check_artifacts, require_artifacts
from odysseus.agents.pipeline.status import discover_runs, get_pipeline_status

__all__ = [
    "check_artifacts",
    "discover_runs",
    "get_pipeline_status",
    "require_artifacts",
]
```

- [ ] **Step 2: Move files**

```bash
git mv odysseus/agents/pipeline_status.py odysseus/agents/pipeline/status.py
git mv odysseus/agents/pipeline_guards.py odysseus/agents/pipeline/guards.py
```

- [ ] **Step 3: Update internal imports in moved files**

`pipeline/status.py` and `pipeline/guards.py` have no intra-agents imports — no changes needed inside them.

- [ ] **Step 4: Update consumers — `odysseus/mcp.py`**

Change:
```python
from odysseus.agents.pipeline_guards import check_artifacts
from odysseus.agents.pipeline_status import get_pipeline_status as _get_pipeline_status
```
To:
```python
from odysseus.agents.pipeline.guards import check_artifacts
from odysseus.agents.pipeline.status import get_pipeline_status as _get_pipeline_status
```

- [ ] **Step 5: Update consumers — test files**

`tests/test_pipeline_guards.py` — change:
```python
from odysseus.agents.pipeline_guards import check_artifacts, require_artifacts
```
To:
```python
from odysseus.agents.pipeline.guards import check_artifacts, require_artifacts
```

`tests/test_pipeline_status.py` — change:
```python
from odysseus.agents.pipeline_status import discover_runs, get_pipeline_status
```
To:
```python
from odysseus.agents.pipeline.status import discover_runs, get_pipeline_status
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_pipeline_guards.py tests/test_pipeline_status.py -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add odysseus/agents/pipeline/
git add -u
git commit -m "refactor(agents): move pipeline modules to agents/pipeline/"
```

---

### Task 2: Create `agents/data_validation/` subdirectory

**Files:**
- Move: `odysseus/agents/data_ingestion_detect.py` → `odysseus/agents/data_validation/detect.py`
- Move: `odysseus/agents/data_ingestion_transform.py` → `odysseus/agents/data_validation/transform.py`
- Move: `odysseus/agents/data_validation_checks.py` → `odysseus/agents/data_validation/checks.py`
- Move: `odysseus/agents/data_validation_format.md` → `odysseus/agents/data_validation/format.md`
- Move: `odysseus/agents/data_validation_output.md` → `odysseus/agents/data_validation/output.md`
- Create: `odysseus/agents/data_validation/__init__.py`

- [ ] **Step 1: Create directory and `__init__.py`**

```bash
mkdir -p odysseus/agents/data_validation
```

Create `odysseus/agents/data_validation/__init__.py`:
```python
"""Data validation — format detection, field mapping, quality checks."""

from __future__ import annotations

from odysseus.agents.data_validation.checks import (
    DataQualityReport,
    LabelDistribution,
    QueryLengthDistribution,
    SchemaFinding,
    TierDistribution,
    TierVolume,
    VolumeAssessment,
    check_label_distribution,
    check_query_length_distribution,
    check_schema_conformance,
    check_volume_adequacy,
    run_all_checks,
)
from odysseus.agents.data_validation.detect import (
    DetectionResult,
    detect_and_parse,
)
from odysseus.agents.data_validation.transform import (
    TransformResult,
    transform_dataset,
)

__all__ = [
    "DataQualityReport",
    "DetectionResult",
    "LabelDistribution",
    "QueryLengthDistribution",
    "SchemaFinding",
    "TierDistribution",
    "TierVolume",
    "TransformResult",
    "VolumeAssessment",
    "check_label_distribution",
    "check_query_length_distribution",
    "check_schema_conformance",
    "check_volume_adequacy",
    "detect_and_parse",
    "run_all_checks",
    "transform_dataset",
]
```

- [ ] **Step 2: Move files**

```bash
git mv odysseus/agents/data_ingestion_detect.py odysseus/agents/data_validation/detect.py
git mv odysseus/agents/data_ingestion_transform.py odysseus/agents/data_validation/transform.py
git mv odysseus/agents/data_validation_checks.py odysseus/agents/data_validation/checks.py
git mv odysseus/agents/data_validation_format.md odysseus/agents/data_validation/format.md
git mv odysseus/agents/data_validation_output.md odysseus/agents/data_validation/output.md
```

- [ ] **Step 3: Update internal imports in moved files**

`data_validation/transform.py` imports from `detect.py` — change:
```python
from odysseus.agents.data_ingestion_detect import _parse_csv, detect_and_parse
```
To:
```python
from odysseus.agents.data_validation.detect import _parse_csv, detect_and_parse
```

`data_validation/checks.py` has no intra-agents imports — no changes needed.
`data_validation/detect.py` has no intra-agents imports — no changes needed.

- [ ] **Step 4: Update consumers — `odysseus/mcp.py`**

Change:
```python
from odysseus.agents.data_ingestion_detect import detect_and_parse
from odysseus.agents.data_ingestion_transform import transform_dataset as _do_transform
from odysseus.agents.data_validation_checks import run_all_checks
```
To:
```python
from odysseus.agents.data_validation.detect import detect_and_parse
from odysseus.agents.data_validation.transform import transform_dataset as _do_transform
from odysseus.agents.data_validation.checks import run_all_checks
```

Also update any resource loader paths that reference `agents/data_validation_format.md` or `agents/data_validation_output.md` to use `agents/data_validation/format.md` and `agents/data_validation/output.md`.

- [ ] **Step 5: Update consumers — test files**

`tests/test_data_ingestion_detect.py` — change:
```python
from odysseus.agents.data_ingestion_detect import (
    DetectionResult,
    detect_and_parse,
)
```
To:
```python
from odysseus.agents.data_validation.detect import (
    DetectionResult,
    detect_and_parse,
)
```

`tests/test_data_ingestion_transform.py` — change:
```python
from odysseus.agents.data_ingestion_transform import (
    TransformResult,
    _check_required_targets,
    _get_nested,
    _maybe_coerce_numeric,
    _set_nested,
    transform_dataset,
)
```
To:
```python
from odysseus.agents.data_validation.transform import (
    TransformResult,
    _check_required_targets,
    _get_nested,
    _maybe_coerce_numeric,
    _set_nested,
    transform_dataset,
)
```

`tests/test_data_validation_checks.py` — change:
```python
from odysseus.agents.data_validation_checks import (...)
```
To:
```python
from odysseus.agents.data_validation.checks import (...)
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_data_ingestion_detect.py tests/test_data_ingestion_transform.py tests/test_data_validation_checks.py -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add odysseus/agents/data_validation/
git add -u
git commit -m "refactor(agents): move data validation modules to agents/data_validation/"
```

---

### Task 3: Create `agents/routing_analysis/` subdirectory

**Files:**
- Move: `odysseus/agents/routing_rationale_models.py` → `odysseus/agents/routing_analysis/models.py`
- Move: `odysseus/agents/routing_rationale_registry.py` → `odysseus/agents/routing_analysis/registry.py`
- Move: `odysseus/agents/routing_rationale_checks.py` → `odysseus/agents/routing_analysis/checks.py`
- Move: `odysseus/agents/routing_rationale_checks_deterministic.py` → `odysseus/agents/routing_analysis/checks_deterministic.py`
- Move: `odysseus/agents/stratified_split.py` → `odysseus/agents/routing_analysis/split.py`
- Create: `odysseus/agents/routing_analysis/__init__.py`

- [ ] **Step 1: Create directory and `__init__.py`**

```bash
mkdir -p odysseus/agents/routing_analysis
```

Create `odysseus/agents/routing_analysis/__init__.py`:
```python
"""Routing analysis — rationale models, vocabulary registry, validation, stratified split."""

from __future__ import annotations

from odysseus.agents.routing_analysis.checks import (
    RationaleCheckResult,
    check_ambiguity_tag_membership,
    check_card_completeness,
    check_cluster_thresholds,
    check_exclusion_coverage,
    check_exclusion_format,
    check_pruning_cleanup,
    check_registry_consistency,
    check_required_fields,
    check_vocabulary_membership,
    find_orphaned_examples,
    validate_rationale_card_set,
)
from odysseus.agents.routing_analysis.checks_deterministic import (
    validate_deterministic,
)
from odysseus.agents.routing_analysis.models import (
    RationaleCard,
    RationaleCardSet,
    RouteDefinition,
    RouteExclusion,
    RouteOrdering,
    RoutingContext,
    RoutingDimension,
    SeedVocabulary,
    VocabularyEntry,
    VocabularyRegistry,
)
from odysseus.agents.routing_analysis.registry import (
    RegistryMergeError,
    compute_dataset_hash,
    create_seed_registry,
    load_registry,
    merge_registry,
    prune_registry,
    resolve_registry,
    save_registry,
)
from odysseus.agents.routing_analysis.split import (
    SplitMismatchError,
    SplitReport,
    stratified_split,
)

__all__ = [
    "RationaleCard",
    "RationaleCardSet",
    "RationaleCheckResult",
    "RegistryMergeError",
    "RouteDefinition",
    "RouteExclusion",
    "RouteOrdering",
    "RoutingContext",
    "RoutingDimension",
    "SeedVocabulary",
    "SplitMismatchError",
    "SplitReport",
    "VocabularyEntry",
    "VocabularyRegistry",
    "check_ambiguity_tag_membership",
    "check_card_completeness",
    "check_cluster_thresholds",
    "check_exclusion_coverage",
    "check_exclusion_format",
    "check_pruning_cleanup",
    "check_registry_consistency",
    "check_required_fields",
    "check_vocabulary_membership",
    "compute_dataset_hash",
    "create_seed_registry",
    "find_orphaned_examples",
    "load_registry",
    "merge_registry",
    "prune_registry",
    "resolve_registry",
    "save_registry",
    "stratified_split",
    "validate_deterministic",
    "validate_rationale_card_set",
]
```

- [ ] **Step 2: Move files**

```bash
git mv odysseus/agents/routing_rationale_models.py odysseus/agents/routing_analysis/models.py
git mv odysseus/agents/routing_rationale_registry.py odysseus/agents/routing_analysis/registry.py
git mv odysseus/agents/routing_rationale_checks.py odysseus/agents/routing_analysis/checks.py
git mv odysseus/agents/routing_rationale_checks_deterministic.py odysseus/agents/routing_analysis/checks_deterministic.py
git mv odysseus/agents/stratified_split.py odysseus/agents/routing_analysis/split.py
```

- [ ] **Step 3: Update internal imports in moved files**

`routing_analysis/checks.py` — change:
```python
from odysseus.agents.routing_rationale_models import (
    RationaleCard, RationaleCardSet, RoutingContext, VocabularyRegistry,
)
```
To:
```python
from odysseus.agents.routing_analysis.models import (
    RationaleCard, RationaleCardSet, RoutingContext, VocabularyRegistry,
)
```

`routing_analysis/checks_deterministic.py` — change:
```python
from odysseus.agents.routing_rationale_checks import (
    RationaleCheckResult, check_ambiguity_tag_membership, check_card_completeness,
    check_cluster_thresholds, check_exclusion_coverage, check_exclusion_format,
    check_pruning_cleanup, check_required_fields, check_vocabulary_membership,
    find_orphaned_examples,
)
from odysseus.agents.routing_rationale_models import (RationaleCardSet, RoutingContext)
```
To:
```python
from odysseus.agents.routing_analysis.checks import (
    RationaleCheckResult, check_ambiguity_tag_membership, check_card_completeness,
    check_cluster_thresholds, check_exclusion_coverage, check_exclusion_format,
    check_pruning_cleanup, check_required_fields, check_vocabulary_membership,
    find_orphaned_examples,
)
from odysseus.agents.routing_analysis.models import (RationaleCardSet, RoutingContext)
```

`routing_analysis/registry.py` — change:
```python
from odysseus.agents.routing_rationale_models import VocabularyEntry, VocabularyRegistry
```
To:
```python
from odysseus.agents.routing_analysis.models import VocabularyEntry, VocabularyRegistry
```

`routing_analysis/split.py` — change:
```python
from odysseus.agents.routing_rationale_models import RationaleCardSet
from odysseus.agents.routing_rationale_registry import compute_dataset_hash
```
To:
```python
from odysseus.agents.routing_analysis.models import RationaleCardSet
from odysseus.agents.routing_analysis.registry import compute_dataset_hash
```

- [ ] **Step 4: Update consumers — `odysseus/mcp.py`**

Change:
```python
from odysseus.agents.routing_rationale_checks_deterministic import validate_deterministic
from odysseus.agents.routing_rationale_models import RationaleCardSet, RoutingContext, VocabularyRegistry
from odysseus.agents.routing_rationale_registry import create_seed_registry, prune_registry, resolve_registry
from odysseus.agents.stratified_split import stratified_split
```
To:
```python
from odysseus.agents.routing_analysis.checks_deterministic import validate_deterministic
from odysseus.agents.routing_analysis.models import RationaleCardSet, RoutingContext, VocabularyRegistry
from odysseus.agents.routing_analysis.registry import create_seed_registry, prune_registry, resolve_registry
from odysseus.agents.routing_analysis.split import stratified_split
```

- [ ] **Step 5: Update consumers — test files**

`tests/test_routing_rationale_models.py` — update all `from odysseus.agents.routing_rationale_models` to `from odysseus.agents.routing_analysis.models`.

`tests/test_routing_rationale_checks.py` — update `from odysseus.agents.routing_rationale_models` to `from odysseus.agents.routing_analysis.models` and `from odysseus.agents.routing_rationale_checks` to `from odysseus.agents.routing_analysis.checks`.

`tests/test_deterministic_validation.py` — update `from odysseus.agents.routing_rationale_checks_deterministic` to `from odysseus.agents.routing_analysis.checks_deterministic` and `from odysseus.agents.routing_rationale_models` to `from odysseus.agents.routing_analysis.models`.

`tests/test_routing_rationale_registry.py` — update `from odysseus.agents.routing_rationale_models` to `from odysseus.agents.routing_analysis.models` and `from odysseus.agents.routing_rationale_registry` to `from odysseus.agents.routing_analysis.registry`.

`tests/test_stratified_split.py` — update `from odysseus.agents.routing_rationale_models` to `from odysseus.agents.routing_analysis.models` and `from odysseus.agents.stratified_split` to `from odysseus.agents.routing_analysis.split`.

`tests/test_stratified_split_card_set.py` — same pattern as above.

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_routing_rationale_models.py tests/test_routing_rationale_checks.py tests/test_deterministic_validation.py tests/test_routing_rationale_registry.py tests/test_stratified_split.py tests/test_stratified_split_card_set.py -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add odysseus/agents/routing_analysis/
git add -u
git commit -m "refactor(agents): move routing analysis modules to agents/routing_analysis/"
```

---

### Task 4: Create `agents/prompt_builder/` subdirectory

**Files:**
- Move: `odysseus/agents/prompt_builder_search.py` → `odysseus/agents/prompt_builder/search.py`
- Move: `odysseus/agents/prompt_builder_search_ops.py` → `odysseus/agents/prompt_builder/search_ops.py`
- Move: `odysseus/agents/prompt_builder_holdout_filter.py` → `odysseus/agents/prompt_builder/holdout_filter.py`
- Move: `odysseus/agents/prompt_builder_best_practices.md` → `odysseus/agents/prompt_builder/best_practices.md`
- Move: `odysseus/agents/prompt_builder_conventions_claude.md` → `odysseus/agents/prompt_builder/conventions_claude.md`
- Move: `odysseus/agents/prompt_builder_conventions_openai.md` → `odysseus/agents/prompt_builder/conventions_openai.md`
- Move: `odysseus/agents/prompt_builder_conventions_openai_gpt-5-2.md` → `odysseus/agents/prompt_builder/conventions_openai_gpt-5-2.md`
- Create: `odysseus/agents/prompt_builder/__init__.py`

- [ ] **Step 1: Create directory and `__init__.py`**

```bash
mkdir -p odysseus/agents/prompt_builder
```

Create `odysseus/agents/prompt_builder/__init__.py`:
```python
"""Prompt builder — search state, candidate management, holdout filtering."""

from __future__ import annotations

from odysseus.agents.prompt_builder.holdout_filter import filter_holdout_dataset
from odysseus.agents.prompt_builder.search import (
    Candidate,
    RoundSummary,
    SearchState,
    dominates,
    select_best,
    update_pareto_front,
)
from odysseus.agents.prompt_builder.search_ops import (
    advance_round,
    get_search_state,
    init_search_state,
    record_eval_result,
    register_candidate,
    set_loop_phase,
)

__all__ = [
    "Candidate",
    "RoundSummary",
    "SearchState",
    "advance_round",
    "dominates",
    "filter_holdout_dataset",
    "get_search_state",
    "init_search_state",
    "record_eval_result",
    "register_candidate",
    "select_best",
    "set_loop_phase",
    "update_pareto_front",
]
```

- [ ] **Step 2: Move files**

```bash
git mv odysseus/agents/prompt_builder_search.py odysseus/agents/prompt_builder/search.py
git mv odysseus/agents/prompt_builder_search_ops.py odysseus/agents/prompt_builder/search_ops.py
git mv odysseus/agents/prompt_builder_holdout_filter.py odysseus/agents/prompt_builder/holdout_filter.py
git mv odysseus/agents/prompt_builder_best_practices.md odysseus/agents/prompt_builder/best_practices.md
git mv odysseus/agents/prompt_builder_conventions_claude.md odysseus/agents/prompt_builder/conventions_claude.md
git mv odysseus/agents/prompt_builder_conventions_openai.md odysseus/agents/prompt_builder/conventions_openai.md
git mv "odysseus/agents/prompt_builder_conventions_openai_gpt-5-2.md" "odysseus/agents/prompt_builder/conventions_openai_gpt-5-2.md"
```

- [ ] **Step 3: Update internal imports in moved files**

`prompt_builder/search_ops.py` — change:
```python
from odysseus.agents.prompt_builder_search import (
    Candidate, RoundSummary, SearchState, update_pareto_front,
)
```
To:
```python
from odysseus.agents.prompt_builder.search import (
    Candidate, RoundSummary, SearchState, update_pareto_front,
)
```

`prompt_builder/search.py` and `prompt_builder/holdout_filter.py` have no intra-agents imports — no changes needed.

- [ ] **Step 4: Update consumers — `odysseus/mcp.py`**

Change:
```python
from odysseus.agents.prompt_builder_holdout_filter import filter_holdout_dataset
from odysseus.agents.prompt_builder_search_ops import (
    advance_round,
    get_search_state,
    init_search_state,
    record_eval_result,
    register_candidate,
)
from odysseus.agents.prompt_builder_search_ops import (
    set_loop_phase as _set_loop_phase,
)
```
To:
```python
from odysseus.agents.prompt_builder.holdout_filter import filter_holdout_dataset
from odysseus.agents.prompt_builder.search_ops import (
    advance_round,
    get_search_state,
    init_search_state,
    record_eval_result,
    register_candidate,
)
from odysseus.agents.prompt_builder.search_ops import (
    set_loop_phase as _set_loop_phase,
)
```

Also update any resource loader paths that reference `agents/prompt_builder_best_practices.md`, `agents/prompt_builder_conventions_claude.md`, etc. to use `agents/prompt_builder/best_practices.md`, `agents/prompt_builder/conventions_claude.md`, etc.

- [ ] **Step 5: Update consumers — test files**

`tests/test_prompt_builder_search.py` — change `from odysseus.agents.prompt_builder_search` to `from odysseus.agents.prompt_builder.search`.

`tests/test_prompt_builder_search_ops.py` — change `from odysseus.agents.prompt_builder_search_ops` to `from odysseus.agents.prompt_builder.search_ops`.

`tests/test_prompt_builder_holdout_filter.py` — change `from odysseus.agents.prompt_builder_holdout_filter` to `from odysseus.agents.prompt_builder.holdout_filter` (if import exists; verify).

`tests/test_run_eval_tool.py` — change `from odysseus.agents.prompt_builder_search` to `from odysseus.agents.prompt_builder.search`.

`tests/test_review_preprocessor.py` — change `from odysseus.agents.prompt_builder_search` to `from odysseus.agents.prompt_builder.search`.

`tests/test_mcp_prompt_builder.py` — has an inline import `from odysseus.agents.prompt_builder_search_ops` inside a test function. Change to `from odysseus.agents.prompt_builder.search_ops`.

- [ ] **Step 6: Update cross-stage consumer — `odysseus/agents/review_models.py`**

This file imports `Candidate` from `prompt_builder_search`. Update now so it doesn't break:

Change:
```python
from odysseus.agents.prompt_builder_search import Candidate
```
To:
```python
from odysseus.agents.prompt_builder.search import Candidate
```

Note: Task 5 will later move this file to `agents/review/models.py` — the import path set here will remain correct.

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/test_prompt_builder_search.py tests/test_prompt_builder_search_ops.py tests/test_prompt_builder_holdout_filter.py tests/test_run_eval_tool.py tests/test_review_preprocessor.py tests/test_mcp_prompt_builder.py -v
```
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add odysseus/agents/prompt_builder/
git add -u
git commit -m "refactor(agents): move prompt builder modules to agents/prompt_builder/"
```

---

### Task 5: Create `agents/review/` subdirectory

**Files:**
- Move: `odysseus/agents/review_models.py` → `odysseus/agents/review/models.py`
- Move: `odysseus/agents/review_ops.py` → `odysseus/agents/review/ops.py`
- Move: `odysseus/agents/review_preprocessor.py` → `odysseus/agents/review/preprocessor.py`
- Create: `odysseus/agents/review/__init__.py`

- [ ] **Step 1: Create directory and `__init__.py`**

```bash
mkdir -p odysseus/agents/review
```

Create `odysseus/agents/review/__init__.py`:
```python
"""Review agent — briefing models, directive persistence, review preprocessing."""

from __future__ import annotations

from odysseus.agents.review.models import (
    CandidateAnalysis,
    ClassRecallEntry,
    DirectiveOutcome,
    DiversityMetrics,
    EditDirective,
    ExampleSummary,
    LoopSignal,
    MetricDeltas,
    MutationHistory,
    MutationRecord,
    OracleMetrics,
    PromotionDecision,
    RankedCandidate,
    RegressionFlag,
    ReviewBriefing,
    ReviewResult,
)
from odysseus.agents.review.ops import (
    load_directive_history,
    load_mutation_log,
    load_round_reports,
    save_directive_history,
    save_mutation_log,
    save_round_report,
)
from odysseus.agents.review.preprocessor import build_review_briefing

__all__ = [
    "CandidateAnalysis",
    "ClassRecallEntry",
    "DirectiveOutcome",
    "DiversityMetrics",
    "EditDirective",
    "ExampleSummary",
    "LoopSignal",
    "MetricDeltas",
    "MutationHistory",
    "MutationRecord",
    "OracleMetrics",
    "PromotionDecision",
    "RankedCandidate",
    "RegressionFlag",
    "ReviewBriefing",
    "ReviewResult",
    "build_review_briefing",
    "load_directive_history",
    "load_mutation_log",
    "load_round_reports",
    "save_directive_history",
    "save_mutation_log",
    "save_round_report",
]
```

- [ ] **Step 2: Move files**

```bash
git mv odysseus/agents/review_models.py odysseus/agents/review/models.py
git mv odysseus/agents/review_ops.py odysseus/agents/review/ops.py
git mv odysseus/agents/review_preprocessor.py odysseus/agents/review/preprocessor.py
```

- [ ] **Step 3: Update internal imports in moved files**

`review/models.py` — should already be updated in Task 4 Step 6. Verify:
```python
from odysseus.agents.prompt_builder.search import Candidate
```

`review/ops.py` — change:
```python
from odysseus.agents.review_models import (DirectiveOutcome, MutationRecord)
```
To:
```python
from odysseus.agents.review.models import (DirectiveOutcome, MutationRecord)
```

`review/preprocessor.py` — change:
```python
from odysseus.agents.review_models import (
    CandidateAnalysis, ClassRecallEntry, DiminishingReturns, DirectiveOutcome,
    DiversityMetrics, ExampleSummary, FrontComparison, MetricDeltas,
    MutationHistory, MutationRecord, OracleMetrics, ReviewBriefing,
)
```
To:
```python
from odysseus.agents.review.models import (
    CandidateAnalysis, ClassRecallEntry, DiminishingReturns, DirectiveOutcome,
    DiversityMetrics, ExampleSummary, FrontComparison, MetricDeltas,
    MutationHistory, MutationRecord, OracleMetrics, ReviewBriefing,
)
```

- [ ] **Step 4: Update consumers — `odysseus/mcp.py`**

Update any dynamic imports inside mcp.py tool functions:
```python
from odysseus.agents.review_models import ExampleSummary
```
→
```python
from odysseus.agents.review.models import ExampleSummary
```

```python
from odysseus.agents.review_ops import (load_directive_history, save_directive_history)
```
→
```python
from odysseus.agents.review.ops import (load_directive_history, save_directive_history)
```

```python
from odysseus.agents.review_preprocessor import build_review_briefing
```
→
```python
from odysseus.agents.review.preprocessor import build_review_briefing
```

- [ ] **Step 5: Update consumers — test files**

`tests/test_review_models.py` — **IMPORTANT: this file has ~30+ local/inline imports inside individual test methods**, not just top-level imports. Use a project-wide find-and-replace for all occurrences:
- `from odysseus.agents.review_models` → `from odysseus.agents.review.models` (all occurrences, both top-level and inline)
- `from odysseus.agents.prompt_builder_search import Candidate` → `from odysseus.agents.prompt_builder.search import Candidate` (cross-module import inside test functions)

`tests/test_review_ops.py` — change `from odysseus.agents.review_models` to `from odysseus.agents.review.models` and `from odysseus.agents.review_ops` to `from odysseus.agents.review.ops`.

`tests/test_review_preprocessor.py` — change `from odysseus.agents.review_models` to `from odysseus.agents.review.models` and `from odysseus.agents.review_preprocessor` to `from odysseus.agents.review.preprocessor`.

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_review_models.py tests/test_review_ops.py tests/test_review_preprocessor.py -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add odysseus/agents/review/
git add -u
git commit -m "refactor(agents): move review modules to agents/review/"
```

---

### Task 6: Move remaining `.md` resource files and update `agents/__init__.py`

**Files:**
- Move: `odysseus/agents/backend_setup_defaults.md` → `odysseus/agents/backend_setup_defaults.md` (stays — no subdirectory)
- Move: `odysseus/agents/backend_setup_taxonomy.md` → `odysseus/agents/backend_setup_taxonomy.md` (stays)
- Move: `odysseus/agents/user_input_context.md` → `odysseus/agents/user_input_context.md` (stays)
- Move: `odysseus/agents/user_input_defaults.md` → `odysseus/agents/user_input_defaults.md` (stays)
- Move: `odysseus/agents/user_input_report_template.md` → `odysseus/agents/user_input_report_template.md` (stays)
- Move: `odysseus/agents/user_input_taxonomy.md` → `odysseus/agents/user_input_taxonomy.md` (stays)
- Modify: `odysseus/agents/__init__.py` — rewrite to re-export from subdirectories

Note: `backend_setup` and `user_input` .md files stay at `agents/` root since these stages have no subdirectory (backend_setup has no agent code, user_input is just constants in `user_input_report.py`). This is a justified deviation from the spec which says to move all .md files to subdirectories.

- [ ] **Step 1: Rewrite `agents/__init__.py`**

Replace the entire file to re-export from subdirectories instead of flat files. **Note:** This intentionally expands the public API surface compared to the current `__init__.py` — symbols like `BaseAgent`, `DetectionResult`, `TransformResult`, pipeline functions, and prompt_builder/review operations are now re-exported for convenience. The implementer should cross-check against the current `__init__.py` and decide whether to match it exactly or adopt the expanded surface below:

```python
"""Odysseus agents — domain logic for each pipeline stage.

Subdirectories:
  pipeline/          — status detection and artifact guards
  data_validation/   — format detection, field mapping, quality checks
  routing_analysis/  — rationale models, vocabulary registry, validation, split
  prompt_builder/    — search state, candidate management, holdout filtering
  review/            — briefing models, directive persistence, preprocessing

Root-level modules:
  base.py            — BaseAgent abstract interface
  user_input_report.py — Input report constants
  eval_runner.py     — EvalRunnerAgent (cross-cutting)
"""

from __future__ import annotations

# --- Root-level modules ---
from odysseus.agents.base import BaseAgent
from odysseus.agents.eval_runner import EvalRunnerAgent
from odysseus.agents.user_input_report import (
    USER_INPUT_REPORT_CONTEXT_KEY as CONTEXT_KEY,
    STATUS_PROCEED,
    STATUS_PROCEED_WITH_DEFAULTS,
    read_user_input_report_status as read_status,
)

# --- Pipeline ---
from odysseus.agents.pipeline import (
    check_artifacts,
    discover_runs,
    get_pipeline_status,
    require_artifacts,
)

# --- Data Validation ---
from odysseus.agents.data_validation import (
    DataQualityReport,
    DetectionResult,
    LabelDistribution,
    QueryLengthDistribution,
    SchemaFinding,
    TierDistribution,
    TierVolume,
    TransformResult,
    VolumeAssessment,
    check_label_distribution,
    check_query_length_distribution,
    check_schema_conformance,
    check_volume_adequacy,
    detect_and_parse,
    run_all_checks,
    transform_dataset,
)

# --- Routing Analysis ---
from odysseus.agents.routing_analysis import (
    RationaleCard,
    RationaleCardSet,
    RationaleCheckResult,
    RegistryMergeError,
    RouteDefinition,
    RouteExclusion,
    RouteOrdering,
    RoutingContext,
    RoutingDimension,
    SeedVocabulary,
    SplitMismatchError,
    SplitReport,
    VocabularyEntry,
    VocabularyRegistry,
    check_ambiguity_tag_membership,
    check_card_completeness,
    check_cluster_thresholds,
    check_exclusion_coverage,
    check_exclusion_format,
    check_pruning_cleanup,
    check_registry_consistency,
    check_required_fields,
    check_vocabulary_membership,
    compute_dataset_hash,
    create_seed_registry,
    find_orphaned_examples,
    load_registry,
    merge_registry,
    prune_registry,
    resolve_registry,
    save_registry,
    stratified_split,
    validate_deterministic,
    validate_rationale_card_set,
)

# --- Prompt Builder ---
from odysseus.agents.prompt_builder import (
    Candidate,
    RoundSummary,
    SearchState,
    advance_round,
    dominates,
    filter_holdout_dataset,
    get_search_state,
    init_search_state,
    record_eval_result,
    register_candidate,
    select_best,
    set_loop_phase,
    update_pareto_front,
)

# --- Review ---
from odysseus.agents.review import (
    CandidateAnalysis,
    ClassRecallEntry,
    DirectiveOutcome,
    DiversityMetrics,
    EditDirective,
    ExampleSummary,
    LoopSignal,
    MetricDeltas,
    MutationHistory,
    MutationRecord,
    OracleMetrics,
    PromotionDecision,
    RankedCandidate,
    RegressionFlag,
    ReviewBriefing,
    ReviewResult,
    build_review_briefing,
    load_directive_history,
    load_mutation_log,
    load_round_reports,
    save_directive_history,
    save_mutation_log,
    save_round_report,
)

__all__ = [
    # Root
    "BaseAgent",
    "CONTEXT_KEY",
    "EvalRunnerAgent",
    "STATUS_PROCEED",
    "STATUS_PROCEED_WITH_DEFAULTS",
    "read_status",
    # Pipeline
    "check_artifacts",
    "discover_runs",
    "get_pipeline_status",
    "require_artifacts",
    # Data Validation
    "DataQualityReport",
    "DetectionResult",
    "LabelDistribution",
    "QueryLengthDistribution",
    "SchemaFinding",
    "TierDistribution",
    "TierVolume",
    "TransformResult",
    "VolumeAssessment",
    "check_label_distribution",
    "check_query_length_distribution",
    "check_schema_conformance",
    "check_volume_adequacy",
    "detect_and_parse",
    "run_all_checks",
    "transform_dataset",
    # Routing Analysis
    "RationaleCard",
    "RationaleCardSet",
    "RationaleCheckResult",
    "RegistryMergeError",
    "RouteDefinition",
    "RouteExclusion",
    "RouteOrdering",
    "RoutingContext",
    "RoutingDimension",
    "SeedVocabulary",
    "SplitMismatchError",
    "SplitReport",
    "VocabularyEntry",
    "VocabularyRegistry",
    "check_ambiguity_tag_membership",
    "check_card_completeness",
    "check_cluster_thresholds",
    "check_exclusion_coverage",
    "check_exclusion_format",
    "check_pruning_cleanup",
    "check_registry_consistency",
    "check_required_fields",
    "check_vocabulary_membership",
    "compute_dataset_hash",
    "create_seed_registry",
    "find_orphaned_examples",
    "load_registry",
    "merge_registry",
    "prune_registry",
    "resolve_registry",
    "save_registry",
    "stratified_split",
    "validate_deterministic",
    "validate_rationale_card_set",
    # Prompt Builder
    "Candidate",
    "RoundSummary",
    "SearchState",
    "advance_round",
    "dominates",
    "filter_holdout_dataset",
    "get_search_state",
    "init_search_state",
    "record_eval_result",
    "register_candidate",
    "select_best",
    "set_loop_phase",
    "update_pareto_front",
    # Review
    "CandidateAnalysis",
    "ClassRecallEntry",
    "DirectiveOutcome",
    "DiversityMetrics",
    "EditDirective",
    "ExampleSummary",
    "LoopSignal",
    "MetricDeltas",
    "MutationHistory",
    "MutationRecord",
    "OracleMetrics",
    "PromotionDecision",
    "RankedCandidate",
    "RegressionFlag",
    "ReviewBriefing",
    "ReviewResult",
    "build_review_briefing",
    "load_directive_history",
    "load_mutation_log",
    "load_round_reports",
    "save_directive_history",
    "save_mutation_log",
    "save_round_report",
]
```

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest -v
```
Expected: all tests pass. This confirms backward compatibility through `agents/__init__.py`.

- [ ] **Step 3: Run linting and type checking**

```bash
uv run ruff check .
uv run pyright
```
Expected: no regressions.

- [ ] **Step 4: Commit**

```bash
git add -u
git add odysseus/agents/__init__.py
git commit -m "refactor(agents): rewrite __init__.py to re-export from subdirectories"
```

---

## Chunk 2: Split `mcp.py` into `mcp/` package

### Task 7: Create `mcp/server.py` with app setup and stage registry

**Files:**
- Create: `odysseus/mcp/__init__.py`
- Create: `odysseus/mcp/server.py`

- [ ] **Step 1: Create directory**

```bash
mkdir -p odysseus/mcp_pkg
```

We use `mcp_pkg` as a temporary name during migration to avoid conflicting with the existing `mcp.py` file. We'll rename after removing the old file.

Actually — since `mcp.py` is a file and `mcp/` would be a package, we need to remove `mcp.py` first or use a temp name. The safest approach:

1. Rename `mcp.py` → `mcp_legacy.py` temporarily
2. Create `mcp/` package
3. Port code
4. Remove `mcp_legacy.py`

```bash
git mv odysseus/mcp.py odysseus/mcp_legacy.py
mkdir -p odysseus/mcp
```

- [ ] **Step 2: Create `odysseus/mcp/__init__.py`**

**IMPORTANT:** `odysseus/cli.py` imports `from odysseus.mcp import main as mcp_main`. This `__init__.py` must re-export `main` from `server.py` so the CLI entry point continues to work.

```python
"""MCP server package for Odysseus.

Thin adapter layer — each tool module delegates to agent classes
that own all business logic.
"""

from __future__ import annotations

from odysseus.mcp.server import create_app, main

__all__ = ["create_app", "main"]
```

- [ ] **Step 2b: Create `odysseus/mcp/__main__.py`**

Required for `python -m odysseus.mcp` to work (Python looks for `__main__.py` inside a package):

```python
"""Allow running as ``python -m odysseus.mcp``."""

from odysseus.mcp.server import main

main()
```

- [ ] **Step 3: Create `odysseus/mcp/server.py`**

This file contains the FastMCP app creation, stage registry, and session state management. Extract the app setup and shared utilities from `mcp_legacy.py` (the `mcp = FastMCP(...)` call, the `_STAGE_PROMPT_MAP`, helper functions like `_resolve_run_dir`, `_read_md_resource`, etc.).

Key contents:
- `STAGE_REGISTRY: dict[str, list[str]]` — maps stage name to tool names
- `create_app() -> FastMCP` — creates and configures the app, registers all tools/resources/prompts from submodules
- Shared helpers used across multiple tool modules

The exact code depends on the current `mcp_legacy.py` structure — the implementer should extract verbatim and only restructure import paths.

- [ ] **Step 4: Verify import**

```bash
uv run python -c "from odysseus.mcp.server import create_app; print('ok')"
```

- [ ] **Step 5: Commit**

```bash
git add odysseus/mcp/
git add -u
git commit -m "refactor(mcp): create mcp/ package with server.py scaffold"
```

---

### Task 8: Extract tool functions into stage-specific files

**Files:**
- Create: `odysseus/mcp/orchestrator_tools.py`
- Create: `odysseus/mcp/input_report_tools.py`
- Create: `odysseus/mcp/data_validation_tools.py`
- Create: `odysseus/mcp/routing_analysis_tools.py`
- Create: `odysseus/mcp/backend_setup_tools.py`
- Create: `odysseus/mcp/prompt_building_tools.py`
- Create: `odysseus/mcp/review_tools.py`
- Create: `odysseus/mcp/holdout_tools.py`

- [ ] **Step 1: Extract orchestrator tools**

Move `optimize_routing_prompt` and `get_pipeline_status` tool functions from `mcp_legacy.py` to `odysseus/mcp/orchestrator_tools.py`. Update imports to use new `agents/` subdirectory paths.

- [ ] **Step 2: Extract input report tools**

Move `submit_input_report` tool function to `odysseus/mcp/input_report_tools.py`.

- [ ] **Step 3: Extract data validation tools**

Move `detect_and_parse_dataset`, `transform_dataset`, `validate_dataset`, `save_routing_context` tool functions to `odysseus/mcp/data_validation_tools.py`.

- [ ] **Step 4: Extract routing analysis tools**

Move `create_seed_registry_tool`, `resolve_registry_tool`, `prune_registry_tool`, `validate_rationale_card_set_tool`, `stratified_split_tool` tool functions to `odysseus/mcp/routing_analysis_tools.py`.

- [ ] **Step 5: Extract backend setup tools**

Move `get_default_pricing` tool function to `odysseus/mcp/backend_setup_tools.py`.

- [ ] **Step 6: Extract prompt building tools**

Move `init_search_state_tool`, `register_candidate_tool`, `run_eval`, `record_eval_result_tool`, `advance_round_tool`, `get_search_state_tool`, `filter_holdout_dataset_tool` tool functions to `odysseus/mcp/prompt_building_tools.py`.

- [ ] **Step 7: Extract review tools**

Move `build_review_briefing_tool`, `record_directive_outcomes_tool` tool functions to `odysseus/mcp/review_tools.py`.

- [ ] **Step 8: Extract holdout tools**

Move `run_holdout_eval` tool function to `odysseus/mcp/holdout_tools.py`.

- [ ] **Step 9: Run tests**

```bash
uv run pytest tests/test_mcp.py tests/test_mcp_data_validation.py tests/test_mcp_prompt_builder.py -v
```
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add odysseus/mcp/
git add -u
git commit -m "refactor(mcp): extract tool functions into stage-specific modules"
```

---

### Task 9: Extract resources and prompts, wire up server.py

**Files:**
- Create: `odysseus/mcp/resources.py`
- Create: `odysseus/mcp/prompts.py`
- Modify: `odysseus/mcp/server.py` — register all submodules
- Delete: `odysseus/mcp_legacy.py`
- Modify: `odysseus/__main__.py` or `odysseus/cli.py` — update import path

- [ ] **Step 1: Extract resources**

Move all `@mcp.resource()` decorated functions from `mcp_legacy.py` to `odysseus/mcp/resources.py`. Update file paths for moved `.md` resource files (e.g., `agents/data_validation/format.md` instead of `agents/data_validation_format.md`).

- [ ] **Step 2: Extract prompts**

Move all `@mcp.prompt()` decorated functions from `mcp_legacy.py` to `odysseus/mcp/prompts.py`.

- [ ] **Step 3: Wire up `server.py`**

Update `create_app()` in `server.py` to import and register tools, resources, and prompts from all submodules. Define `STAGE_REGISTRY` mapping.

- [ ] **Step 4: Update entry points**

Update `odysseus/cli.py` (or wherever the MCP server is started) to import from `odysseus.mcp` instead of `odysseus.mcp_legacy`.

Check `pyproject.toml` for any references to `odysseus.mcp` module and update if needed.

- [ ] **Step 5: Delete legacy file**

```bash
git rm odysseus/mcp_legacy.py
```

- [ ] **Step 6: Update test imports**

`tests/test_mcp.py` — update any imports from `odysseus.mcp` (these should still work since `odysseus/mcp/__init__.py` re-exports, but verify).

`tests/test_mcp_data_validation.py` and `tests/test_mcp_prompt_builder.py` — same.

- [ ] **Step 7: Run full test suite**

```bash
uv run pytest -v
```

- [ ] **Step 8: Test MCP server starts**

```bash
uv run python -m odysseus.mcp
```
Verify it starts without errors (Ctrl+C to exit).

- [ ] **Step 9: Run linting and type checking**

```bash
uv run ruff check .
uv run pyright
```

- [ ] **Step 10: Commit**

```bash
git add -u
git add odysseus/mcp/
git commit -m "refactor(mcp): complete mcp/ package migration, remove mcp_legacy.py"
```

---

## Chunk 3: Add session-scoped tool filtering

### Task 10: Implement stage session state and `start_stage`/`complete_stage` tools

**Files:**
- Modify: `odysseus/mcp/server.py` — add session state, `STAGE_REGISTRY`, `tools/list` override
- Modify: `odysseus/mcp/orchestrator_tools.py` — add `start_stage` and `complete_stage` tools

- [ ] **Step 1: Define `STAGE_REGISTRY` in `server.py`**

Add the stage → tool name mapping:

```python
STAGE_REGISTRY: dict[str, list[str]] = {
    "orchestrator": [
        "optimize_routing_prompt",
        "get_pipeline_status",
        "start_stage",
        "complete_stage",
    ],
    "input_report": [
        "submit_input_report",
        "get_pipeline_status",
    ],
    "data_validation": [
        "detect_and_parse_dataset",
        "transform_dataset",
        "validate_dataset",
        "save_routing_context",
        "get_pipeline_status",
    ],
    "routing_analysis": [
        "create_seed_registry_tool",
        "resolve_registry_tool",
        "prune_registry_tool",
        "validate_rationale_card_set_tool",
        "stratified_split_tool",
        "get_pipeline_status",
    ],
    "backend_setup": [
        "get_default_pricing",
        "get_pipeline_status",
    ],
    "prompt_building": [
        "init_search_state_tool",
        "register_candidate_tool",
        "run_eval",
        "record_eval_result_tool",
        "advance_round_tool",
        "get_search_state_tool",
        "filter_holdout_dataset_tool",
        "get_pipeline_status",
    ],
    "review": [
        "build_review_briefing_tool",
        "record_directive_outcomes_tool",
        "get_search_state_tool",
        "run_eval",
        "get_pipeline_status",
    ],
    "holdout": [
        "filter_holdout_dataset_tool",
        "run_holdout_eval",
        "get_pipeline_status",
    ],
}
```

- [ ] **Step 2: Add session state management**

Add per-session `active_stage` tracking to `server.py`. The implementation depends on how FastMCP exposes session context — consult FastMCP docs for the session/context mechanism. The state should:
- Default to `"orchestrator"` for new connections
- Be mutable via `start_stage` / `complete_stage`
- Reset to `"orchestrator"` on connection drop

- [ ] **Step 3: Override `tools/list`**

Override the MCP `tools/list` handler in `server.py` to filter the tool list based on `active_stage`. Only return tools whose names appear in `STAGE_REGISTRY[active_stage]`.

- [ ] **Step 4: Implement `start_stage` tool**

Add to `odysseus/mcp/orchestrator_tools.py`:

```python
@mcp.tool()
async def start_stage(run_id: str, stage: str, ctx: Context) -> dict:
    """Activate a pipeline stage, scoping visible tools to that stage's tool set.

    Parameters:
        run_id: The active run identifier.
        stage: Stage name (e.g., "data_validation", "routing_analysis").

    Returns:
        Confirmation with list of tools now available.
    """
    if stage not in STAGE_REGISTRY:
        raise ToolError(f"Unknown stage: {stage!r}. Valid: {sorted(STAGE_REGISTRY)}")
    # Set active_stage on session
    ctx.session.active_stage = stage  # actual API depends on FastMCP
    return {
        "stage": stage,
        "tools_available": STAGE_REGISTRY[stage],
    }
```

- [ ] **Step 5: Implement `complete_stage` tool**

```python
@mcp.tool()
async def complete_stage(run_id: str, ctx: Context) -> dict:
    """Complete the current stage and return to orchestrator mode.

    Parameters:
        run_id: The active run identifier.

    Returns:
        Confirmation.
    """
    previous = getattr(ctx.session, "active_stage", "orchestrator")
    ctx.session.active_stage = "orchestrator"
    return {
        "completed_stage": previous,
        "tools_available": STAGE_REGISTRY["orchestrator"],
    }
```

- [ ] **Step 6: Write tests for stage scoping**

Create `tests/test_mcp_stage_scoping.py`:

```python
"""Tests for MCP session-scoped tool filtering."""

import pytest
from odysseus.mcp.server import STAGE_REGISTRY, create_app


def test_stage_registry_has_all_stages():
    expected = {
        "orchestrator", "input_report", "data_validation",
        "routing_analysis", "backend_setup", "prompt_building",
        "review", "holdout",
    }
    assert set(STAGE_REGISTRY) == expected


def test_every_stage_includes_get_pipeline_status():
    for stage, tools in STAGE_REGISTRY.items():
        if stage != "orchestrator":
            assert "get_pipeline_status" in tools, f"{stage} missing get_pipeline_status"


def test_orchestrator_stage_has_only_4_tools():
    assert len(STAGE_REGISTRY["orchestrator"]) == 4
    assert "start_stage" in STAGE_REGISTRY["orchestrator"]
    assert "complete_stage" in STAGE_REGISTRY["orchestrator"]


def test_no_stage_specific_tools_in_orchestrator():
    orchestrator_tools = set(STAGE_REGISTRY["orchestrator"])
    stage_only_tools = {"submit_input_report", "detect_and_parse_dataset",
                        "validate_dataset", "run_eval"}
    assert not orchestrator_tools & stage_only_tools
```

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/test_mcp_stage_scoping.py -v
```
Expected: all pass.

- [ ] **Step 8: Run full test suite**

```bash
uv run pytest -v
```
Expected: all pass (existing tests unaffected by stage filtering since they call tools directly).

- [ ] **Step 9: Commit**

```bash
git add odysseus/mcp/ tests/test_mcp_stage_scoping.py
git add -u
git commit -m "feat(mcp): add session-scoped stage filtering with start_stage/complete_stage"
```

---

### Task 11: Update orchestrator system prompt

**Files:**
- Modify: `odysseus/agents/prompts/user_input_system.md` (or whichever prompt the orchestrator loads first)
- Modify: `odysseus/agents/pipeline/status.py` — update `subagent_instruction` to reference `start_stage`/`complete_stage`

- [ ] **Step 1: Update `pipeline/status.py`**

The `get_pipeline_status` return value includes `subagent_instruction` that tells the orchestrator how to dispatch sub-agents. Update this to instruct the orchestrator to call `start_stage` before spawning a sub-agent and `complete_stage` after.

Find the instruction text assembly in `get_pipeline_status()` and prepend/append the stage lifecycle calls. The exact changes depend on the current instruction format — the implementer should read the current `subagent_instruction` text and add:
- Before sub-agent dispatch: `"First, call start_stage(run_id='{run_id}', stage='{stage_name}') to scope tools for this stage."`
- After sub-agent completion: `"After the sub-agent completes, call complete_stage(run_id='{run_id}') to return to orchestrator mode."`

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_pipeline_status.py -v
```
Expected: all pass (update test assertions if they check `subagent_instruction` text).

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "feat(pipeline): update subagent instructions to use start_stage/complete_stage"
```

---

## Chunk 4: Update documentation

### Task 12: Update project documentation

**Files:**
- Modify: `docs/architecture.md`
- Modify: `CLAUDE.md`
- Modify: `odysseus/agents/README.md`
- Create: `odysseus/mcp/README.md`

- [ ] **Step 1: Update `CLAUDE.md` project structure**

Replace the project structure section with the new layout showing `mcp/` package and `agents/` subdirectories. Match the actual file tree.

- [ ] **Step 2: Update `docs/architecture.md`**

- Update the project structure diagram
- Add a new section on MCP session/stage scoping explaining: stage registry, `start_stage`/`complete_stage` lifecycle, tool visibility
- Update module reference tables to use new paths

- [ ] **Step 3: Rewrite `odysseus/agents/README.md`**

Document the subdirectory organization:
- Which subdirectory backs which pipeline stage
- Cross-stage dependency direction
- Root-level modules that stayed flat

- [ ] **Step 4: Create `odysseus/mcp/README.md`**

Document:
- MCP package structure (server.py, tool files, resources, prompts)
- Stage registry and how tool filtering works
- How to add a new tool to a stage

- [ ] **Step 5: Check and update `odysseus/eval/README.md`**

Verify no stale cross-references to old agents/ module paths. Update if found.

- [ ] **Step 5b: Check and update `prompts/README.md`**

Verify no stale references to old module paths. Update if found.

- [ ] **Step 6: Review agent system prompts**

Check each prompt in `odysseus/agents/prompts/` for references to specific tool names or tool counts. Sub-agents now get only their stage's tools, so remove any "you have access to these N tools" language that might be inaccurate.

- [ ] **Step 7: Run full test suite one final time**

```bash
uv run pytest -v
uv run ruff check .
uv run pyright
```
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add -u
git add odysseus/mcp/README.md
git commit -m "docs: update architecture, CLAUDE.md, READMEs for new module structure"
```
