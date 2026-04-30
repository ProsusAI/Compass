"""Tests for review MCP tools — record_directive_outcomes_tool decomposed params."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
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
