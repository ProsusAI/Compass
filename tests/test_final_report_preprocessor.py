"""Tests for the Final Report preprocessor."""

import json
from pathlib import Path

from odysseus.agents.final_report.preprocessor import build_final_report_briefing


def _setup_minimal_run(tmp_path: Path, run_id: str = "test-run") -> Path:
    """Create a minimal run directory with required artifacts."""
    run_dir = tmp_path / run_id
    (run_dir / "input").mkdir(parents=True)
    (run_dir / "input" / "input_report.md").write_text("# Test Problem\nRoute requests to models.")

    (run_dir / "validation").mkdir(parents=True)
    (run_dir / "validation" / "routing_context.json").write_text(
        json.dumps(
            {
                "routes": [{"name": "haiku"}, {"name": "sonnet"}, {"name": "opus"}],
                "dimensions": [{"name": "cost"}, {"name": "quality"}],
            }
        )
    )

    (run_dir / "analysis").mkdir(parents=True)
    dev_examples = [
        {"id": f"dev-{i}", "input": f"request {i}", "expected": {"route": "haiku", "routes": {}}} for i in range(80)
    ]
    holdout_examples = [
        {"id": f"hold-{i}", "input": f"holdout request {i}", "expected": {"route": "sonnet", "routes": {}}}
        for i in range(20)
    ]
    (run_dir / "analysis" / "dev.jsonl").write_text("\n".join(json.dumps(e) for e in dev_examples))
    (run_dir / "analysis" / "holdout.jsonl").write_text("\n".join(json.dumps(e) for e in holdout_examples))
    (run_dir / "analysis" / "split_report.json").write_text(
        json.dumps(
            {
                "dev_count": 80,
                "holdout_count": 20,
                "route_distribution": {
                    "haiku": {"dev": 48, "holdout": 12},
                    "sonnet": {"dev": 24, "holdout": 6},
                    "opus": {"dev": 8, "holdout": 2},
                },
            }
        )
    )

    (run_dir / "search").mkdir(parents=True)
    (run_dir / "search" / "search_state.json").write_text(
        json.dumps(
            {
                "search_state_id": "ss-1",
                "backend": "anthropic",
                "round": 3,
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
                        "cost": 0.6,
                        "round_introduced": 2,
                    },
                    {
                        "prompt_version": "v3",
                        "parent_version": "v2",
                        "quality_score": 0.92,
                        "cost": 0.4,
                        "round_introduced": 3,
                    },
                ],
                "round_history": [
                    {
                        "round": 1,
                        "candidates_evaluated": ["v1"],
                        "new_pareto_points": 1,
                        "front_size": 1,
                        "mutation_mode": "targeted",
                        "stagnation_count": 0,
                    },
                    {
                        "round": 2,
                        "candidates_evaluated": ["v2"],
                        "new_pareto_points": 1,
                        "front_size": 2,
                        "mutation_mode": "targeted",
                        "stagnation_count": 0,
                    },
                    {
                        "round": 3,
                        "candidates_evaluated": ["v3"],
                        "new_pareto_points": 1,
                        "front_size": 3,
                        "mutation_mode": "exploratory",
                        "stagnation_count": 5,
                    },
                ],
            }
        )
    )
    (run_dir / "search" / "mutation_log.json").write_text(
        json.dumps(
            [
                {
                    "mutation_type": "example_swap",
                    "child_version": "v2",
                    "parent_version": "v1",
                    "description": "swapped example",
                },
                {
                    "mutation_type": "rule_edit",
                    "child_version": "v3",
                    "parent_version": "v2",
                    "description": "edited rule",
                },
                {
                    "mutation_type": "rule_add",
                    "child_version": "v4",
                    "parent_version": "v1",
                    "description": "added rule",
                },
            ]
        )
    )

    (run_dir / "prompts").mkdir(parents=True)
    (run_dir / "prompts" / "v1.txt").write_text("Route to haiku for simple requests.")
    (run_dir / "prompts" / "v2.txt").write_text("Route based on complexity analysis.")
    (run_dir / "prompts" / "v3.txt").write_text("Route with cost-quality tradeoff.")

    (run_dir / "eval").mkdir(parents=True)
    (run_dir / "eval" / "report.json").write_text(
        json.dumps(
            {
                "metrics": {
                    "accuracy": 0.90,
                    "f1/macro": 0.88,
                    "cost_reduction": -0.30,
                    "recall/haiku": 0.95,
                    "recall/sonnet": 0.85,
                    "recall/opus": 0.80,
                    "precision/haiku": 0.92,
                    "precision/sonnet": 0.87,
                    "precision/opus": 0.82,
                    "f1/haiku": 0.93,
                    "f1/sonnet": 0.86,
                    "f1/opus": 0.81,
                },
                "summary": {"total": 80, "succeeded": 78, "failed": 2},
            }
        )
    )

    (run_dir / "holdout_eval").mkdir(parents=True)
    (run_dir / "holdout_eval" / "report.json").write_text(
        json.dumps(
            {
                "metrics": {
                    "accuracy": 0.85,
                    "f1/macro": 0.83,
                    "cost_reduction": -0.25,
                    "oracle_cost_reduction": -0.40,
                    "oracle_quality_reduction": 0.0,
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
                    "support/sonnet": 7,
                    "support/opus": 3,
                },
                "summary": {"total": 20, "succeeded": 18, "failed": 2},
            }
        )
    )

    # Holdout eval results with some misrouted
    holdout_results = [
        json.dumps(
            {"meta": "__meta__", "prompt_version": "v3", "backend": "anthropic", "data_source": "holdout.jsonl"}
        ),
    ]
    for i in range(20):
        predicted = "sonnet" if i < 17 else "haiku"  # 3 misrouted
        holdout_results.append(
            json.dumps(
                {
                    "example_id": f"hold-{i}",
                    "model": "claude",
                    "output": {"route": predicted},
                    "error": None,
                    "latency_ms": 100,
                    "retries": 0,
                }
            )
        )
    (run_dir / "holdout_eval" / "results.jsonl").write_text("\n".join(holdout_results))

    return run_dir


class TestBuildFinalReportBriefing:
    def test_returns_briefing(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.run_id == "test-run"
        assert briefing.backend_name == "anthropic"

    def test_problem_summary(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert "Test Problem" in briefing.problem_summary

    def test_dataset_overview(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.dataset_overview.dev_count == 80
        assert briefing.dataset_overview.holdout_count == 20
        assert briefing.dataset_overview.total_examples == 100
        assert "haiku" in briefing.dataset_overview.routes

    def test_optimization_journey(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        journey = briefing.optimization_journey
        assert journey.total_rounds == 3
        assert "Stagnation" in journey.convergence_reason
        assert len(journey.pareto_front_size_per_round) == 3

    def test_best_prompt(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.best_prompt.version == "v3"
        assert briefing.best_prompt.quality_score == 0.92
        assert "cost-quality" in briefing.best_prompt_text

    def test_pareto_front(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert len(briefing.pareto_front) == 3
        versions = {p.version for p in briefing.pareto_front}
        assert versions == {"v1", "v2", "v3"}

    def test_eval_comparison(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        metrics = {c.metric for c in briefing.eval_comparison}
        assert "accuracy" in metrics
        assert "f1/macro" in metrics
        # Check deltas
        acc = next(c for c in briefing.eval_comparison if c.metric == "accuracy")
        assert acc.dev_value == 0.90
        assert acc.holdout_value == 0.85
        assert acc.delta == -0.05

    def test_per_class_performance(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        routes = {p.route for p in briefing.per_class_performance}
        assert routes == {"haiku", "sonnet", "opus"}
        haiku = next(p for p in briefing.per_class_performance if p.route == "haiku")
        assert haiku.recall == 0.90
        assert haiku.support == 10

    def test_oracle_analysis(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.oracle_analysis is not None
        assert briefing.oracle_analysis.oracle_cost_reduction == -0.40

    def test_charts_generated(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.charts.quality_progression is not None
        assert briefing.charts.cost_progression is not None
        assert briefing.charts.pareto_front is not None
        # Charts should be saved as files
        assert (run_dir / briefing.charts.quality_progression).is_file()
        assert (run_dir / briefing.charts.pareto_front).is_file()

    def test_mutation_analysis(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        journey = briefing.optimization_journey
        assert "example_swap" in journey.mutation_type_counts
        assert "rule_edit" in journey.mutation_type_counts
        # v2 and v3 are on pareto front, so their mutations are effective
        assert "example_swap" in journey.effective_mutation_types
        assert "rule_edit" in journey.effective_mutation_types
        # v4 is not on the front
        assert "rule_add" in journey.ineffective_mutation_types


class TestGracefulDegradation:
    def test_missing_mutation_log(self, tmp_path: Path) -> None:
        """Preprocessor works without mutation_log.json."""
        run_dir = _setup_minimal_run(tmp_path)
        (run_dir / "search" / "mutation_log.json").unlink()
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.optimization_journey.mutation_type_counts == {}

    def test_missing_holdout_results(self, tmp_path: Path) -> None:
        """Error analysis works without holdout results.jsonl."""
        run_dir = _setup_minimal_run(tmp_path)
        (run_dir / "holdout_eval" / "results.jsonl").unlink()
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.error_analysis.total_evaluated == 0
        assert briefing.error_analysis.total_errors == 0

    def test_missing_dev_report(self, tmp_path: Path) -> None:
        """Eval comparison is empty without dev report."""
        run_dir = _setup_minimal_run(tmp_path)
        (run_dir / "eval" / "report.json").unlink()
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.eval_comparison == []

    def test_missing_split_report_uses_line_counts(self, tmp_path: Path) -> None:
        """Falls back to counting JSONL lines when split_report.json missing."""
        run_dir = _setup_minimal_run(tmp_path)
        (run_dir / "analysis" / "split_report.json").unlink()
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.dataset_overview.dev_count == 80
        assert briefing.dataset_overview.holdout_count == 20


class TestErrorAnalysis:
    def test_confusion_matrix_computed(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        ea = briefing.error_analysis
        assert ea.total_evaluated == 20
        assert ea.total_errors == 3
        matrix_dict = {(e.expected, e.predicted): e.count for e in ea.confusion_matrix}
        assert matrix_dict[("sonnet", "sonnet")] == 17
        assert matrix_dict[("sonnet", "haiku")] == 3

    def test_empty_results(self, tmp_path: Path) -> None:
        run_dir = _setup_minimal_run(tmp_path)
        (run_dir / "holdout_eval" / "results.jsonl").unlink()
        briefing = build_final_report_briefing(run_id="test-run", run_dir=run_dir, project_dir=tmp_path)
        assert briefing.error_analysis.total_evaluated == 0
        assert briefing.error_analysis.confusion_matrix == []
