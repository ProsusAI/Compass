"""Business logic for the initiate_rerun MCP tool.

Separated from the MCP decorator layer so it can be tested without an async context.
"""

from __future__ import annotations

import json
from pathlib import Path

from odysseus.agents.prompt_builder.search import Candidate, select_best


def initiate_rerun_logic(
    outputs_dir: Path,
    run_id: str,
    source_prompt_version: str | None = None,
) -> dict:
    """Validate Stage 4 is complete, select the best prompt, and write rerun_config.json.

    Args:
        outputs_dir: Path to the outputs directory (project_dir/outputs).
        run_id: Pipeline run identifier.
        source_prompt_version: Override the source prompt version. If None, the best
            candidate on the Pareto front is selected automatically.

    Returns:
        Dict with keys: source_prompt_version, original_backend, message.

    Raises:
        ValueError: If Stage 4 is not complete (search_state.json missing or not converged).
        FileNotFoundError: If the run directory does not exist.
    """
    run_dir = outputs_dir / run_id
    search_state_path = run_dir / "search" / "search_state.json"

    if not search_state_path.is_file():
        raise ValueError(
            f"Stage 4 is not complete for run '{run_id}': "
            f"search_state.json not found at {search_state_path}"
        )

    try:
        data = json.loads(search_state_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"Could not read search_state.json for run '{run_id}': {e}") from e

    if not data.get("converged"):
        raise ValueError(
            f"Stage 4 is not complete for run '{run_id}': "
            f"search_state.json exists but converged is not true"
        )

    original_backend: str = data.get("backend", "unknown")

    # Select source prompt version
    if source_prompt_version is None:
        pareto_front_data: list[dict] = data.get("pareto_front", [])
        if not pareto_front_data:
            raise ValueError(
                f"No candidates on Pareto front for run '{run_id}'. "
                f"Cannot select best prompt version automatically."
            )
        front = [Candidate.model_validate(c) for c in pareto_front_data]
        source_prompt_version = select_best(front)

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
