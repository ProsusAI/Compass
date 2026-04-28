"""Tests for review MCP tools — record_directive_outcomes_tool decomposed params."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

from odysseus.mcp import get_prompt_text_tool, query_holdout_examples_tool, record_directive_outcomes_tool

_RESOLVE_PROJECT_DIR = "odysseus.mcp.review_tools._resolve_project_dir"
_SEARCH_OPS_PATCH = "odysseus.agents.prompt_builder.search_ops.get_project_dir"


@contextmanager
def _patch_project_dir(tmp_path: Path):
    with (
        patch(_RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
        patch(_SEARCH_OPS_PATCH, return_value=tmp_path),
    ):
        yield


_RUN_ID = "test-run-outcomes"

_OUTCOME = {
    "prior_directive_id": "d1",
    "was_attempted": True,
    "outcome": "improved",
}

_CANDIDATE_RANKING = [{"version": "v2", "rank": 1, "rationale": "best quality"}]
_PROMOTION_DECISIONS = [{"version": "v2", "decision": "promote", "reason": "top rank"}]
_REGRESSION_GUARDS: list[dict] = []
_LOOP_SIGNAL = {"action": "refine", "reason": "not converged yet"}
_CHILD_VARIANTS = [
    {
        "hypothesis": "Fix recall on route_a",
        "directives": [
            {
                "directive_id": "d2",
                "target_version": "v2",
                "block_type": "rule",
                "block_identifier": "Rule 1",
                "granularity": "micro",
                "directive": "Tighten wording",
                "priority": "medium",
            }
        ],
    }
]


class TestRecordDirectiveOutcomesDecomposed:
    """Tests for the decomposed-params path of record_directive_outcomes_tool."""

    async def test_decomposed_params_persists_review_result(self, tmp_path: Path) -> None:
        """Passing decomposed params writes a review_result.json to disk."""
        with _patch_project_dir(tmp_path):
            result_json = await record_directive_outcomes_tool(
                ctx=None,
                run_id=_RUN_ID,
                outcomes=[_OUTCOME],
                loop_signal=_LOOP_SIGNAL,
                child_variants=_CHILD_VARIANTS,
                candidate_ranking=_CANDIDATE_RANKING,
                promotion_decisions=_PROMOTION_DECISIONS,
                regression_guards=_REGRESSION_GUARDS,
                output_dir="outputs",
            )

        result = json.loads(result_json)
        assert result["recorded"] == 1

        review_result_path = tmp_path / "outputs" / _RUN_ID / "search" / "review_result.json"
        assert review_result_path.exists(), "review_result.json should be written for decomposed params"
        saved = json.loads(review_result_path.read_text())
        assert saved["candidate_ranking"] == _CANDIDATE_RANKING
        assert saved["promotion_decisions"] == _PROMOTION_DECISIONS
        assert saved["regression_guards"] == _REGRESSION_GUARDS
        assert saved["loop_signal"] == _LOOP_SIGNAL
        assert saved["child_variants"] == _CHILD_VARIANTS
        assert len(saved["directive_history_update"]) == 1

    async def test_legacy_review_result_path_persists(self, tmp_path: Path) -> None:
        """Passing review_result blob (legacy) also writes review_result.json."""
        legacy_blob = {
            "candidate_ranking": _CANDIDATE_RANKING,
            "promotion_decisions": _PROMOTION_DECISIONS,
            "regression_guards": _REGRESSION_GUARDS,
            "loop_signal": _LOOP_SIGNAL,
            "child_variants": _CHILD_VARIANTS,
            "directive_history_update": [_OUTCOME],
        }
        with _patch_project_dir(tmp_path):
            result_json = await record_directive_outcomes_tool(
                ctx=None,
                run_id=_RUN_ID,
                outcomes=[_OUTCOME],
                loop_signal=_LOOP_SIGNAL,
                child_variants=_CHILD_VARIANTS,
                review_result=legacy_blob,
                output_dir="outputs",
            )

        result = json.loads(result_json)
        assert result["recorded"] == 1

        review_result_path = tmp_path / "outputs" / _RUN_ID / "search" / "review_result.json"
        assert review_result_path.exists()
        saved = json.loads(review_result_path.read_text())
        assert saved["candidate_ranking"] == _CANDIDATE_RANKING

    async def test_decomposed_and_legacy_produce_same_candidate_ranking(self, tmp_path: Path) -> None:
        """Decomposed params and legacy review_result produce the same persisted candidate_ranking."""
        run_decomposed = "run-decomposed"
        run_legacy = "run-legacy"

        legacy_blob = {
            "candidate_ranking": _CANDIDATE_RANKING,
            "promotion_decisions": _PROMOTION_DECISIONS,
            "regression_guards": _REGRESSION_GUARDS,
            "directive_history_update": [],
        }

        with _patch_project_dir(tmp_path):
            await record_directive_outcomes_tool(
                ctx=None,
                run_id=run_decomposed,
                outcomes=[],
                candidate_ranking=_CANDIDATE_RANKING,
                promotion_decisions=_PROMOTION_DECISIONS,
                regression_guards=_REGRESSION_GUARDS,
                output_dir="outputs",
            )
            await record_directive_outcomes_tool(
                ctx=None,
                run_id=run_legacy,
                outcomes=[],
                review_result=legacy_blob,
                output_dir="outputs",
            )

        decomposed_path = tmp_path / "outputs" / run_decomposed / "search" / "review_result.json"
        legacy_path = tmp_path / "outputs" / run_legacy / "search" / "review_result.json"

        decomposed_saved = json.loads(decomposed_path.read_text())
        legacy_saved = json.loads(legacy_path.read_text())

        assert decomposed_saved["candidate_ranking"] == legacy_saved["candidate_ranking"]
        assert decomposed_saved["promotion_decisions"] == legacy_saved["promotion_decisions"]
        assert decomposed_saved["regression_guards"] == legacy_saved["regression_guards"]

    async def test_no_review_result_written_when_no_decomposed_or_legacy(self, tmp_path: Path) -> None:
        """When neither decomposed params nor review_result provided, no review_result.json is written."""
        with _patch_project_dir(tmp_path):
            await record_directive_outcomes_tool(
                ctx=None,
                run_id=_RUN_ID,
                outcomes=[_OUTCOME],
                output_dir="outputs",
            )

        review_result_path = tmp_path / "outputs" / _RUN_ID / "search" / "review_result.json"
        assert not review_result_path.exists()


class TestChildVariantNoParentPreference:
    """Tests for ChildVariant.parent_preference being optional."""

    def test_child_variant_without_parent_preference(self) -> None:
        """ChildVariant constructs cleanly without parent_preference (cold-start use case)."""
        from odysseus.agents.review.models import ChildVariant

        cv = ChildVariant(
            parent_version="base",
            hypothesis="Seed round-0 variant",
            directives=[],
        )
        assert cv.parent_preference is None
        assert cv.parent_version == "base"

    def test_child_variant_with_parent_preference(self) -> None:
        """ChildVariant still works when parent_preference is provided."""
        from odysseus.agents.review.models import ChildVariant

        cv = ChildVariant(
            hypothesis="Target weakest class",
            directives=[],
            parent_preference="weakest_on_class",
            parent_preference_class="route_a",
        )
        assert cv.parent_preference == "weakest_on_class"
        assert cv.parent_preference_class == "route_a"


class TestGetPromptTextTool:
    """Tests for get_prompt_text_tool prompt-directory fallback and run_id requirement."""

    _RUN_ID = "test-run-prompt"

    async def test_version_found_in_run_specific_dir(self, tmp_path: Path) -> None:
        """Version in outputs/<run_id>/prompts/ is returned without checking project dir."""
        run_prompts = tmp_path / "outputs" / self._RUN_ID / "prompts"
        run_prompts.mkdir(parents=True)
        (run_prompts / "v1.txt").write_text("run-specific content")

        project_prompts = tmp_path / "prompts"
        project_prompts.mkdir()
        (project_prompts / "v1.txt").write_text("project content")

        with _patch_project_dir(tmp_path):
            result = await get_prompt_text_tool(
                ctx=None, version="v1", run_id=self._RUN_ID, output_dir="outputs"
            )

        assert result == "run-specific content"

    async def test_fallback_to_project_dir_when_absent_from_run(self, tmp_path: Path) -> None:
        """Version absent from run-specific dir is loaded from project-level prompts/."""
        run_prompts = tmp_path / "outputs" / self._RUN_ID / "prompts"
        run_prompts.mkdir(parents=True)

        project_prompts = tmp_path / "prompts"
        project_prompts.mkdir()
        (project_prompts / "v2.txt").write_text("project v2")

        with _patch_project_dir(tmp_path):
            result = await get_prompt_text_tool(
                ctx=None, version="v2", run_id=self._RUN_ID, output_dir="outputs"
            )

        assert result == "project v2"

    async def test_error_json_when_version_in_neither_dir(self, tmp_path: Path) -> None:
        """Version absent from both dirs returns a JSON error with the expected shape."""
        run_prompts = tmp_path / "outputs" / self._RUN_ID / "prompts"
        run_prompts.mkdir(parents=True)
        project_prompts = tmp_path / "prompts"
        project_prompts.mkdir()

        with _patch_project_dir(tmp_path):
            result = await get_prompt_text_tool(
                ctx=None, version="vX", run_id=self._RUN_ID, output_dir="outputs"
            )

        parsed = json.loads(result)
        assert "error" in parsed
        assert "vX" in parsed["error"]

    def test_run_id_is_required(self) -> None:
        """get_prompt_text_tool requires run_id — calling without it raises TypeError."""
        import inspect

        sig = inspect.signature(get_prompt_text_tool)
        param = sig.parameters.get("run_id")
        assert param is not None, "run_id parameter not found on get_prompt_text_tool"
        assert param.default is inspect.Parameter.empty, "run_id must have no default (required)"


class TestQueryHoldoutExamplesPagination:
    """Smoke tests for offset pagination in query_holdout_examples_tool."""

    _RUN_ID = "test-run-pagination"
    _ROUTE = "route_x"
    _OTHER_ROUTE = "route_y"

    def _make_holdout(self, tmp_path: Path, n_matching: int, n_other: int = 5) -> None:
        """Write a holdout.jsonl with n_matching rows for _ROUTE and n_other for _OTHER_ROUTE."""
        analysis_dir = tmp_path / "outputs" / self._RUN_ID / "analysis"
        analysis_dir.mkdir(parents=True)
        rows = []
        for i in range(n_matching):
            rows.append(
                json.dumps({"id": f"m{i}", "input": f"text {i}", "expected": {"route": self._ROUTE}})
            )
        for i in range(n_other):
            rows.append(
                json.dumps({"id": f"o{i}", "input": f"other {i}", "expected": {"route": self._OTHER_ROUTE}})
            )
        (analysis_dir / "holdout.jsonl").write_text("\n".join(rows))

    async def test_offset_returns_correct_slice(self, tmp_path: Path) -> None:
        """offset=20, limit=10 returns exactly 10 items starting at the 21st matching row."""
        self._make_holdout(tmp_path, n_matching=35)

        with _patch_project_dir(tmp_path):
            result_json = await query_holdout_examples_tool(
                ctx=None,
                run_id=self._RUN_ID,
                route=self._ROUTE,
                offset=20,
                limit=10,
                output_dir="outputs",
            )

        result = json.loads(result_json)
        assert result["total_matching"] == 35
        assert len(result["examples"]) == 10
        # The 21st–30th matching rows have ids m20 through m29
        returned_ids = [ex["id"] for ex in result["examples"]]
        assert returned_ids == [f"m{i}" for i in range(20, 30)]

    async def test_offset_past_end_returns_empty(self, tmp_path: Path) -> None:
        """offset beyond total_matching returns an empty examples list."""
        self._make_holdout(tmp_path, n_matching=10)

        with _patch_project_dir(tmp_path):
            result_json = await query_holdout_examples_tool(
                ctx=None,
                run_id=self._RUN_ID,
                route=self._ROUTE,
                offset=50,
                limit=10,
                output_dir="outputs",
            )

        result = json.loads(result_json)
        assert result["total_matching"] == 10
        assert result["examples"] == []
