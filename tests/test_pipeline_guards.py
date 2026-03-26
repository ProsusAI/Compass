from pathlib import Path

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.agents.pipeline_guards import check_artifacts, require_artifacts


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
            tmp_path / "missing.json", stage=3, stage_name="Routing Analysis", hint="Complete phases 1-3 first."
        )
        def my_tool() -> str:
            return "ok"

        with pytest.raises(ToolError, match="stage 3") as exc_info:
            my_tool()
        msg = str(exc_info.value)
        assert "Routing Analysis" in msg
        assert "Complete phases 1-3 first." in msg
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
