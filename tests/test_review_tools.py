"""Tests for review MCP tools — record_directive_outcomes_tool decomposed params."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

from odysseus.mcp import record_directive_outcomes_tool

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
