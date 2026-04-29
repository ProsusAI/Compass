"""Smoke test: _try_write_viz is called and produces viz.html at state-mutation call sites."""

from __future__ import annotations

import json
from pathlib import Path

from odysseus.agents.prompt_builder.search_ops import init_search_state, register_candidate


def test_viz_html_written_after_init_and_register(tmp_path: Path) -> None:
    """init_search_state + register_candidate each call _try_write_viz; viz.html exists after both."""
    run_id = "viz-smoke-test"

    init_search_state("anthropic", run_id=run_id, output_dir=tmp_path)

    # viz.html is written best-effort; it requires candidate_archive.json to exist.
    # Seed the archive so collect_data can succeed.
    search_dir = tmp_path / run_id / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    (search_dir / "candidate_archive.json").write_text(json.dumps([]), encoding="utf-8")

    register_candidate(run_id, "v1", output_dir=tmp_path)

    # After register: viz.html should exist and be non-empty
    viz_path = search_dir / "viz.html"
    assert viz_path.exists(), "viz.html not created by register_candidate"
    assert viz_path.stat().st_size > 0, "viz.html is empty after register_candidate"
