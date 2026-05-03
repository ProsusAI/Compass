"""Tests for review MCP tools — record_directive_outcomes_tool decomposed params."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from odysseus.mcp import (
    build_review_briefing_tool,
    get_prompt_text_tool,
    query_holdout_examples_tool,
    record_directive_outcomes_tool,
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


class TestRecordDirectiveOutcomesTrajectoryId:
    """Tests for the EMOSA trajectory_id fanout path of record_directive_outcomes_tool."""

    _RUN_ID = "test-run-trajectory"

    async def test_trajectory_id_writes_per_trajectory_file(self, tmp_path: Path) -> None:
        """trajectory_id=2 writes child_variants_t2.json, not child_variants.json."""
        with _patch_project_dir(tmp_path):
            result_json = await record_directive_outcomes_tool(
                ctx=None,
                run_id=self._RUN_ID,
                outcomes=[_OUTCOME],
                child_variants=_CHILD_VARIANTS,
                trajectory_id=2,
                output_dir="outputs",
            )

        result = json.loads(result_json)
        assert result["child_variants_saved"] == 1

        # Per-trajectory file must exist
        per_traj = tmp_path / "outputs" / self._RUN_ID / "search" / "child_variants_t2.json"
        assert per_traj.exists(), "child_variants_t2.json must be written for trajectory_id=2"

        # Single-slot sentinel must NOT be written
        single_slot = tmp_path / "outputs" / self._RUN_ID / "search" / "child_variants.json"
        assert not single_slot.exists(), "child_variants.json must not be written for EMOSA fanout"

    async def test_trajectory_id_updates_review_dispatched(self, tmp_path: Path) -> None:
        """trajectory_id=2 adds 2 to review_dispatched.json trajectory_ids list."""
        with _patch_project_dir(tmp_path):
            await record_directive_outcomes_tool(
                ctx=None,
                run_id=self._RUN_ID,
                outcomes=[_OUTCOME],
                child_variants=_CHILD_VARIANTS,
                trajectory_id=2,
                output_dir="outputs",
            )

        from odysseus.agents.review.ops import load_dispatched_trajectories

        dispatched = load_dispatched_trajectories(self._RUN_ID, output_dir=tmp_path / "outputs")
        assert 2 in dispatched, f"trajectory_id 2 must appear in dispatched list; got {dispatched}"

    async def test_trajectory_variant_id_format(self, tmp_path: Path) -> None:
        """Variant ids use cv-{round}-t{trajectory_id}-{i} format for EMOSA fanout."""
        with _patch_project_dir(tmp_path):
            result_json = await record_directive_outcomes_tool(
                ctx=None,
                run_id=self._RUN_ID,
                outcomes=[_OUTCOME],
                child_variants=[{**_CHILD_VARIANTS[0]}],  # no variant_id set
                trajectory_id=2,
                output_dir="outputs",
            )

        result = json.loads(result_json)
        summary = result["variants_summary"]
        assert len(summary) == 1
        # round defaults to 0 when no search_state.json exists
        assert summary[0]["variant_id"] == "cv-0-t2-0"

    async def test_single_slot_path_unchanged_without_trajectory_id(self, tmp_path: Path) -> None:
        """Without trajectory_id, the existing single-slot path still writes child_variants.json."""
        with _patch_project_dir(tmp_path):
            await record_directive_outcomes_tool(
                ctx=None,
                run_id=self._RUN_ID + "-single",
                outcomes=[_OUTCOME],
                child_variants=_CHILD_VARIANTS,
                output_dir="outputs",
            )

        single_slot = tmp_path / "outputs" / (self._RUN_ID + "-single") / "search" / "child_variants.json"
        assert single_slot.exists(), "child_variants.json must be written for single-slot path"


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
            result = await get_prompt_text_tool(ctx=None, version="v1", run_id=self._RUN_ID, output_dir="outputs")

        assert result == "run-specific content"

    async def test_fallback_to_project_dir_when_absent_from_run(self, tmp_path: Path) -> None:
        """Version absent from run-specific dir is loaded from project-level prompts/."""
        run_prompts = tmp_path / "outputs" / self._RUN_ID / "prompts"
        run_prompts.mkdir(parents=True)

        project_prompts = tmp_path / "prompts"
        project_prompts.mkdir()
        (project_prompts / "v2.txt").write_text("project v2")

        with _patch_project_dir(tmp_path):
            result = await get_prompt_text_tool(ctx=None, version="v2", run_id=self._RUN_ID, output_dir="outputs")

        assert result == "project v2"

    async def test_error_json_when_version_in_neither_dir(self, tmp_path: Path) -> None:
        """Version absent from both dirs returns a JSON error with the expected shape."""
        run_prompts = tmp_path / "outputs" / self._RUN_ID / "prompts"
        run_prompts.mkdir(parents=True)
        project_prompts = tmp_path / "prompts"
        project_prompts.mkdir()

        with _patch_project_dir(tmp_path):
            result = await get_prompt_text_tool(ctx=None, version="vX", run_id=self._RUN_ID, output_dir="outputs")

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


class TestVariantIdSequentialCounter:
    """variant_ids assigned by record_directive_outcomes_tool are sequential across calls."""

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
            result_json = await record_directive_outcomes_tool(
                ctx=None,
                run_id=self._RUN_ID,
                outcomes=[],
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
            await record_directive_outcomes_tool(
                ctx=None,
                run_id=self._RUN_ID,
                outcomes=[],
                child_variants=[self._CHILD_VARIANT_RAW],
                output_dir="outputs",
            )
            result_json = await record_directive_outcomes_tool(
                ctx=None,
                run_id=self._RUN_ID,
                outcomes=[],
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
            await record_directive_outcomes_tool(
                ctx=None,
                run_id=self._RUN_ID,
                outcomes=[],
                child_variants=[self._CHILD_VARIANT_RAW, dict(self._CHILD_VARIANT_RAW, hypothesis="V2")],
                output_dir="outputs",
            )
            await record_directive_outcomes_tool(
                ctx=None,
                run_id=self._RUN_ID,
                outcomes=[],
                child_variants=[dict(self._CHILD_VARIANT_RAW, hypothesis="V3")],
                output_dir="outputs",
            )

        state = _load_state(self._RUN_ID, tmp_path / "outputs")
        assert state.next_variant_seq == 4


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
            rows.append(json.dumps({"id": f"m{i}", "input": f"text {i}", "expected": {"route": self._ROUTE}}))
        for i in range(n_other):
            rows.append(json.dumps({"id": f"o{i}", "input": f"other {i}", "expected": {"route": self._OTHER_ROUTE}}))
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


# ---------------------------------------------------------------------------
# Helpers for build_review_briefing_tool tests
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
    """Tests for confusion-analysis selector behavior in build_review_briefing_tool."""

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
            result = await build_review_briefing_tool(
                ctx=None,
                run_id=run_id,
                output_dir="outputs",
            )

        # Extract briefing JSON from output (may have executive summary header)
        briefing_json = result.split("# Full Briefing Data\n\n", 1)[1] if "# Full Briefing Data" in result else result
        briefing = json.loads(briefing_json)

        confusion = briefing.get("confusion_analysis", [])
        assert len(confusion) > 0, "expected non-empty confusion_analysis"

        # Count unique misrouted example IDs: e1 appears in both versions but
        # dedup should count it once. e2 appears in v2 only. So count == 2.
        simple_to_complex = next(
            (c for c in confusion if c["true_route"] == "simple" and c["predicted_route"] == "complex"),
            None,
        )
        assert simple_to_complex is not None
        assert simple_to_complex["count"] == 2  # deduped: e1 + e2, not 3

    async def test_empty_elite_set_yields_empty_confusion(self, tmp_path: Path) -> None:
        """Round 0 / empty elite_set: confusion_analysis == [] without errors."""
        run_id = self._RUN_ID + "-empty"
        state_dict = _make_state_dict(run_id, elite_set=[], round_=0)
        _write_state(tmp_path, run_id, state_dict)

        with _patch_project_dir(tmp_path):
            result = await build_review_briefing_tool(
                ctx=None,
                run_id=run_id,
                output_dir="outputs",
            )

        briefing_json = result.split("# Full Briefing Data\n\n", 1)[1] if "# Full Briefing Data" in result else result
        briefing = json.loads(briefing_json)
        assert briefing.get("confusion_analysis") == []

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

        original_selector = _rt._select_confusion_candidates
        try:
            # Override: only analyse "va"
            _rt._select_confusion_candidates = lambda state: ["va"]  # type: ignore[assignment]

            with _patch_project_dir(tmp_path):
                result = await build_review_briefing_tool(
                    ctx=None,
                    run_id=run_id,
                    output_dir="outputs",
                )
        finally:
            _rt._select_confusion_candidates = original_selector

        briefing_json = result.split("# Full Briefing Data\n\n", 1)[1] if "# Full Briefing Data" in result else result
        briefing = json.loads(briefing_json)

        confusion = briefing.get("confusion_analysis", [])
        # Only va's misroutes counted: e1 only → count == 1
        simple_to_complex = next(
            (c for c in confusion if c["true_route"] == "simple" and c["predicted_route"] == "complex"),
            None,
        )
        assert simple_to_complex is not None
        assert simple_to_complex["count"] == 1, (
            "selector override to 'va' only should reflect 1 unique misroute (e1), not 2"
        )


# ---------------------------------------------------------------------------
# B2: build_review_briefing_tool auto-fires calibration for EMOSA
# ---------------------------------------------------------------------------


def _make_emosa_state_dict(run_id: str, annealing_state: dict) -> dict:
    """Build a minimal SearchState dict for an EMOSA run."""
    return {
        "search_state_id": run_id,
        "backend": "anthropic",
        "round": 0,
        "elite_set": [],
        "round_history": [],
        "stagnation_count": 0,
        "stagnation_limit": 3,
        "convergence_limit": 5,
        "max_rounds": 50,
        "mutation_mode": "targeted",
        "converged": False,
        "algorithm": "emosa",
        "algorithm_state": annealing_state,
        "loop_phase": "review",
    }


def _write_pending_candidates(tmp_path: Path, run_id: str, candidates: list[dict]) -> None:
    """Write pending_candidates.json for the given run."""
    search_dir = tmp_path / "outputs" / run_id / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    (search_dir / "pending_candidates.json").write_text(json.dumps(candidates), encoding="utf-8")


class TestBuildReviewBriefingAutoFiresCalibration:
    """B2: build_review_briefing_tool auto-fires _calibration_complete on first review entry."""

    _RUN_ID = "test-emosa-autocalib"

    def _make_scored_candidates(self, run_id: str, num: int = 5) -> list[dict]:
        """Build K scored pending candidates that form a Pareto front (none dominated).

        Trade-off: higher quality → higher cost, so no single candidate dominates another.
        """
        return [
            {
                "prompt_version": f"v{i + 1}",
                "parent_version": None,
                "quality_score": 0.7 + i * 0.03,  # higher quality …
                "cost": 0.01 + i * 0.02,  # … but also higher cost
                "round_introduced": 1,
                "eval_status": "complete",
                "example_ids": [],
            }
            for i in range(num)
        ]

    async def test_build_review_briefing_auto_fires_calibration(self, tmp_path: Path) -> None:
        """With K=5 scored pending and empty elite_set, calibration fires automatically.

        Post-call state must have round==1, len(elite_set)==5, algorithm_state["phase"]=="search".
        """
        from odysseus.agents.prompt_builder.annealing import AnnealingState
        from odysseus.agents.prompt_builder.search_ops import (
            _build_emosa_initial_state,
            get_search_state,
        )

        run_id = self._RUN_ID + "-fires"
        annealing_state = _build_emosa_initial_state(num_trajectories=5)
        state_dict = _make_emosa_state_dict(run_id, annealing_state)
        _write_state(tmp_path, run_id, state_dict)
        candidates = self._make_scored_candidates(run_id, num=5)
        _write_pending_candidates(tmp_path, run_id, candidates)

        with _patch_project_dir(tmp_path):
            await build_review_briefing_tool(
                ctx=None,
                run_id=run_id,
                output_dir="outputs",
            )

        post_state = get_search_state(run_id=run_id, output_dir=tmp_path / "outputs")
        assert post_state.round == 1, f"Expected round==1, got {post_state.round}"
        assert len(post_state.elite_set) == 5, f"Expected 5 elite entries, got {len(post_state.elite_set)}"
        annealing = AnnealingState.model_validate(post_state.algorithm_state)
        assert annealing.phase == "search", f"Expected phase=='search', got {annealing.phase}"

    async def test_build_review_briefing_auto_fire_idempotent(self, tmp_path: Path) -> None:
        """After first call seeds elite_set, calling again does NOT re-trigger calibration.

        round stays at 1 and elite_set stays at 5 entries after the second call.
        """
        from odysseus.agents.prompt_builder.search_ops import (
            _build_emosa_initial_state,
            get_search_state,
        )

        run_id = self._RUN_ID + "-idempotent"
        annealing_state = _build_emosa_initial_state(num_trajectories=5)
        state_dict = _make_emosa_state_dict(run_id, annealing_state)
        _write_state(tmp_path, run_id, state_dict)
        candidates = self._make_scored_candidates(run_id, num=5)
        _write_pending_candidates(tmp_path, run_id, candidates)

        with _patch_project_dir(tmp_path):
            # First call: should auto-fire calibration
            await build_review_briefing_tool(
                ctx=None,
                run_id=run_id,
                output_dir="outputs",
            )

            post_first = get_search_state(run_id=run_id, output_dir=tmp_path / "outputs")
            assert post_first.round == 1
            assert len(post_first.elite_set) == 5

            # Second call: elite_set is non-empty → guard short-circuits, round stays at 1
            await build_review_briefing_tool(
                ctx=None,
                run_id=run_id,
                output_dir="outputs",
            )

        post_second = get_search_state(run_id=run_id, output_dir=tmp_path / "outputs")
        assert post_second.round == 1, f"Expected round to stay at 1, got {post_second.round}"
        assert len(post_second.elite_set) == 5, (
            f"Expected elite_set to stay at 5 entries, got {len(post_second.elite_set)}"
        )

    async def test_build_review_briefing_skips_calibration_when_elite_set_populated(self, tmp_path: Path) -> None:
        """If elite_set is already populated, calibration guard is skipped (non-EMOSA path)."""
        from odysseus.agents.prompt_builder.search_ops import get_search_state

        run_id = self._RUN_ID + "-skip"
        # State already has elite_set entries (post-calibration shape)
        state_dict = _make_state_dict(
            run_id,
            elite_set=[
                {
                    "prompt_version": "v1",
                    "parent_version": None,
                    "quality_score": 0.80,
                    "cost": 1.0,
                    "round_introduced": 1,
                }
            ],
            round_=1,
        )
        state_dict["algorithm"] = "emosa"
        _write_state(tmp_path, run_id, state_dict)

        with _patch_project_dir(tmp_path):
            await build_review_briefing_tool(
                ctx=None,
                run_id=run_id,
                output_dir="outputs",
            )

        post_state = get_search_state(run_id=run_id, output_dir=tmp_path / "outputs")
        # round should NOT have advanced beyond what calibration would do
        assert post_state.round == 1, "round should stay at 1 when elite_set is already populated"


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
        from odysseus.eval.models import ScoreReport
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

        # Must still be a valid ScoreReport
        ScoreReport.model_validate(result)


class TestEmptyOutcomeGuardrail:
    """Tests for the B.3 guardrail: warn when round N≥2 has empty outcomes with prior directives."""

    _RUN_ID = "test-run-guardrail"

    def _write_search_state(self, tmp_path: Path, run_id: str, round_num: int) -> None:
        search_dir = tmp_path / "outputs" / run_id / "search"
        search_dir.mkdir(parents=True, exist_ok=True)
        state_dict = {
            "search_state_id": run_id,
            "backend": "anthropic",
            "algorithm": "beam",
            "round": round_num,
            "elite_set": [],
            "round_history": [],
            "stagnation_count": 0,
            "stagnation_limit": 3,
            "convergence_limit": 5,
            "max_rounds": 50,
            "mutation_mode": "targeted",
            "converged": False,
            "next_variant_seq": 1,
        }
        (search_dir / "search_state.json").write_text(json.dumps(state_dict), encoding="utf-8")

    def _write_prior_child_variants(self, tmp_path: Path, run_id: str) -> None:
        search_dir = tmp_path / "outputs" / run_id / "search"
        search_dir.mkdir(parents=True, exist_ok=True)
        (search_dir / "child_variants.json").write_text("[]", encoding="utf-8")

    async def test_warns_when_round2_empty_outcomes_with_prior_directives(self, tmp_path: Path, capsys: Any) -> None:
        """round=2 + outcomes=[] + child_variants.json present → warning on stderr."""
        self._write_search_state(tmp_path, self._RUN_ID, round_num=2)
        self._write_prior_child_variants(tmp_path, self._RUN_ID)

        with _patch_project_dir(tmp_path):
            await record_directive_outcomes_tool(
                ctx=None,
                run_id=self._RUN_ID,
                outcomes=[],
                output_dir="outputs",
            )

        captured = capsys.readouterr()
        assert "Warning" in captured.err
        assert "round 2" in captured.err
        assert "empty outcomes" in captured.err

    async def test_no_warning_for_round1_empty_outcomes(self, tmp_path: Path, capsys: Any) -> None:
        """round=1 + outcomes=[] → no warning (no prior directives)."""
        self._write_search_state(tmp_path, self._RUN_ID + "-r1", round_num=1)

        with _patch_project_dir(tmp_path):
            await record_directive_outcomes_tool(
                ctx=None,
                run_id=self._RUN_ID + "-r1",
                outcomes=[],
                output_dir="outputs",
            )

        captured = capsys.readouterr()
        assert "Warning" not in captured.err

    async def test_no_warning_when_outcomes_non_empty(self, tmp_path: Path, capsys: Any) -> None:
        """round=2 + non-empty outcomes → no warning."""
        self._write_search_state(tmp_path, self._RUN_ID + "-nonempty", round_num=2)
        self._write_prior_child_variants(tmp_path, self._RUN_ID + "-nonempty")

        with _patch_project_dir(tmp_path):
            await record_directive_outcomes_tool(
                ctx=None,
                run_id=self._RUN_ID + "-nonempty",
                outcomes=[_OUTCOME],
                output_dir="outputs",
            )

        captured = capsys.readouterr()
        assert "Warning" not in captured.err


class TestBuildReviewBriefingDoesNotWriteRoundReport:
    """C.2: build_review_briefing_tool must NOT write round_reports/round_N.json."""

    _RUN_ID = "test-run-no-rr-write"

    async def test_briefing_does_not_write_round_report(self, tmp_path: Path) -> None:
        """build_review_briefing_tool leaves round_reports/ untouched (no racy write)."""
        run_id = self._RUN_ID
        state_dict = _make_state_dict(run_id, elite_set=[], round_=2)
        _write_state(tmp_path, run_id, state_dict)

        round_reports_dir = tmp_path / "outputs" / run_id / "search" / "round_reports"

        with _patch_project_dir(tmp_path):
            await build_review_briefing_tool(
                ctx=None,
                run_id=run_id,
                output_dir="outputs",
            )

        assert not round_reports_dir.exists(), (
            "build_review_briefing_tool must not create round_reports/ directory"
        )

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
            await build_review_briefing_tool(
                ctx=None,
                run_id=run_id,
                output_dir="outputs",
            )

        on_disk = json.loads((round_reports_dir / "round_2.json").read_text(encoding="utf-8"))
        assert on_disk == sentinel, (
            "build_review_briefing_tool must not overwrite existing round_reports/round_2.json"
        )
