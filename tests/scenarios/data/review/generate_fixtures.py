#!/usr/bin/env python3
"""Generate fixture data for Review Agent integration test scenarios 51-53.

Run from the project root:
    python tests/scenarios/data/review/generate_fixtures.py

Creates search states, score reports, mutation logs, round reports, and
minimal prompt files required by build_review_briefing_tool.
"""

import json
from pathlib import Path

BASE = Path(__file__).parent
PROMPTS = Path(__file__).resolve().parents[4] / "prompts"

SUMMARY_TEMPLATE = {
    "total": 20,
    "succeeded": 20,
    "failed": 0,
    "total_cost": 0.0,
    "start_time": "2026-03-25T12:00:00+00:00",
    "end_time": "2026-03-25T12:00:05+00:00",
    "duration_seconds": 5.0,
}


def _score_report(
    *,
    accuracy: float,
    cost: float,
    recall: dict[str, float],
    support: dict[str, int],
    oracle_cost_reduction: float = 0.003,
    oracle_quality_reduction: float = 0.15,
    cost_reduction: float = 0.0,
    quality_reduction: float = 0.0,
    report_path: str = "",
    results_path: str = "",
) -> dict:
    metrics = {
        "accuracy": accuracy,
        "cost": cost,
        "oracle_cost_reduction": oracle_cost_reduction,
        "oracle_quality_reduction": oracle_quality_reduction,
        "cost_reduction": cost_reduction,
        "quality_reduction": quality_reduction,
    }
    for route, val in recall.items():
        metrics[f"recall/{route}"] = val
    for route, val in support.items():
        metrics[f"support/{route}"] = val

    summary = dict(SUMMARY_TEMPLATE)
    summary["total_cost"] = cost

    return {
        "metrics": metrics,
        "summary": summary,
        "errors": [],
        "diff": None,
        "report_path": report_path,
        "results_path": results_path,
    }


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(BASE)}")


def _write_prompt(version: str, content: str) -> None:
    """Write a minimal prompt file for diversity calculation."""
    path = PROMPTS / f"{version}.txt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"  wrote prompts/{version}.txt")


# ─── Scenario 51: Basic Review (abc123) ───────────────────────────


def gen_scenario_51():
    print("\nScenario 51: abc123")
    d = BASE / "abc123"

    # SearchState: round 1, v1 on Pareto front
    _write_json(
        d / "search_state.json",
        {
            "search_state_id": "abc123",
            "backend": "anthropic",
            "primary_metric_name": "accuracy",
            "round": 1,
            "pareto_front": [
                {
                    "prompt_version": "v1",
                    "parent_version": None,
                    "quality_score": 0.72,
                    "cost": 0.002,
                    "round_introduced": 1,
                    "dominated": False,
                }
            ],
            "round_history": [],
            "stagnation_count": 0,
            "stagnation_limit": 3,
            "convergence_limit": 5,
            "max_rounds": 50,
            "mutation_mode": "targeted",
            "converged": False,
        },
    )

    # Score reports
    v1_report = _score_report(
        accuracy=0.72,
        cost=0.002,
        recall={"haiku": 0.80, "sonnet": 0.65, "opus": 0.70},
        support={"haiku": 10, "sonnet": 7, "opus": 3},
        oracle_cost_reduction=0.003,
        oracle_quality_reduction=0.15,
        cost_reduction=0.0012,
        quality_reduction=0.072,
        report_path="tests/scenarios/data/review/abc123/v1_score_report.json",
        results_path="tests/scenarios/data/review/abc123/v1_results.jsonl",
    )
    _write_json(d / "v1_score_report.json", v1_report)

    v2_report = _score_report(
        accuracy=0.78,
        cost=0.0025,
        recall={"haiku": 0.85, "sonnet": 0.70, "opus": 0.75},
        support={"haiku": 10, "sonnet": 7, "opus": 3},
        oracle_cost_reduction=0.003,
        oracle_quality_reduction=0.15,
        cost_reduction=0.0018,
        quality_reduction=0.09,
        report_path="tests/scenarios/data/review/abc123/v2_score_report.json",
        results_path="tests/scenarios/data/review/abc123/v2_results.jsonl",
    )
    _write_json(d / "v2_score_report.json", v2_report)

    # Mutation log
    _write_json(
        d / "mutation_log.json",
        [
            {
                "child_version": "v2",
                "parent_version": "v1",
                "mutation_type": "example_swap",
                "description": "added second sonnet example",
                "directive_ids": None,
            }
        ],
    )

    # Minimal prompts for diversity
    _write_prompt(
        "v1",
        (
            "# Routing Prompt v1\n\n"
            "## Rules\n1. Route simple queries to haiku.\n"
            "2. Route analytical queries to opus.\n\n"
            "## Examples\n### Example 1\nSimple lookup → haiku\n\n"
            '## Output Schema\n{"route": "<model>"}\n'
        ),
    )
    _write_prompt(
        "v2",
        (
            "# Routing Prompt v2\n\n"
            "## Rules\n1. Route simple queries to haiku.\n"
            "2. Route analytical queries to opus.\n"
            "3. Route moderate-complexity queries to sonnet.\n\n"
            "## Examples\n### Example 1\nSimple lookup → haiku\n"
            "### Example 2\nModerate analysis → sonnet\n\n"
            '## Output Schema\n{"route": "<model>"}\n'
        ),
    )


# ─── Scenario 52: Regression Guard (def456) ──────────────────────


def gen_scenario_52():
    print("\nScenario 52: def456")
    d = BASE / "def456"

    # SearchState: round 2, v2 on Pareto front
    _write_json(
        d / "search_state.json",
        {
            "search_state_id": "def456",
            "backend": "anthropic",
            "primary_metric_name": "accuracy",
            "round": 2,
            "pareto_front": [
                {
                    "prompt_version": "v2",
                    "parent_version": "v1",
                    "quality_score": 0.78,
                    "cost": 0.0025,
                    "round_introduced": 1,
                    "dominated": False,
                }
            ],
            "round_history": [],
            "stagnation_count": 0,
            "stagnation_limit": 3,
            "convergence_limit": 5,
            "max_rounds": 50,
            "mutation_mode": "targeted",
            "converged": False,
        },
    )

    # v2 score report (Pareto front member, needed for delta computation)
    v2_report = _score_report(
        accuracy=0.78,
        cost=0.0025,
        recall={"haiku": 0.85, "sonnet": 0.70, "opus": 0.75},
        support={"haiku": 10, "sonnet": 7, "opus": 3},
        oracle_cost_reduction=0.003,
        oracle_quality_reduction=0.15,
        cost_reduction=0.0018,
        quality_reduction=0.09,
        report_path="tests/scenarios/data/review/def456/v2_score_report.json",
        results_path="tests/scenarios/data/review/def456/v2_results.jsonl",
    )
    _write_json(d / "v2_score_report.json", v2_report)

    # v3 score report: quality improved but opus recall regressed
    v3_report = _score_report(
        accuracy=0.82,
        cost=0.0023,
        recall={"haiku": 0.92, "sonnet": 0.78, "opus": 0.45},
        support={"haiku": 10, "sonnet": 7, "opus": 3},
        oracle_cost_reduction=0.003,
        oracle_quality_reduction=0.15,
        cost_reduction=0.002,
        quality_reduction=0.105,
        report_path="tests/scenarios/data/review/def456/v3_score_report.json",
        results_path="tests/scenarios/data/review/def456/v3_results.jsonl",
    )
    _write_json(d / "v3_score_report.json", v3_report)

    # Round 1 historical report (v2's report for trend calculation)
    _write_json(
        d / "round_reports" / "round_1.json",
        {
            "v2": v2_report,
        },
    )

    # Mutation log
    _write_json(
        d / "mutation_log.json",
        [
            {
                "child_version": "v2",
                "parent_version": "v1",
                "mutation_type": "example_swap",
                "description": "added second sonnet example",
                "directive_ids": None,
            },
            {
                "child_version": "v3",
                "parent_version": "v2",
                "mutation_type": "rule_edit",
                "description": "tightened haiku/sonnet boundary rule",
                "directive_ids": None,
            },
        ],
    )

    # Prompts
    _write_prompt(
        "v3",
        (
            "# Routing Prompt v3\n\n"
            "## Rules\n1. Route simple factual queries to haiku.\n"
            "2. Route analytical multi-step queries to opus.\n"
            "3. Route moderate-complexity queries to sonnet — tightened boundary: "
            "queries with single-step reasoning go to haiku, not sonnet.\n\n"
            "## Examples\n### Example 1\nSimple lookup → haiku\n"
            "### Example 2\nModerate analysis → sonnet\n\n"
            '## Output Schema\n{"route": "<model>"}\n'
        ),
    )


# ─── Scenario 53: Loop Exit (ghi789) ─────────────────────────────


def gen_scenario_53():
    print("\nScenario 53: ghi789")
    d = BASE / "ghi789"

    # SearchState: round 5, v6 on front, stagnation active
    _write_json(
        d / "search_state.json",
        {
            "search_state_id": "ghi789",
            "backend": "anthropic",
            "primary_metric_name": "accuracy",
            "round": 5,
            "pareto_front": [
                {
                    "prompt_version": "v6",
                    "parent_version": "v5",
                    "quality_score": 0.89,
                    "cost": 0.0021,
                    "round_introduced": 5,
                    "dominated": False,
                }
            ],
            "round_history": [],
            "stagnation_count": 2,
            "stagnation_limit": 3,
            "convergence_limit": 5,
            "max_rounds": 50,
            "mutation_mode": "targeted",
            "converged": False,
        },
    )

    supports = {"haiku": 10, "sonnet": 7, "opus": 3}

    # Historical rounds showing diminishing returns.
    # Score trajectory must produce stagnation_flag=True.
    # The preprocessor uses a window of min(4, len) entries and threshold 0.005.
    # Trajectory: [0.87, 0.878, 0.884, 0.888, 0.89]
    # Window (last 4): [0.878, 0.884, 0.888, 0.89]
    # Deltas: [0.006, 0.004, 0.002] → avg 0.004 < 0.005 → stagnation!
    rounds_data = {
        1: ("v1", 0.87, 0.0024, {"haiku": 0.88, "sonnet": 0.75, "opus": 0.78}),
        2: ("v2", 0.878, 0.0023, {"haiku": 0.89, "sonnet": 0.77, "opus": 0.79}),
        3: ("v3", 0.884, 0.0022, {"haiku": 0.90, "sonnet": 0.78, "opus": 0.80}),
        4: ("v5", 0.888, 0.00215, {"haiku": 0.91, "sonnet": 0.79, "opus": 0.81}),
    }

    for round_num, (version, accuracy, cost, recall) in rounds_data.items():
        report = _score_report(
            accuracy=accuracy,
            cost=cost,
            recall=recall,
            support=supports,
            oracle_cost_reduction=0.003,
            oracle_quality_reduction=0.15,
            cost_reduction=cost * 0.85,
            quality_reduction=accuracy * 0.13,
            report_path=f"tests/scenarios/data/review/ghi789/{version}_score_report.json",
            results_path=f"tests/scenarios/data/review/ghi789/{version}_results.jsonl",
        )
        _write_json(
            d / "round_reports" / f"round_{round_num}.json",
            {
                version: report,
            },
        )

    # v6 score report: near oracle ceiling
    # candidate_quality_captured = quality_reduction / oracle_quality_reduction = 0.93
    # candidate_cost_captured = cost_reduction / oracle_cost_reduction = 0.91
    v6_report = _score_report(
        accuracy=0.89,
        cost=0.0021,
        recall={"haiku": 0.92, "sonnet": 0.80, "opus": 0.82},
        support=supports,
        oracle_cost_reduction=0.003,
        oracle_quality_reduction=0.15,
        cost_reduction=0.00273,  # 0.91 * 0.003
        quality_reduction=0.1395,  # 0.93 * 0.15
        report_path="tests/scenarios/data/review/ghi789/v6_score_report.json",
        results_path="tests/scenarios/data/review/ghi789/v6_results.jsonl",
    )
    _write_json(d / "v6_score_report.json", v6_report)

    # v5 score report (parent of v6, loaded via parent_versions)
    _write_json(
        d / "v5_score_report.json",
        _score_report(
            accuracy=0.888,
            cost=0.00215,
            recall={"haiku": 0.91, "sonnet": 0.79, "opus": 0.81},
            support=supports,
            oracle_cost_reduction=0.003,
            oracle_quality_reduction=0.15,
            cost_reduction=0.00268,
            quality_reduction=0.138,
            report_path="tests/scenarios/data/review/ghi789/v5_score_report.json",
            results_path="tests/scenarios/data/review/ghi789/v5_results.jsonl",
        ),
    )

    # Mutation log spanning all rounds
    _write_json(
        d / "mutation_log.json",
        [
            {
                "child_version": "v2",
                "parent_version": "v1",
                "mutation_type": "example_swap",
                "description": "replaced haiku example with sonnet boundary case",
                "directive_ids": None,
            },
            {
                "child_version": "v3",
                "parent_version": "v2",
                "mutation_type": "rule_edit",
                "description": "added explicit opus trigger conditions",
                "directive_ids": None,
            },
            {
                "child_version": "v4",
                "parent_version": "v3",
                "mutation_type": "rule_add",
                "description": "added cost-awareness rule for haiku preference",
                "directive_ids": None,
            },
            {
                "child_version": "v5",
                "parent_version": "v4",
                "mutation_type": "example_swap",
                "description": "swapped opus example for ambiguity-tagged boundary case",
                "directive_ids": None,
            },
            {
                "child_version": "v6",
                "parent_version": "v5",
                "mutation_type": "rule_edit",
                "description": "micro-edit — rephrased haiku instruction",
                "directive_ids": None,
            },
        ],
    )

    # Minimal prompts — nearly identical for low diversity
    base_prompt = (
        "# Routing Prompt\n\n"
        "## Rules\n"
        "1. Route simple factual queries to haiku.\n"
        "2. Route moderate-complexity analytical queries to sonnet.\n"
        "3. Route complex multi-step reasoning to opus.\n"
        "4. Prefer haiku when cost is a concern and quality is equivalent.\n\n"
        "## Examples\n"
        "### Example 1\nSimple lookup → haiku\n"
        "### Example 2\nModerate analysis → sonnet\n"
        "### Example 3\nComplex reasoning → opus\n\n"
        '## Output Schema\n{"route": "<model>"}\n'
    )
    _write_prompt("v5", base_prompt)
    _write_prompt(
        "v6",
        base_prompt.replace(
            "Route simple factual queries to haiku.",
            "Route simple factual queries to haiku (including translations and arithmetic).",
        ),
    )


if __name__ == "__main__":
    print("Generating Review Agent scenario fixtures...")
    gen_scenario_51()
    gen_scenario_52()
    gen_scenario_53()
    print("\nDone.")
