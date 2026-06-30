# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Tests for the Final Report preprocessor."""

import json
from datetime import UTC, datetime
from pathlib import Path

from compass.agents.final_report.preprocessor import build_final_report_briefing


def _run_report(
    *,
    prompt_version: str,
    data_source: str,
    metrics: dict[str, float],
    total: int,
    succeeded: int,
    failed: int,
    total_cost: float,
    with_confidence_intervals: bool = False,
) -> dict:
    now = datetime.now(tz=UTC).isoformat()
    report = {
        "config": {
            "backend": "anthropic",
            "prompt_version": prompt_version,
            "data_source": data_source,
            "metrics": [{"name": "accuracy"}],
        },
        "metrics": metrics,
        "results": [
            {
                "example_id": f"{prompt_version}-0",
                "model": "claude",
                "output": {"route": "haiku"},
                "error": None,
                "latency_ms": 100.0,
                "retries": 0,
                "token_usage": None,
                "cost": total_cost,
            }
        ],
        "summary": {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "total_cost": total_cost,
            "start_time": now,
            "end_time": now,
            "duration_seconds": 1.0,
        },
    }
    if with_confidence_intervals:
        report["confidence_intervals"] = {
            "accuracy": {"lower": 0.8, "upper": 0.9, "level": 0.95},
            "f1/macro": {"lower": 0.78, "upper": 0.88, "level": 0.95},
            "confusion/haiku->sonnet": {"lower": 1.0, "upper": 3.0, "level": 0.95},
        }
    return report


def _holdout_examples() -> list[dict]:
    expected_costs = {
        "haiku": {"cost": 0.1, "quality_score": 0.6},
        "sonnet": {"cost": 0.5, "quality_score": 0.9},
        "opus": {"cost": 1.0, "quality_score": 0.95},
    }
    routes = (["haiku"] * 10) + (["sonnet"] * 6) + (["opus"] * 4)
    return [
        {
            "id": f"hold-{i}",
            "input": f"holdout request {i}",
            "expected": {
                "route": route,
                "routes": expected_costs,
            },
        }
        for i, route in enumerate(routes)
    ]


def _predicted_route(index: int, actual: str, version: str) -> str:
    if version == "v3":
        if index in {3, 11, 18}:
            return {"haiku": "sonnet", "sonnet": "haiku", "opus": "sonnet"}[actual]
        return actual
    if index in {1, 7, 12, 16, 19}:
        return {"haiku": "sonnet", "sonnet": "haiku", "opus": "haiku"}[actual]
    return actual


def _write_results(path: Path, *, prompt_version: str, examples: list[dict]) -> None:
    rows = [
        json.dumps(
            {
                "__meta__": "run_fingerprint",
                "prompt_version": prompt_version,
                "backend": "anthropic",
                "data_source": "analysis/holdout.jsonl",
            }
        )
    ]
    for index, example in enumerate(examples):
        rows.append(
            json.dumps(
                {
                    "example_id": example["id"],
                    "model": "claude",
                    "output": {"route": _predicted_route(index, example["expected"]["route"], prompt_version)},
                    "error": None,
                    "latency_ms": 100,
                    "retries": 0,
                }
            )
        )
    path.write_text("\n".join(rows), encoding="utf-8")


def _baseline_json(version: str) -> dict:
    quality = 0.88 if version == "v3" else 0.84
    cost = 0.35 if version == "v3" else 0.31
    return {
        "baselines": [
            {"strategy": "always_cheapest", "route": "haiku", "quality_score": 0.65, "cost": 0.1},
            {"strategy": "always_capable", "route": "opus", "quality_score": 0.95, "cost": 1.0},
        ],
        "optimized": {
            "strategy": "optimized_prompt",
            "route": "mixed",
            "quality_score": quality,
            "cost": cost,
        },
    }


def _setup_final_report_run(
    tmp_path: Path,
    *,
    run_id: str = "test-run",
    versions: tuple[str, ...] = ("v3", "v5"),
) -> Path:
    run_dir = tmp_path / run_id
    (run_dir / "input").mkdir(parents=True)
    (run_dir / "input" / "input_report.md").write_text("# Test Problem\nRoute requests to models.", encoding="utf-8")

    (run_dir / "validation").mkdir(parents=True)
    (run_dir / "validation" / "routing_context.json").write_text(
        json.dumps(
            {
                "routes": [{"name": "haiku"}, {"name": "sonnet"}, {"name": "opus"}],
                "dimensions": [{"name": "cost"}, {"name": "quality"}],
            }
        ),
        encoding="utf-8",
    )

    (run_dir / "analysis").mkdir(parents=True)
    dev_examples = [
        {"id": f"dev-{i}", "input": f"request {i}", "expected": {"route": "haiku", "routes": {}}} for i in range(80)
    ]
    holdout_examples = _holdout_examples()
    (run_dir / "analysis" / "dev.jsonl").write_text(
        "\n".join(json.dumps(e) for e in dev_examples),
        encoding="utf-8",
    )
    (run_dir / "analysis" / "holdout.jsonl").write_text(
        "\n".join(json.dumps(e) for e in holdout_examples),
        encoding="utf-8",
    )
    (run_dir / "analysis" / "split_report.json").write_text(
        json.dumps(
            {
                "dev_count": 80,
                "holdout_count": 20,
                "route_distribution": {
                    "haiku": {"dev": 48, "holdout": 10},
                    "sonnet": {"dev": 24, "holdout": 6},
                    "opus": {"dev": 8, "holdout": 4},
                },
            }
        ),
        encoding="utf-8",
    )

    (run_dir / "search").mkdir(parents=True)
    (run_dir / "search" / "search_state.json").write_text(
        json.dumps(
            {
                "search_state_id": "ss-1",
                "backend": "anthropic",
                "round": 4,
                "converged": True,
                "loop_phase": "build",
                "stagnation_count": 5,
                "stagnation_limit": 3,
                "convergence_limit": 5,
                "max_rounds": 50,
                "mutation_mode": "exploratory",
                "pareto_front": [
                    {
                        "prompt_version": "v1",
                        "parent_version": None,
                        "quality_score": 0.85,
                        "cost": 0.5,
                        "round_introduced": 1,
                    },
                    {
                        "prompt_version": "v2",
                        "parent_version": "v1",
                        "quality_score": 0.90,
                        "cost": 0.45,
                        "round_introduced": 2,
                    },
                    {
                        "prompt_version": "v3",
                        "parent_version": "v2",
                        "quality_score": 0.92,
                        "cost": 0.40,
                        "round_introduced": 3,
                    },
                    {
                        "prompt_version": "v5",
                        "parent_version": "v3",
                        "quality_score": 0.91,
                        "cost": 0.32,
                        "round_introduced": 4,
                    },
                ],
                "round_history": [
                    {"round": 1, "candidates_evaluated": ["v1"], "new_pareto_points": 1, "front_size": 1},
                    {"round": 2, "candidates_evaluated": ["v2"], "new_pareto_points": 1, "front_size": 2},
                    {"round": 3, "candidates_evaluated": ["v3"], "new_pareto_points": 1, "front_size": 3},
                    {"round": 4, "candidates_evaluated": ["v5"], "new_pareto_points": 1, "front_size": 4},
                ],
            }
        ),
        encoding="utf-8",
    )

    (run_dir / "prompts").mkdir(parents=True)
    (run_dir / "prompts" / "v3.txt").write_text("Route with cost-quality tradeoff.", encoding="utf-8")
    (run_dir / "prompts" / "v5.txt").write_text("Route aggressively toward lower cost.", encoding="utf-8")

    for version in versions:
        eval_dir = run_dir / "eval" / version
        holdout_dir = run_dir / "holdout_eval" / version
        eval_dir.mkdir(parents=True, exist_ok=True)
        holdout_dir.mkdir(parents=True, exist_ok=True)

        if version == "v3":
            dev_metrics = {
                "accuracy": 0.90,
                "f1/macro": 0.88,
                "cost_change": -0.30,
                "recall/haiku": 0.95,
                "recall/sonnet": 0.85,
                "recall/opus": 0.80,
                "precision/haiku": 0.92,
                "precision/sonnet": 0.87,
                "precision/opus": 0.82,
                "f1/haiku": 0.93,
                "f1/sonnet": 0.86,
                "f1/opus": 0.81,
            }
            holdout_metrics = {
                "accuracy": 0.85,
                "f1/macro": 0.83,
                "cost_change": -0.25,
                "oracle_cost_change": -0.40,
                "oracle_quality_change": 0.0,
                "recall/haiku": 0.90,
                "recall/sonnet": 0.80,
                "recall/opus": 0.75,
                "precision/haiku": 0.88,
                "precision/sonnet": 0.82,
                "precision/opus": 0.78,
                "f1/haiku": 0.89,
                "f1/sonnet": 0.81,
                "f1/opus": 0.76,
                "support/haiku": 10,
                "support/sonnet": 6,
                "support/opus": 4,
            }
            total_cost = 0.25
        else:
            dev_metrics = {
                "accuracy": 0.89,
                "f1/macro": 0.87,
                "cost_change": -0.36,
                "recall/haiku": 0.93,
                "recall/sonnet": 0.82,
                "recall/opus": 0.78,
                "precision/haiku": 0.90,
                "precision/sonnet": 0.84,
                "precision/opus": 0.80,
                "f1/haiku": 0.91,
                "f1/sonnet": 0.83,
                "f1/opus": 0.79,
            }
            holdout_metrics = {
                "accuracy": 0.80,
                "f1/macro": 0.79,
                "cost_change": -0.33,
                "oracle_cost_change": -0.40,
                "oracle_quality_change": 0.0,
                "recall/haiku": 0.82,
                "recall/sonnet": 0.78,
                "recall/opus": 0.72,
                "precision/haiku": 0.84,
                "precision/sonnet": 0.79,
                "precision/opus": 0.74,
                "f1/haiku": 0.83,
                "f1/sonnet": 0.78,
                "f1/opus": 0.73,
                "support/haiku": 10,
                "support/sonnet": 6,
                "support/opus": 4,
            }
            total_cost = 0.21

        (eval_dir / "report.json").write_text(
            json.dumps(
                _run_report(
                    prompt_version=version,
                    data_source="analysis/dev.jsonl",
                    metrics=dev_metrics,
                    total=80,
                    succeeded=78,
                    failed=2,
                    total_cost=0.8,
                )
            ),
            encoding="utf-8",
        )
        (holdout_dir / "report.json").write_text(
            json.dumps(
                _run_report(
                    prompt_version=version,
                    data_source="analysis/holdout.jsonl",
                    metrics=holdout_metrics,
                    total=20,
                    succeeded=20,
                    failed=0,
                    total_cost=total_cost,
                    with_confidence_intervals=(version == "v5"),
                )
            ),
            encoding="utf-8",
        )
        _write_results(holdout_dir / "results.jsonl", prompt_version=version, examples=holdout_examples)
        (holdout_dir / "baseline_comparison.json").write_text(
            json.dumps(_baseline_json(version)),
            encoding="utf-8",
        )

    return run_dir


class TestBuildFinalReportBriefing:
    def test_returns_briefing_for_multiple_versions(self, tmp_path: Path) -> None:
        run_dir = _setup_final_report_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)

        assert briefing.run_id == "test-run"
        assert briefing.backend_name == "anthropic"
        assert briefing.evaluated_versions == ["v3", "v5"]
        assert set(briefing.evaluated_prompts) == {"v3", "v5"}
        assert set(briefing.prompt_texts) == {"v3", "v5"}
        assert set(briefing.dev_score_report_md) == {"v3", "v5"}
        assert set(briefing.holdout_score_report_md) == {"v3", "v5"}
        assert set(briefing.baseline_comparison_md) == {"v3", "v5"}
        assert set(briefing.holdout_report_paths) == {"v3", "v5"}

    def test_single_candidate_regression(self, tmp_path: Path) -> None:
        run_dir = _setup_final_report_run(tmp_path, versions=("v3",))
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)

        assert briefing.evaluated_versions == ["v3"]
        assert list(briefing.dev_score_report_md) == ["v3"]
        assert list(briefing.holdout_score_report_md) == ["v3"]
        assert list(briefing.baseline_comparison_md) == ["v3"]

    def test_round_trip_with_rendered_snippets(self, tmp_path: Path) -> None:
        from compass.agents.final_report.models import FinalReportBriefing

        run_dir = _setup_final_report_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        reparsed = FinalReportBriefing.model_validate_json(briefing.model_dump_json())

        assert reparsed.evaluated_versions == briefing.evaluated_versions
        assert reparsed.dev_score_report_md == briefing.dev_score_report_md
        assert reparsed.holdout_score_report_md == briefing.holdout_score_report_md
        assert reparsed.baseline_comparison_md == briefing.baseline_comparison_md

    def test_problem_summary_and_dataset_overview(self, tmp_path: Path) -> None:
        run_dir = _setup_final_report_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)

        assert "Test Problem" in briefing.problem_summary
        assert briefing.dataset_overview.dev_count == 80
        assert briefing.dataset_overview.holdout_count == 20
        assert briefing.dataset_overview.total_examples == 100
        assert "haiku" in briefing.dataset_overview.routes

    def test_optimization_journey_and_charts(self, tmp_path: Path) -> None:
        run_dir = _setup_final_report_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)

        journey = briefing.optimization_journey
        assert journey.total_rounds == 4
        assert "Stagnation" in journey.convergence_reason
        assert len(journey.pareto_front_size_per_round) == 4
        assert journey.oracle_cost_change == -0.4
        assert briefing.charts.quality_progression is not None
        assert briefing.charts.cost_progression is not None
        assert briefing.charts.pareto_front is not None
        assert (run_dir / briefing.charts.quality_progression).is_file()
        assert (run_dir / briefing.charts.pareto_front).is_file()

    def test_evaluated_prompts_and_texts(self, tmp_path: Path) -> None:
        run_dir = _setup_final_report_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)

        assert briefing.evaluated_prompts["v3"].quality_score == 0.92
        assert briefing.evaluated_prompts["v5"].cost == 0.32
        assert "cost-quality" in briefing.prompt_texts["v3"]
        assert "lower cost" in briefing.prompt_texts["v5"]

    def test_eval_comparison_is_per_version(self, tmp_path: Path) -> None:
        run_dir = _setup_final_report_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)

        v3_accuracy = next(metric for metric in briefing.eval_comparison["v3"] if metric.metric == "accuracy")
        v5_accuracy = next(metric for metric in briefing.eval_comparison["v5"] if metric.metric == "accuracy")
        assert v3_accuracy.dev_value == 0.90
        assert v3_accuracy.holdout_value == 0.85
        assert v5_accuracy.dev_value == 0.89
        assert v5_accuracy.holdout_value == 0.80

    def test_per_class_and_error_analysis_are_per_version(self, tmp_path: Path) -> None:
        run_dir = _setup_final_report_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)

        assert {p.route for p in briefing.per_class_performance["v3"]} == {"haiku", "sonnet", "opus"}
        assert briefing.error_analysis["v3"].total_evaluated == 20
        assert briefing.error_analysis["v3"].total_errors == 3
        assert briefing.error_analysis["v5"].total_errors == 5

    def test_baseline_comparison_and_markdown_are_per_version(self, tmp_path: Path) -> None:
        run_dir = _setup_final_report_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)

        assert briefing.baseline_comparison["v3"] is not None
        assert briefing.baseline_comparison["v5"] is not None
        assert "## Baseline comparison" in briefing.baseline_comparison_md["v3"]
        assert "## Baseline comparison" in briefing.baseline_comparison_md["v5"]

    def test_confidence_intervals_are_per_version(self, tmp_path: Path) -> None:
        run_dir = _setup_final_report_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)

        assert "v5" in briefing.confidence_intervals
        assert "accuracy" in briefing.confidence_intervals["v5"]
        assert "confusion/haiku->sonnet" not in briefing.confidence_intervals["v5"]


class TestGracefulDegradation:
    def test_missing_holdout_results_zeroes_only_that_version(self, tmp_path: Path) -> None:
        run_dir = _setup_final_report_run(tmp_path)
        (run_dir / "holdout_eval" / "v5" / "results.jsonl").unlink()

        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.error_analysis["v5"].total_evaluated == 0
        assert briefing.error_analysis["v3"].total_evaluated == 20

    def test_missing_split_report_uses_line_counts(self, tmp_path: Path) -> None:
        run_dir = _setup_final_report_run(tmp_path)
        (run_dir / "analysis" / "split_report.json").unlink()

        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.dataset_overview.dev_count == 80
        assert briefing.dataset_overview.holdout_count == 20

    def test_missing_baseline_computes_from_raw(self, tmp_path: Path) -> None:
        run_dir = _setup_final_report_run(tmp_path)
        (run_dir / "holdout_eval" / "v5" / "baseline_comparison.json").unlink()

        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.baseline_comparison["v5"] is not None
        assert briefing.baseline_comparison["v5"].baselines[0].route == "haiku"
        assert "## Baseline comparison" in briefing.baseline_comparison_md["v5"]

    def test_support_populated_from_confusion_matrix_when_missing(self, tmp_path: Path) -> None:
        run_dir = _setup_final_report_run(tmp_path)
        report_path = run_dir / "holdout_eval" / "v3" / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for key in list(report["metrics"]):
            if key.startswith("support/"):
                del report["metrics"][key]
        report_path.write_text(json.dumps(report), encoding="utf-8")

        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        supports = {entry.route: entry.support for entry in briefing.per_class_performance["v3"]}
        assert supports["haiku"] == 10
        assert supports["sonnet"] == 6
        assert supports["opus"] == 4
