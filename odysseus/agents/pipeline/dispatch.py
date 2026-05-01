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

from odysseus.project_dir import get_project_dir


def _search_dir(run_id: str, output_dir: Path | None = None) -> Path:
    base = output_dir or (get_project_dir() / "outputs")
    return base / run_id / "search"


def _build_marker_path(run_id: str, output_dir: Path | None = None) -> Path:
    return _search_dir(run_id, output_dir) / "build_dispatched.json"


def _review_marker_path(run_id: str, output_dir: Path | None = None) -> Path:
    return _search_dir(run_id, output_dir) / "review_dispatched.json"


def record_build_dispatched(run_id: str, *, round: int, output_dir: Path | None = None) -> None:
    """Mark that the Prompt Builder sub-agent has been dispatched for this round.

    ``complete_stage(prompt_building)`` will refuse to advance while this marker exists.
    """
    path = _build_marker_path(run_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"round": round}), encoding="utf-8")


def clear_build_dispatched(run_id: str, output_dir: Path | None = None) -> None:
    """Remove the build-dispatch marker if it exists."""
    path = _build_marker_path(run_id, output_dir)
    if path.exists():
        path.unlink()


def is_build_dispatched(run_id: str, output_dir: Path | None = None) -> bool:
    """Return True iff the build-dispatch marker file exists on disk."""
    return _build_marker_path(run_id, output_dir).exists()


def record_review_dispatched(run_id: str, *, round: int, output_dir: Path | None = None) -> None:
    """Mark that the Review Agent sub-agent has been dispatched for this round."""
    path = _review_marker_path(run_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"round": round}), encoding="utf-8")


def clear_review_dispatched(run_id: str, output_dir: Path | None = None) -> None:
    """Remove the review-dispatch marker if it exists."""
    path = _review_marker_path(run_id, output_dir)
    if path.exists():
        path.unlink()


def is_review_dispatched(run_id: str, output_dir: Path | None = None) -> bool:
    """Return True iff the review-dispatch marker file exists on disk."""
    return _review_marker_path(run_id, output_dir).exists()


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

    For strategies with a single sub-agent per round (hill-climb, beam, sms-emoa),
    this collapses to a degenerate one-slot fanout.  EMOSA uses a multi-slot
    variant (one per trajectory).  The fanout helper shared with the orchestrator
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

    For the single-slot case (hill-climb / beam / sms-emoa), ``expected=1`` and
    the fanout is complete iff ``child_variants.json`` exists.  EMOSA overrides
    this on its branch to read per-trajectory marker files.

    Args:
        run_id: Pipeline run identifier.
        algorithm: Branch algorithm discriminator.  Must be ``"hill_climb"`` on
            this branch; accepted explicitly so callers can pass
            ``algorithm=_BRANCH_ALGORITHM`` without defaulting silently.
        expected: Number of sub-agents expected in this fanout.  Must be 1 on
            this branch; EMOSA passes K (number of trajectories).
        output_dir: Root output directory override (default: project outputs/).

    Returns:
        :class:`DispatchFanout` describing which slots are complete / in-flight /
        not dispatched.

    Raises:
        NotImplementedError: When ``expected > 1`` — multi-slot fanout requires
            a strategy override (implemented on the EMOSA branch).
    """
    del algorithm  # accepted for interface parity; always hill_climb on this branch
    search_dir = _search_dir(run_id, output_dir)
    child_variants_path = search_dir / "child_variants.json"
    if expected == 1:
        if child_variants_path.exists():
            return DispatchFanout(expected=1, completed=[0])
        if is_review_dispatched(run_id, output_dir):
            return DispatchFanout(expected=1, in_flight=[0])
        return DispatchFanout(expected=1, not_dispatched=[0])
    # Multi-slot fanout is a strategy override (EMOSA replaces this function).
    raise NotImplementedError(f"review_fanout_status: expected={expected} fanout requires a strategy override")
