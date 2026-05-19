"""Tests for review MCP tools — record_directive_outcomes decomposed params."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from odysseus.mcp import (
    build_review_briefing,
    get_prompt_text,
    get_score_report,
    query_dev_examples,
    query_holdout_examples,
    record_directive_outcomes,
)

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
    """Tests for the decomposed-params path of record_directive_outcomes."""

    async def test_decomposed_params_persists_review_result(self, tmp_path: Path) -> None:
        """Passing decomposed params writes a review_result.json to disk."""
        with _patch_project_dir(tmp_path):
            result_json = await record_directive_outcomes(
                ctx=None,
                run_id=_RUN_ID,
                loop_signal=_LOOP_SIGNAL,
                child_variants=_CHILD_VARIANTS,
                candidate_ranking=_CANDIDATE_RANKING,
                promotion_decisions=_PROMOTION_DECISIONS,
                regression_guards=_REGRESSION_GUARDS,
                output_dir="outputs",
            )

        result = json.loads(result_json)
        # No "recorded" key — outcomes are synthesized in code, not passed by agent
        assert "recorded" not in result

        review_result_path = tmp_path / "outputs" / _RUN_ID / "search" / "review_result.json"
        assert review_result_path.exists(), "review_result.json should be written for decomposed params"
        saved = json.loads(review_result_path.read_text())
        assert saved["candidate_ranking"] == _CANDIDATE_RANKING
        assert saved["promotion_decisions"] == _PROMOTION_DECISIONS
        assert saved["regression_guards"] == _REGRESSION_GUARDS
        assert saved["loop_signal"] == _LOOP_SIGNAL
        assert saved["child_variants"] == _CHILD_VARIANTS
        # directive_history_update is no longer written to the audit record
        assert "directive_history_update" not in saved

    async def test_legacy_review_result_path_persists(self, tmp_path: Path) -> None:
        """Passing review_result blob (legacy) also writes review_result.json."""
        legacy_blob = {
            "candidate_ranking": _CANDIDATE_RANKING,
            "promotion_decisions": _PROMOTION_DECISIONS,
            "regression_guards": _REGRESSION_GUARDS,
            "loop_signal": _LOOP_SIGNAL,
            "child_variants": _CHILD_VARIANTS,
        }
        with _patch_project_dir(tmp_path):
            result_json = await record_directive_outcomes(
                ctx=None,
                run_id=_RUN_ID,
                loop_signal=_LOOP_SIGNAL,
                child_variants=_CHILD_VARIANTS,
                review_result=legacy_blob,
                output_dir="outputs",
            )

        result = json.loads(result_json)
        assert "recorded" not in result

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
        }

        with _patch_project_dir(tmp_path):
            await record_directive_outcomes(
                ctx=None,
                run_id=run_decomposed,
                candidate_ranking=_CANDIDATE_RANKING,
                promotion_decisions=_PROMOTION_DECISIONS,
                regression_guards=_REGRESSION_GUARDS,
                output_dir="outputs",
            )
            await record_directive_outcomes(
                ctx=None,
                run_id=run_legacy,
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
            await record_directive_outcomes(
                ctx=None,
                run_id=_RUN_ID,
                output_dir="outputs",
            )

        review_result_path = tmp_path / "outputs" / _RUN_ID / "search" / "review_result.json"
        assert not review_result_path.exists()



class TestRecordDirectiveOutcomesSingleSlot:
    """Tests for the single-slot path of record_directive_outcomes."""

    _RUN_ID = "test-run-trajectory"

    async def test_single_slot_path_writes_child_variants(self, tmp_path: Path) -> None:
        """Without trajectory_id, the single-slot path writes child_variants.json."""
        with _patch_project_dir(tmp_path):
            await record_directive_outcomes(
                ctx=None,
                run_id=self._RUN_ID + "-single",
                child_variants=_CHILD_VARIANTS,
                output_dir="outputs",
            )

        single_slot = tmp_path / "outputs" / (self._RUN_ID + "-single") / "search" / "child_variants.json"
        assert single_slot.exists(), "child_variants.json must be written for single-slot path"



class TestChildVariantTrajectoryIdField:
    """Tests for the trajectory_id field on ChildVariant model."""

    def test_child_variant_has_trajectory_id_field_defaulting_none(self) -> None:
        """ChildVariant has trajectory_id field defaulting to None."""
        from odysseus.agents.review.models import ChildVariant

        cv = ChildVariant(
            hypothesis="test",
            directives=[],
        )
        assert hasattr(cv, "trajectory_id")
        assert cv.trajectory_id is None

    def test_child_variant_trajectory_id_roundtrips(self) -> None:
        """ChildVariant.model_dump includes trajectory_id and round-trips via model_validate."""
        from odysseus.agents.review.models import ChildVariant

        cv = ChildVariant(
            hypothesis="test",
            directives=[],
            trajectory_id=4,
        )
        dumped = cv.model_dump(mode="json")
        assert dumped["trajectory_id"] == 4
        loaded = ChildVariant.model_validate(dumped)
        assert loaded.trajectory_id == 4

    def test_child_variant_model_copy_with_trajectory_id(self) -> None:
        """model_copy(update={'trajectory_id': N}) stamps trajectory_id correctly."""
        from odysseus.agents.review.models import ChildVariant

        cv = ChildVariant(hypothesis="test", directives=[])
        stamped = cv.model_copy(update={"trajectory_id": 2})
        assert stamped.trajectory_id == 2
        assert cv.trajectory_id is None  # original unchanged


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
    """Tests for get_prompt_text prompt-directory fallback and run_id requirement."""

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
            result = await get_prompt_text(ctx=None, version="v1", run_id=self._RUN_ID, output_dir="outputs")

        assert result == "run-specific content"

    async def test_fallback_to_project_dir_when_absent_from_run(self, tmp_path: Path) -> None:
        """Version absent from run-specific dir is loaded from project-level prompts/."""
        run_prompts = tmp_path / "outputs" / self._RUN_ID / "prompts"
        run_prompts.mkdir(parents=True)

        project_prompts = tmp_path / "prompts"
        project_prompts.mkdir()
        (project_prompts / "v2.txt").write_text("project v2")

        with _patch_project_dir(tmp_path):
            result = await get_prompt_text(ctx=None, version="v2", run_id=self._RUN_ID, output_dir="outputs")

        assert result == "project v2"

    async def test_error_json_when_version_in_neither_dir(self, tmp_path: Path) -> None:
        """Version absent from both dirs returns a JSON error with the expected shape."""
        run_prompts = tmp_path / "outputs" / self._RUN_ID / "prompts"
        run_prompts.mkdir(parents=True)
        project_prompts = tmp_path / "prompts"
        project_prompts.mkdir()

        with _patch_project_dir(tmp_path):
            result = await get_prompt_text(ctx=None, version="vX", run_id=self._RUN_ID, output_dir="outputs")

        parsed = json.loads(result)
        assert "error" in parsed
        assert "vX" in parsed["error"]

    def test_run_id_is_required(self) -> None:
        """get_prompt_text requires run_id — calling without it raises TypeError."""
        import inspect

        sig = inspect.signature(get_prompt_text)
        param = sig.parameters.get("run_id")
        assert param is not None, "run_id parameter not found on get_prompt_text"
        assert param.default is inspect.Parameter.empty, "run_id must have no default (required)"


class TestVariantIdSequentialCounter:
    """variant_ids assigned by record_directive_outcomes are sequential across calls."""

    _RUN_ID = "test-run-seq"

    _CHILD_VARIANT_RAW = {
        "hypothesis": "Improve recall on route_a",
        "directives": [
            {
                "directive_id": "d1",
                "target_version": "v1",
                "block_type": "rule",
                "block_identifier": "Rule 1",
                "granularity": "micro",
                "directive": "Add rule",
                "priority": "medium",
            }
        ],
    }

    def _make_search_state(self, tmp_path: Path, run_id: str, next_seq: int = 1) -> None:
        """Write a minimal search_state.json with the given next_variant_seq."""
        from odysseus.agents.prompt_builder.search import SearchState
        from odysseus.agents.prompt_builder.search_ops import _save_state

        state = SearchState(
            search_state_id=run_id,
            backend="anthropic",
            next_variant_seq=next_seq,
        )
        out = tmp_path / "outputs"
        _save_state(run_id, state, out)

    async def test_first_call_assigns_v1_v2(self, tmp_path: Path) -> None:
        """First call with two variants assigns v1 and v2."""
        self._make_search_state(tmp_path, self._RUN_ID, next_seq=1)

        two_variants = [self._CHILD_VARIANT_RAW, dict(self._CHILD_VARIANT_RAW, hypothesis="Variant 2")]

        with _patch_project_dir(tmp_path):
            result_json = await record_directive_outcomes(
                ctx=None,
                run_id=self._RUN_ID,
                child_variants=two_variants,
                output_dir="outputs",
            )

        result = json.loads(result_json)
        ids = [v["variant_id"] for v in result["variants_summary"]]
        assert ids == ["v1", "v2"]

    async def test_second_call_continues_counter(self, tmp_path: Path) -> None:
        """Second call picks up where the first left off (counter persisted in state)."""
        self._make_search_state(tmp_path, self._RUN_ID, next_seq=1)

        with _patch_project_dir(tmp_path):
            await record_directive_outcomes(
                ctx=None,
                run_id=self._RUN_ID,
                child_variants=[self._CHILD_VARIANT_RAW],
                output_dir="outputs",
            )
            result_json = await record_directive_outcomes(
                ctx=None,
                run_id=self._RUN_ID,
                child_variants=[
                    dict(self._CHILD_VARIANT_RAW, hypothesis="Round 2 variant A"),
                    dict(self._CHILD_VARIANT_RAW, hypothesis="Round 2 variant B"),
                ],
                output_dir="outputs",
            )

        result = json.loads(result_json)
        ids = [v["variant_id"] for v in result["variants_summary"]]
        assert ids == ["v2", "v3"]

    async def test_state_next_variant_seq_updated(self, tmp_path: Path) -> None:
        """After assigning 3 ids across two calls, next_variant_seq == 4."""
        from odysseus.agents.prompt_builder.search_ops import _load_state

        self._make_search_state(tmp_path, self._RUN_ID, next_seq=1)

        with _patch_project_dir(tmp_path):
            await record_directive_outcomes(
                ctx=None,
                run_id=self._RUN_ID,
                child_variants=[self._CHILD_VARIANT_RAW, dict(self._CHILD_VARIANT_RAW, hypothesis="V2")],
                output_dir="outputs",
            )
            await record_directive_outcomes(
                ctx=None,
                run_id=self._RUN_ID,
                child_variants=[dict(self._CHILD_VARIANT_RAW, hypothesis="V3")],
                output_dir="outputs",
            )

        state = _load_state(self._RUN_ID, tmp_path / "outputs")
        assert state.next_variant_seq == 4


class TestQueryHoldoutExamplesPagination:
    """Smoke tests for paginated dataset row queries."""

    _RUN_ID = "test-run-pagination"
    _ROUTE = "route_x"
    _OTHER_ROUTE = "route_y"

    def _make_holdout(self, tmp_path: Path, n_matching: int, n_other: int = 5) -> None:
        """Write a holdout.jsonl with n_matching rows for _ROUTE and n_other for _OTHER_ROUTE."""
        analysis_dir = tmp_path / "outputs" / self._RUN_ID / "analysis"
        analysis_dir.mkdir(parents=True)
        rows = []
        for i in range(n_matching):
            rows.append(json.dumps({"id": f"m{i}", "input": f"text {i}", "expected": {"route": self._ROUTE}}))
        for i in range(n_other):
            rows.append(json.dumps({"id": f"o{i}", "input": f"other {i}", "expected": {"route": self._OTHER_ROUTE}}))
        (analysis_dir / "holdout.jsonl").write_text("\n".join(rows))

    async def test_offset_returns_correct_slice(self, tmp_path: Path) -> None:
        """offset=20, limit=10 returns exactly 10 items starting at the 21st matching row."""
        self._make_holdout(tmp_path, n_matching=35)

        with _patch_project_dir(tmp_path):
            result_json = await query_holdout_examples(
                ctx=None,
                run_id=self._RUN_ID,
                route=self._ROUTE,
                offset=20,
                limit=10,
                output_dir="outputs",
            )

        result = json.loads(result_json)
        assert len(result["examples"]) == 10
        # The 21st–30th matching rows have ids m20 through m29
        returned_ids = [ex["id"] for ex in result["examples"]]
        assert returned_ids == [f"m{i}" for i in range(20, 30)]

    async def test_offset_past_end_returns_empty(self, tmp_path: Path) -> None:
        """offset beyond total_matching returns an empty examples list."""
        self._make_holdout(tmp_path, n_matching=10)

        with _patch_project_dir(tmp_path):
            result_json = await query_holdout_examples(
                ctx=None,
                run_id=self._RUN_ID,
                route=self._ROUTE,
                offset=50,
                limit=10,
                output_dir="outputs",
            )

        result = json.loads(result_json)
        assert result["examples"] == []

    async def test_query_dev_examples_uses_same_pagination_shape(self, tmp_path: Path) -> None:
        """The dev query tool returns the same paginated examples shape."""
        analysis_dir = tmp_path / "outputs" / self._RUN_ID / "analysis"
        analysis_dir.mkdir(parents=True)
        rows = [json.dumps({"id": f"d{i}", "input": f"text {i}", "expected": {"route": self._ROUTE}}) for i in range(6)]
        (analysis_dir / "dev.jsonl").write_text("\n".join(rows), encoding="utf-8")

        with _patch_project_dir(tmp_path):
            result_json = await query_dev_examples(
                ctx=None,
                run_id=self._RUN_ID,
                route=self._ROUTE,
                offset=2,
                limit=3,
                output_dir="outputs",
            )

        result = json.loads(result_json)
        assert [ex["id"] for ex in result["examples"]] == ["d2", "d3", "d4"]

    @pytest.mark.parametrize(
        ("offset", "limit", "message"),
        [
            (-1, 10, "offset must be >= 0"),
            (0, 0, "limit must be > 0"),
            (0, 51, "limit must be <= 50"),
        ],
    )
    async def test_invalid_pagination_raises_tool_error(
        self,
        tmp_path: Path,
        offset: int,
        limit: int,
        message: str,
    ) -> None:
        """Invalid pagination args raise ToolError consistently."""
        self._make_holdout(tmp_path, n_matching=5)

        with _patch_project_dir(tmp_path), pytest.raises(ToolError, match=message):
            await query_holdout_examples(
                ctx=None,
                run_id=self._RUN_ID,
                route=self._ROUTE,
                offset=offset,
                limit=limit,
                output_dir="outputs",
            )

    async def test_unfiltered_query_is_capped_by_limit(self, tmp_path: Path) -> None:
        """Route-less queries return only the requested page size."""
        self._make_holdout(tmp_path, n_matching=35, n_other=10)

        with _patch_project_dir(tmp_path):
            result_json = await query_holdout_examples(
                ctx=None,
                run_id=self._RUN_ID,
                offset=0,
                limit=20,
                output_dir="outputs",
            )

        result = json.loads(result_json)
        assert len(result["examples"]) == 20

    async def test_pagination_terminates_when_page_is_short(self, tmp_path: Path) -> None:
        """Callers can detect the end of pagination from a short page."""
        self._make_holdout(tmp_path, n_matching=7, n_other=0)

        with _patch_project_dir(tmp_path):
            first_page = json.loads(
                await query_holdout_examples(
                    ctx=None,
                    run_id=self._RUN_ID,
                    route=self._ROUTE,
                    offset=0,
                    limit=5,
                    output_dir="outputs",
                )
            )
            second_page = json.loads(
                await query_holdout_examples(
                    ctx=None,
                    run_id=self._RUN_ID,
                    route=self._ROUTE,
                    offset=5,
                    limit=5,
                    output_dir="outputs",
                )
            )

        assert len(first_page["examples"]) == 5
        assert len(second_page["examples"]) == 2


# ---------------------------------------------------------------------------
# Helpers for build_review_briefing tests
# ---------------------------------------------------------------------------


def _write_state(tmp_path: Path, run_id: str, state_dict: dict) -> None:
    """Write a search_state.json for the given run."""
    search_dir = tmp_path / "outputs" / run_id / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    (search_dir / "search_state.json").write_text(json.dumps(state_dict), encoding="utf-8")


def _write_results_jsonl(
    tmp_path: Path,
    run_id: str,
    version: str,
    rows: list[dict],
) -> None:
    """Write eval/<version>/results.jsonl for the given run."""
    eval_dir = tmp_path / "outputs" / run_id / "eval" / version
    eval_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in rows]
    (eval_dir / "results.jsonl").write_text("\n".join(lines), encoding="utf-8")


def _write_dev_jsonl(tmp_path: Path, run_id: str, examples: list[dict]) -> None:
    """Write analysis/dev.jsonl for the given run."""
    analysis_dir = tmp_path / "outputs" / run_id / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e) for e in examples]
    (analysis_dir / "dev.jsonl").write_text("\n".join(lines), encoding="utf-8")


def _make_state_dict(
    run_id: str,
    elite_set: list[dict],
    round_: int = 2,
) -> dict:
    return {
        "search_state_id": run_id,
        "backend": "anthropic",
        "round": round_,
        "elite_set": elite_set,
        "round_history": [],
        "stagnation_count": 0,
        "stagnation_limit": 3,
        "convergence_limit": 5,
        "max_rounds": 50,
        "mutation_mode": "targeted",
        "converged": False,
    }


def _make_eval_result(example_id: str, route: str) -> dict:
    """Minimal EvalResult dict with route output."""
    return {
        "example_id": example_id,
        "model": "test-model",
        "output": {"route": route},
        "error": None,
        "latency_ms": 10.0,
        "retries": 0,
        "token_usage": None,
        "cost": 0.001,
    }


def _make_example(id_: str, true_route: str, routes: list[str] | None = None) -> dict:
    """Minimal Example dict."""
    route_names = routes or [true_route, "complex"]
    routes_dict = {r: {"cost": 0.01 * (i + 1), "quality_score": 0.8 + 0.05 * i} for i, r in enumerate(route_names)}
    return {
        "id": id_,
        "input": f"query for {id_}",
        "expected": {"route": true_route, "routes": routes_dict},
    }


class TestBuildReviewBriefingToolSelector:
    """Tests for confusion-analysis selector behavior in build_review_briefing."""

    _RUN_ID = "test-run-confusion"

    async def test_elite_set_two_candidates_yields_non_empty_confusion(self, tmp_path: Path) -> None:
        """elite_set with two candidates: confusion_analysis is non-empty and deduped."""
        run_id = self._RUN_ID + "-two"
        # Two elite candidates
        state_dict = _make_state_dict(
            run_id,
            elite_set=[
                {
                    "prompt_version": "v1",
                    "parent_version": None,
                    "quality_score": 0.80,
                    "cost": 1.0,
                    "round_introduced": 1,
                },
                {
                    "prompt_version": "v2",
                    "parent_version": "v1",
                    "quality_score": 0.82,
                    "cost": 1.0,
                    "round_introduced": 2,
                },
            ],
        )
        _write_state(tmp_path, run_id, state_dict)

        # Both v1 and v2 misroute "e1" (simple→complex)
        # v2 additionally misroutes "e2"
        _write_results_jsonl(
            tmp_path,
            run_id,
            "v1",
            [
                _make_eval_result("e1", "complex"),  # misroute
                _make_eval_result("e2", "simple"),  # correct
            ],
        )
        _write_results_jsonl(
            tmp_path,
            run_id,
            "v2",
            [
                _make_eval_result("e1", "complex"),  # same misroute as v1
                _make_eval_result("e2", "complex"),  # additional misroute
            ],
        )
        _write_dev_jsonl(
            tmp_path,
            run_id,
            [
                _make_example("e1", "simple"),
                _make_example("e2", "simple"),
            ],
        )

        # Write a dummy report for scoring (avoids empty score_reports)
        from datetime import UTC, datetime

        now = datetime.now(tz=UTC).isoformat()
        for v in ("v1", "v2"):
            report = {
                "metrics": {"accuracy": 0.80},
                "summary": {
                    "total": 2,
                    "succeeded": 2,
                    "failed": 0,
                    "total_cost": 0.01,
                    "start_time": now,
                    "end_time": now,
                    "duration_seconds": 1.0,
                },
                "errors": [],
                "diff": None,
                "report_path": str(tmp_path / "outputs" / run_id / "eval" / v / "report.json"),
                "results_path": str(tmp_path / "outputs" / run_id / "eval" / v / "results.jsonl"),
            }
            report_path = tmp_path / "outputs" / run_id / "eval" / v / "report.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report), encoding="utf-8")

        with _patch_project_dir(tmp_path):
            result = await build_review_briefing(
                ctx=None,
                run_id=run_id,
                output_dir="outputs",
            )

        # Tool now returns markdown — verify it ran and contains the confusion section.
        assert isinstance(result, str) and len(result) > 0
        assert "## Confusion analysis" in result

        # For field-level assertions, call build_review_briefing directly.
        from odysseus.agents.prompt_builder.search_ops import _load_pending, get_search_state
        from odysseus.agents.review.ops import load_round_reports
        from odysseus.agents.review.preprocessor import build_review_briefing as _build_review_briefing_impl

        out = tmp_path / "outputs"
        state = get_search_state(run_id=run_id, output_dir=out)
        pending = _load_pending(run_id, out)
        candidate_versions = [c.prompt_version for c in pending]
        parent_versions = {c.prompt_version: c.parent_version for c in pending}
        all_versions = {c.prompt_version for c in state.elite_set}
        score_reports: dict = {}
        for v in (list(all_versions) + candidate_versions):
            rp = out / run_id / "eval" / v / "report.json"
            if rp.exists():
                from odysseus.mcp.review_tools import _load_score_report_dict
                score_reports[v] = _load_score_report_dict(rp, rp.parent / "results.jsonl")
        from odysseus.eval.models import EvalResult, Example
        all_er: list[EvalResult] = []
        for v in [c.prompt_version for c in state.elite_set]:
            rsp = out / run_id / "eval" / v / "results.jsonl"
            if rsp.exists():
                for line in rsp.read_text(encoding="utf-8").splitlines():
                    s = line.strip()
                    if s:
                        try:
                            all_er.append(EvalResult.model_validate(json.loads(s)))
                        except Exception:
                            pass
        loaded_examples: list[Example] = []
        dev_p = out / run_id / "analysis" / "dev.jsonl"
        if dev_p.exists():
            for line in dev_p.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s:
                    try:
                        loaded_examples.append(Example.model_validate_json(s))
                    except Exception:
                        pass
        briefing = _build_review_briefing_impl(
            search_state=state,
            score_reports=score_reports,
            historical_reports=load_round_reports(run_id, output_dir=out),
            prompt_texts={},
            candidate_versions=candidate_versions,
            parent_versions=parent_versions,
            routing_context=None,
            child_variants=None,
            pending_candidates=pending,
            user_targets=None,
            full_dataset_oracle=None,
            dev_oracle=None,
            eval_results=all_er or None,
            examples=loaded_examples or None,
            run_dir=out / run_id,
            cell_attempt_history=None,
            emosa_trajectory_id=None,
        )

        confusion = briefing.confusion_analysis
        assert len(confusion) > 0, "expected non-empty confusion_analysis"

        # Count unique misrouted example IDs: e1 appears in both versions but
        # dedup should count it once. e2 appears in v2 only. So count == 2.
        simple_to_complex = next(
            (c for c in confusion if c.true_route == "simple" and c.predicted_route == "complex"),
            None,
        )
        assert simple_to_complex is not None
        assert simple_to_complex.count == 2  # deduped: e1 + e2, not 3

    async def test_empty_elite_set_yields_empty_confusion(self, tmp_path: Path) -> None:
        """Round 0 / empty elite_set: confusion_analysis == [] without errors."""
        run_id = self._RUN_ID + "-empty"
        state_dict = _make_state_dict(run_id, elite_set=[], round_=0)
        _write_state(tmp_path, run_id, state_dict)

        with _patch_project_dir(tmp_path):
            result = await build_review_briefing(
                ctx=None,
                run_id=run_id,
                output_dir="outputs",
            )

        # Tool now returns markdown — verify it ran.
        assert isinstance(result, str) and len(result) > 0
        # Empty elite set → no confusion section in summary.
        assert "## Confusion analysis" not in result

    async def test_monkey_patch_selector_limits_to_single_version(self, tmp_path: Path) -> None:
        """Monkey-patching _select_confusion_candidates limits analysis to one version."""
        import odysseus.mcp.review_tools as _rt

        run_id = self._RUN_ID + "-patch"
        state_dict = _make_state_dict(
            run_id,
            elite_set=[
                {
                    "prompt_version": "va",
                    "parent_version": None,
                    "quality_score": 0.80,
                    "cost": 1.0,
                    "round_introduced": 1,
                },
                {
                    "prompt_version": "vb",
                    "parent_version": "va",
                    "quality_score": 0.82,
                    "cost": 1.0,
                    "round_introduced": 2,
                },
            ],
        )
        _write_state(tmp_path, run_id, state_dict)

        # va misroutes e1 only; vb misroutes both e1 and e2
        _write_results_jsonl(
            tmp_path,
            run_id,
            "va",
            [
                _make_eval_result("e1", "complex"),
                _make_eval_result("e2", "simple"),  # correct
            ],
        )
        _write_results_jsonl(
            tmp_path,
            run_id,
            "vb",
            [
                _make_eval_result("e1", "complex"),
                _make_eval_result("e2", "complex"),
            ],
        )
        _write_dev_jsonl(
            tmp_path,
            run_id,
            [
                _make_example("e1", "simple"),
                _make_example("e2", "simple"),
            ],
        )

        from datetime import UTC, datetime

        now = datetime.now(tz=UTC).isoformat()
        for v in ("va", "vb"):
            report = {
                "metrics": {"accuracy": 0.80},
                "summary": {
                    "total": 2,
                    "succeeded": 2,
                    "failed": 0,
                    "total_cost": 0.01,
                    "start_time": now,
                    "end_time": now,
                    "duration_seconds": 1.0,
                },
                "errors": [],
                "diff": None,
                "report_path": str(tmp_path / "outputs" / run_id / "eval" / v / "report.json"),
                "results_path": str(tmp_path / "outputs" / run_id / "eval" / v / "results.jsonl"),
            }
            rp = tmp_path / "outputs" / run_id / "eval" / v / "report.json"
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(json.dumps(report), encoding="utf-8")

        from odysseus.agents.prompt_builder.search_ops import _load_pending, get_search_state
        from odysseus.agents.review.ops import load_round_reports
        from odysseus.agents.review.preprocessor import build_review_briefing as _build_review_briefing_impl
        from odysseus.eval.models import EvalResult, Example
        from odysseus.mcp.review_tools import _load_score_report_dict

        original_selector = _rt._select_confusion_candidates
        try:
            # Override: only analyse "va"
            _rt._select_confusion_candidates = lambda state: ["va"]  # type: ignore[assignment]

            with _patch_project_dir(tmp_path):
                result = await build_review_briefing(
                    ctx=None,
                    run_id=run_id,
                    output_dir="outputs",
                )

            # Build briefing directly with same selector override to inspect fields.
            out = tmp_path / "outputs"
            state = get_search_state(run_id=run_id, output_dir=out)
            pending = _load_pending(run_id, out)
            candidate_versions = [c.prompt_version for c in pending]
            parent_versions = {c.prompt_version: c.parent_version for c in pending}
            score_reports: dict = {}
            for v in [c.prompt_version for c in state.elite_set]:
                rp = out / run_id / "eval" / v / "report.json"
                if rp.exists():
                    score_reports[v] = _load_score_report_dict(rp, rp.parent / "results.jsonl")
            # Only load "va" results (selector override)
            all_er: list[EvalResult] = []
            rsp = out / run_id / "eval" / "va" / "results.jsonl"
            if rsp.exists():
                for line in rsp.read_text(encoding="utf-8").splitlines():
                    s = line.strip()
                    if s:
                        try:
                            all_er.append(EvalResult.model_validate(json.loads(s)))
                        except Exception:
                            pass
            loaded_examples: list[Example] = []
            dev_p = out / run_id / "analysis" / "dev.jsonl"
            if dev_p.exists():
                for line in dev_p.read_text(encoding="utf-8").splitlines():
                    s = line.strip()
                    if s:
                        try:
                            loaded_examples.append(Example.model_validate_json(s))
                        except Exception:
                            pass
            briefing = _build_review_briefing_impl(
                search_state=state,
                score_reports=score_reports,
                historical_reports=load_round_reports(run_id, output_dir=out),
                prompt_texts={},
                candidate_versions=candidate_versions,
                parent_versions=parent_versions,
                routing_context=None,
                child_variants=None,
                pending_candidates=pending,
                user_targets=None,
                full_dataset_oracle=None,
                dev_oracle=None,
                eval_results=all_er or None,
                examples=loaded_examples or None,
                run_dir=out / run_id,
                cell_attempt_history=None,
                emosa_trajectory_id=None,
            )
        finally:
            _rt._select_confusion_candidates = original_selector

        confusion = briefing.confusion_analysis
        # Only va's misroutes counted: e1 only → count == 1
        simple_to_complex = next(
            (c for c in confusion if c.true_route == "simple" and c.predicted_route == "complex"),
            None,
        )
        assert simple_to_complex is not None
        assert simple_to_complex.count == 1, (
            "selector override to 'va' only should reflect 1 unique misroute (e1), not 2"
        )


# ---------------------------------------------------------------------------
# Tests for _load_score_report_dict
# ---------------------------------------------------------------------------


class TestLoadScoreReportDict:
    """Unit tests for the _load_score_report_dict helper."""

    def _minimal_run_report_dict(self) -> dict:
        """Return a minimal RunReport-shaped dict."""
        from datetime import UTC, datetime

        now = datetime.now(tz=UTC).isoformat()
        return {
            "config": {
                "backend": "anthropic",
                "prompt_version": "v1",
                "data_source": "data/test.jsonl",
                "metrics": [{"name": "accuracy"}],
            },
            "metrics": {"accuracy": 0.85},
            "results": [
                {
                    "example_id": "e1",
                    "model": "claude-test",
                    "output": {"route": "simple"},
                    "error": None,
                    "latency_ms": 10.0,
                    "retries": 0,
                    "token_usage": None,
                    "cost": 0.001,
                }
            ],
            "summary": {
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "total_cost": 0.001,
                "start_time": now,
                "end_time": now,
                "duration_seconds": 0.5,
            },
        }

    def _minimal_score_report_dict(self, report_path: str, results_path: str) -> dict:
        """Return a minimal ScoreReport-shaped dict."""
        from datetime import UTC, datetime

        now = datetime.now(tz=UTC).isoformat()
        return {
            "metrics": {"accuracy": 0.90},
            "summary": {
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "total_cost": 0.001,
                "start_time": now,
                "end_time": now,
                "duration_seconds": 0.5,
            },
            "errors": [],
            "diff": None,
            "report_path": report_path,
            "results_path": results_path,
        }

    def test_load_score_report_dict_converts_runreport(self, tmp_path: Path) -> None:
        """A RunReport-shaped JSON is converted to a ScoreReport-shaped dict without error."""
        from odysseus.eval.models import ScoreReport
        from odysseus.mcp.review_tools import _load_score_report_dict

        report_path = tmp_path / "report.json"
        results_path = tmp_path / "results.jsonl"
        report_path.write_text(json.dumps(self._minimal_run_report_dict()), encoding="utf-8")

        result = _load_score_report_dict(report_path, results_path)

        # Must not raise — i.e., result is a valid ScoreReport
        score_report = ScoreReport.model_validate(result)
        assert score_report.metrics == {"accuracy": 0.85}
        assert score_report.errors == []
        assert score_report.diff is None
        assert score_report.report_path == str(report_path)
        assert score_report.results_path == str(results_path)

    def test_load_score_report_dict_converts_runreport_derives_results_path(self, tmp_path: Path) -> None:
        """When results_path is None, it is derived from report_path's parent dir."""
        from odysseus.eval.models import ScoreReport
        from odysseus.mcp.review_tools import _load_score_report_dict

        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(self._minimal_run_report_dict()), encoding="utf-8")

        result = _load_score_report_dict(report_path)

        score_report = ScoreReport.model_validate(result)
        assert score_report.results_path == str(tmp_path / "results.jsonl")

    def test_load_score_report_dict_idempotent_on_scorereport(self, tmp_path: Path) -> None:
        """A ScoreReport-shaped JSON is returned as-is without double-conversion."""
        from odysseus.mcp.review_tools import _load_score_report_dict

        report_path = tmp_path / "report.json"
        results_path = tmp_path / "results.jsonl"
        original = self._minimal_score_report_dict(str(report_path), str(results_path))
        report_path.write_text(json.dumps(original), encoding="utf-8")

        result = _load_score_report_dict(report_path, results_path)

        # Content must be identical to what was written
        assert result["metrics"] == original["metrics"]
        assert result["errors"] == original["errors"]
        assert result["diff"] == original["diff"]
        assert result["report_path"] == original["report_path"]
        assert result["results_path"] == original["results_path"]


class TestGetScoreReportTool:
    _RUN_ID = "test-score-report-tool"

    def _write_report(self, tmp_path: Path, version: str, with_confidence_intervals: bool = False) -> None:
        report_dir = tmp_path / "outputs" / self._RUN_ID / "eval" / version
        report_dir.mkdir(parents=True, exist_ok=True)
        report = TestLoadScoreReportDict()._minimal_run_report_dict()
        if with_confidence_intervals:
            report["confidence_intervals"] = {
                "accuracy": {"lower": 0.8, "upper": 0.9, "level": 0.95},
            }
        (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
        (report_dir / "results.jsonl").write_text("", encoding="utf-8")

    async def test_uses_renderer_diff_shape(self, tmp_path: Path) -> None:
        report_dir = tmp_path / "outputs" / self._RUN_ID / "eval" / "v3"
        report_dir.mkdir(parents=True, exist_ok=True)
        score_report = {
            "metrics": {"accuracy": 0.9},
            "summary": TestLoadScoreReportDict()._minimal_score_report_dict(
                "outputs/report.json", "outputs/results.jsonl"
            )["summary"],
            "errors": [],
            "diff": {
                "metric_diffs": [{"key": "accuracy", "old": 0.8, "new": 0.9, "status": "changed"}],
                "overhead_diff": {"old_cost": 0.1, "new_cost": 0.2, "old_duration": 1.0, "new_duration": 1.5},
            },
            "report_path": str(report_dir / "report.json"),
            "results_path": str(report_dir / "results.jsonl"),
        }
        (report_dir / "report.json").write_text(json.dumps(score_report), encoding="utf-8")
        (report_dir / "results.jsonl").write_text("", encoding="utf-8")

        with _patch_project_dir(tmp_path):
            result = await get_score_report(ctx=None, run_id=self._RUN_ID, version="v3", output_dir="outputs")

        assert "| metric | old | new | status |" in result
        assert "| accuracy | 0.8000 | 0.9000 | changed |" in result

    async def test_confidence_intervals_not_rendered(self, tmp_path: Path) -> None:
        self._write_report(tmp_path, "v5", with_confidence_intervals=True)

        with _patch_project_dir(tmp_path):
            result = await get_score_report(ctx=None, run_id=self._RUN_ID, version="v5", output_dir="outputs")

        assert "confidence_intervals" not in result
        assert "0.95" not in result
        assert "## Score report" in result


class TestBuildReviewBriefingDoesNotWriteRoundReport:
    """C.2: build_review_briefing must NOT write round_reports/round_N.json."""

    _RUN_ID = "test-run-no-rr-write"

    async def test_briefing_does_not_write_round_report(self, tmp_path: Path) -> None:
        """build_review_briefing leaves round_reports/ untouched (no racy write)."""
        run_id = self._RUN_ID
        state_dict = _make_state_dict(run_id, elite_set=[], round_=2)
        _write_state(tmp_path, run_id, state_dict)

        round_reports_dir = tmp_path / "outputs" / run_id / "search" / "round_reports"

        with _patch_project_dir(tmp_path):
            await build_review_briefing(
                ctx=None,
                run_id=run_id,
                output_dir="outputs",
            )

        assert not round_reports_dir.exists(), "build_review_briefing must not create round_reports/ directory"

    async def test_briefing_does_not_clobber_existing_round_report(self, tmp_path: Path) -> None:
        """If round_reports/round_2.json was pre-written by advance_round, briefing leaves it intact."""
        run_id = self._RUN_ID + "-clobber"
        state_dict = _make_state_dict(run_id, elite_set=[], round_=2)
        _write_state(tmp_path, run_id, state_dict)

        # Pre-write a round report (as advance_round would do)
        round_reports_dir = tmp_path / "outputs" / run_id / "search" / "round_reports"
        round_reports_dir.mkdir(parents=True, exist_ok=True)
        sentinel = {"pre_written_candidate": {"metrics": {"accuracy": 0.9}}}
        (round_reports_dir / "round_2.json").write_text(json.dumps(sentinel), encoding="utf-8")

        with _patch_project_dir(tmp_path):
            await build_review_briefing(
                ctx=None,
                run_id=run_id,
                output_dir="outputs",
            )

        on_disk = json.loads((round_reports_dir / "round_2.json").read_text(encoding="utf-8"))
        assert on_disk == sentinel, "build_review_briefing must not overwrite existing round_reports/round_2.json"


class TestBuildReviewBriefingSurface:
    """build_review_briefing returns the rendered markdown summary at the MCP boundary."""

    _RUN_ID = "test-review-briefing-surface"

    async def test_returns_markdown_headings_not_json(self, tmp_path: Path) -> None:
        state_dict = _make_state_dict(
            self._RUN_ID,
            elite_set=[
                {
                    "prompt_version": "v1",
                    "parent_version": None,
                    "quality_score": 0.85,
                    "cost": 0.02,
                    "round_introduced": 1,
                    "example_ids": [],
                }
            ],
            round_=2,
        )
        _write_state(tmp_path, self._RUN_ID, state_dict)

        with _patch_project_dir(tmp_path):
            result = await build_review_briefing(
                ctx=None,
                run_id=self._RUN_ID,
                output_dir="outputs",
            )

        assert "## Round" in result
        assert "## Diversity & diminishing returns" in result
        assert "## Elite set" in result
        assert not result.lstrip().startswith("{")


# ---------------------------------------------------------------------------
# Tests for get_dataset_oracle_distribution
# ---------------------------------------------------------------------------

_DEV_ROWS = [
    {
        "id": "row-1",
        "input": "query 1",
        "expected": {
            "route": "complex",
            "routes": {
                "simple": {"cost": 0.01, "quality_score": 0.7},
                "moderate": {"cost": 0.03, "quality_score": 0.8},
                "complex": {"cost": 0.10, "quality_score": 0.95},
            },
        },
    },
    {
        "id": "row-2",
        "input": "query 2",
        "expected": {
            "route": "simple",
            "routes": {
                "simple": {"cost": 0.01, "quality_score": 0.9},
                "moderate": {"cost": 0.03, "quality_score": 0.9},
                "complex": {"cost": 0.10, "quality_score": 0.9},
            },
        },
    },
    {
        "id": "row-3",
        "input": "query 3",
        "expected": {
            "route": "simple",
            "routes": {
                "simple": {"cost": 0.01, "quality_score": 0.85},
                "moderate": {"cost": 0.03, "quality_score": 0.88},
                "complex": {"cost": 0.10, "quality_score": 0.90},
            },
        },
    },
]


class TestGetDatasetOracleDistributionTool:
    _RUN_ID = "test-oracle-dist"

    def _write_dev(self, tmp_path: Path, rows: list[dict] | None = None) -> None:
        analysis_dir = tmp_path / "outputs" / self._RUN_ID / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        data = rows if rows is not None else _DEV_ROWS
        lines = [json.dumps(r) for r in data]
        (analysis_dir / "dev.jsonl").write_text("\n".join(lines), encoding="utf-8")

    async def test_aggregates_section_always_present(self, tmp_path: Path) -> None:
        self._write_dev(tmp_path)
        with _patch_project_dir(tmp_path):
            from odysseus.mcp.review_tools import get_dataset_oracle_distribution

            result = await get_dataset_oracle_distribution(                ctx=None,
                run_id=self._RUN_ID,
                output_dir="outputs",
            )
        assert "### Aggregates" in result
        assert "complex" in result
        assert "simple" in result

    async def test_route_filter_shows_rows_section(self, tmp_path: Path) -> None:
        self._write_dev(tmp_path)
        with _patch_project_dir(tmp_path):
            from odysseus.mcp.review_tools import get_dataset_oracle_distribution

            result = await get_dataset_oracle_distribution(                ctx=None,
                run_id=self._RUN_ID,
                route="simple",
                output_dir="outputs",
            )
        assert "### Rows" in result
        assert "row-2" in result
        assert "row-3" in result
        # row-1 is labeled complex, not simple
        assert "row-1" not in result.split("### Rows")[1]

    async def test_example_ids_filter(self, tmp_path: Path) -> None:
        self._write_dev(tmp_path)
        with _patch_project_dir(tmp_path):
            from odysseus.mcp.review_tools import get_dataset_oracle_distribution

            result = await get_dataset_oracle_distribution(                ctx=None,
                run_id=self._RUN_ID,
                example_ids=["row-1"],
                output_dir="outputs",
            )
        assert "row-1" in result
        # row-2 not in requested ids
        rows_section = result.split("### Rows")[1] if "### Rows" in result else result
        assert "row-2" not in rows_section

    async def test_limit_cap(self, tmp_path: Path) -> None:
        """limit=1 returns at most 1 row in the rows section."""
        self._write_dev(tmp_path)
        with _patch_project_dir(tmp_path):
            from odysseus.mcp.review_tools import get_dataset_oracle_distribution

            result = await get_dataset_oracle_distribution(                ctx=None,
                run_id=self._RUN_ID,
                route="simple",
                limit=1,
                output_dir="outputs",
            )
        # Should say "1 shown"
        assert "1 shown" in result

    async def test_missing_dev_jsonl_returns_explanatory_message(self, tmp_path: Path) -> None:
        """When dev.jsonl doesn't exist, returns an explanatory message (no exception)."""
        # Don't write any dev.jsonl
        with _patch_project_dir(tmp_path):
            from odysseus.mcp.review_tools import get_dataset_oracle_distribution

            result = await get_dataset_oracle_distribution(                ctx=None,
                run_id=self._RUN_ID,
                output_dir="outputs",
            )
        assert "not found" in result.lower() or "only available" in result.lower()

    async def test_no_rows_section_without_filter(self, tmp_path: Path) -> None:
        """Without route or example_ids filter, rows section is omitted."""
        self._write_dev(tmp_path)
        with _patch_project_dir(tmp_path):
            from odysseus.mcp.review_tools import get_dataset_oracle_distribution

            result = await get_dataset_oracle_distribution(                ctx=None,
                run_id=self._RUN_ID,
                output_dir="outputs",
            )
        assert "### Rows" not in result

    async def test_pareto_count_for_dominated_route(self, tmp_path: Path) -> None:
        """row-2 has simple labeled but moderate/complex have same quality at higher cost — simple IS pareto."""
        self._write_dev(tmp_path)
        with _patch_project_dir(tmp_path):
            from odysseus.mcp.review_tools import get_dataset_oracle_distribution

            result = await get_dataset_oracle_distribution(                ctx=None,
                run_id=self._RUN_ID,
                output_dir="outputs",
            )
        # simple route appears in aggregates table
        assert "simple" in result

    async def test_ties_with_cheaper_route_count(self, tmp_path: Path) -> None:
        """row-2: labeled 'simple' but moderate/complex have same quality at higher cost → no cheaper tie.
        row-3: labeled 'simple' and moderate has same quality at higher cost → no cheaper tie either.
        complex row-1: simple/moderate have same or lower quality and lower cost → ties_with_cheaper=1."""
        self._write_dev(tmp_path)
        with _patch_project_dir(tmp_path):
            from odysseus.mcp.review_tools import get_dataset_oracle_distribution

            result = await get_dataset_oracle_distribution(                ctx=None,
                run_id=self._RUN_ID,
                output_dir="outputs",
            )
        # Just verify the column exists in the table
        assert "ties_with_cheaper_route_count" in result


# ---------------------------------------------------------------------------
# Tests for get_per_class_recall# ---------------------------------------------------------------------------


class TestGetPerClassRecallTool:
    _RUN_ID = "test-pcr-tool"

    def _make_state_with_reports(self, tmp_path: Path) -> None:
        """Write search state + round reports with recall metrics."""
        from odysseus.agents.prompt_builder.search import SearchState
        from odysseus.agents.prompt_builder.search_ops import _save_state

        state = SearchState(
            search_state_id=self._RUN_ID,
            backend="anthropic",
            round=2,
        )
        out = tmp_path / "outputs"
        _save_state(self._RUN_ID, state, out)

        # Write round 1 report with recall metrics for route_a, route_b, route_low
        from datetime import UTC, datetime

        now = datetime.now(tz=UTC).isoformat()
        report = {
            "config": {"backend": "anthropic", "prompt_version": "v1", "data_source": "d.jsonl", "metrics": []},
            "metrics": {
                "accuracy": 0.80,
                "recall/route_a": 0.85,
                "support/route_a": 50,
                "recall/route_b": 0.72,
                "support/route_b": 40,
                "recall/route_low": 0.50,
                "support/route_low": 3,
            },
            "results": [],
            "summary": {
                "total": 93,
                "succeeded": 93,
                "failed": 0,
                "total_cost": 0.05,
                "start_time": now,
                "end_time": now,
                "duration_seconds": 5.0,
            },
        }

        round_dir = out / self._RUN_ID / "search" / "round_reports"
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / "round_1.json").write_text(json.dumps({"v1": report}), encoding="utf-8")

        eval_dir = out / self._RUN_ID / "eval" / "v1"
        eval_dir.mkdir(parents=True, exist_ok=True)
        (eval_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")

    async def test_full_table_includes_all_routes(self, tmp_path: Path) -> None:
        """get_per_class_recall returns all routes including low-support ones."""
        self._make_state_with_reports(tmp_path)
        with _patch_project_dir(tmp_path):
            from odysseus.mcp.review_tools import get_per_class_recall

            result = await get_per_class_recall(                ctx=None,
                run_id=self._RUN_ID,
                output_dir="outputs",
            )
        assert "route_a" in result
        assert "route_b" in result
        assert "route_low" in result

    async def test_columns_present(self, tmp_path: Path) -> None:
        """Result markdown contains all expected column headers."""
        self._make_state_with_reports(tmp_path)
        with _patch_project_dir(tmp_path):
            from odysseus.mcp.review_tools import get_per_class_recall

            result = await get_per_class_recall(                ctx=None,
                run_id=self._RUN_ID,
                output_dir="outputs",
            )
        assert "recall" in result
        assert "support" in result
        assert "trend" in result
        assert "regression" in result

    async def test_missing_search_state_returns_message(self, tmp_path: Path) -> None:
        """When search state doesn't exist, returns an explanatory string (no exception)."""
        with _patch_project_dir(tmp_path):
            from odysseus.mcp.review_tools import get_per_class_recall

            result = await get_per_class_recall(                ctx=None,
                run_id="nonexistent-run",
                output_dir="outputs",
            )
        assert "not found" in result.lower() or "not initialised" in result.lower()
