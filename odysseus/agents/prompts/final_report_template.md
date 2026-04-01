# Routing Prompt Optimization Report

## Executive Summary

{3-5 sentences: what problem was solved, what was achieved, and deployment guidance. Do NOT include pipeline next steps — those are presented separately by the orchestrator.}

## Recommended Prompt

> See [Usage Guide](#usage-guide) for deployment instructions and limitations.

```
{best_prompt_text}
```

## Results

**Best prompt:** {version} | Quality: {quality_score} | Cost: {cost} | Introduced: round {round}

| Metric | Dev | Holdout | Delta |
|--------|-----|---------|-------|
| {metric} | {dev_value} | {holdout_value} | {delta} |

{Flag any |delta| >5% as potential overfitting signal}

## Per-Class Performance

| Route | Precision | Recall | F1 | Support |
|-------|-----------|--------|----|---------|
| {route} | {precision} | {recall} | {f1} | {support} |

## Strengths & Weaknesses

{Agent synthesis: high-performing routes, cost savings, low-recall routes, actionable recommendations}

## Error Analysis

**Error rate:** {error_rate}% ({total_errors}/{total_evaluated})

**Confusion Matrix:**

| Expected \ Predicted | {route_1} | {route_2} | ... |
|---------------------|-----------|-----------|-----|
| {route_1}           | {count}   | {count}   | ... |

{Brief interpretation of dominant misclassification patterns}

---

<!-- Sections below are supporting detail -->

<!-- Include only if baseline_comparison is not null -->
## Baseline Comparison

| Strategy | Quality | Cost |
|----------|---------|------|
| Always cheapest ({route}) | {quality} | {cost} |
| Always most capable ({route}) | {quality} | {cost} |
| **Optimized prompt ({version})** | **{quality}** | **{cost}** |

{Contextual sentence positioning the optimized prompt between the two baselines}

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
**Oracle note:** Theoretical optimum would achieve {oracle_cost_reduction}% cost reduction with {oracle_quality_reduction}% quality change. Negative cost = cheaper (good). Positive quality = better (good).

<!-- Include only if chart paths are not null -->
![Quality Progression](charts/quality_progression.png)
![Cost Progression](charts/cost_progression.png)

## Pareto Front

<!-- Include only if chart path is not null -->
![Pareto Front](charts/pareto_front.png)

| Version | Quality | Cost | Round |
|---------|---------|------|-------|
| {version} | {quality} | {cost} | {round} |

## Usage Guide

- **Deployment:** {how to use the prompt in production}
- **Expected performance:** accuracy ~{X}%, cost ~${Y}/request
- **When to re-run:** {triggers for re-optimization}
- **Limitations:** {known weaknesses, edge cases}
