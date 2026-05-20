"""Shared dispatch-marker and fanout primitives for Stage 4 sub-agent coordination.

Note: ``build_recovering`` is exempt from the "fresh dispatch" check because the
build-dispatch marker may already be present from the prior aborted attempt.  The
recovery sub-agent runs with the marker held and clears it on completion (via the
auto-transition in ``run_batch_eval_impl``).  Do not call ``record_build_dispatched``
again in the recovery path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from compass.agents.pipeline import paths
from compass.project_dir import get_project_dir


def record_build_dispatched(run_id: str, *, round: int, output_dir: Path | None = None) -> None:
    """Mark that the Prompt Builder sub-agent has been dispatched for this round.

    ``complete_stage(prompt_building)`` will refuse to advance while this marker exists.
    """
    path = paths.build_marker_path(run_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"round": round}), encoding="utf-8")


def clear_build_dispatched(run_id: str, output_dir: Path | None = None) -> None:
    """Remove the build-dispatch marker if it exists."""
    path = paths.build_marker_path(run_id, output_dir)
    if path.exists():
        path.unlink()


def is_build_dispatched(run_id: str, output_dir: Path | None = None) -> bool:
    """Return True iff the build-dispatch marker file exists on disk."""
    return paths.build_marker_path(run_id, output_dir).exists()


def record_review_dispatched(run_id: str, *, round: int, output_dir: Path | None = None) -> None:
    """Mark that the Review Agent sub-agent has been dispatched for this round."""
    path = paths.review_marker_path(run_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"round": round}), encoding="utf-8")


def clear_review_dispatched(run_id: str, output_dir: Path | None = None) -> None:
    """Remove the review-dispatch marker if it exists."""
    path = paths.review_marker_path(run_id, output_dir)
    if path.exists():
        path.unlink()


def is_review_dispatched(run_id: str, output_dir: Path | None = None) -> bool:
    """Return True iff the review-dispatch marker file exists on disk."""
    return paths.review_marker_path(run_id, output_dir).exists()


def is_build_recovering(run_id: str, output_dir: str = "outputs") -> bool:
    """Return True iff SearchState.active_evals is non-empty.

    Used by the orchestrator to detect that a prior build attempt was interrupted
    mid-eval and the recovery sub-agent should be dispatched.
    """
    base = Path(output_dir)
    if not base.is_absolute():
        base = get_project_dir() / output_dir
    state_path = base / run_id / "search" / "search_state.json"
    if not state_path.is_file():
        return False
    try:
        data = json.loads(state_path.read_text())
        return bool(data.get("active_evals", []))
    except (json.JSONDecodeError, ValueError, TypeError):
        return False


@dataclass
class DispatchFanout:
    """Status of a fan-out dispatch (Review or Build).

    For the single-sub-agent-per-round case (hill-climb), this collapses to a
    degenerate one-slot fanout.  The fanout helper shared with the orchestrator
    asks: 'has the dispatch completed?'.
    """

    expected: int = 1
    completed: list[int] = field(default_factory=list)
    in_flight: list[int] = field(default_factory=list)
    not_dispatched: list[int] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """Return True iff all expected sub-agents have completed."""
        return len(self.completed) >= self.expected

    @property
    def missing(self) -> list[int]:
        """Return slot ids that have not yet completed (in-flight + not dispatched)."""
        return self.in_flight + self.not_dispatched


def review_fanout_status(
    run_id: str,
    *,
    algorithm: str = "hill_climb",
    expected: int = 1,
    output_dir: Path | None = None,
) -> DispatchFanout:
    """Read review-dispatch state from disk and report fanout completion.

    For the single-slot case (hill-climb), ``expected=1`` and
    the fanout is complete iff ``child_variants.json`` exists.  For EMOSA, the
    K-way path delegates to :func:`trajectory_fanout_missing` and returns a
    multi-slot :class:`DispatchFanout`.

    Args:
        run_id: Pipeline run identifier.
        algorithm: Search algorithm discriminator.  When ``"emosa"``, uses the
            per-trajectory fanout path; otherwise uses single-slot semantics.
        expected: Number of sub-agents expected in this fanout.  Ignored for
            EMOSA (derived from ``trajectory_fanout_missing``); must be 1 for
            non-EMOSA algorithms.
        output_dir: Root output directory override (default: project outputs/).

    Returns:
        :class:`DispatchFanout` describing which slots are complete / in-flight /
        not dispatched.
    """
    # EMOSA: K-way per-trajectory fanout
    if algorithm == "emosa":
        from odysseus.agents.review import ops as _review_ops

        trajectory_fanout_missing = _review_ops.trajectory_fanout_missing  # pyright: ignore[reportAttributeAccessIssue]  # TODO: drop after project-wide dispatch fanout cleanup splits EMOSA-only path from non-EMOSA leaves

        fanout = trajectory_fanout_missing(run_id, output_dir=output_dir)
        if fanout is not None:
            return DispatchFanout(
                expected=fanout.num_trajectories,
                completed=fanout.completed,
                in_flight=fanout.in_flight,
                not_dispatched=fanout.not_dispatched,
            )
        # No algorithm_state yet — fall through to single-slot semantics (pre-calibration).

    # Single-slot path (hill-climb, or EMOSA pre-calibration)
    search_dir = paths.search_dir(run_id, output_dir)
    child_variants_path = search_dir / "child_variants.json"
    if child_variants_path.exists():
        return DispatchFanout(expected=1, completed=[0])
    if is_review_dispatched(run_id, output_dir):
        return DispatchFanout(expected=1, in_flight=[0])
    return DispatchFanout(expected=1, not_dispatched=[0])
