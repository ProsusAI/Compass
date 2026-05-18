"""Sub-agent HARD_STOP instruction templates for each pipeline stage.

These templates are embedded in ``get_pipeline_status`` responses so that the
orchestrator knows how to dispatch sub-agents.  Placeholders like ``{run_id}``
are filled at runtime by ``status.py``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Per-stage tool lists (module-level constants; passed into _hard_stop)
# ---------------------------------------------------------------------------

_STAGE_1_TOOLS: list[str] = [
    "get_pipeline_status",
    "submit_input_report",
]

_STAGE_2_TOOLS: list[str] = [
    "get_pipeline_status",
    "validate_dataset",
    "detect_and_parse_dataset",
    "transform_dataset",
    "save_routing_context",
    "stratified_split",
    "save_proposed_mapping",
]

_STAGE_3_TOOLS: list[str] = [
    "get_pipeline_status",
    "get_default_pricing",
    "save_backend_options",
]

_STAGE_4_COLD_TOOLS: list[str] = [
    "get_pipeline_status",
    "get_search_state",
    "build_review_briefing",
    "record_directive_outcomes",
]

_STAGE_4_BUILD_BASE_TOOLS: list[str] = [
    "get_pipeline_status",
    "get_search_state",
    "get_routing_context",
    "get_child_variants",
    "get_edit_directives",
    "get_prompt_text",
    "get_score_report",
    "init_search_state",
    "register_candidate",
    "record_eval_result",
    "advance_step",
    "save_prompt",
    "run_eval",
]

_STAGE_4_BUILD_RECOVERY_TOOLS: list[str] = _STAGE_4_BUILD_BASE_TOOLS + ["run_batch_eval"]

_STAGE_4_RERUN_TOOLS: list[str] = [
    "get_pipeline_status",
    "get_search_state",
    "get_routing_context",
    "get_prompt_text",
    "init_search_state",
    "register_candidate",
    "record_eval_result",
    "advance_step",
    "save_prompt",
    "run_eval",
]

_STAGE_4_REVIEW_TOOLS: list[str] = [
    "get_pipeline_status",
    "get_search_state",
    "build_review_briefing",
    "record_directive_outcomes",
    "get_prompt_text",
    "query_holdout_examples",
]

_STAGE_5_TOOLS: list[str] = [
    "get_pipeline_status",
    "filter_holdout_dataset",
    "list_pareto_candidates",
    "run_holdout_eval",
    "build_final_report_briefing",
    "save_final_report",
]


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------


def _hard_stop(
    *,
    stage: str,
    stage_label: str,
    tools: list[str],
    dispatch_context: str | None = None,
    recovery_note: str | None = None,
    detail_branches: str | None = None,
    extra_notes: list[str] | None = None,
    must_not_line: str | None = None,
    post_exit_line: str | None = None,
) -> str:
    """Build a HARD_STOP instruction string for a pipeline stage sub-agent dispatch."""
    parts: list[str] = []

    if dispatch_context is not None:
        parts.append(dispatch_context)

    parts.append("<HARD_STOP>\n")

    if must_not_line is not None:
        parts.append(must_not_line + "\n\n")
    else:
        parts.append(f"You MUST NOT call any {stage_label} tools from the current context.\n\n")

    parts.append(
        "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    )

    parts.append(f"Sub-agent tools: {', '.join(tools)}")

    if recovery_note is not None:
        parts.append("\n\n" + recovery_note)

    parts.append("\n")
    parts.append("Your tools: get_pipeline_status only\n\n")

    if extra_notes:
        for note in extra_notes:
            parts.append(note + "\n\n")

    if post_exit_line is not None:
        parts.append(post_exit_line + "\n")
    else:
        parts.append(
            "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
            "then call start_stage(run_id='{run_id}') to get the next dispatch.\n"
        )

    if detail_branches is not None:
        parts.append(detail_branches)
    else:
        parts.append(
            f"If {stage_label} is not complete, re-dispatch the appropriate sub-agent. "
            "Do not call stage tools yourself.\n"
        )

    parts.append("</HARD_STOP>")

    return "".join(parts)


# ---------------------------------------------------------------------------
# Stage 1 — User Input
# ---------------------------------------------------------------------------

STAGE_1_INSTRUCTION: str = _hard_stop(
    stage="input_report",
    stage_label="Stage 1",
    tools=_STAGE_1_TOOLS,
    post_exit_line=(
        "POST-EXIT: After the sub-agent returns, extract the run_id from its output, "
        "then call complete_stage(run_id='<run_id_from_submit>'), "
        "then call start_stage(run_id='<run_id_from_submit>') to get the next dispatch."
    ),
    detail_branches=("If Stage 1 is not complete, re-dispatch the sub-agent. Do not call stage tools yourself.\n"),
)

# ---------------------------------------------------------------------------
# Stage 2 — Data Validation
# ---------------------------------------------------------------------------

STAGE_2_INSTRUCTION: str = _hard_stop(
    stage="data_validation",
    stage_label="Stage 2",
    tools=_STAGE_2_TOOLS,
    detail_branches=(
        "If Stage 2 is not complete with a non-empty detail field, follow the generic\n"
        "user-mediation flow: read detail.artifact_path, present detail.prompt_to_user\n"
        "to the user, wait for their real reply, call start_stage again, re-dispatch the\n"
        "sub-agent with the reply in context. If the detail kind is 'halt', do NOT proceed\n"
        "to downstream stages. If the detail's halt_on_failure_after limit is reached,\n"
        "report the error to the user and halt.\n"
        "If Stage 2 is incomplete with no detail, call start_stage again and re-dispatch.\n"
        "Do not call stage tools yourself.\n"
    ),
)

# ---------------------------------------------------------------------------
# Stage 3 — Backend Setup
# ---------------------------------------------------------------------------

STAGE_3_INSTRUCTION: str = _hard_stop(
    stage="backend_setup",
    stage_label="Stage 3",
    tools=_STAGE_3_TOOLS,
    must_not_line="You MUST NOT perform backend setup from the current context.",
    detail_branches=(
        "If Stage 3 is not complete with a non-empty detail field, follow the generic\n"
        "user-mediation flow: read detail.artifact_path, present detail.prompt_to_user\n"
        "to the user, wait for their real reply, call start_stage again, re-dispatch the\n"
        "sub-agent with the reply in context. If the detail's halt_on_failure_after limit\n"
        "is reached, report the error to the user and halt.\n"
        "If Stage 3 is incomplete with no detail, call start_stage again and re-dispatch.\n"
        "Do not perform backend setup yourself.\n"
    ),
)

# ---------------------------------------------------------------------------
# Stage 4 — Refinement Loop (dynamic phases)
# ---------------------------------------------------------------------------

STAGE_4_COLD_START_INSTRUCTION: str = _hard_stop(
    stage="review_cold",
    stage_label="Stage 4",
    tools=_STAGE_4_COLD_TOOLS,
    detail_branches=(
        "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. Do not call stage tools yourself.\n"
    ),
)

_STAGE_4_BUILD_DISPATCH_CONTEXT: str = (
    "<DISPATCH_CONTEXT>\n"
    "This is an optimization round (round 2+ in the refinement loop). A search state already exists for this run.\n"
    "- Begin by calling get_search_state (NOT init_search_state).\n"
    "- Skip Phase 1 of your system prompt entirely. Proceed directly to Phase 2.\n"
    "- Calling init_search_state now would clobber the optimization history.\n"
    "</DISPATCH_CONTEXT>\n\n"
)

_STAGE_4_BUILD_RECOVERY_NOTE: str = (
    "RECOVERY MODE: active_evals is non-empty. The sub-agent must call "
    "run_batch_eval(run_id='{run_id}', candidates=[]) to resume in-flight evaluations. "
    "Completed evals (eval_status='complete') are recovered from disk automatically; "
    "only missing or incomplete evals (eval_status='pending' or 'running') are re-run."
)

_STAGE_4_BUILD_NOTE: str = (
    "NOTE: optimize_routing_prompt is the pipeline entry-point tool (orchestrator-level only). "
    "Do not call it from within the sub-agent."
)

_STAGE_4_BUILD_MUST_NOT: str = "You MUST NOT call any Stage 4 build-phase tools from the current context."

_STAGE_4_BUILD_DETAIL: str = (
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. Do not call stage tools yourself.\n"
)


def STAGE_4_BUILD_INSTRUCTION(  # noqa: N802
    *,
    is_first_round: bool = False,
    recover_active_evals: bool = False,
) -> str:
    """Return the Stage-4 build sub-agent instruction for the given variant.

    Three output variants:
    - ``is_first_round=True``: first build after cold-start seeding (no DISPATCH_CONTEXT).
    - ``recover_active_evals=True``: recovery mode, includes ``run_batch_eval`` in toolbelt.
    - else (steady-state): optimisation round with leading DISPATCH_CONTEXT.
    """
    if recover_active_evals:
        return _hard_stop(
            stage="prompt_building",
            stage_label="Stage 4",
            tools=_STAGE_4_BUILD_RECOVERY_TOOLS,
            must_not_line=_STAGE_4_BUILD_MUST_NOT,
            recovery_note=_STAGE_4_BUILD_RECOVERY_NOTE,
            extra_notes=[_STAGE_4_BUILD_NOTE],
            detail_branches=_STAGE_4_BUILD_DETAIL,
        )
    if is_first_round:
        return _hard_stop(
            stage="prompt_building",
            stage_label="Stage 4",
            tools=_STAGE_4_BUILD_BASE_TOOLS,
            must_not_line=_STAGE_4_BUILD_MUST_NOT,
            extra_notes=[_STAGE_4_BUILD_NOTE],
            detail_branches=_STAGE_4_BUILD_DETAIL,
        )
    return _hard_stop(
        stage="prompt_building",
        stage_label="Stage 4",
        tools=_STAGE_4_BUILD_BASE_TOOLS,
        dispatch_context=_STAGE_4_BUILD_DISPATCH_CONTEXT,
        must_not_line=_STAGE_4_BUILD_MUST_NOT,
        extra_notes=[_STAGE_4_BUILD_NOTE],
        detail_branches=_STAGE_4_BUILD_DETAIL,
    )


# Convenience pre-built strings for backward compatibility with tests that compare text.
# These are not public API — internal use only.
_STAGE_4_BUILD_OPTIMIZE_INSTRUCTION: str = STAGE_4_BUILD_INSTRUCTION()
_STAGE_4_BUILD_V1_INSTRUCTION: str = STAGE_4_BUILD_INSTRUCTION(is_first_round=True)
_STAGE_4_BUILD_RECOVERING_INSTRUCTION: str = STAGE_4_BUILD_INSTRUCTION(recover_active_evals=True)

STAGE_4_RERUN_INSTRUCTION: str = _hard_stop(
    stage="prompt_building",
    stage_label="Stage 4",
    tools=_STAGE_4_RERUN_TOOLS,
    must_not_line=_STAGE_4_BUILD_MUST_NOT,
    extra_notes=[
        "NOTE: This is a rerun — the Prompt Builder Rerun agent will restructure the existing prompt "
        "for the new backend. Source prompt version: '{source_prompt_version}'. "
        "New backend: '{new_backend}'."
    ],
    detail_branches=_STAGE_4_BUILD_DETAIL,
)

STAGE_4_BUILD_RECOVERING_INSTRUCTION: str = STAGE_4_BUILD_INSTRUCTION(recover_active_evals=True)

STAGE_4_REVIEW_INSTRUCTION: str = _hard_stop(
    stage="review",
    stage_label="Stage 4",
    tools=_STAGE_4_REVIEW_TOOLS,
    must_not_line="You MUST NOT call any Stage 4 review-phase tools from the current context.",
    detail_branches=_STAGE_4_BUILD_DETAIL,
)

# ---------------------------------------------------------------------------
# Stage 5 — Final Report
# ---------------------------------------------------------------------------

STAGE_5_INSTRUCTION: str = _hard_stop(
    stage="final_report",
    stage_label="Stage 5",
    tools=_STAGE_5_TOOLS,
    detail_branches=(
        "If Stage 5 is not complete with a non-empty detail field, follow the generic\n"
        "user-mediation flow: read detail.artifact_path, present detail.prompt_to_user\n"
        "to the user, wait for their real reply, call start_stage again, re-dispatch the\n"
        "sub-agent with the reply in context. If the detail's halt_on_failure_after limit\n"
        "is reached, report the error to the user and halt.\n"
        "If Stage 5 is incomplete with no detail, call start_stage again and re-dispatch.\n"
        "Do not call stage tools yourself.\n"
    ),
)
