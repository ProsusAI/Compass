"""Tests for pipeline artifact guards and Stage-4 dispatch-marker guards."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.agents.pipeline.dispatch import record_build_dispatched
from odysseus.agents.pipeline.guards import check_artifacts, require_artifacts
from odysseus.agents.pipeline.status import _detect_stage_4_phase


class TestRequireArtifacts:
    def test_passes_when_all_exist(self, tmp_path: Path) -> None:
        (tmp_path / "a.json").write_text("{}")
        (tmp_path / "b.json").write_text("{}")

        @require_artifacts(
            tmp_path / "a.json",
            tmp_path / "b.json",
            stage=2,
            stage_name="Data Validated",
            hint="Run validate_dataset first.",
        )
        def my_tool() -> str:
            return "ok"

        assert my_tool() == "ok"

    def test_raises_when_missing(self, tmp_path: Path) -> None:
        (tmp_path / "a.json").write_text("{}")

        @require_artifacts(
            tmp_path / "a.json",
            tmp_path / "missing.json",
            stage=2,
            stage_name="Data Validated",
            hint="Run validate_dataset first.",
        )
        def my_tool() -> str:
            return "ok"

        with pytest.raises(ToolError, match="Pipeline precondition not met"):
            my_tool()

    def test_lists_all_missing(self, tmp_path: Path) -> None:
        @require_artifacts(
            tmp_path / "a.json",
            tmp_path / "b.json",
            stage=2,
            stage_name="Data Validated",
            hint="Run validate_dataset first.",
        )
        def my_tool() -> str:
            return "ok"

        with pytest.raises(ToolError, match="a.json") as exc_info:
            my_tool()
        assert "b.json" in str(exc_info.value)

    def test_error_includes_stage_hint_and_status_ref(self, tmp_path: Path) -> None:
        @require_artifacts(
            tmp_path / "missing.json", stage=3, stage_name="Data Validation", hint="Complete data validation first."
        )
        def my_tool() -> str:
            return "ok"

        with pytest.raises(ToolError, match="stage 3") as exc_info:
            my_tool()
        msg = str(exc_info.value)
        assert "Data Validation" in msg
        assert "Complete data validation first." in msg
        assert "get_pipeline_status" in msg

    async def test_works_with_async(self, tmp_path: Path) -> None:
        (tmp_path / "a.json").write_text("{}")

        @require_artifacts(tmp_path / "a.json", stage=1, stage_name="Input", hint="Submit report.")
        async def my_async_tool() -> str:
            return "ok"

        assert await my_async_tool() == "ok"

    async def test_raises_for_async_when_missing(self, tmp_path: Path) -> None:
        @require_artifacts(tmp_path / "missing.json", stage=1, stage_name="Input", hint="Submit report.")
        async def my_async_tool() -> str:
            return "ok"

        with pytest.raises(ToolError, match="Pipeline precondition not met"):
            await my_async_tool()


class TestCheckArtifacts:
    def test_passes_when_all_exist(self, tmp_path: Path) -> None:
        (tmp_path / "a.json").write_text("{}")
        check_artifacts(tmp_path / "a.json", stage=1, stage_name="Input", hint="Submit report.")

    def test_raises_when_missing(self, tmp_path: Path) -> None:
        with pytest.raises(ToolError, match="Pipeline precondition not met"):
            check_artifacts(tmp_path / "nope.json", stage=1, stage_name="Input", hint="Submit report.")


# ---------------------------------------------------------------------------
# Stage-4 dispatch-marker guards via complete_stage
# ---------------------------------------------------------------------------

_SEARCH_OPS_PATCH = "odysseus.agents.prompt_builder.search_ops.get_project_dir"
_DISPATCH_PATCH = "odysseus.agents.pipeline.dispatch.get_project_dir"


def _setup_stage_scope(stage_name: str) -> None:
    """Set the active MCP stage so complete_stage is callable."""
    from odysseus.mcp.server import set_active_stage

    set_active_stage(stage_name)


def _teardown_stage_scope() -> None:
    """Reset MCP stage to orchestrator after a test."""
    from odysseus.mcp.server import set_active_stage

    set_active_stage("orchestrator")


class TestCompleteStageBuildGuard:
    """complete_stage('prompt_building') should reject while build marker present.

    The dispatch module uses ``get_project_dir() / "outputs"`` as the base when
    no explicit ``output_dir`` is passed.  Tests patch ``get_project_dir`` in the
    dispatch module to ``tmp_path`` and create the marker under
    ``tmp_path / "outputs" / run_id / "search"``.
    """

    async def test_raises_when_build_dispatched(self, tmp_path: Path) -> None:
        from odysseus.mcp.orchestrator_tools import complete_stage

        # The dispatch module resolves: base = get_project_dir() / "outputs"
        # So the marker lives at tmp_path/outputs/run1/search/build_dispatched.json
        outputs_dir = tmp_path / "outputs"
        record_build_dispatched("run1", round=1, output_dir=outputs_dir)
        _setup_stage_scope("prompt_building")
        try:
            ctx = MagicMock()
            ctx.session.send_tool_list_changed = AsyncMock()
            with (
                patch(_DISPATCH_PATCH, return_value=tmp_path),
                pytest.raises(ToolError, match="Build sub-agent still dispatched"),
            ):
                await complete_stage(ctx, run_id="run1")
        finally:
            _teardown_stage_scope()

    async def test_passes_when_marker_absent(self, tmp_path: Path) -> None:
        from odysseus.mcp.orchestrator_tools import complete_stage

        _setup_stage_scope("prompt_building")
        try:
            ctx = MagicMock()
            ctx.session.send_tool_list_changed = AsyncMock()
            with patch(_DISPATCH_PATCH, return_value=tmp_path):
                result = await complete_stage(ctx, run_id="run1")
            assert "prompt_building" in result
        finally:
            _teardown_stage_scope()


class TestCompleteStageReviewGuard:
    """complete_stage('review') should reject while review fanout is incomplete.

    Same path convention as build guard: ``tmp_path/outputs/run_id/search``.
    """

    async def test_raises_when_fanout_incomplete(self, tmp_path: Path) -> None:
        from odysseus.mcp.orchestrator_tools import complete_stage

        # No child_variants.json and no review marker — fanout not_dispatched
        _setup_stage_scope("review")
        try:
            ctx = MagicMock()
            ctx.session.send_tool_list_changed = AsyncMock()
            with (
                patch(_DISPATCH_PATCH, return_value=tmp_path),
                pytest.raises(ToolError, match="Review fanout incomplete"),
            ):
                await complete_stage(ctx, run_id="run1")
        finally:
            _teardown_stage_scope()

    async def test_passes_when_child_variants_exist(self, tmp_path: Path) -> None:
        from odysseus.mcp.orchestrator_tools import complete_stage

        # child_variants.json at the dispatch-module path
        search_dir = tmp_path / "outputs" / "run1" / "search"
        search_dir.mkdir(parents=True)
        (search_dir / "child_variants.json").write_text("[]")

        _setup_stage_scope("review")
        try:
            ctx = MagicMock()
            ctx.session.send_tool_list_changed = AsyncMock()
            with patch(_DISPATCH_PATCH, return_value=tmp_path):
                result = await complete_stage(ctx, run_id="run1")
            assert "review" in result
        finally:
            _teardown_stage_scope()

    async def test_hill_climb_passes_with_child_variants(self, tmp_path: Path) -> None:
        """Regression: complete_stage('review') succeeds for hill_climb when child_variants.json present.

        Verifies that _BRANCH_ALGORITHM='hill_climb' is passed to review_fanout_status
        so it looks for the single-slot child_variants.json (not per-trajectory files).
        """
        from odysseus.mcp.orchestrator_tools import complete_stage

        search_dir = tmp_path / "outputs" / "run1" / "search"
        search_dir.mkdir(parents=True)
        (search_dir / "child_variants.json").write_text("[]")

        _setup_stage_scope("review")
        try:
            ctx = MagicMock()
            ctx.session.send_tool_list_changed = AsyncMock()
            with patch(_DISPATCH_PATCH, return_value=tmp_path):
                result = await complete_stage(ctx, run_id="run1")
            assert "review" in result
        finally:
            _teardown_stage_scope()

    async def test_hill_climb_fails_without_child_variants(self, tmp_path: Path) -> None:
        """Regression: complete_stage('review') fails for hill_climb when child_variants.json absent.

        Without child_variants.json the hill_climb fanout is incomplete (missing=[0])
        and complete_stage must raise ToolError.
        """
        from odysseus.mcp.orchestrator_tools import complete_stage

        # No child_variants.json — fanout slot 0 is missing
        _setup_stage_scope("review")
        try:
            ctx = MagicMock()
            ctx.session.send_tool_list_changed = AsyncMock()
            with (
                patch(_DISPATCH_PATCH, return_value=tmp_path),
                pytest.raises(ToolError, match="Review fanout incomplete"),
            ):
                await complete_stage(ctx, run_id="run1")
        finally:
            _teardown_stage_scope()


# ---------------------------------------------------------------------------
# Defense-in-depth phase flip in _detect_stage_4_phase
# ---------------------------------------------------------------------------


def _make_run_dir(tmp_path: Path, run_id: str = "run1") -> Path:
    """Create minimal run dir with v1 prompt and directive_history so we reach phase 3."""
    run_dir = tmp_path / run_id
    search_dir = run_dir / "search"
    search_dir.mkdir(parents=True)
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "v1.txt").write_text("prompt")
    (search_dir / "directive_history.json").write_text("[]")
    return run_dir


class TestDefenseInDepthPhaseFlip:
    def test_build_flips_to_review_when_no_artifacts(self, tmp_path: Path) -> None:
        """If loop_phase='build' but no child_variants.json and no build marker → 'review'."""
        run_dir = _make_run_dir(tmp_path)
        state = {
            "search_state_id": "abc",
            "backend": "test",
            "loop_phase": "build",
        }
        (run_dir / "search" / "search_state.json").write_text(json.dumps(state))

        phase = _detect_stage_4_phase(run_dir, rerun_config=None)
        assert phase == "review"

    def test_build_retained_when_build_marker_present(self, tmp_path: Path) -> None:
        """If loop_phase='build' and build_dispatched.json exists → keep 'build'."""
        run_dir = _make_run_dir(tmp_path)
        state = {
            "search_state_id": "abc",
            "backend": "test",
            "loop_phase": "build",
        }
        (run_dir / "search" / "search_state.json").write_text(json.dumps(state))
        record_build_dispatched("run1", round=2, output_dir=tmp_path)

        phase = _detect_stage_4_phase(run_dir, rerun_config=None)
        assert phase == "build"

    def test_build_retained_when_child_variants_present(self, tmp_path: Path) -> None:
        """If loop_phase='build' and child_variants.json exists → keep 'build'."""
        run_dir = _make_run_dir(tmp_path)
        state = {
            "search_state_id": "abc",
            "backend": "test",
            "loop_phase": "build",
        }
        (run_dir / "search" / "search_state.json").write_text(json.dumps(state))
        (run_dir / "search" / "child_variants.json").write_text("[]")

        phase = _detect_stage_4_phase(run_dir, rerun_config=None)
        assert phase == "build"

    def test_review_phase_unchanged(self, tmp_path: Path) -> None:
        """If loop_phase='review', no re-flip should occur."""
        run_dir = _make_run_dir(tmp_path)
        state = {
            "search_state_id": "abc",
            "backend": "test",
            "loop_phase": "review",
        }
        (run_dir / "search" / "search_state.json").write_text(json.dumps(state))

        phase = _detect_stage_4_phase(run_dir, rerun_config=None)
        assert phase == "review"

    def test_sms_emoa_build_flips_to_review_when_no_artifacts(self, tmp_path: Path) -> None:
        """sms_emoa: loop_phase='build', warm_up_complete, no child_variants → 'review'.

        Defense-in-depth guard in _detect_stage_4_phase_sms_emoa prevents
        deadlock when the review sub-agent exited silently without writing
        child_variants.json.
        """
        run_dir = _make_run_dir(tmp_path)
        state = {
            "algorithm": "sms_emoa",
            "search_state_id": "abc",
            "backend": "test",
            "loop_phase": "build",
            "warm_up_complete": True,
        }
        (run_dir / "search" / "search_state.json").write_text(json.dumps(state))

        phase = _detect_stage_4_phase(run_dir, rerun_config=None)
        assert phase == "review"

    def test_sms_emoa_build_retained_when_child_variants_present(self, tmp_path: Path) -> None:
        """sms_emoa: loop_phase='build', warm_up_complete, child_variants.json exists → 'build'."""
        run_dir = _make_run_dir(tmp_path)
        state = {
            "algorithm": "sms_emoa",
            "search_state_id": "abc",
            "backend": "test",
            "loop_phase": "build",
            "warm_up_complete": True,
        }
        (run_dir / "search" / "search_state.json").write_text(json.dumps(state))
        (run_dir / "search" / "child_variants.json").write_text("[{}]")

        phase = _detect_stage_4_phase(run_dir, rerun_config=None)
        assert phase == "build"


# ---------------------------------------------------------------------------
# SMS-EMOA: complete_stage review guard regression
# ---------------------------------------------------------------------------


class TestCompleteStageSmsEmoaReviewGuard:
    """Regression: complete_stage('review') with algorithm='sms_emoa' state.

    sms_emoa uses single-slot fanout (child_variants.json), the same as
    hill_climb.  These tests confirm the guard works correctly for runs that
    have algorithm='sms_emoa' persisted in search_state.json.
    """

    async def test_raises_when_child_variants_absent(self, tmp_path: Path) -> None:
        """complete_stage('review') raises when child_variants.json is missing."""
        from odysseus.mcp.orchestrator_tools import complete_stage

        # Create a run dir with algorithm=sms_emoa in state but no child_variants.json
        search_dir = tmp_path / "outputs" / "run1" / "search"
        search_dir.mkdir(parents=True)
        state = {
            "algorithm": "sms_emoa",
            "loop_phase": "review",
            "warm_up_complete": True,
        }
        (search_dir / "search_state.json").write_text(json.dumps(state))

        _setup_stage_scope("review")
        try:
            ctx = MagicMock()
            ctx.session.send_tool_list_changed = AsyncMock()
            with (
                patch(_DISPATCH_PATCH, return_value=tmp_path),
                pytest.raises(ToolError, match="Review fanout incomplete"),
            ):
                await complete_stage(ctx, run_id="run1")
        finally:
            _teardown_stage_scope()

    async def test_passes_when_child_variants_present(self, tmp_path: Path) -> None:
        """complete_stage('review') succeeds when child_variants.json is present."""
        from odysseus.mcp.orchestrator_tools import complete_stage

        search_dir = tmp_path / "outputs" / "run1" / "search"
        search_dir.mkdir(parents=True)
        state = {
            "algorithm": "sms_emoa",
            "loop_phase": "build",
            "warm_up_complete": True,
        }
        (search_dir / "search_state.json").write_text(json.dumps(state))
        (search_dir / "child_variants.json").write_text("[]")

        _setup_stage_scope("review")
        try:
            ctx = MagicMock()
            ctx.session.send_tool_list_changed = AsyncMock()
            with patch(_DISPATCH_PATCH, return_value=tmp_path):
                result = await complete_stage(ctx, run_id="run1")
            assert "review" in result
        finally:
            _teardown_stage_scope()
