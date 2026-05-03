"""EMOSA per-round diagnostic trace.

Off by default. To enable for a run, set the env var:

    ODYSSEUS_EMOSA_TRACE=1

OR flip ``EMOSA_TRACE_ENABLED`` to ``True`` below.

When enabled, a per-round trace is written to
``<output_dir>/<run_id>/search/emosa_trace.log`` (one file per run).
The trace covers round boundaries, per-trajectory Metropolis decisions,
and EMOSA neighborhood-replacement events. It does NOT touch
``search_state.json`` or normal log handlers — strictly an opt-in
diagnostic file.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

EMOSA_TRACE_ENABLED: bool = os.environ.get("ODYSSEUS_EMOSA_TRACE", "0") == "1"
"""Toggle. Set ODYSSEUS_EMOSA_TRACE=1 in the environment, or flip this
constant to True locally, to enable the trace log. Off by default."""

_LOGGER_NAME = "odysseus.emosa.trace"
_attached_runs: set[str] = set()


def get_trace_logger(run_id: str, search_dir: Path) -> logging.Logger | None:
    """Return the trace logger for *run_id*, or ``None`` if disabled.

    Lazily attaches a single ``FileHandler`` per run that writes to
    ``<search_dir>/emosa_trace.log``. Subsequent calls reuse it.
    Sets ``propagate = False`` so trace lines never leak into the root
    logger / MCP stdout.
    """
    if not EMOSA_TRACE_ENABLED:
        return None
    logger = logging.getLogger(_LOGGER_NAME)
    if run_id not in _attached_runs:
        search_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(search_dir / "emosa_trace.log", mode="a", encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        _attached_runs.add(run_id)
    return logger


def record_metropolis_decision(
    search_dir: Path,
    *,
    round: int,
    trajectory_id: int,
    parent_version: str | None,
    child_version: str,
    parent_energy: float | None,
    child_energy: float,
    delta_e: float | None,
    temperature: float,
    p_accept: float | None,
    accepted: bool,
) -> None:
    """Append one JSONL row to ``<search_dir>/emosa_trace.jsonl``.

    No-op when ``EMOSA_TRACE_ENABLED`` is ``False``.
    """
    if not EMOSA_TRACE_ENABLED:
        return
    search_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "round": round,
        "trajectory_id": trajectory_id,
        "parent_version": parent_version,
        "child_version": child_version,
        "parent_energy": parent_energy,
        "child_energy": child_energy,
        "delta_e": delta_e,
        "temperature": temperature,
        "p_accept": p_accept,
        "accepted": accepted,
    }
    with (search_dir / "emosa_trace.jsonl").open("a", encoding="utf-8", buffering=1) as fh:
        fh.write(json.dumps(record) + "\n")
