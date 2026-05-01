"""Smoke tests for Prompt Builder MCP tools."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from odysseus.mcp import (
    advance_step_tool,
    filter_holdout_dataset_tool,
    get_child_variants_tool,
    get_edit_directives_tool,
    get_search_state_tool,
    init_search_state_tool,
    record_eval_result_tool,
    register_candidate_tool,
)

_RUN_ID = "test_run"

RESOLVE_PROJECT_DIR = "odysseus.project_dir.resolve_project_dir"
_SEARCH_OPS_PATCH = "odysseus.agents.prompt_builder.search_ops.get_project_dir"


@contextmanager
def _patch_project_dir(tmp_path: Path):
    """Patch project dir resolution in all relevant modules."""
    with (
        patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
        patch(_SEARCH_OPS_PATCH, return_value=tmp_path),
    ):
        yield


def _setup_guard_artifacts(tmp_path: Path, run_id: str = _RUN_ID, stage: str = "analysis") -> None:
    """Create prerequisite artifacts so pipeline guards pass."""
    # Stage 1 prerequisite
    input_dir = tmp_path / "outputs" / run_id / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "input_report.md").write_text("# Report")

    # Stage 2 prerequisites
    val_dir = tmp_path / "outputs" / run_id / "validation"
    val_dir.mkdir(parents=True, exist_ok=True)
    (val_dir / "data_quality_report.json").write_text("{}")
    (val_dir / "routing_context.json").write_text("{}")
    (val_dir / "transformed.jsonl").write_text("")

    if stage in ("analysis", "search"):
        # Stage 3 prerequisites
        analysis_dir = tmp_path / "outputs" / run_id / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "validation_report.json").write_text("{}")
        (analysis_dir / "dev.jsonl").write_text("")
        (analysis_dir / "holdout.jsonl").write_text("")


class TestSearchStateTools:
    async def test_init_returns_valid_json(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            result = await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test")
            data = json.loads(result)
            assert "search_state_id" in data
            assert data["backend"] == "test"

    async def test_init_sets_defaults(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            result = await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="anthropic")
            data = json.loads(result)
            assert data["max_rounds"] == 50
            assert data["stagnation_limit"] == 3
            assert data["convergence_limit"] == 5
            assert data["round"] == 0
            assert data["converged"] is False

    async def test_full_round_lifecycle(self, tmp_path: Path) -> None:
        """EMOSA calibration lifecycle: init K=5 state, register+score K candidates, advance."""
        import json as _json

        from odysseus.agents.prompt_builder.annealing import (
            AnnealingState,
            TrajectoryState,
            compute_weight_vectors,
        )
        from odysseus.agents.prompt_builder.search_ops import _load_state, _save_state

        _setup_guard_artifacts(tmp_path, stage="search")
        output_dir = tmp_path / "outputs"
        with _patch_project_dir(tmp_path):
            # Init -> patch to calibration phase -> Register K=5 candidates -> Record -> Advance -> Get
            init_result = _json.loads(await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test"))
            assert "search_state_id" in init_result

            # Patch persisted state to calibration phase with full AnnealingState pocket
            num_traj = 5
            wvs = compute_weight_vectors(num_traj)
            trajs = [TrajectoryState(trajectory_id=i, weight_vector=wvs[i]) for i in range(num_traj)]
            annealing = AnnealingState(
                num_trajectories=num_traj, trajectories=trajs, phase="calibration", total_evals=0
            )
            state = _load_state(_RUN_ID, output_dir)
            patched = state.model_copy(
                update={
                    "algorithm_state": _json.loads(annealing.model_dump_json()),
                    "loop_phase": "calibration",
                }
            )
            _save_state(_RUN_ID, patched, output_dir)

            for i in range(num_traj):
                await register_candidate_tool(_RUN_ID, f"v{i + 1}")
                # Use scores where each candidate trades off on a different objective,
                # so all K are mutually non-dominated (Pareto front has K entries).
                # v_i: quality = 0.5 + 0.1*i (increasing), cost = 0.1 + 0.1*i (increasing).
                # No candidate dominates another: higher quality always comes with higher cost.
                await record_eval_result_tool(_RUN_ID, f"v{i + 1}", 0.5 + i * 0.1, 0.1 + i * 0.1)

            adv = _json.loads(await advance_step_tool(_RUN_ID))
            assert adv["round"] == 1
            assert adv["new_elite_entries"] == num_traj  # all K seeds are Pareto-non-dominated

            state_after = _json.loads(await get_search_state_tool(_RUN_ID))
            assert state_after["round"] == 1

    async def test_register_candidate_returns_confirmation(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test")

            reg = json.loads(await register_candidate_tool(_RUN_ID, "v1"))
            assert reg["registered"] == "v1"

    async def test_register_duplicate_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test")

            await register_candidate_tool(_RUN_ID, "v1")
            with pytest.raises(ToolError):
                await register_candidate_tool(_RUN_ID, "v1")

    async def test_record_eval_result_returns_scores(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test")

            await register_candidate_tool(_RUN_ID, "v1")
            result = json.loads(await record_eval_result_tool(_RUN_ID, "v1", 0.9, 0.05))
            assert result["prompt_version"] == "v1"
            assert result["quality_score"] == pytest.approx(0.9)
            assert result["cost"] == pytest.approx(0.05)

    async def test_record_eval_unknown_version_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test")

            with pytest.raises(ToolError):
                await record_eval_result_tool(_RUN_ID, "nonexistent", 0.5, 0.1)

    async def test_advance_round_no_pending_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path):
            await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test")

            with pytest.raises(ToolError):
                await advance_step_tool(_RUN_ID)

    async def test_get_search_state_unknown_id_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with _patch_project_dir(tmp_path), pytest.raises(ToolError):
            await get_search_state_tool("nonexistent-id")

    async def test_calibration_advance_flips_to_review(self, tmp_path: Path) -> None:
        """EMOSA calibration: after K=5 candidates are scored and advance_step runs,
        loop_phase flips from 'calibration' to 'review'."""
        import json as _json

        from odysseus.agents.prompt_builder.annealing import (
            AnnealingState,
            TrajectoryState,
            compute_weight_vectors,
        )
        from odysseus.agents.prompt_builder.search_ops import _load_state, _save_state

        _setup_guard_artifacts(tmp_path, stage="search")
        output_dir = tmp_path / "outputs"
        with _patch_project_dir(tmp_path):
            await init_search_state_tool(ctx=None, run_id=_RUN_ID, backend="test", stagnation_limit=2)

            # Patch to calibration phase with full AnnealingState pocket
            num_traj = 5
            wvs = compute_weight_vectors(num_traj)
            trajs = [TrajectoryState(trajectory_id=i, weight_vector=wvs[i]) for i in range(num_traj)]
            annealing = AnnealingState(
                num_trajectories=num_traj, trajectories=trajs, phase="calibration", total_evals=0
            )
            state = _load_state(_RUN_ID, output_dir)
            patched = state.model_copy(
                update={
                    "algorithm_state": _json.loads(annealing.model_dump_json()),
                    "loop_phase": "calibration",
                }
            )
            _save_state(_RUN_ID, patched, output_dir)

            # Register and score K=5 candidates with mutually non-dominated scores
            for i in range(num_traj):
                await register_candidate_tool(_RUN_ID, f"v{i + 1}")
                # Trade-off: higher quality = higher cost; no candidate dominates another.
                await record_eval_result_tool(_RUN_ID, f"v{i + 1}", 0.5 + i * 0.1, 0.1 + i * 0.1)

            r1 = json.loads(await advance_step_tool(_RUN_ID))
            assert r1["new_elite_entries"] == num_traj  # all K seeds are Pareto-non-dominated

            # After calibration completes, loop_phase should flip to 'review'
            state_after = _json.loads(await get_search_state_tool(_RUN_ID))
            assert state_after["loop_phase"] == "review"


class TestFilterHoldoutTool:
    async def test_filters_examples(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        holdout = tmp_path / "holdout.jsonl"
        holdout.write_text(
            '{"id":"ex1","input":"q1","expected":{"route":"a","routes":{"a":{"cost":0.01,"quality_score":0.9}}}}\n'
            '{"id":"ex2","input":"q2","expected":{"route":"b","routes":{"b":{"cost":0.02,"quality_score":0.8}}}}\n'
        )
        with _patch_project_dir(tmp_path):
            result = json.loads(
                await filter_holdout_dataset_tool(
                    ctx=None, holdout_jsonl_path=str(holdout), exclude_ids=["ex1"], run_id=_RUN_ID
                )
            )
        assert "filtered_holdout_path" in result

        filtered = Path(result["filtered_holdout_path"])
        lines = filtered.read_text().strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["id"] == "ex2"

    async def test_missing_file_raises_tool_error(self, tmp_path: Path) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        _setup_guard_artifacts(tmp_path, stage="search")
        with _patch_project_dir(tmp_path), pytest.raises(ToolError):
            await filter_holdout_dataset_tool(
                ctx=None, holdout_jsonl_path="/nonexistent.jsonl", exclude_ids=[], run_id=_RUN_ID
            )

    async def test_empty_exclude_list_keeps_all_rows(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        holdout = tmp_path / "holdout.jsonl"
        holdout.write_text(
            '{"id":"ex1","input":"q1","expected":{"route":"a","routes":{"a":{"cost":0.01,"quality_score":0.9}}}}\n'
            '{"id":"ex2","input":"q2","expected":{"route":"b","routes":{"b":{"cost":0.02,"quality_score":0.8}}}}\n'
        )
        with _patch_project_dir(tmp_path):
            result = json.loads(
                await filter_holdout_dataset_tool(
                    ctx=None, holdout_jsonl_path=str(holdout), exclude_ids=[], run_id=_RUN_ID
                )
            )
        filtered = Path(result["filtered_holdout_path"])
        lines = filtered.read_text().strip().splitlines()
        assert len(lines) == 2

    async def test_exclude_all_rows_produces_empty_file(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        holdout = tmp_path / "holdout.jsonl"
        holdout.write_text(
            '{"id":"ex1","input":"q1","expected":{"route":"a","routes":{"a":{"cost":0.01,"quality_score":0.9}}}}\n'
        )
        with _patch_project_dir(tmp_path):
            result = json.loads(
                await filter_holdout_dataset_tool(
                    ctx=None, holdout_jsonl_path=str(holdout), exclude_ids=["ex1"], run_id=_RUN_ID
                )
            )
        filtered = Path(result["filtered_holdout_path"])
        content = filtered.read_text().strip()
        assert content == ""

    async def test_output_filename_has_filtered_suffix(self, tmp_path: Path) -> None:
        _setup_guard_artifacts(tmp_path, stage="search")
        holdout = tmp_path / "holdout.jsonl"
        holdout.write_text(
            '{"id":"ex1","input":"q1","expected":{"route":"a","routes":{"a":{"cost":0.01,"quality_score":0.9}}}}\n'
        )
        with _patch_project_dir(tmp_path):
            result = json.loads(
                await filter_holdout_dataset_tool(
                    ctx=None, holdout_jsonl_path=str(holdout), exclude_ids=[], run_id=_RUN_ID
                )
            )
        assert "holdout_filtered" in result["filtered_holdout_path"]


class TestRecordDirectiveOutcomesToolLoopPhase:
    @pytest.mark.asyncio
    async def test_transitions_loop_phase_to_build(self, tmp_path: Path) -> None:
        from odysseus.agents.prompt_builder.search_ops import get_search_state, init_search_state, set_loop_phase
        from odysseus.mcp import record_directive_outcomes_tool

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            # Init search state in review phase
            init_search_state(
                "anthropic",
                run_id=_RUN_ID,
                output_dir=tmp_path / "outputs",
            )
            set_loop_phase(_RUN_ID, "review", output_dir=tmp_path / "outputs")

            await record_directive_outcomes_tool(
                ctx=None,
                run_id=_RUN_ID,
                outcomes=[],
                output_dir=str(tmp_path / "outputs"),
            )

            state = get_search_state(run_id=_RUN_ID, output_dir=tmp_path / "outputs")
            assert state.loop_phase == "build"


class TestEditDirectivesPersistence:
    @pytest.mark.asyncio
    async def test_record_persists_child_variants(self, tmp_path: Path) -> None:
        from odysseus.agents.prompt_builder.search_ops import init_search_state, set_loop_phase
        from odysseus.agents.review.ops import load_child_variants
        from odysseus.mcp import record_directive_outcomes_tool

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            init_search_state("anthropic", run_id=_RUN_ID, output_dir=tmp_path / "outputs")
            set_loop_phase(_RUN_ID, "review", output_dir=tmp_path / "outputs")

            result = await record_directive_outcomes_tool(
                ctx=None,
                run_id=_RUN_ID,
                outcomes=[],
                child_variants=[
                    {
                        "hypothesis": "Add a clearer boundary example",
                        "directives": [
                            {
                                "directive_id": "d1",
                                "target_version": "v1",
                                "block_type": "example",
                                "block_identifier": "Example 1",
                                "granularity": "macro",
                                "directive": "Add example",
                                "priority": "high",
                            }
                        ],
                    }
                ],
                output_dir=str(tmp_path / "outputs"),
            )

            data = json.loads(result)
            assert data["child_variants_saved"] == 1

            loaded = load_child_variants(_RUN_ID, output_dir=tmp_path / "outputs")
            assert len(loaded) == 1
            assert loaded[0].directives[0].directive_id == "d1"

    @pytest.mark.asyncio
    async def test_get_edit_directives_tool(self, tmp_path: Path) -> None:
        from odysseus.agents.review.models import ChildVariant, EditDirective
        from odysseus.agents.review.ops import save_child_variants

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            variant = ChildVariant(
                hypothesis="Test hypothesis",
                directives=[
                    EditDirective(
                        directive_id="d1",
                        target_version="v1",
                        block_type="rule",
                        block_identifier="Rule 1",
                        granularity="micro",
                        directive="Tighten wording",
                        priority="medium",
                    ),
                ],
            )
            save_child_variants(_RUN_ID, [variant], output_dir=tmp_path / "outputs")

            result = await get_edit_directives_tool(
                ctx=None,
                run_id=_RUN_ID,
                output_dir=str(tmp_path / "outputs"),
            )
            data = json.loads(result)
            assert len(data) == 1
            assert data[0]["directive_id"] == "d1"

    @pytest.mark.asyncio
    async def test_get_edit_directives_tool_empty(self, tmp_path: Path) -> None:
        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            result = await get_edit_directives_tool(
                ctx=None,
                run_id=_RUN_ID,
                output_dir=str(tmp_path / "outputs"),
            )
            data = json.loads(result)
            assert data == []

    @pytest.mark.asyncio
    async def test_get_edit_directives_tool_flattens_multiple_variants(self, tmp_path: Path) -> None:
        """get_edit_directives_tool must flatten directives across all child variants in file order."""
        from odysseus.agents.review.models import ChildVariant, EditDirective
        from odysseus.agents.review.ops import save_child_variants

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            variant_a = ChildVariant(
                hypothesis="First variant",
                directives=[
                    EditDirective(
                        directive_id="d1",
                        target_version="v1",
                        block_type="rule",
                        block_identifier="Rule 1",
                        granularity="micro",
                        directive="Edit A",
                        priority="high",
                    ),
                ],
            )
            variant_b = ChildVariant(
                hypothesis="Second variant",
                directives=[
                    EditDirective(
                        directive_id="d2",
                        target_version="v1",
                        block_type="example",
                        block_identifier="Example 1",
                        granularity="macro",
                        directive="Edit B",
                        priority="medium",
                    ),
                    EditDirective(
                        directive_id="d3",
                        target_version="v1",
                        block_type="rule",
                        block_identifier="Rule 2",
                        granularity="micro",
                        directive="Edit C",
                        priority="low",
                    ),
                ],
            )
            save_child_variants(_RUN_ID, [variant_a, variant_b], output_dir=tmp_path / "outputs")

            result = await get_edit_directives_tool(
                ctx=None,
                run_id=_RUN_ID,
                output_dir=str(tmp_path / "outputs"),
            )
            data = json.loads(result)
            assert len(data) == 3
            assert [d["directive_id"] for d in data] == ["d1", "d2", "d3"]

    @pytest.mark.asyncio
    async def test_get_child_variants_tool(self, tmp_path: Path) -> None:
        from odysseus.agents.review.models import ChildVariant, EditDirective
        from odysseus.agents.review.ops import save_child_variants

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            variant = ChildVariant(
                hypothesis="Add a clearer boundary example",
                directives=[
                    EditDirective(
                        directive_id="d1",
                        target_version="v1",
                        block_type="example",
                        block_identifier="Example 1",
                        granularity="macro",
                        directive="Add example",
                        priority="high",
                    ),
                ],
            )
            save_child_variants(_RUN_ID, [variant], output_dir=tmp_path / "outputs")

            result = await get_child_variants_tool(
                ctx=None,
                run_id=_RUN_ID,
                output_dir=str(tmp_path / "outputs"),
            )
            data = json.loads(result)
            assert len(data) == 1
            assert data[0]["hypothesis"] == "Add a clearer boundary example"
            assert len(data[0]["directives"]) == 1
            assert data[0]["directives"][0]["directive_id"] == "d1"


class TestTrajectoryChildVariantsFallback:
    """Tests for EMOSA per-trajectory child variant source-resolution precedence."""

    @pytest.mark.asyncio
    async def test_get_child_variants_prefers_trajectory_files(self, tmp_path: Path) -> None:
        """When per-trajectory files exist, get_child_variants_tool returns them in trajectory_id order."""
        from odysseus.agents.review.models import ChildVariant, EditDirective
        from odysseus.agents.review.ops import save_child_variants, save_trajectory_child_variants

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")

            # Write three per-trajectory files (t0, t1, t2)
            for tid, hyp, did in [
                (0, "Trajectory 0 variant", "t0_d1"),
                (1, "Trajectory 1 variant", "t1_d1"),
                (2, "Trajectory 2 variant", "t2_d1"),
            ]:
                variant = ChildVariant(
                    hypothesis=hyp,
                    directives=[
                        EditDirective(
                            directive_id=did,
                            target_version="v1",
                            block_type="example",
                            block_identifier="Example 1",
                            granularity="macro",
                            directive="Add example",
                            priority="high",
                        ),
                    ],
                )
                save_trajectory_child_variants(_RUN_ID, tid, [variant], output_dir=tmp_path / "outputs")

            # Write a stale single-slot file with a clearly different variant
            stale_variant = ChildVariant(
                hypothesis="STALE single-slot variant — should be ignored",
                directives=[
                    EditDirective(
                        directive_id="stale_d1",
                        target_version="v1",
                        block_type="rule",
                        block_identifier="Rule 99",
                        granularity="micro",
                        directive="Stale edit",
                        priority="low",
                    ),
                ],
            )
            save_child_variants(_RUN_ID, [stale_variant], output_dir=tmp_path / "outputs")

            result = await get_child_variants_tool(
                ctx=None,
                run_id=_RUN_ID,
                output_dir=str(tmp_path / "outputs"),
            )
            data = json.loads(result)

            # Should return the three per-trajectory variants, not the stale one
            assert len(data) == 3
            hypotheses = [d["hypothesis"] for d in data]
            assert "Trajectory 0 variant" in hypotheses
            assert "Trajectory 1 variant" in hypotheses
            assert "Trajectory 2 variant" in hypotheses
            assert "STALE single-slot variant — should be ignored" not in hypotheses

            # Returned in trajectory_id order (t0, t1, t2)
            assert hypotheses == ["Trajectory 0 variant", "Trajectory 1 variant", "Trajectory 2 variant"]

            directive_ids = [d["directives"][0]["directive_id"] for d in data]
            assert directive_ids == ["t0_d1", "t1_d1", "t2_d1"]

    @pytest.mark.asyncio
    async def test_get_edit_directives_prefers_trajectory_files(self, tmp_path: Path) -> None:
        """get_edit_directives_tool must also use per-trajectory files when present."""
        from odysseus.agents.review.models import ChildVariant, EditDirective
        from odysseus.agents.review.ops import save_child_variants, save_trajectory_child_variants

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")

            for tid, did in [(0, "t0_d1"), (1, "t1_d1")]:
                variant = ChildVariant(
                    hypothesis=f"Trajectory {tid}",
                    directives=[
                        EditDirective(
                            directive_id=did,
                            target_version="v1",
                            block_type="example",
                            block_identifier="Example 1",
                            granularity="macro",
                            directive="Add example",
                            priority="high",
                        ),
                    ],
                )
                save_trajectory_child_variants(_RUN_ID, tid, [variant], output_dir=tmp_path / "outputs")

            # Write stale single-slot file
            stale_variant = ChildVariant(
                hypothesis="STALE",
                directives=[
                    EditDirective(
                        directive_id="stale_d1",
                        target_version="v1",
                        block_type="rule",
                        block_identifier="Rule 1",
                        granularity="micro",
                        directive="Stale",
                        priority="low",
                    ),
                ],
            )
            save_child_variants(_RUN_ID, [stale_variant], output_dir=tmp_path / "outputs")

            result = await get_edit_directives_tool(
                ctx=None,
                run_id=_RUN_ID,
                output_dir=str(tmp_path / "outputs"),
            )
            data = json.loads(result)

            directive_ids = [d["directive_id"] for d in data]
            assert "stale_d1" not in directive_ids
            assert directive_ids == ["t0_d1", "t1_d1"]

    @pytest.mark.asyncio
    async def test_get_child_variants_falls_back_to_single_slot(self, tmp_path: Path) -> None:
        """When no per-trajectory files exist, get_child_variants_tool returns single-slot variants."""
        from odysseus.agents.review.models import ChildVariant, EditDirective
        from odysseus.agents.review.ops import save_child_variants

        with _patch_project_dir(tmp_path):
            _setup_guard_artifacts(tmp_path, stage="search")
            variant = ChildVariant(
                hypothesis="Single-slot variant",
                directives=[
                    EditDirective(
                        directive_id="single_d1",
                        target_version="v1",
                        block_type="example",
                        block_identifier="Example 1",
                        granularity="macro",
                        directive="Edit",
                        priority="medium",
                    ),
                ],
            )
            save_child_variants(_RUN_ID, [variant], output_dir=tmp_path / "outputs")

            result = await get_child_variants_tool(
                ctx=None,
                run_id=_RUN_ID,
                output_dir=str(tmp_path / "outputs"),
            )
            data = json.loads(result)
            assert len(data) == 1
            assert data[0]["hypothesis"] == "Single-slot variant"
            assert data[0]["directives"][0]["directive_id"] == "single_d1"
