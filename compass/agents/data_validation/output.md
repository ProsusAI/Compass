# Data Quality Report — Output Format Reference

This document defines the structure and content of the data quality report produced by the Data Validation agent. It is read by the agent at runtime via the `compass://agents/data-validation/output-spec` resource handle.

## Report Sections

The report has six sections, produced in this order.

### 1. Dataset Summary

Write two natural-language paragraphs:

1. **Data description** — what the dataset contains: the routing problem domain, what kinds of queries are represented, and what the routing tiers correspond to. Base this on the user's problem description and the data you observed.
2. **Validation summary** — total record count, tier names and distribution, any issues found, and overall verdict (ready for downstream processing or blocked by critical issues).

### 2. Schema Consistency Findings

Present the `schema_findings` from the tool output. Each finding includes a `severity` field (`"critical"`, `"warning"`, or `"info"`). For each finding with status `"fail"`, state its severity, explain the violation, and list the affected row indices. Group passing checks into a single summary line.

Checks: required keys present and non-null, correct types, route-in-routes, non-empty routes, consistent model set, unique IDs.

### 3. Label Distribution Stats

Present the `label_distribution` from the tool output. Show per-tier counts and percentages. Flag any imbalanced tiers.

### 4. Volume Adequacy Assessment

Present the `volume_assessment` from the tool output. Show per-tier verdicts (`adequate` / `insufficient` / `absent`), actual counts, and minimum required. State the overall verdict (`pass` / `fail`).

### 5. Query Length Distribution

Present the `query_length` stats from the tool output: min, max, mean, and p95 character lengths.

### 6. Routing Context

Synthesize a `routing_context` block for downstream annotation skills. Derive it from the dataset and the user's problem description:

- **`domain`**: Two sentences. First: what the routing system decides (from the problem description and dataset structure). Second: what topics and domains the queries cover (sample queries across routes and summarize the topic clusters you observe).
- **`routes`**: One entry per route found in the `consistent_model_set`. The `name` field MUST be one of the keys of `expected.routes` in the transformed dataset, verbatim — `save_routing_context` validates the route-name set against the canonical dataset key set and rejects any mismatch. For each route, examine a few example queries assigned to it and write a one-sentence description of what that route typically handles.
- **`routing_dimensions`**: One entry per numeric field in `expected.routes` (e.g., `cost`, `quality_score`). Infer `direction` from the field semantics (`cost` → `lower_is_better`, `quality_score` → `higher_is_better`).
- **`route_ordering`**: If routes have a natural ordering along one dimension (e.g., capability tiers), include it. If routes are unordered (e.g., specialized tools), omit this field.

Present the routing context as a fenced YAML code block in the report, then call `save_routing_context` with the `run_id` and the routing context serialized as JSON.

The JSON passed to `save_routing_context` must match this structure exactly (fill in values from the dataset and problem description — do not pass the problem description itself):

```json
{
  "domain": "Two-sentence domain description...",
  "routes": [
    {"name": "route_name_from_dataset", "description": "One sentence describing what this route handles."},
    {"name": "another_route", "description": "One sentence describing what this route handles."}
  ],
  "routing_dimensions": [
    {"name": "cost", "direction": "lower_is_better", "description": "Per-call cost in USD."},
    {"name": "quality_score", "direction": "higher_is_better", "description": "Model quality score 0–1."}
  ],
  "route_ordering": {"dimension": "cost", "order": ["cheap_route", "expensive_route"]}
}
```

Omit `route_ordering` if routes have no natural ordering.

**Field mapping notes:**
- `routes` corresponds to what the problem description may call "tiers", "tools", or "models" — use the actual route names from the dataset (e.g. `simple`, `moderate`, `complex`), not the word "tiers".
- Do NOT include optimization metadata (`optimization_goal`, `primary_metric`, `constraints`, `dataset_characteristics`, `benchmarks`, or any other fields from the problem specification). The `RoutingContext` schema has exactly four fields: `domain`, `routes`, `routing_dimensions`, and `route_ordering` (optional). Any other field will cause a validation error.
