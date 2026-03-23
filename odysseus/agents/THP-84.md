# THP-84 — Create context for routing dataset quality

**Type:** Task  
**Status:** To Do  
**Epic:** [THP-73](https://prosus-thymo-thesis.atlassian.net/browse/THP-73) — Data validation agent  
**Jira:** [THP-84](https://prosus-thymo-thesis.atlassian.net/browse/THP-84)

## Description

Define the static domain knowledge preloaded into the Data Validation agent about what makes a high-quality routing dataset. This context grounds the agent's quality assessment in routing-specific knowledge rather than generic data-quality heuristics, and is tailored to the cost-quality routing problem.

## What to build

Produce a reference document covering:

1. **Ideal label balance** — what a well-balanced routing dataset looks like:
   - Recommended class ratios (e.g. no tier should represent less than 10% of the dataset unless the routing task is intentionally skewed).
   - Acceptable imbalance thresholds and when to flag a class as underrepresented.
   - Distinction between natural imbalance (reflecting real traffic distribution) and sampling bias.

2. **Minimum query diversity requirements** — what "diverse enough" means for a routing dataset:
   - Minimum number of semantically distinct queries per routing tier.
   - How to detect semantic redundancy (e.g. many near-identical phrasings of the same question all assigned to the same tier).
   - Why diversity matters for prompt optimisation: a prompt that only sees one type of query per tier will not generalise.

3. **Decision boundary coverage** — ensuring examples near tier boundaries are represented:
   - What boundary examples are: queries that could plausibly be routed to two or more tiers.
   - Why they are important: the routing prompt's quality is most visible at the margins.
   - Minimum boundary coverage recommendation (e.g. at least 10–15% of each tier's examples should be near-boundary cases).

4. **Edge case representation** — rare but important routing cases:
   - Examples of edge cases: very short queries, queries with special characters, queries mixing languages, queries that require tool use.
   - Why missing edge cases causes prompt failure in production.
   - Recommendation: include at least one edge case per routing tier.

Suggested file: `odysseus/agents/data_validation_quality_context.md`

## How it links with the rest of the codebase

| Touch point | Detail |
|---|---|
| THP-81 | Missing signal detection and data collection suggestions in the output report are grounded in the quality criteria defined here. |
| THP-106 | Final system prompt embeds this context so quality judgements are domain-specific, not generic. |
| THP-69 | Volume thresholds in the User Input agent's static context should align with the minimum counts defined here. |

## Dependencies between tasks

- No blockers — can be written in parallel with THP-80, THP-81, and THP-82.
- THP-106 (final prompt) depends on this being finalised.
