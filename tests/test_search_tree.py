"""Tests for odysseus.agents.prompt_builder.search_tree (Phase 2 rewrite)."""

from __future__ import annotations

import json
from pathlib import Path

from odysseus.agents.prompt_builder.search_tree import collect_data


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_candidate(
    version: str,
    parent: str | None,
    iteration_introduced: int,
    quality: float = 0.8,
    cost: float = 0.5,
    secondary_parent: str | None = None,
) -> dict:
    return {
        "prompt_version": version,
        "parent_version": parent,
        "secondary_parent_version": secondary_parent,
        "quality_score": quality,
        "cost": cost,
        "iteration_introduced": iteration_introduced,
        "eval_status": "scored",
    }


def _make_eval_report(
    quality_change: float = 0.1,
    cost_change: float = -0.2,
    predicted_cost: float = 0.4,
    routing_overhead: float = 0.05,
    baseline_cost: float = 0.5,
    baseline_quality: float = 0.7,
    oracle_cost_change: float | None = -0.3,
    oracle_quality_change: float | None = 0.15,
) -> dict:
    metrics: dict = {
        "quality_change": quality_change,
        "cost_change": cost_change,
        "cost_change_with_overhead": cost_change * 0.9,
        "predicted_cost": predicted_cost,
        "routing_overhead": routing_overhead,
        "baseline_cost": baseline_cost,
        "baseline_quality": baseline_quality,
    }
    if oracle_cost_change is not None:
        metrics["oracle_cost_change"] = oracle_cost_change
    if oracle_quality_change is not None:
        metrics["oracle_quality_change"] = oracle_quality_change
    return {"metrics": metrics}


class TestCollectDataFromArchive:
    """collect_data reads from archive + per-candidate eval reports, not round_reports/."""

    def test_basic_archive_no_round_reports_dir(self, tmp_path: Path) -> None:
        """With archive + per-candidate eval reports and no round_reports/, collect_data returns data."""
        search_dir = tmp_path / "search"
        eval_dir = tmp_path / "eval"

        # 8 warm-up seeds (iteration_introduced=0)
        archive = [_make_candidate(f"cv-0-{i}", None, 0, quality=0.7 + i * 0.01, cost=0.5 - i * 0.01) for i in range(8)]

        state = {
            "search_state_id": "test-run",
            "backend": "anthropic",
            "primary_metric_name": "accuracy",
            "iteration": 0,
            "algorithm": "sms_emoa",
            "algorithm_state": {"mu": 8},
            "elite_set": archive[:8],
            "warm_up_complete": True,
            "evaluation_budget": 50,
            "evaluations_used": 8,
            "reference_delta": 0.05,
            "stagnation_window": 5,
            "reference_point": [0.5, 0.6],
            "converged": False,
            "loop_phase": "review",
            "active_evals": [],
        }

        _write_json(search_dir / "search_state.json", state)
        _write_json(search_dir / "candidate_archive.json", archive)
        _write_json(search_dir / "pending_candidates.json", [])

        # Write per-candidate eval reports
        for i in range(8):
            v = f"cv-0-{i}"
            _write_json(
                eval_dir / v / "report.json",
                _make_eval_report(
                    quality_change=0.05 + i * 0.01,
                    cost_change=-0.1 - i * 0.01,
                    predicted_cost=0.4 - i * 0.01,
                ),
            )

        data = collect_data(search_dir, run_dir=tmp_path)

        assert len(data["candidates"]) == 8
        # All warm-up seeds → one iterations entry (iteration=0)
        assert len(data["iterations"]) == 1
        assert data["iterations"][0]["iteration"] == 0
        assert len(data["iterations"][0]["candidates"]) == 8

        # Candidates should have non-zero cost metrics from eval reports
        for c in data["candidates"]:
            assert "cost_reduction" not in c  # internal name doesn't leak
            assert "version" in c
            assert "abs_quality" in c

    def test_warmup_only_produces_one_round_entry(self, tmp_path: Path) -> None:
        """Warm-up only state (all iteration_introduced=0) → exactly one rounds[] entry."""
        search_dir = tmp_path / "search"
        eval_dir = tmp_path / "eval"

        archive = [_make_candidate(f"cv-0-{i}", None, 0) for i in range(8)]
        state = {
            "search_state_id": "test-run",
            "backend": "anthropic",
            "iteration": 0,
            "algorithm": "sms_emoa",
            "algorithm_state": {"mu": 8},
            "elite_set": archive,
            "warm_up_complete": True,
            "evaluation_budget": 50,
            "evaluations_used": 8,
            "reference_delta": 0.05,
            "stagnation_window": 5,
            "reference_point": [0.5, 0.6],
            "converged": False,
            "loop_phase": "review",
            "active_evals": [],
        }
        _write_json(search_dir / "search_state.json", state)
        _write_json(search_dir / "candidate_archive.json", archive)
        _write_json(search_dir / "pending_candidates.json", [])

        for i in range(8):
            v = f"cv-0-{i}"
            _write_json(eval_dir / v / "report.json", _make_eval_report())

        data = collect_data(search_dir, run_dir=tmp_path)

        assert len(data["iterations"]) == 1
        assert data["iterations"][0]["iteration"] == 0

    def test_multiple_iterations_produce_multiple_round_entries(self, tmp_path: Path) -> None:
        """Archive with seeds + 2 children → 3 iterations entries (iter 0, 1, 2)."""
        search_dir = tmp_path / "search"
        eval_dir = tmp_path / "eval"

        # 8 seeds (iteration 0) + 1 child per iteration
        archive = [_make_candidate(f"cv-0-{i}", None, 0) for i in range(8)]
        archive.append(_make_candidate("cv-1-0", "cv-0-0", 1, quality=0.82, cost=0.48))
        archive.append(_make_candidate("cv-2-0", "cv-1-0", 2, quality=0.85, cost=0.46))

        elite_set = [c for c in archive if c["prompt_version"] in {"cv-0-7", "cv-1-0", "cv-2-0"}]
        state = {
            "search_state_id": "test-run",
            "backend": "anthropic",
            "iteration": 2,
            "algorithm": "sms_emoa",
            "algorithm_state": {"mu": 8},
            "elite_set": elite_set,
            "warm_up_complete": True,
            "evaluation_budget": 50,
            "evaluations_used": 10,
            "reference_delta": 0.05,
            "stagnation_window": 5,
            "reference_point": [0.5, 0.6],
            "converged": False,
            "loop_phase": "review",
            "active_evals": [],
        }
        _write_json(search_dir / "search_state.json", state)
        _write_json(search_dir / "candidate_archive.json", archive)
        _write_json(search_dir / "pending_candidates.json", [])

        for c in archive:
            v = c["prompt_version"]
            _write_json(
                eval_dir / v / "report.json",
                _make_eval_report(
                    quality_change=c["quality_score"] - 0.7,
                    cost_change=-(0.5 - c["cost"]),
                ),
            )

        data = collect_data(search_dir, run_dir=tmp_path)

        assert len(data["candidates"]) == 10
        assert len(data["iterations"]) == 3
        round_nums = [r["iteration"] for r in data["iterations"]]
        assert round_nums == [0, 1, 2]

    def test_missing_eval_report_handled_gracefully(self, tmp_path: Path) -> None:
        """A candidate with no eval report still appears with zero metrics."""
        search_dir = tmp_path / "search"

        archive = [_make_candidate("cv-0-0", None, 0)]
        state = {
            "search_state_id": "test-run",
            "backend": "anthropic",
            "iteration": 0,
            "algorithm": "sms_emoa",
            "algorithm_state": {"mu": 8},
            "elite_set": archive,
            "warm_up_complete": True,
            "evaluation_budget": 50,
            "evaluations_used": 1,
            "reference_delta": 0.05,
            "stagnation_window": 5,
            "reference_point": [0.5, 0.6],
            "converged": False,
            "loop_phase": "review",
            "active_evals": [],
        }
        _write_json(search_dir / "search_state.json", state)
        _write_json(search_dir / "candidate_archive.json", archive)
        _write_json(search_dir / "pending_candidates.json", [])
        # No eval report written — eval_dir doesn't exist

        data = collect_data(search_dir, run_dir=tmp_path)

        assert len(data["candidates"]) == 1
        c = data["candidates"][0]
        assert c["version"] == "cv-0-0"
        assert c["score"] == 0.0  # no eval report → zeroed metrics

    def test_collect_data_succeeds_without_archive(self, tmp_path: Path) -> None:
        """collect_data succeeds when candidate_archive.json is absent; falls back to empty list."""
        search_dir = tmp_path / "search"
        eval_dir = tmp_path / "eval"

        pending_candidate = _make_candidate("cv-0-0", None, 0)
        pending_candidate["eval_status"] = "scored"

        state = {
            "search_state_id": "x",
            "backend": "b",
            "elite_set": [],
            "iteration": 0,
            "algorithm": "sms_emoa",
        }
        _write_json(search_dir / "search_state.json", state)
        _write_json(search_dir / "pending_candidates.json", [pending_candidate])
        # No candidate_archive.json written

        _write_json(eval_dir / "cv-0-0" / "report.json", _make_eval_report())

        data = collect_data(search_dir, run_dir=tmp_path)

        assert len(data["candidates"]) == 1
        assert data["candidates"][0]["version"] == "cv-0-0"

    def test_collect_data_surfaces_ghost_candidates_from_eval_dir(self, tmp_path: Path) -> None:
        """Candidates only in eval/<v>/report.json (ghosts) appear with parent=None and report metrics."""
        search_dir = tmp_path / "search"
        eval_dir = tmp_path / "eval"

        state = {
            "search_state_id": "ghost-test",
            "backend": "anthropic",
            "elite_set": [],
            "iteration": 0,
            "algorithm": "sms_emoa",
        }
        _write_json(search_dir / "search_state.json", state)
        # No archive, no pending
        _write_json(search_dir / "pending_candidates.json", [])

        # Two ghost candidates only known from eval reports
        _write_json(
            eval_dir / "v1" / "report.json",
            _make_eval_report(quality_change=0.05, cost_change=-0.1, predicted_cost=0.4),
        )
        _write_json(
            eval_dir / "v2" / "report.json",
            _make_eval_report(quality_change=0.08, cost_change=-0.15, predicted_cost=0.35),
        )

        data = collect_data(search_dir, run_dir=tmp_path)

        versions = {c["version"] for c in data["candidates"]}
        assert "v1" in versions
        assert "v2" in versions

        for c in data["candidates"]:
            assert c["parent"] is None  # lineage unknown for ghosts

        # Scores are populated from the eval reports (non-zero quality_change)
        v1_entry = next(c for c in data["candidates"] if c["version"] == "v1")
        assert v1_entry["score"] != 0.0  # 0.05 quality_change from report

    def test_pareto_front_correct_in_synthesized_rounds(self, tmp_path: Path) -> None:
        """new_elite in a round should be candidates on the Pareto front at that iteration."""
        search_dir = tmp_path / "search"
        eval_dir = tmp_path / "eval"

        # Two candidates: A dominates B (higher quality, lower cost)
        archive = [
            _make_candidate("vA", None, 0, quality=0.9, cost=0.3),
            _make_candidate("vB", None, 0, quality=0.7, cost=0.5),
        ]
        state = {
            "search_state_id": "test-run",
            "backend": "anthropic",
            "iteration": 0,
            "algorithm": "sms_emoa",
            "algorithm_state": {"mu": 2},
            "elite_set": [archive[0]],  # vA is on front
            "warm_up_complete": True,
            "evaluation_budget": 50,
            "evaluations_used": 2,
            "reference_delta": 0.05,
            "stagnation_window": 5,
            "reference_point": [0.5, 0.6],
            "converged": False,
            "loop_phase": "review",
            "active_evals": [],
        }
        _write_json(search_dir / "search_state.json", state)
        _write_json(search_dir / "candidate_archive.json", archive)
        _write_json(search_dir / "pending_candidates.json", [])

        for c in archive:
            _write_json(
                eval_dir / c["prompt_version"] / "report.json",
                _make_eval_report(
                    quality_change=c["quality_score"] - 0.7,
                    predicted_cost=c["cost"],
                ),
            )

        data = collect_data(search_dir, run_dir=tmp_path)

        assert len(data["iterations"]) == 1
        rd = data["iterations"][0]
        # vA dominates vB so only vA should be in new_elite
        assert "vA" in rd["new_elite"]
        assert "vB" not in rd["new_elite"]
        assert rd["front_size"] == 1

    def test_regression_6bfddeee_duplicate_archive_and_missing_population_child(self, tmp_path: Path) -> None:
        """Regression for run 6bfddeee: v6 duplicated in archive, v9 only in elite_set."""
        search_dir = tmp_path / "search"
        eval_dir = tmp_path / "eval"

        # Archive has 9 entries: v1-v8 from warm-up flush + v6 again from eviction
        archive = [
            _make_candidate(f"v{i}", "base", 0, quality=0.7 + i * 0.01, cost=0.5 - i * 0.01) for i in range(1, 9)
        ]
        archive.append(_make_candidate("v6", "base", 0, quality=0.76, cost=0.44))  # duplicate

        # elite_set has v1-v5, v7, v8, v9; v9 is a crossover child (only here, not in archive)
        elite_set = [
            _make_candidate(f"v{i}", "base", 0, quality=0.7 + i * 0.01, cost=0.5 - i * 0.01)
            for i in [1, 2, 3, 4, 5, 7, 8]
        ]
        elite_set.append(_make_candidate("v9", "v7", 1, quality=0.88, cost=0.42, secondary_parent="v8"))

        state = {
            "search_state_id": "6bfddeee",
            "backend": "anthropic",
            "primary_metric_name": "accuracy",
            "iteration": 1,
            "algorithm": "sms_emoa",
            "algorithm_state": {"mu": 8},
            "elite_set": elite_set,
            "warm_up_complete": True,
            "evaluation_budget": 50,
            "evaluations_used": 9,
            "reference_delta": 0.05,
            "stagnation_window": 5,
            "reference_point": [0.5, 0.6],
            "converged": False,
            "loop_phase": "review",
            "active_evals": [],
        }

        _write_json(search_dir / "search_state.json", state)
        _write_json(search_dir / "candidate_archive.json", archive)
        _write_json(search_dir / "pending_candidates.json", [])

        # Write eval reports for all 9 unique versions (v1-v9)
        for i in range(1, 10):
            v = f"v{i}"
            _write_json(
                eval_dir / v / "report.json",
                _make_eval_report(
                    quality_change=0.05 + i * 0.01,
                    cost_change=-0.1 - i * 0.01,
                    predicted_cost=0.4 - i * 0.01,
                ),
            )

        data = collect_data(search_dir, run_dir=tmp_path)

        # Deduplicated: 9 unique versions (v1-v9), not 10
        assert len(data["candidates"]) == 9

        # Two iterations: I0 (8 warm-up seeds) and I1 (v9)
        assert len(data["iterations"]) == 2
        iter_nums = [r["iteration"] for r in data["iterations"]]
        assert iter_nums == [0, 1]

        iter0 = data["iterations"][0]
        assert iter0["iteration"] == 0
        assert len(iter0["candidates"]) == 8
        # v6 appears exactly once in I0
        assert iter0["candidates"].count("v6") == 1

        iter1 = data["iterations"][1]
        assert iter1["iteration"] == 1
        assert iter1["candidates"] == ["v9"]

        # v9 entry has correct parent linkage
        v9 = next(c for c in data["candidates"] if c["version"] == "v9")
        assert v9["parent"] == "v7"
        assert v9["secondary_parent"] == "v8"

        # v6 is dominated (not in elite_set), v9 is on the front (in elite_set)
        v6 = next(c for c in data["candidates"] if c["version"] == "v6")
        assert v6["on_front"] is False
        assert v9["on_front"] is True


class TestLegacyStateCompat:
    """Legacy SMS-EMOA state-file shapes (top-level population + mu) still read correctly."""

    def test_legacy_smsemoa_state_shape_still_reads(self, tmp_path: Path) -> None:
        """Legacy state with top-level 'population' and 'mu' still produces a non-empty candidates list
        and the mu chip appears via the algorithm_state fallback path."""
        search_dir = tmp_path / "search"
        eval_dir = tmp_path / "eval"

        # Legacy shape: top-level 'population' and 'mu' (no elite_set, no algorithm_state)
        archive = [_make_candidate(f"cv-0-{i}", None, 0, quality=0.7 + i * 0.01, cost=0.5 - i * 0.01) for i in range(4)]

        state = {
            "search_state_id": "legacy-test",
            "backend": "anthropic",
            "iteration": 0,
            "mu": 4,  # top-level, legacy SMS-EMOA shape
            "population": archive,  # legacy key, not elite_set
            "algorithm": "sms_emoa",  # algorithm present so chip adapter activates
            "warm_up_complete": True,
            "evaluation_budget": 20,
            "evaluations_used": 4,
            "converged": False,
            "loop_phase": "review",
            "active_evals": [],
        }

        _write_json(search_dir / "search_state.json", state)
        _write_json(search_dir / "candidate_archive.json", archive)
        _write_json(search_dir / "pending_candidates.json", [])

        for i in range(4):
            v = f"cv-0-{i}"
            _write_json(eval_dir / v / "report.json", _make_eval_report())

        data = collect_data(search_dir, run_dir=tmp_path)

        # Legacy shape still produces candidates
        assert len(data["candidates"]) > 0

        # The mu chip should appear via the top-level fallback in _algorithm_chips
        assert len(data["algorithm_chips"]) == 1
        assert data["algorithm_chips"][0]["label"] == "population (μ)"
        assert data["algorithm_chips"][0]["value"] == 4


class TestStrategySeams:
    """Strategy label and algorithm_chips injection seams work correctly."""

    def test_strategy_seams_for_non_smsemoa(self, tmp_path: Path) -> None:
        """A parallel_beam state yields correct strategy_label and empty algorithm_chips."""
        search_dir = tmp_path / "search"

        archive = [_make_candidate("cv-0-0", None, 0)]
        state = {
            "search_state_id": "beam-test",
            "backend": "anthropic",
            "iteration": 0,
            "algorithm": "parallel_beam",
            "elite_set": archive,
            "warm_up_complete": True,
            "evaluation_budget": 20,
            "evaluations_used": 1,
            "converged": False,
            "loop_phase": "review",
            "active_evals": [],
        }

        _write_json(search_dir / "search_state.json", state)
        _write_json(search_dir / "candidate_archive.json", archive)
        _write_json(search_dir / "pending_candidates.json", [])

        data = collect_data(search_dir, run_dir=tmp_path)

        assert data["strategy_label"] == "Parallel Beam Search"
        assert data["algorithm_chips"] == []


class TestEmosaAlgorithmChips:
    """EMOSA _algorithm_chips adapter renders correct chips; non-emosa runs are guarded."""

    def _make_emosa_state(self, tmp_path: Path, **pocket_overrides: object) -> dict:
        """Write a minimal EMOSA search_state.json and return the data from collect_data."""
        search_dir = tmp_path / "search"
        archive = [_make_candidate("v1", None, 0)]
        # Build per-trajectory state (temperature/step_count are now per-trajectory)
        trajectories = [
            {
                "trajectory_id": i,
                "weight_vector": [0.5, 0.5],
                "temperature": 0.5,
                "alpha": 0.95,
                "step_count": 3,
            }
            for i in range(5)
        ]
        pocket: dict = {
            "t_min": 0.01,
            "num_trajectories": 5,
            "trajectories": trajectories,
            "total_evals": 15,
            "max_evals": 50,
            "phase": "search",
        }
        pocket.update(pocket_overrides)
        state = {
            "search_state_id": "emosa-test",
            "backend": "mock-echo",
            "round": 1,
            "algorithm": "emosa",
            "algorithm_state": pocket,
            "elite_set": archive,
            "converged": False,
            "loop_phase": "review",
            "active_evals": [],
        }
        _write_json(search_dir / "search_state.json", state)
        _write_json(search_dir / "candidate_archive.json", archive)
        _write_json(search_dir / "pending_candidates.json", [])
        return collect_data(search_dir, run_dir=tmp_path)

    def test_emosa_chips_renders_all_four_chips(self, tmp_path: Path) -> None:
        """emosa run renders traj, T (min–max range), step (min–max range), and evals chips."""
        data = self._make_emosa_state(tmp_path)
        chips = {c["label"]: c["value"] for c in data["algorithm_chips"]}

        assert "traj" in chips
        assert chips["traj"] == "5"

        # T shows min–max range; all 5 trajectories have T=0.5, so range is "5.00e-01–5.00e-01"
        assert "T" in chips
        assert chips["T"] == "5.00e-01–5.00e-01"

        # step shows min–max range; all trajectories have step=3
        assert "step" in chips
        assert chips["step"] == "3–3"

        assert "evals" in chips
        assert chips["evals"] == "15/50"

    def test_non_emosa_run_does_not_render_emosa_chips(self, tmp_path: Path) -> None:
        """hill_climb run does NOT render traj, T, step, or evals chips (regression guard)."""
        search_dir = tmp_path / "search"
        archive = [_make_candidate("v1", None, 0)]
        state = {
            "search_state_id": "hill-climb-test",
            "backend": "anthropic",
            "round": 1,
            "algorithm": "hill_climb",
            "algorithm_state": {},
            "elite_set": archive,
            "converged": False,
            "loop_phase": "review",
            "active_evals": [],
        }
        _write_json(search_dir / "search_state.json", state)
        _write_json(search_dir / "candidate_archive.json", archive)
        _write_json(search_dir / "pending_candidates.json", [])
        data = collect_data(search_dir, run_dir=tmp_path)

        chip_labels = {c["label"] for c in data["algorithm_chips"]}
        assert "traj" not in chip_labels
        assert "T" not in chip_labels
        assert "step" not in chip_labels
        assert "evals" not in chip_labels
