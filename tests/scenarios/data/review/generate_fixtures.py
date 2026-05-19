#!/usr/bin/env python3
"""Generate fixture data for Review Agent integration test scenarios 51-53.

Run from the project root:
    python tests/scenarios/data/review/generate_fixtures.py

Creates search states, score reports, mutation logs, round reports, and
minimal prompt files required by build_review_briefing.
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
    oracle_cost_change: float = 0.003,
    oracle_quality_change: float = 0.15,
    cost_change: float = 0.0,
    quality_change: float = 0.0,
    report_path: str = "",
    results_path: str = "",
) -> dict:
    metrics = {
        "accuracy": accuracy,
        "cost": cost,
        "oracle_cost_change": oracle_cost_change,
        "oracle_quality_change": oracle_quality_change,
        "cost_change": cost_change,
        "cost_change_with_overhead": cost_change * 0.85,
        "quality_change": quality_change,
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
        oracle_cost_change=0.003,
        oracle_quality_change=0.15,
        cost_change=0.0012,
        quality_change=0.072,
        report_path="tests/scenarios/data/review/abc123/v1_score_report.json",
        results_path="tests/scenarios/data/review/abc123/v1_results.jsonl",
    )
    _write_json(d / "v1_score_report.json", v1_report)

    v2_report = _score_report(
        accuracy=0.78,
        cost=0.0025,
        recall={"haiku": 0.85, "sonnet": 0.70, "opus": 0.75},
        support={"haiku": 10, "sonnet": 7, "opus": 3},
        oracle_cost_change=0.003,
        oracle_quality_change=0.15,
        cost_change=0.0018,
        quality_change=0.09,
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
        oracle_cost_change=0.003,
        oracle_quality_change=0.15,
        cost_change=0.0018,
        quality_change=0.09,
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
        oracle_cost_change=0.003,
        oracle_quality_change=0.15,
        cost_change=0.002,
        quality_change=0.105,
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
            oracle_cost_change=0.003,
            oracle_quality_change=0.15,
            cost_change=cost * 0.85,
            quality_change=accuracy * 0.13,
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
    # candidate_quality_captured = quality_change / oracle_quality_change = 0.93
    # candidate_cost_captured = cost_change / oracle_cost_change = 0.91
    v6_report = _score_report(
        accuracy=0.89,
        cost=0.0021,
        recall={"haiku": 0.92, "sonnet": 0.80, "opus": 0.82},
        support=supports,
        oracle_cost_change=0.003,
        oracle_quality_change=0.15,
        cost_change=0.00273,  # 0.91 * oracle_cost_change
        quality_change=0.1395,  # 0.93 * oracle_quality_change
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
            oracle_cost_change=0.003,
            oracle_quality_change=0.15,
            cost_change=0.00268,
            quality_change=0.138,
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


# ─── EMOSA fixtures (scenario 18 — calibration round) ────────────
#
# These fixtures emit a canonical SearchState for EMOSA with K=5
# trajectories in the calibration phase. The algorithm_state pocket
# follows the AnnealingState schema from annealing.py.


def gen_emosa_calibration():
    """EMOSA calibration fixture: K=5 unseeded trajectories, loop_phase='calibration'."""
    print("\nEMOSA calibration (emosa_calibration)")

    weight_vectors = [(0.9, 0.1), (0.7, 0.3), (0.5, 0.5), (0.3, 0.7), (0.1, 0.9)]
    trajectories = [
        {
            "trajectory_id": i,
            "weight_vector": list(wv),
            "current_solution": None,
            "current_energy": None,
            "current_quality": None,
            "current_cost": None,
            "acceptance_history": [],
            "quality_reference": None,
            "cost_reference": None,
        }
        for i, wv in enumerate(weight_vectors)
    ]

    # The state dict is returned as a canonical SearchState representation.
    # Callers can write it to disk or pass it directly to build_review_briefing.
    state = {
        "search_state_id": "emosa_calibration",
        "backend": "mock-echo",
        "primary_metric_name": "accuracy",
        "round": 0,
        "elite_set": [],
        "round_history": [],
        "stagnation_count": 0,
        "stagnation_limit": 3,
        "convergence_limit": 4,
        "max_rounds": 50,
        "mutation_mode": "targeted",
        "converged": False,
        "algorithm": "emosa",
        "algorithm_state": {
            "temperature": 1.0,
            "t_initial": 1.0,
            "t_min": 0.01,
            "alpha": 0.95,
            "num_trajectories": 5,
            "children_per_trajectory": 1,
            "step_count": 0,
            "trajectories": trajectories,
            "neighborhood_size": 4,
            "ideal_point": [1.0, 0.0],
            "nadir_point": [0.0, 1.0],
            "max_evals": 50,
            "total_evals": 0,
            "convergence_limit": 4,
            "epsilon": 0.003,
            "phase": "calibration",
            "rho": 1e-3,
        },
        "active_evals": [],
        "loop_phase": "calibration",
    }
    return state


def gen_emosa_steady_state():
    """EMOSA steady-state fixture: K=5 seeded trajectories, loop_phase='review', phase='search'.

    Represents post-calibration state where each trajectory already has a
    current_solution (seed prompt version), current_quality, current_cost,
    current_energy, and an initial acceptance_history = [True] from calibration.

    step_count=1, temperature=0.95 (cooled once from 1.0 via alpha=0.95).
    """
    weight_vectors = [(0.9, 0.1), (0.7, 0.3), (0.5, 0.5), (0.3, 0.7), (0.1, 0.9)]
    seed_qualities = [0.82, 0.78, 0.75, 0.72, 0.68]
    seed_costs = [0.0010, 0.0018, 0.0025, 0.0032, 0.0040]

    # Ideal/nadir computed from seed qualities/costs after calibration
    # ideal = (max_quality, min_cost) = (0.82, 0.0010)
    # nadir = (min_quality, max_cost) = (0.68, 0.0040)
    ideal_point = [0.82, 0.0010]
    nadir_point = [0.68, 0.0040]

    def _tchebycheff_energy(quality: float, cost: float, wv: tuple, ideal: list, nadir: list) -> float:
        """Minimal inline Tchebycheff for fixture generation (no import needed at test time)."""
        ideal_q, ideal_c = ideal
        nadir_q, nadir_c = nadir
        range_q = max(nadir_q - ideal_q, 1e-9)
        range_c = max(nadir_c - ideal_c, 1e-9)
        norm_q = (ideal_q - quality) / range_q  # lower quality → higher norm_q (cost term)
        norm_c = (cost - ideal_c) / range_c
        wq, wc = wv
        return max(wq * norm_q, wc * norm_c)

    trajectories = []
    for i, (wv, quality, cost) in enumerate(zip(weight_vectors, seed_qualities, seed_costs, strict=True)):
        energy = _tchebycheff_energy(quality, cost, wv, ideal_point, nadir_point)
        trajectories.append(
            {
                "trajectory_id": i,
                "weight_vector": list(wv),
                "current_solution": f"v_seed_{i}",
                "current_energy": energy,
                "current_quality": quality,
                "current_cost": cost,
                "acceptance_history": [True],
                "quality_reference": None,
                "cost_reference": None,
            }
        )

    # Pending child variants: one per trajectory, children of the seed solutions.
    # Format follows child_variants_t<N>.json pattern used by save_trajectory_child_variants.
    pending_children = [
        {
            "trajectory_id": i,
            "parent_version": f"v_seed_{i}",
            "child_versions": [f"v_child_{i}_0"],
            "weight_vector": list(wv),
        }
        for i, wv in enumerate(weight_vectors)
    ]

    state = {
        "search_state_id": "emosa_steady_state",
        "backend": "mock-echo",
        "primary_metric_name": "accuracy",
        "round": 1,
        "elite_set": [
            {
                "prompt_version": f"v_seed_{i}",
                "parent_version": None,
                "quality_score": q,
                "cost": c,
                "round_introduced": 0,
            }
            for i, (q, c) in enumerate(zip(seed_qualities, seed_costs, strict=True))
        ],
        "round_history": [],
        "stagnation_count": 0,
        "stagnation_limit": 3,
        "convergence_limit": 4,
        "max_rounds": 50,
        "mutation_mode": "targeted",
        "converged": False,
        "algorithm": "emosa",
        "algorithm_state": {
            "temperature": 0.95,
            "t_initial": 1.0,
            "t_min": 0.01,
            "alpha": 0.95,
            "num_trajectories": 5,
            "children_per_trajectory": 1,
            "step_count": 1,
            "trajectories": trajectories,
            "neighborhood_size": 4,
            "ideal_point": ideal_point,
            "nadir_point": nadir_point,
            "max_evals": 50,
            "total_evals": 5,
            "convergence_limit": 4,
            "epsilon": 0.003,
            "phase": "search",
            "rho": 1e-3,
        },
        "active_evals": [],
        "loop_phase": "review",
        "pending_children": pending_children,
    }
    return state


if __name__ == "__main__":
    print("Generating Review Agent scenario fixtures...")
    gen_scenario_51()
    gen_scenario_52()
    gen_scenario_53()
    print("\nDone.")
    print("\nEMOSA calibration state (not written to disk — use gen_emosa_calibration() directly).")
    import json

    print(json.dumps(gen_emosa_calibration(), indent=2))
    print("\nEMOSA steady-state fixture (not written to disk — use gen_emosa_steady_state() directly).")
    print(json.dumps(gen_emosa_steady_state(), indent=2))
