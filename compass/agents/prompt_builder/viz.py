# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Live visualization for the optimization loop.

Regenerates the interactive search tree HTML on each state mutation.
The HTML is self-contained (no external chart images needed).

Public API
----------
write_viz(run_id, output_dir=None) -> Path
_try_write_viz(run_id, output_dir) -> None
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def write_viz(run_id: str, output_dir: Path | None = None) -> Path:
    """Regenerate the interactive search tree visualization.

    Reads search state, archive, pending candidates, and round reports,
    then renders the full interactive HTML (tree + scatter plot).

    Returns:
        Path to the written HTML file.
    """
    from compass.agents.prompt_builder.search_tree import collect_data, render_html
    from compass.project_dir import get_project_dir

    if output_dir is None:
        output_dir = get_project_dir() / "outputs"

    search_dir = output_dir / run_id / "search"
    run_dir = output_dir / run_id
    data = collect_data(search_dir, run_dir=run_dir)
    html = render_html(data, run_id)

    viz_path = search_dir / "viz.html"
    viz_path.parent.mkdir(parents=True, exist_ok=True)
    viz_path.write_text(html, encoding="utf-8")

    logger.debug("viz: wrote %s", viz_path)
    return viz_path


def _try_write_viz(run_id: str, output_dir: Path) -> None:
    """Best-effort wrapper around :func:`write_viz` — never raises.

    Viz failure must never interrupt the optimization loop.
    """
    try:
        write_viz(run_id, output_dir)
    except Exception:
        logger.warning("viz: failed to write visualization", exc_info=True)
