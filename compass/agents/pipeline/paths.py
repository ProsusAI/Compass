"""Centralised Stage-4 artifact path construction.

Pure path arithmetic — no filesystem access. Exists to dissolve the
status ↔ dispatch circular-import workaround and deduplicate the
identical `_search_dir`/marker-path helpers that lived in
status.py, dispatch.py, review/ops.py, and prompt_builder/search_ops.py.
"""

from __future__ import annotations

from pathlib import Path

from compass.project_dir import get_project_dir


def _resolve_output_dir(output_dir: Path | None) -> Path:
    return output_dir if output_dir is not None else get_project_dir() / "outputs"


def search_dir(run_id: str, output_dir: Path | None = None) -> Path:
    """Return `<output_dir>/<run_id>/search`."""
    return _resolve_output_dir(output_dir) / run_id / "search"


def search_state_path(run_id: str, output_dir: Path | None = None) -> Path:
    """Return `<output_dir>/<run_id>/search/search_state.json`."""
    return search_dir(run_id, output_dir) / "search_state.json"


def build_marker_path(run_id: str, output_dir: Path | None = None) -> Path:
    """Return the build-dispatch marker path."""
    return search_dir(run_id, output_dir) / "build_dispatched.json"


def review_marker_path(run_id: str, output_dir: Path | None = None) -> Path:
    """Return the review-dispatch marker path."""
    return search_dir(run_id, output_dir) / "review_dispatched.json"


def is_build_dispatched(run_id: str, output_dir: Path | None = None) -> bool:
    """Return True iff the build-dispatch marker file exists on disk."""
    return build_marker_path(run_id, output_dir).exists()
