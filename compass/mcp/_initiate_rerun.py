# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Business logic for the initiate_rerun MCP tool.

Separated from the MCP decorator layer so it can be tested without an async context.
"""

from __future__ import annotations

import json
from pathlib import Path

from compass.agents.prompt_builder.search import Candidate


def initiate_rerun_logic(
    outputs_dir: Path,
    run_id: str,
    source_prompt_version: str | None = None,
) -> dict:
    """Validate Stage 4 is complete and write rerun_config.json.

    This function supports a two-call flow:

    1. First call (source_prompt_version=None): returns
       ``{"action_required": "version_selection", "candidates": [...], "message": ...}``
       so the caller can present the elite set to the user and collect their choice.
    2. Second call (source_prompt_version=<chosen version>): renames
       search_state.json and writes rerun_config.json, then returns
       ``{"source_prompt_version": ..., "original_backend": ..., "message": ...}``.

    Args:
        outputs_dir: Path to the outputs directory (project_dir/outputs).
        run_id: Pipeline run identifier.
        source_prompt_version: The prompt version to use for the rerun.  When
            None the function returns the candidate list for user selection instead
            of executing the rerun.

    Returns:
        On version_selection: dict with action_required, candidates, and message.
        On rerun execution: dict with source_prompt_version, original_backend, and message.

    Raises:
        ValueError: If Stage 4 is not complete (search_state.json missing or not converged).
        FileNotFoundError: If the run directory does not exist.
    """
    run_dir = outputs_dir / run_id
    search_state_path = run_dir / "search" / "search_state.json"

    if not search_state_path.is_file():
        raise ValueError(
            f"Stage 4 is not complete for run '{run_id}': search_state.json not found at {search_state_path}"
        )

    try:
        data = json.loads(search_state_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"Could not read search_state.json for run '{run_id}': {e}") from e

    if not data.get("converged"):
        raise ValueError(
            f"Stage 4 is not complete for run '{run_id}': search_state.json exists but converged is not true"
        )

    original_backend: str = data.get("backend", "unknown")

    # Return candidate list for user selection if no version provided
    if source_prompt_version is None:
        elite_set_data: list[dict] = data.get("elite_set", data.get("pareto_front", []))
        if not elite_set_data:
            raise ValueError(
                f"No candidates in elite set for run '{run_id}'. Cannot list candidates for version selection."
            )
        front = [Candidate.model_validate(c) for c in elite_set_data]
        candidate_dicts = [
            {
                "prompt_version": c.prompt_version,
                "quality_score": c.quality_score,
                "cost": c.cost,
                "round_introduced": c.round_introduced,
            }
            for c in front
        ]
        candidates = sorted(
            candidate_dicts,
            key=lambda c: (-float(c["quality_score"]), float(c["cost"])),
        )
        return {
            "action_required": "version_selection",
            "candidates": candidates,
            "message": (
                "Choose a source_prompt_version from the candidates above, "
                "then call initiate_rerun again with your choice."
            ),
        }

    # Rename search_state.json to search_state_original.json so _check_stage_4
    # sees Stage 4 as incomplete (required for rerun to proceed through Stage 4)
    original_path = run_dir / "search" / "search_state_original.json"
    search_state_path.rename(original_path)

    # Write rerun_config.json
    rerun_config = {
        "mode": "rerun",
        "source_prompt_version": source_prompt_version,
        "original_backend": original_backend,
        "new_backend": None,
    }
    (run_dir / "rerun_config.json").write_text(json.dumps(rerun_config, indent=2))

    return {
        "source_prompt_version": source_prompt_version,
        "original_backend": original_backend,
        "message": (
            f"Rerun initiated for run '{run_id}'. "
            f"Source prompt: {source_prompt_version}. "
            f"Original backend: {original_backend}. "
            f"Next step: proceed to Stage 3 to configure the new backend. "
            f"Once Stage 3 is complete, call get_pipeline_status to continue."
        ),
    }
