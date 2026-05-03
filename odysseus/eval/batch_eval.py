"""Batch evaluation — concurrent dispatch across multiple prompt candidates.

Evaluates many candidates in a single round concurrently using a shared
``TokenBucketRateLimiter``, then processes results sequentially to avoid
concurrent file writes.

Normal-mode entry point: ``run_batch_eval_impl(run_id, candidates)``.
Recovery mode: call ``run_batch_eval_impl(run_id, candidates=[])`` to resume
after a crash — smart-skips candidates whose ``report.json`` already exists
and re-runs the rest.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from odysseus.agents.pipeline.dispatch import clear_build_dispatched
from odysseus.agents.prompt_builder.search_ops import (
    _load_pending,
    _load_state,
    _save_pending,
    _save_state,
    record_eval_result,
    register_candidate,
    set_loop_phase,
)
from odysseus.eval.backends.registry import BackendRegistry
from odysseus.eval.collector import JsonResultsCollector
from odysseus.eval.dataset import JsonlDatasetManager
from odysseus.eval.metrics import create_default_engine
from odysseus.eval.protocols import RunDependencies
from odysseus.eval.rate_limiter import TokenBucketRateLimiter
from odysseus.mcp.prompt_building_tools import build_pipeline_config
from odysseus.project_dir import get_project_dir
from odysseus.prompts.manager import FilePromptManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class BatchEvalCandidate(BaseModel):
    """A prompt candidate to evaluate as part of a batch."""

    prompt_version: str
    parent_version: str | None = None
    example_ids: list[str] = Field(default_factory=list)
    trajectory_id: int | None = None


class CandidateEvalOutcome(BaseModel):
    """Outcome of evaluating a single candidate."""

    prompt_version: str
    eval_status: Literal["complete", "failed"]
    quality_score: float | None = None
    cost: float | None = None
    error: str | None = None


class BatchEvalResult(BaseModel):
    """Aggregated result of a batch evaluation."""

    succeeded: list[CandidateEvalOutcome]
    failed: list[CandidateEvalOutcome]


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------


def _add_to_active_evals(run_id: str, prompt_version: str, output_dir: Path) -> None:
    """Add a prompt_version to SearchState.active_evals and persist."""
    state = _load_state(run_id, output_dir)
    if prompt_version not in state.active_evals:
        updated = state.model_copy(update={"active_evals": [*state.active_evals, prompt_version]})
        _save_state(run_id, updated, output_dir)


def _remove_from_active_evals(run_id: str, prompt_version: str, output_dir: Path) -> None:
    """Remove a prompt_version from SearchState.active_evals and persist."""
    state = _load_state(run_id, output_dir)
    new_evals = [v for v in state.active_evals if v != prompt_version]
    updated = state.model_copy(update={"active_evals": new_evals})
    _save_state(run_id, updated, output_dir)


def _set_candidate_eval_status(
    run_id: str,
    prompt_version: str,
    status: Literal["pending", "running", "complete", "failed"],
    output_dir: Path,
) -> None:
    """Update eval_status on a specific candidate in pending_candidates.json."""
    pending = _load_pending(run_id, output_dir)
    updated_pending = []
    for c in pending:
        if c.prompt_version == prompt_version:
            updated_pending.append(c.model_copy(update={"eval_status": status}))
        else:
            updated_pending.append(c)
    _save_pending(run_id, updated_pending, output_dir)


# ---------------------------------------------------------------------------
# Single eval helper
# ---------------------------------------------------------------------------


async def _run_single_eval(
    candidate: BatchEvalCandidate,
    run_id: str,
    rate_limiter: TokenBucketRateLimiter,
    output_dir: Path,
) -> object:
    """Run eval for one candidate, returning a RunReport.

    Wires dependencies manually (including the shared rate limiter) and calls
    controller.run() directly.  Exceptions propagate to the caller.
    """
    from odysseus.eval import controller

    project_dir = output_dir.parent if output_dir.name == "outputs" else output_dir

    state = _load_state(run_id, output_dir)

    data_source = str(output_dir / run_id / "analysis" / "dev.jsonl")
    config = build_pipeline_config(
        state=state,
        prompt_version=candidate.prompt_version,
        data_source=data_source,
        run_id=run_id,
        project_dir=project_dir,
    )

    registry = BackendRegistry.from_directory(project_dir / "backends")
    profile = registry.get_profile(config.backend)
    backend_instance = registry.create_backend(config.backend)
    prompts_dir = output_dir / run_id / "prompts"

    deps = RunDependencies(
        backend=backend_instance,
        prompt_manager=FilePromptManager(prompts_dir=prompts_dir),
        dataset_manager=JsonlDatasetManager(),
        metrics_engine=create_default_engine(),
        results_collector=JsonResultsCollector(),
        requests_per_minute=profile.requests_per_minute,
        tokens_per_minute=profile.tokens_per_minute,
        rate_limiter=rate_limiter,
    )

    return await controller.run(config, deps)


# ---------------------------------------------------------------------------
# Score extraction helpers
# ---------------------------------------------------------------------------


def _extract_quality_score(report: object, primary_metric_name: str | None) -> float | None:
    """Extract quality_score from a RunReport using the primary metric."""
    metrics = getattr(report, "metrics", {}) or {}
    if not metrics:
        return None

    if primary_metric_name:
        metric_name = primary_metric_name.split("/")[0]
        if metric_name in metrics:
            return float(metrics[metric_name])

    if "oracle_quality_captured" in metrics:
        return float(metrics["oracle_quality_captured"])
    if "accuracy" in metrics:
        return float(metrics["accuracy"])

    if metrics:
        return float(next(iter(metrics.values())))

    return None


def _extract_cost(report: object) -> float | None:
    """Extract cost_change_with_overhead from a RunReport metrics dict."""
    metrics = getattr(report, "metrics", {}) or {}
    val = metrics.get("cost_change_with_overhead")
    return float(val) if val is not None else None


def _extract_quality_score_from_dict(metrics: dict[str, Any], primary_metric_name: str | None) -> float | None:
    """Extract quality_score from a metrics dict (used when recovering from disk)."""
    if not metrics:
        return None
    if primary_metric_name:
        metric_name = primary_metric_name.split("/")[0]
        if metric_name in metrics:
            return float(metrics[metric_name])
    if "oracle_quality_captured" in metrics:
        return float(metrics["oracle_quality_captured"])
    if "accuracy" in metrics:
        return float(metrics["accuracy"])
    if metrics:
        return float(next(iter(metrics.values())))
    return None


def _try_load_existing_report(run_id: str, prompt_version: str, output_dir: Path) -> dict[str, Any] | None:
    """Return parsed report.json if it exists and is valid for this candidate.

    A valid report has a non-empty ``metrics`` dict and ``summary.succeeded > 0``.
    Returns ``None`` when the report is missing, incomplete, or corrupt — which
    triggers a re-run for that candidate.
    """
    report_path = output_dir / run_id / "eval" / prompt_version / "report.json"
    if not report_path.is_file():
        return None
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        metrics = data.get("metrics")
        summary = data.get("summary", {})
        if not metrics or summary.get("succeeded", 0) == 0:
            return None
        return data
    except (json.JSONDecodeError, ValueError, TypeError, KeyError):
        return None


# ---------------------------------------------------------------------------
# Drain helper (shared by normal and recovery branches)
# ---------------------------------------------------------------------------


async def _finalize_drain(run_id: str, output_dir: Path) -> None:
    """If active_evals is now empty, clear build_dispatched and flip to review."""
    state = _load_state(run_id, output_dir)
    if not state.active_evals:
        clear_build_dispatched(run_id, output_dir)
        set_loop_phase(run_id, "review", output_dir=output_dir)


# ---------------------------------------------------------------------------
# Recovery branch
# ---------------------------------------------------------------------------


async def _run_recovery(run_id: str, output_dir: Path) -> BatchEvalResult:
    """Recovery mode: resume an interrupted batch eval.

    Reads ``pending_candidates.json``, filters to candidates with
    ``eval_status ∈ {"pending", "running"}`` that are in ``state.active_evals``,
    smart-skips any whose ``report.json`` already exists on disk (loading the
    score from disk and marking complete), and re-runs the rest.

    When ``active_evals`` drains, calls ``_finalize_drain`` to clear the
    build-dispatched marker and flip ``loop_phase`` to ``"review"``.
    """
    state = _load_state(run_id, output_dir)
    pending = _load_pending(run_id, output_dir)

    # Filter to candidates that are still in-flight and tracked by active_evals
    in_flight = [
        c for c in pending if c.eval_status in ("pending", "running") and c.prompt_version in state.active_evals
    ]

    if not in_flight:
        if state.active_evals:
            logger.warning(
                "Recovery: active_evals=%r but no matching pending candidates; clearing.",
                state.active_evals,
            )
            for pv in list(state.active_evals):
                _remove_from_active_evals(run_id, pv, output_dir)
            await _finalize_drain(run_id, output_dir)
        return BatchEvalResult(succeeded=[], failed=[])

    # ------------------------------------------------------------------ #
    # Triage: smart-skip vs re-run
    # ------------------------------------------------------------------ #
    already_done: list[tuple[Any, dict[str, Any]]] = []  # (Candidate, report_data)
    still_need_eval: list[Any] = []  # list[Candidate]

    for c in in_flight:
        report_data = _try_load_existing_report(run_id, c.prompt_version, output_dir)
        if report_data is not None:
            already_done.append((c, report_data))
        else:
            still_need_eval.append(c)

    # ------------------------------------------------------------------ #
    # Process smart-skip results (sequential — no concurrent file writes)
    # ------------------------------------------------------------------ #
    primary_metric = state.primary_metric_name
    pre_succeeded: list[CandidateEvalOutcome] = []

    for c, rdata in already_done:
        metrics = rdata.get("metrics", {})
        quality_score = _extract_quality_score_from_dict(metrics, primary_metric)
        cost_metric: float | None = metrics.get("cost_change_with_overhead")

        record_eval_result(
            run_id=run_id,
            prompt_version=c.prompt_version,
            quality_score=quality_score or 0.0,
            cost=cost_metric or 0.0,
            output_dir=output_dir,
        )
        _remove_from_active_evals(run_id, c.prompt_version, output_dir)
        pre_succeeded.append(
            CandidateEvalOutcome(
                prompt_version=c.prompt_version,
                eval_status="complete",
                quality_score=quality_score,
                cost=cost_metric,
                error=None,
            )
        )

    if not still_need_eval:
        # All candidates had valid on-disk reports — nothing left to run
        await _finalize_drain(run_id, output_dir)
        return BatchEvalResult(succeeded=pre_succeeded, failed=[])

    # ------------------------------------------------------------------ #
    # Re-run remaining candidates
    # ------------------------------------------------------------------ #
    # Convert Candidate objects back to BatchEvalCandidate for _run_single_eval
    eval_candidates = [
        BatchEvalCandidate(
            prompt_version=c.prompt_version,
            parent_version=c.parent_version,
            example_ids=c.example_ids or [],
        )
        for c in still_need_eval
    ]

    # Build a shared rate limiter
    project_dir = output_dir.parent if output_dir.name == "outputs" else output_dir
    try:
        registry = BackendRegistry.from_directory(project_dir / "backends")
        rec_state = _load_state(run_id, output_dir)
        profile = registry.get_profile(rec_state.backend)
        shared_limiter = TokenBucketRateLimiter(
            requests_per_minute=profile.requests_per_minute,
            tokens_per_minute=profile.tokens_per_minute,
        )
    except Exception:
        shared_limiter = TokenBucketRateLimiter(
            requests_per_minute=60,
            tokens_per_minute=100_000,
        )

    # Concurrent dispatch
    raw_results = await asyncio.gather(
        *[_run_single_eval(ec, run_id, shared_limiter, output_dir) for ec in eval_candidates],
        return_exceptions=True,
    )

    # Sequential result processing
    rec_state = _load_state(run_id, output_dir)
    rec_primary = rec_state.primary_metric_name

    succeeded: list[CandidateEvalOutcome] = list(pre_succeeded)
    failed: list[CandidateEvalOutcome] = []

    for ec, raw in zip(eval_candidates, raw_results, strict=True):
        if isinstance(raw, BaseException):
            error_msg = f"{type(raw).__name__}: {raw}"
            logger.warning("Recovery eval failed for %s: %s", ec.prompt_version, error_msg)
            _set_candidate_eval_status(run_id, ec.prompt_version, "failed", output_dir)
            _remove_from_active_evals(run_id, ec.prompt_version, output_dir)
            failed.append(
                CandidateEvalOutcome(
                    prompt_version=ec.prompt_version,
                    eval_status="failed",
                    quality_score=None,
                    cost=None,
                    error=error_msg,
                )
            )
        else:
            report = raw
            quality_score = _extract_quality_score(report, rec_primary)
            cost_metric_r: float | None = _extract_cost(report)

            summary = getattr(report, "summary", None)
            succeeded_count = getattr(summary, "succeeded", None) if summary is not None else None
            if succeeded_count is not None and succeeded_count == 0:
                logger.warning(
                    "Recovery candidate %s had 0 successful evals — marking as failed",
                    ec.prompt_version,
                )
                _set_candidate_eval_status(run_id, ec.prompt_version, "failed", output_dir)
                _remove_from_active_evals(run_id, ec.prompt_version, output_dir)
                failed.append(
                    CandidateEvalOutcome(
                        prompt_version=ec.prompt_version,
                        eval_status="failed",
                        quality_score=quality_score,
                        cost=cost_metric_r,
                        error="All eval examples failed (0 succeeded)",
                    )
                )
            else:
                record_eval_result(
                    run_id=run_id,
                    prompt_version=ec.prompt_version,
                    quality_score=quality_score or 0.0,
                    cost=cost_metric_r or 0.0,
                    output_dir=output_dir,
                )
                _remove_from_active_evals(run_id, ec.prompt_version, output_dir)
                succeeded.append(
                    CandidateEvalOutcome(
                        prompt_version=ec.prompt_version,
                        eval_status="complete",
                        quality_score=quality_score,
                        cost=cost_metric_r,
                        error=None,
                    )
                )

    await _finalize_drain(run_id, output_dir)
    return BatchEvalResult(succeeded=succeeded, failed=failed)


# ---------------------------------------------------------------------------
# Core public function
# ---------------------------------------------------------------------------


async def run_batch_eval_impl(
    run_id: str,
    candidates: list[BatchEvalCandidate],
    output_dir: str | Path = "outputs",
) -> BatchEvalResult:
    """Evaluate multiple prompt candidates concurrently.

    Normal mode (``candidates`` non-empty):

    1. Register each candidate (``eval_status="pending"``) and add to
       ``active_evals``.
    2. Flip ``eval_status`` to ``"running"`` immediately before dispatch.
    3. Create a single shared ``TokenBucketRateLimiter``.
    4. Run all evals concurrently via ``asyncio.gather``.
    5. Process results sequentially (to avoid concurrent file writes):
       successes call ``record_eval_result``; failures call
       ``_set_candidate_eval_status(..., "failed")``.  Both paths then call
       ``_remove_from_active_evals``.
    6. When ``active_evals`` drains: ``clear_build_dispatched`` then
       ``set_loop_phase("review")``.

    Recovery mode (``candidates`` empty):

    Reads ``pending_candidates.json``, filters to ``eval_status ∈
    {"pending","running"}`` candidates whose ``prompt_version`` is in
    ``state.active_evals``, smart-skips any with a valid on-disk
    ``report.json`` (loads score from disk), and re-runs the rest.
    Drains ``active_evals`` and flips to review when done.
    """
    if isinstance(output_dir, str):
        eff_output_dir = Path(output_dir)
        if not eff_output_dir.is_absolute():
            eff_output_dir = get_project_dir() / output_dir
    else:
        eff_output_dir = output_dir

    if not candidates:
        return await _run_recovery(run_id, eff_output_dir)

    # ---------------------------------------------------------------------- #
    # Step 1: Register all candidates + add to active_evals
    # ---------------------------------------------------------------------- #
    for c in candidates:
        register_candidate(
            run_id=run_id,
            prompt_version=c.prompt_version,
            parent_version=c.parent_version,
            example_ids=c.example_ids,
            output_dir=eff_output_dir,
            eval_status="pending",
            trajectory_id=c.trajectory_id,
        )
        _add_to_active_evals(run_id, c.prompt_version, eff_output_dir)

    # ---------------------------------------------------------------------- #
    # Step 2: Flip eval_status to "running" before dispatch
    # ---------------------------------------------------------------------- #
    for c in candidates:
        _set_candidate_eval_status(run_id, c.prompt_version, "running", eff_output_dir)

    # ---------------------------------------------------------------------- #
    # Step 3: Create ONE shared rate limiter
    # ---------------------------------------------------------------------- #
    state = _load_state(run_id, eff_output_dir)
    project_dir = eff_output_dir.parent if eff_output_dir.name == "outputs" else eff_output_dir
    try:
        registry = BackendRegistry.from_directory(project_dir / "backends")
        profile = registry.get_profile(state.backend)
        shared_limiter = TokenBucketRateLimiter(
            requests_per_minute=profile.requests_per_minute,
            tokens_per_minute=profile.tokens_per_minute,
        )
    except Exception:
        shared_limiter = TokenBucketRateLimiter(
            requests_per_minute=60,
            tokens_per_minute=100_000,
        )

    # ---------------------------------------------------------------------- #
    # Step 4: Concurrent dispatch
    # ---------------------------------------------------------------------- #
    raw_results = await asyncio.gather(
        *[_run_single_eval(c, run_id, shared_limiter, eff_output_dir) for c in candidates],
        return_exceptions=True,
    )

    # ---------------------------------------------------------------------- #
    # Step 5: Sequential result processing (no concurrent file writes)
    # ---------------------------------------------------------------------- #
    succeeded: list[CandidateEvalOutcome] = []
    failed: list[CandidateEvalOutcome] = []

    state = _load_state(run_id, eff_output_dir)
    primary_metric = state.primary_metric_name

    for c, raw in zip(candidates, raw_results, strict=True):
        if isinstance(raw, BaseException):
            error_msg = f"{type(raw).__name__}: {raw}"
            logger.warning("Eval failed for %s: %s", c.prompt_version, error_msg)
            _set_candidate_eval_status(run_id, c.prompt_version, "failed", eff_output_dir)
            _remove_from_active_evals(run_id, c.prompt_version, eff_output_dir)
            failed.append(
                CandidateEvalOutcome(
                    prompt_version=c.prompt_version,
                    eval_status="failed",
                    quality_score=None,
                    cost=None,
                    error=error_msg,
                )
            )
        else:
            report = raw
            quality_score = _extract_quality_score(report, primary_metric)
            cost_metric = _extract_cost(report)

            # Guard: treat 0-success runs as failed
            summary = getattr(report, "summary", None)
            succeeded_count = getattr(summary, "succeeded", None) if summary is not None else None
            if succeeded_count is not None and succeeded_count == 0:
                logger.warning(
                    "Candidate %s had 0 successful evals — marking as failed",
                    c.prompt_version,
                )
                _set_candidate_eval_status(run_id, c.prompt_version, "failed", eff_output_dir)
                _remove_from_active_evals(run_id, c.prompt_version, eff_output_dir)
                failed.append(
                    CandidateEvalOutcome(
                        prompt_version=c.prompt_version,
                        eval_status="failed",
                        quality_score=quality_score,
                        cost=cost_metric,
                        error="All eval examples failed (0 succeeded)",
                    )
                )
            else:
                record_eval_result(
                    run_id=run_id,
                    prompt_version=c.prompt_version,
                    quality_score=quality_score or 0.0,
                    cost=cost_metric or 0.0,
                    output_dir=eff_output_dir,
                )
                _remove_from_active_evals(run_id, c.prompt_version, eff_output_dir)
                succeeded.append(
                    CandidateEvalOutcome(
                        prompt_version=c.prompt_version,
                        eval_status="complete",
                        quality_score=quality_score,
                        cost=cost_metric,
                        error=None,
                    )
                )

    # ---------------------------------------------------------------------- #
    # Step 6: Auto-transition to review when active_evals drains
    # ---------------------------------------------------------------------- #
    await _finalize_drain(run_id, eff_output_dir)

    return BatchEvalResult(succeeded=succeeded, failed=failed)
