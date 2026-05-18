"""Stage-4 (Refinement Loop) phase detection and next-action helpers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from odysseus.agents.pipeline import paths, tool_registry
from odysseus.agents.pipeline.instructions import (
    STAGE_4_BUILD_INSTRUCTION,
    STAGE_4_COLD_START_INSTRUCTION,
    STAGE_4_RERUN_INSTRUCTION,
    STAGE_4_REVIEW_INSTRUCTION,
)
from odysseus.eval.backends.profile import BackendProfile
from odysseus.project_dir import get_project_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stage-4 phase constants
# ---------------------------------------------------------------------------

_VALID_LOOP_PHASES = {"build", "review"}

_STAGE_4_BUILD_ACTION_RECOVER: str = (
    "Stage 4 — build-recovering phase: active_evals is non-empty from a prior interrupted run. "
    "Spawn the Prompt Builder to resume in-flight evaluations via run_batch_eval(candidates=[]). "
    "REQUIRED: activate prompt 'odysseus_prompt_builder' before calling any build tools."
)
_STAGE_4_BUILD_ACTION_FIRST: str = (
    "Stage 4 — build phase: spawn the Prompt Builder to compile the "
    "initial routing prompt (v1) using seed examples from the Review Agent. "
    "REQUIRED: activate prompt 'odysseus_prompt_builder' before calling any build tools."
)
_STAGE_4_BUILD_ACTION_STEADY: str = (
    "Stage 4 — build phase: spawn the Prompt Builder to generate "
    "prompt variants and evaluate them. "
    "REQUIRED: activate prompt 'odysseus_prompt_builder' before calling any build tools."
)

# Static (action_text, tools, prompts, subagent_instruction) per non-build phase.
_STAGE_4_PHASE_CONFIG: dict[str, tuple[str, list[str], list[str], str]] = {
    "cold_review": (
        "Stage 4 — cold-start: spawn the Review Agent to seed the search "
        "with diverse initial hypotheses. "
        "REQUIRED: activate prompt 'odysseus_review_agent_cold_start' before calling any review tools.",
        tool_registry.COLD_REVIEW_TOOLS,
        ["odysseus_review_agent_cold_start"],
        STAGE_4_COLD_START_INSTRUCTION,
    ),
    "review": (
        "Stage 4 — review phase: spawn the Review Agent to analyse "
        "eval results and emit edit directives. "
        "REQUIRED: activate prompt 'odysseus_review_agent_iterative' before calling any review tools.",
        tool_registry.REVIEW_TOOLS,
        ["odysseus_review_agent_iterative"],
        STAGE_4_REVIEW_INSTRUCTION,
    ),
}


# ---------------------------------------------------------------------------
# Phase detection
# ---------------------------------------------------------------------------


def _detect_stage_4_phase(
    run_dir: Path,
    rerun_config: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """Detect which phase Stage 4 is in.

    Returns ``(phase, flags)`` where phase ∈ {``"rerun"``, ``"cold_review"``,
    ``"review"``, ``"build"``} and flags carries runtime variance:

    - ``("build", {"is_first_round": True})``: first build after cold-start seeding.
    - ``("build", {"recover_active_evals": True})``: recovery mode (active_evals non-empty).
    - ``("build", {})``: steady-state optimization build.

    Defense-in-depth: if the persisted ``loop_phase`` is ``"build"`` but
    neither ``child_variants.json`` nor ``build_dispatched.json`` exist on
    disk, the phase is re-interpreted as ``"review"`` to prevent deadlock.

    Unexpected ``loop_phase`` values (including extended phases used by
    algorithm leaf branches: ``warmup_seed``, ``warmup_build``,
    ``warmup_reduce``, ``calibration``, ``build_recovering``) fall back to
    ``"review"``.
    """
    if rerun_config is not None:
        return ("rerun", {})

    search_dir = run_dir / "search"
    search_state_path = search_dir / "search_state.json"

    child_variants_sentinel = search_dir / "child_variants.json"

    # Cold-review: no child variants written yet (search_state.json may exist
    # due to pre-initialisation by _ensure_stage4_search_state).
    if not child_variants_sentinel.is_file():
        return ("cold_review", {})

    # Load state once — used for both first-round detection and loop_phase reading.
    state_data: dict[str, Any] = {}
    if search_state_path.is_file():
        try:
            state_data = json.loads(search_state_path.read_text())
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("Failed to parse search_state.json in %s: %s", run_dir, exc)

    # First build: child variants emitted but no round has been advanced yet.
    # Trust state.round, not a filename glob: variant_ids are assigned monotonically
    # from state.next_variant_seq and the first one is not guaranteed to be "v1".
    if int(state_data.get("round", 0)) == 0:
        return ("build", {"is_first_round": True})

    # Normal loop — read loop_phase from already-loaded state_data.
    raw_phase = state_data.get("loop_phase", "review")
    loop_phase = raw_phase if raw_phase in _VALID_LOOP_PHASES else "review"
    if raw_phase != loop_phase:
        logger.warning(
            "Unexpected loop_phase '%s' in %s/search/search_state.json, defaulting to 'review'",
            raw_phase,
            run_dir,
        )

    # Recovery detection: if loop_phase is "build" and active_evals is non-empty,
    # a previous build attempt was interrupted mid-eval — enter recovery mode.
    if loop_phase == "build":
        active_evals = state_data.get("active_evals", [])
        if active_evals:
            return ("build", {"recover_active_evals": True})

    # Defense-in-depth: if loop_phase is "build" but there are no child_variants
    # on disk AND the build marker is also absent, the builder was never actually
    # dispatched — flip back to "review" to prevent deadlock.
    if loop_phase == "build":
        child_variants = search_dir / "child_variants.json"
        if not child_variants.exists() and not paths.is_build_dispatched(run_dir.name, run_dir.parent):
            logger.warning(
                "loop_phase='build' but child_variants.json and build_dispatched.json absent "
                "in %s/search/ — defense-in-depth re-flip to 'review'",
                run_dir,
            )
            loop_phase = "review"

    return (loop_phase, {})


def _read_algorithm_from_state(run_dir: Path) -> str:
    """Read the algorithm discriminator from search_state.json.

    Returns ``"hill_climb"`` (the default) when the file is absent, unreadable,
    or does not contain an ``algorithm`` field.
    """
    search_state_path = run_dir / "search" / "search_state.json"
    if not search_state_path.is_file():
        return "hill_climb"
    try:
        data = json.loads(search_state_path.read_text())
        return str(data.get("algorithm", "hill_climb"))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Failed to read algorithm from %s: %s", search_state_path, exc)
        return "hill_climb"


def _detect_stage_4_phase_beam(
    run_dir: Path,
    rerun_config: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """Beam-specific Stage-4 phase detection wrapping the base detector.

    Applies the beam post-cold-start override on top of
    :func:`_detect_stage_4_phase`.  When the base returns ``("review", {})``
    at round 1 (the first review pass after cold-start seeding), this function
    instead returns ``("review", {"protected_parent_round": True})``, signalling
    that the dispatcher should use the post-coldstart overlay and mandate exactly
    one protected child per cold-start parent.
    """
    phase, flags = _detect_stage_4_phase(run_dir, rerun_config)
    if phase == "review" and not flags:
        search_state_path = run_dir / "search" / "search_state.json"
        try:
            state_data: dict[str, Any] = (
                json.loads(search_state_path.read_text()) if search_state_path.is_file() else {}
            )
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("Failed to read round from %s: %s", search_state_path, exc)
            state_data = {}
        if (
            state_data.get("algorithm") == "beam"
            and int(state_data.get("round", 0)) == 1
        ):
            return ("review", {"protected_parent_round": True})
    return (phase, flags)


def _ensure_stage4_search_state(run_dir: Path, project_dir: Path | None = None) -> None:
    """Auto-create ``search_state.json`` at Stage 4 entry if it does not exist.

    This runs once on first Stage-4 dispatch so that ``_detect_stage_4_phase``
    and the cold-start Review Agent see a real ``SearchState`` with the branch
    algorithm already persisted — ``get_search_state`` no longer raises
    ``FileNotFoundError`` during the cold-start sub-agent.

    When the file already exists this function is a no-op.

    Args:
        run_dir: Run-level output directory (``outputs/<run_id>``).
        project_dir: Project root used to locate ``backends/``. Defaults to
            :func:`get_project_dir` when ``None``.
    """
    search_state_path = run_dir / "search" / "search_state.json"
    # Safe to skip: init_search_state is a no-op on pristine state and raises
    # FileExistsError on any state with progress, so the is_file() guard here
    # and init_search_state's own guard together make concurrent dispatch safe.
    if search_state_path.is_file():
        return

    if project_dir is None:
        project_dir = get_project_dir()

    # Deferred import: odysseus.agents.prompt_builder.search_ops imports
    # odysseus.agents.pipeline.paths at module level, which would create a
    # circular import if hoisted here (stage4.py is part of the pipeline package).
    from odysseus.agents.prompt_builder.search_ops import init_search_state

    # Resolve backend from Stage 3 outputs (backends/*.yaml stem), falling back
    # to the first priced backend found, then empty string.
    backend: str = ""
    backends_dir = project_dir / "backends"
    if backends_dir.is_dir():
        for yf in sorted(backends_dir.glob("*.yaml")):
            try:
                profile = BackendProfile.from_yaml(yf)
                if profile.pricing is not None:
                    backend = yf.stem
                    break
            except Exception:
                continue

    # Read primary_metric_name from routing_context.json if available.
    primary_metric_name: str | None = None
    routing_context_path = run_dir / "validation" / "routing_context.json"
    if routing_context_path.is_file():
        try:
            rc_data = json.loads(routing_context_path.read_text())
            raw = rc_data.get("primary_metric_name")
            if isinstance(raw, str) and raw:
                primary_metric_name = raw
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("Failed to read primary_metric_name from %s: %s", routing_context_path, exc)

    # output_dir is run_dir's parent (e.g. <project>/outputs)
    output_dir = run_dir.parent
    run_id = run_dir.name
    try:
        init_search_state(
            run_id=run_id,
            backend=backend,
            primary_metric_name=primary_metric_name,
            output_dir=output_dir,
        )
        logger.info("Pre-initialised search_state.json for run %s (backend=%r)", run_id, backend)
    except Exception as exc:
        logger.warning("Failed to pre-initialise search_state.json for run %s: %s", run_id, exc)


# ---------------------------------------------------------------------------
# Next-action for Stage 4
# ---------------------------------------------------------------------------


def _next_action_for_stage_4(
    run_dir: Path,
    rerun_config: dict[str, Any] | None = None,
    project_dir: Path | None = None,
) -> tuple[str, list[str], list[str], str, str]:
    """Return (action, tools, prompts, subagent_instruction, algorithm) for Stage 4.

    The ``algorithm`` element is the search strategy discriminator read from
    ``search_state.json`` (defaults to ``"hill_climb"`` when absent).  It is
    used by the orchestrator to compose the strategy-aware Review Agent prompt.
    """
    # Pre-init search_state.json on first Stage-4 dispatch so cold-start
    # sub-agents can call get_search_state without FileNotFoundError.
    _ensure_stage4_search_state(run_dir, project_dir=project_dir)

    phase, flags = _detect_stage_4_phase_beam(run_dir, rerun_config)
    algorithm = _read_algorithm_from_state(run_dir)

    if phase == "rerun":
        assert rerun_config is not None  # noqa: S101
        source_version = rerun_config.get("source_prompt_version", "unknown")
        new_backend = rerun_config.get("new_backend", "unknown")
        rerun_instr = STAGE_4_RERUN_INSTRUCTION.format(
            run_id=run_dir.name,
            source_prompt_version=source_version,
            new_backend=new_backend,
        )
        return (
            "Stage 4 — rerun mode: spawn the Prompt Builder Rerun agent to restructure "
            f"the source prompt (version {source_version}) for the new backend ({new_backend}). "
            "REQUIRED: activate prompt 'odysseus_prompt_builder_rerun' before calling any build tools.",
            tool_registry.RERUN_TOOLS,
            ["odysseus_prompt_builder_rerun"],
            rerun_instr,
            algorithm,
        )

    # Beam post-cold-start: protected_parent_round flag selects the round-2 overlay.
    if phase == "review" and flags.get("protected_parent_round"):
        return (
            "Stage 4 — post-cold-start review (round 2): spawn the Review Agent to emit "
            "exactly one protected child per scored cold-start parent. "
            "REQUIRED: activate prompt 'odysseus_review_agent_post_coldstart' before calling any review tools.",
            tool_registry.REVIEW_TOOLS,
            ["odysseus_review_agent_post_coldstart"],
            STAGE_4_REVIEW_INSTRUCTION,
            algorithm,
        )

    if phase in _STAGE_4_PHASE_CONFIG:
        action, tools, prompts, instr = _STAGE_4_PHASE_CONFIG[phase]
        return action, tools, prompts, instr, algorithm

    # phase == "build" — behaviour varies by flags
    is_first_round = flags.get("is_first_round", False)
    recover_active_evals = flags.get("recover_active_evals", False)
    if recover_active_evals:
        action_text = _STAGE_4_BUILD_ACTION_RECOVER
    elif is_first_round:
        action_text = _STAGE_4_BUILD_ACTION_FIRST
    else:
        action_text = _STAGE_4_BUILD_ACTION_STEADY

    return (
        action_text,
        tool_registry.BUILD_TOOLS,
        ["odysseus_prompt_builder"],
        STAGE_4_BUILD_INSTRUCTION(is_first_round=is_first_round, recover_active_evals=recover_active_evals),
        algorithm,
    )
