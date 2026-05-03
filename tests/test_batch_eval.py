"""Tests for odysseus.eval.batch_eval — run_batch_eval_impl and models."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from odysseus.agents.prompt_builder.search_ops import (
    _load_pending,
    _load_state,
    _save_state,
    init_search_state,
    register_candidate,
)
from odysseus.eval.batch_eval import (
    BatchEvalCandidate,
    BatchEvalResult,
    CandidateEvalOutcome,
    _extract_quality_score,
    _extract_quality_score_from_dict,
    _set_candidate_eval_status,
    run_batch_eval_impl,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SINGLE_EVAL = "odysseus.eval.batch_eval._run_single_eval"


def _make_mock_run_report(quality_score: float = 0.85) -> MagicMock:
    """Create a minimal mock RunReport with the metrics/summary structure."""
    report = MagicMock()
    report.metrics = {"accuracy": quality_score, "cost_change_with_overhead": -0.3}
    report.summary = MagicMock()
    report.summary.succeeded = 10
    report.summary.total = 10
    return report


def _make_candidates(count: int = 2) -> list[BatchEvalCandidate]:
    return [
        BatchEvalCandidate(
            prompt_version=f"v{i + 2}",
            parent_version="v1",
            example_ids=["e1", "e2"],
        )
        for i in range(count)
    ]


@pytest.fixture
def tmp_run(tmp_path: Path):
    """Set up a search state in tmp_path and return (run_id, tmp_path)."""
    run_id = "test-run-001"
    init_search_state(
        backend="anthropic",
        run_id=run_id,
        output_dir=tmp_path,
    )
    return run_id, tmp_path


# ---------------------------------------------------------------------------
# Test 1: normal mode — all 3 candidates succeed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normal_mode_concurrent_succeeds(tmp_run: tuple[str, Path]) -> None:
    """Register 3 candidates; all succeed; state reflects completion."""
    run_id, tmp_path = tmp_run
    candidates = _make_candidates(3)
    mock_report = _make_mock_run_report(quality_score=0.9)

    with patch(_SINGLE_EVAL, new=AsyncMock(return_value=mock_report)):
        result = await run_batch_eval_impl(run_id, candidates, output_dir=tmp_path)

    assert len(result.succeeded) == 3
    assert len(result.failed) == 0

    # eval_status on disk is "complete" (set by record_eval_result)
    pending = _load_pending(run_id, tmp_path)
    assert all(c.eval_status == "complete" for c in pending)

    # active_evals drained
    state = _load_state(run_id, tmp_path)
    assert state.active_evals == []

    # loop_phase auto-transitioned to "review"
    assert state.loop_phase == "review"


# ---------------------------------------------------------------------------
# Test 2: one candidate raises, others succeed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_candidate_raises_others_succeed(tmp_run: tuple[str, Path]) -> None:
    """One _run_single_eval raises; that candidate lands in failed, others succeed."""
    run_id, tmp_path = tmp_run
    candidates = _make_candidates(3)
    mock_report = _make_mock_run_report(quality_score=0.8)

    call_count = 0

    async def side_effect(candidate, rid, rate_limiter, output_dir):
        nonlocal call_count
        call_count += 1
        if candidate.prompt_version == "v2":
            raise RuntimeError("network timeout")
        return mock_report

    with patch(_SINGLE_EVAL, new=side_effect):
        result = await run_batch_eval_impl(run_id, candidates, output_dir=tmp_path)

    assert len(result.succeeded) == 2
    assert len(result.failed) == 1

    failed_outcome = result.failed[0]
    assert failed_outcome.prompt_version == "v2"
    assert failed_outcome.eval_status == "failed"
    assert "network timeout" in (failed_outcome.error or "")
    assert failed_outcome.quality_score is None

    # Check disk state
    pending = _load_pending(run_id, tmp_path)
    status_map = {c.prompt_version: c.eval_status for c in pending}
    assert status_map["v2"] == "failed"
    assert status_map["v3"] == "complete"
    assert status_map["v4"] == "complete"

    # active_evals still drained
    state = _load_state(run_id, tmp_path)
    assert state.active_evals == []
    assert state.loop_phase == "review"


# ---------------------------------------------------------------------------
# Test 3: recovery — smart-skip uses existing report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_smart_skip_uses_existing_report(tmp_run: tuple[str, Path]) -> None:
    """Recovery mode smart-skips a candidate whose report.json already exists on disk."""
    run_id, tmp_path = tmp_run

    # Register candidate, then flip to "running" to simulate an interrupted eval
    register_candidate(
        run_id=run_id,
        prompt_version="v9",
        parent_version="v1",
        example_ids=["e1"],
        output_dir=tmp_path,
        eval_status="pending",
    )
    _set_candidate_eval_status(run_id, "v9", "running", tmp_path)

    # Add its prompt_version to active_evals
    state = _load_state(run_id, tmp_path)
    state = state.model_copy(update={"active_evals": ["v9"]})
    _save_state(run_id, state, tmp_path)

    # Pre-write a valid report.json at the expected path
    report_dir = tmp_path / run_id / "eval" / "v9"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_data = {
        "metrics": {"accuracy": 0.91, "cost_change_with_overhead": -0.2},
        "summary": {"succeeded": 5, "total": 5},
    }
    (report_dir / "report.json").write_text(json.dumps(report_data), encoding="utf-8")

    with patch(_SINGLE_EVAL, new=AsyncMock()) as mock_run:
        result = await run_batch_eval_impl(run_id, [], output_dir=tmp_path)

    # controller.run should NOT have been invoked
    mock_run.assert_not_called()

    assert len(result.succeeded) == 1
    assert len(result.failed) == 0
    assert result.succeeded[0].prompt_version == "v9"
    assert result.succeeded[0].eval_status == "complete"
    assert result.succeeded[0].quality_score == pytest.approx(0.91)

    # Disk state
    pending = _load_pending(run_id, tmp_path)
    assert pending[0].eval_status == "complete"

    final_state = _load_state(run_id, tmp_path)
    assert final_state.active_evals == []
    assert final_state.loop_phase == "review"


# ---------------------------------------------------------------------------
# Test 4: recovery — corrupt report triggers re-run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_corrupt_report_reruns_eval(tmp_run: tuple[str, Path]) -> None:
    """Recovery mode re-runs a candidate whose report.json is malformed JSON."""
    run_id, tmp_path = tmp_run

    register_candidate(
        run_id=run_id,
        prompt_version="v9",
        parent_version="v1",
        example_ids=["e1"],
        output_dir=tmp_path,
        eval_status="pending",
    )
    _set_candidate_eval_status(run_id, "v9", "running", tmp_path)

    state = _load_state(run_id, tmp_path)
    state = state.model_copy(update={"active_evals": ["v9"]})
    _save_state(run_id, state, tmp_path)

    # Write malformed JSON to the report path
    report_dir = tmp_path / run_id / "eval" / "v9"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.json").write_text("{corrupt json{{", encoding="utf-8")

    mock_report = _make_mock_run_report(quality_score=0.75)

    with patch(_SINGLE_EVAL, new=AsyncMock(return_value=mock_report)) as mock_run:
        result = await run_batch_eval_impl(run_id, [], output_dir=tmp_path)

    # controller.run should have been called once for the re-run
    assert mock_run.call_count == 1

    assert len(result.succeeded) == 1
    assert result.succeeded[0].prompt_version == "v9"
    assert result.succeeded[0].eval_status == "complete"

    final_state = _load_state(run_id, tmp_path)
    assert final_state.active_evals == []
    assert final_state.loop_phase == "review"


# ---------------------------------------------------------------------------
# Test 5: recovery — empty pending returns empty result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_empty_pending_returns_empty(tmp_run: tuple[str, Path]) -> None:
    """Recovery with no pending candidates returns an empty BatchEvalResult."""
    run_id, tmp_path = tmp_run

    # active_evals is empty (default), pending is empty (no registered candidates)
    result = await run_batch_eval_impl(run_id, [], output_dir=tmp_path)

    assert result == BatchEvalResult(succeeded=[], failed=[])


# ---------------------------------------------------------------------------
# Test 11: recovery — drains active_evals and transitions to review
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_drains_active_evals_and_transitions_to_review(
    tmp_run: tuple[str, Path],
) -> None:
    """After recovery, active_evals is empty, loop_phase is 'review', build_dispatched cleared."""
    run_id, tmp_path = tmp_run

    from odysseus.agents.pipeline.dispatch import record_build_dispatched

    # Record a build-dispatched marker so we can assert it's cleared
    record_build_dispatched(run_id, round=1, output_dir=tmp_path)
    dispatched_marker = tmp_path / run_id / "search" / "build_dispatched.json"
    assert dispatched_marker.exists(), "Precondition: marker must exist before recovery"

    register_candidate(
        run_id=run_id,
        prompt_version="v9",
        parent_version="v1",
        example_ids=["e1"],
        output_dir=tmp_path,
        eval_status="pending",
    )
    _set_candidate_eval_status(run_id, "v9", "running", tmp_path)

    state = _load_state(run_id, tmp_path)
    state = state.model_copy(update={"active_evals": ["v9"]})
    _save_state(run_id, state, tmp_path)

    mock_report = _make_mock_run_report(quality_score=0.8)

    with patch(_SINGLE_EVAL, new=AsyncMock(return_value=mock_report)):
        result = await run_batch_eval_impl(run_id, [], output_dir=tmp_path)

    assert len(result.succeeded) == 1
    assert result.succeeded[0].prompt_version == "v9"

    final_state = _load_state(run_id, tmp_path)
    assert final_state.active_evals == []
    assert final_state.loop_phase == "review"

    # build_dispatched marker should have been cleared
    assert not dispatched_marker.exists(), "build_dispatched marker must be removed after recovery"


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_evals_populated_before_gather(tmp_run: tuple[str, Path]) -> None:
    """active_evals is populated before gather and cleared after."""
    run_id, tmp_path = tmp_run
    candidates = _make_candidates(2)
    captured_states: list[list[str]] = []

    async def mock_eval(candidate, rid, rate_limiter, output_dir):
        state = _load_state(rid, output_dir)
        captured_states.append(list(state.active_evals))
        return _make_mock_run_report()

    with patch(_SINGLE_EVAL, new=mock_eval):
        await run_batch_eval_impl(run_id, candidates, output_dir=tmp_path)

    assert len(captured_states) >= 2
    for captured in captured_states:
        assert len(captured) >= 1


# ---------------------------------------------------------------------------
# trajectory_id plumbing through BatchEvalCandidate → register_candidate
# ---------------------------------------------------------------------------


def test_batch_eval_candidate_has_trajectory_id_field() -> None:
    """BatchEvalCandidate has a trajectory_id field defaulting to None."""
    c = BatchEvalCandidate(prompt_version="v1")
    assert c.trajectory_id is None


def test_batch_eval_candidate_trajectory_id_roundtrips() -> None:
    """BatchEvalCandidate.model_validate with trajectory_id=1 round-trips correctly."""
    data = {"prompt_version": "v1", "parent_version": None, "example_ids": [], "trajectory_id": 1}
    c = BatchEvalCandidate.model_validate(data)
    assert c.trajectory_id == 1
    dumped = c.model_dump()
    assert dumped["trajectory_id"] == 1


@pytest.mark.asyncio
async def test_batch_eval_forwards_trajectory_id_to_register_candidate(tmp_run: tuple[str, Path]) -> None:
    """run_batch_eval_impl forwards trajectory_id from BatchEvalCandidate to register_candidate."""
    run_id, tmp_path = tmp_run
    candidates = [
        BatchEvalCandidate(
            prompt_version="v2",
            parent_version="v1",
            example_ids=["e1"],
            trajectory_id=3,
        )
    ]
    mock_report = _make_mock_run_report(quality_score=0.9)

    with patch(_SINGLE_EVAL, new=AsyncMock(return_value=mock_report)):
        await run_batch_eval_impl(run_id, candidates, output_dir=tmp_path)

    # After run, candidate should have trajectory_id=3 in pending (archive is populated later by advance_round)
    pending = _load_pending(run_id, tmp_path)
    v2 = next((c for c in pending if c.prompt_version == "v2"), None)
    assert v2 is not None
    assert v2.trajectory_id == 3

    state = _load_state(run_id, tmp_path)
    assert state.active_evals == []


@pytest.mark.asyncio
async def test_eval_status_running_during_dispatch(tmp_run: tuple[str, Path]) -> None:
    """eval_status is 'running' while _run_single_eval executes."""
    run_id, tmp_path = tmp_run
    candidates = _make_candidates(1)
    captured_status: list[str | None] = []

    async def mock_eval(candidate, rid, rate_limiter, output_dir):
        pending = _load_pending(rid, output_dir)
        for c in pending:
            if c.prompt_version == candidate.prompt_version:
                captured_status.append(c.eval_status)
        return _make_mock_run_report()

    with patch(_SINGLE_EVAL, new=mock_eval):
        await run_batch_eval_impl(run_id, candidates, output_dir=tmp_path)

    assert captured_status == ["running"]


@pytest.mark.asyncio
async def test_all_fail_still_transitions_to_review(tmp_run: tuple[str, Path]) -> None:
    """Even when all candidates fail, loop_phase transitions to 'review'."""
    run_id, tmp_path = tmp_run
    candidates = _make_candidates(2)

    with patch(_SINGLE_EVAL, new=AsyncMock(side_effect=RuntimeError("boom"))):
        result = await run_batch_eval_impl(run_id, candidates, output_dir=tmp_path)

    assert len(result.succeeded) == 0
    assert len(result.failed) == 2

    state = _load_state(run_id, tmp_path)
    assert state.active_evals == []
    assert state.loop_phase == "review"


@pytest.mark.asyncio
async def test_quality_score_from_primary_metric(tmp_run: tuple[str, Path]) -> None:
    """quality_score is extracted using primary_metric_name from SearchState."""
    run_id, tmp_path = tmp_run

    from odysseus.agents.prompt_builder.search_ops import _save_state

    state = _load_state(run_id, tmp_path)
    state = state.model_copy(update={"primary_metric_name": "f1/macro"})
    _save_state(run_id, state, tmp_path)

    candidates = _make_candidates(1)
    mock_report = MagicMock()
    mock_report.metrics = {"accuracy": 0.5, "f1": 0.88}
    mock_report.summary = MagicMock()
    mock_report.summary.succeeded = 5
    mock_report.summary.total = 5

    with patch(_SINGLE_EVAL, new=AsyncMock(return_value=mock_report)):
        result = await run_batch_eval_impl(run_id, candidates, output_dir=tmp_path)

    assert len(result.succeeded) == 1
    assert result.succeeded[0].quality_score == 0.88


@pytest.mark.asyncio
async def test_zero_succeeded_marked_as_failed(tmp_run: tuple[str, Path]) -> None:
    """Candidate with summary.succeeded==0 is treated as failed."""
    run_id, tmp_path = tmp_run
    candidates = _make_candidates(1)

    mock_report = MagicMock()
    mock_report.metrics = {"accuracy": 0.0}
    mock_report.summary = MagicMock()
    mock_report.summary.succeeded = 0
    mock_report.summary.total = 5

    with patch(_SINGLE_EVAL, new=AsyncMock(return_value=mock_report)):
        result = await run_batch_eval_impl(run_id, candidates, output_dir=tmp_path)

    assert len(result.succeeded) == 0
    assert len(result.failed) == 1
    assert "0 succeeded" in (result.failed[0].error or "")

    pending = _load_pending(run_id, tmp_path)
    assert pending[0].eval_status == "failed"


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestBatchEvalModels:
    def test_batch_eval_candidate_defaults(self) -> None:
        c = BatchEvalCandidate(prompt_version="v1")
        assert c.parent_version is None
        assert c.example_ids == []

    def test_batch_eval_candidate_with_fields(self) -> None:
        c = BatchEvalCandidate(
            prompt_version="v2",
            parent_version="v1",
            example_ids=["e1", "e2"],
        )
        assert c.prompt_version == "v2"
        assert c.parent_version == "v1"
        assert c.example_ids == ["e1", "e2"]

    def test_candidate_eval_outcome_complete(self) -> None:
        o = CandidateEvalOutcome(
            prompt_version="v2",
            eval_status="complete",
            quality_score=0.9,
            cost=-0.1,
        )
        assert o.eval_status == "complete"
        assert o.error is None

    def test_candidate_eval_outcome_failed(self) -> None:
        o = CandidateEvalOutcome(
            prompt_version="v2",
            eval_status="failed",
            error="Connection error",
        )
        assert o.eval_status == "failed"
        assert o.quality_score is None

    def test_batch_eval_result_empty(self) -> None:
        r = BatchEvalResult(succeeded=[], failed=[])
        assert r.succeeded == []
        assert r.failed == []


# ---------------------------------------------------------------------------
# MCP tool roundtrip
# ---------------------------------------------------------------------------

RESOLVE_PROJECT_DIR = "odysseus.project_dir.resolve_project_dir"
_RUN_BATCH_EVAL_IMPL = "odysseus.eval.batch_eval.run_batch_eval_impl"


@pytest.mark.asyncio
async def test_run_batch_eval_mcp_tool_roundtrip(tmp_run: tuple[str, Path]) -> None:
    """run_batch_eval MCP tool parses candidates and returns JSON-serialised BatchEvalResult."""
    from odysseus.mcp.prompt_building_tools import run_batch_eval as run_batch_eval_tool

    run_id, tmp_path = tmp_run
    mock_result = BatchEvalResult(
        succeeded=[
            CandidateEvalOutcome(
                prompt_version="v2",
                eval_status="complete",
                quality_score=0.75,
                cost=-0.1,
            )
        ],
        failed=[],
    )

    candidates_payload = [{"prompt_version": "v2", "parent_version": "v1", "example_ids": ["e1"]}]

    with (
        patch(RESOLVE_PROJECT_DIR, new_callable=AsyncMock, return_value=tmp_path),
        patch(_RUN_BATCH_EVAL_IMPL, new_callable=AsyncMock, return_value=mock_result) as mock_impl,
    ):
        raw = await run_batch_eval_tool(ctx=None, run_id=run_id, candidates=candidates_payload)

    # Verify the returned value is valid JSON with the expected shape
    parsed = json.loads(raw)
    assert "succeeded" in parsed
    assert "failed" in parsed
    assert len(parsed["succeeded"]) == 1
    assert parsed["succeeded"][0]["prompt_version"] == "v2"
    assert parsed["succeeded"][0]["eval_status"] == "complete"
    assert len(parsed["failed"]) == 0

    # Verify run_batch_eval_impl was called with parsed BatchEvalCandidate objects
    mock_impl.assert_called_once()
    call_args = mock_impl.call_args
    assert call_args.args[0] == run_id
    parsed_candidates = call_args.args[1]
    assert len(parsed_candidates) == 1
    assert isinstance(parsed_candidates[0], BatchEvalCandidate)
    assert parsed_candidates[0].prompt_version == "v2"
    assert parsed_candidates[0].parent_version == "v1"
    assert parsed_candidates[0].example_ids == ["e1"]


# ---------------------------------------------------------------------------
# _extract_quality_score preference tests
# ---------------------------------------------------------------------------


class TestExtractQualityScorePreference:
    """oracle_quality_captured should be preferred over accuracy."""

    def _fake_report(self, metrics: dict) -> object:
        """Build a minimal report-like object with a .metrics attribute."""
        report = MagicMock()
        report.metrics = metrics
        return report

    def test_prefers_oracle_quality_captured_over_accuracy(self):
        """When both keys present, returns oracle_quality_captured."""
        report = self._fake_report({"oracle_quality_captured": 0.92, "accuracy": 0.85})
        assert _extract_quality_score(report, primary_metric_name=None) == pytest.approx(0.92)

    def test_falls_back_to_accuracy_when_no_oracle_key(self):
        """Without oracle_quality_captured, falls back to accuracy."""
        report = self._fake_report({"accuracy": 0.85})
        assert _extract_quality_score(report, primary_metric_name=None) == pytest.approx(0.85)

    def test_primary_metric_name_takes_precedence(self):
        """Explicit primary_metric_name overrides oracle_quality_captured."""
        report = self._fake_report({"accuracy": 0.75, "oracle_quality_captured": 0.92})
        assert _extract_quality_score(report, primary_metric_name="accuracy") == pytest.approx(0.75)

    def test_extract_quality_score_from_dict_prefers_oracle(self):
        """_extract_quality_score_from_dict mirrors the same preference."""
        metrics = {"oracle_quality_captured": 0.92, "accuracy": 0.85}
        assert _extract_quality_score_from_dict(metrics, primary_metric_name=None) == pytest.approx(0.92)

    def test_extract_quality_score_from_dict_no_oracle(self):
        """_extract_quality_score_from_dict falls back to accuracy when oracle key absent."""
        metrics = {"accuracy": 0.85}
        assert _extract_quality_score_from_dict(metrics, primary_metric_name=None) == pytest.approx(0.85)
