# Datasets

Supplementary datasets accompanying the Compass paper appendix. These are static, versioned artifacts — distinct from the `data/` path used at runtime by the pipeline (which is local-only and gitignored).

Licensed under [CC-BY-4.0](LICENSE), separately from the repository's code (Apache-2.0).

## `model_routing_dataset.json`

Text-query LLM-routing benchmark: 1,416 records spanning 8 QA/research source benchmarks — `deepresearch`, `fever`, `freshqa`, `hotpotqa`, `naturalquestions`, `simpleqa`, `browsecomp`, `deepsearchqa`. For each query, three candidate model tiers (`simple`, `moderate`, `complex`) were scored for answer quality and cost, and the resulting utility gap between tiers was computed and bucketed. Records are balanced evenly across `low_gap` / `average_gap` / `high_gap` (472 each).

A JSON array of objects with the following fields:

| Field | Type | Description |
|---|---|---|
| `query` | string | The input query text. |
| `benchmark` | string | Source benchmark the query was drawn from. |
| `model_tier` | int | Index (0–2) of the tier selected as the routing decision. |
| `model_tier_label` | string | Label for `model_tier`: `simple`, `moderate`, or `complex`. |
| `utility_gap` | float | Utility difference between the best and next-best tier for this query. |
| `tier_details` | object | Per-tier breakdown, keyed `0_simple` / `1_moderate` / `2_complex`, each with `score` (answer quality), `cost_usd`, and `utility` (quality/cost combined). |
| `utility_gap_category` | string | Bucketed `utility_gap`: `low_gap`, `average_gap`, or `high_gap`. |

## `ratings_lambda08.jsonl`

Image-generation model-routing ratings: 180 records across 6 prompt categories — `TIG_A`, `TIG_CG`, `TIG_I`, `TIG_P`, `TIG_S`, `TIG_T` (30 each) — evaluated against 8 image-generation models (`januspro`, `sdxl`, `qwenimage`, `flux1kreadev`, `gemini`, `bagel`, `omnigen2`, `gpt-image-1`) at a fixed cost/quality trade-off weight of `lambda=0.8`.

Newline-delimited JSON, one object per line:

| Field | Type | Description |
|---|---|---|
| `sample_id` | string | Unique ID, prefixed by prompt category (e.g. `TIG_A_000003`). |
| `refined_prompt` | string | The image generation prompt. |
| `lambda` | float | Cost/quality trade-off weight used to compute utility (fixed at `0.8` in this file). |
| `models` | object | Per-model breakdown keyed by model name, each with `cost` (USD), `quality` (human rating, 1–5), and `utility` (quality/cost combined via `lambda`). |
| `selected_model` | string | The utility-maximizing model for this prompt. |
| `selected_cost` / `selected_quality` / `selected_utility` | float | The `cost` / `quality` / `utility` values of `selected_model`, duplicated at the top level for convenience. |

## Citation

If you use these datasets, please cite the accompanying paper:

```
[citation placeholder — add once the paper has a venue/DOI]
```
