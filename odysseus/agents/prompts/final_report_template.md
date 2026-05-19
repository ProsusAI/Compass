# Routing Prompt Optimization Report

## Executive Summary

{3-5 sentences: what problem was solved, what was achieved across the selected prompt candidates, and deployment guidance. Do NOT pick a single winner unless the user explicitly asked for one.}

## Compared Candidates

| Prompt | Dev Accuracy | Holdout Accuracy | Dev F1 | Holdout F1 | Holdout Cost Change | Introduced |
|--------|--------------|------------------|--------|------------|---------------------|------------|
| {version} | {dev_accuracy} | {holdout_accuracy} | {dev_f1} | {holdout_f1} | {holdout_cost_change} | round {round} |

{Call out overfitting signals, ties, and tradeoffs across the selected candidates.}

## Candidate Details

<!-- Repeat this block once per prompt_version in briefing.evaluated_versions -->
### Candidate `{version}`

```
{prompt_texts[version]}
```

**Pareto metadata:** Quality {quality_score} | Cost {cost} | Introduced round {round}

#### Dev Evaluation

{dev_score_report_md[version]}

#### Holdout Evaluation

{holdout_score_report_md[version]}

#### Per-Class Performance

| Route | Precision | Recall | F1 | Support |
|-------|-----------|--------|----|---------|
| {route} | {precision} | {recall} | {f1} | {support} |

#### Error Analysis

**Error rate:** {error_rate}% ({total_errors}/{total_evaluated})

**Confusion Matrix:**

| Expected \ Predicted | {route_1} | {route_2} | ... |
|---------------------|-----------|-----------|-----|
| {route_1}           | {count}   | {count}   | ... |

{Brief interpretation of dominant misclassification patterns for this candidate.}

<!-- Include only if baseline_comparison_md[version] is non-empty -->
#### Baseline Comparison

{baseline_comparison_md[version]}

#### Usage Notes

- **Deployment:** {how to use this prompt in production}
- **Expected performance:** {candidate-specific expectations}
- **Limitations:** {known weaknesses, edge cases}

---

<!-- Sections below are shared supporting detail -->

## Problem Definition

{problem_summary from input_report.md}

## Dataset Overview

| | Total | Dev | Holdout |
|--|-------|-----|---------|
| Examples | {total} | {dev_count} | {holdout_count} |
| {route} | {dev + holdout} | {dev} | {holdout} |

**Routes:** {routes}
**Dimensions:** {dimensions}

## Optimization Process

**Rounds:** {total_rounds} | **Converged:** {convergence_reason} | **Stagnation:** {stagnation_count}

<!-- Include only if oracle values are not null -->
**Oracle note:** Theoretical optimum would achieve {oracle_cost_change}% cost change with {oracle_quality_change}% quality change. Negative cost = cheaper (good). Positive quality = better (good).

<!-- Include only if chart paths are not null -->
![Quality Progression](charts/quality_progression.png)
![Cost Progression](charts/cost_progression.png)

## Pareto Front

<!-- Include only if chart path is not null -->
![Pareto Front](charts/pareto_front.png)

| Version | Quality | Cost | Round |
|---------|---------|------|-------|
| {version} | {quality} | {cost} | {round} |
