"""Snapshot tests: _hard_stop builder output is byte-for-byte identical to pre-builder strings.

Pre-builder strings are copied verbatim from the original instructions.py before A1 was applied.
Any mismatch here is a builder regression.
"""

from __future__ import annotations

from odysseus.agents.pipeline.instructions import (
    _STAGE_4_BUILD_OPTIMIZE_INSTRUCTION,
    _STAGE_4_BUILD_RECOVERING_INSTRUCTION,
    _STAGE_4_BUILD_V1_INSTRUCTION,
    STAGE_1_INSTRUCTION,
    STAGE_2_INSTRUCTION,
    STAGE_3_INSTRUCTION,
    STAGE_4_BUILD_INSTRUCTION,
    STAGE_4_COLD_START_INSTRUCTION,
    STAGE_4_RERUN_INSTRUCTION,
    STAGE_4_REVIEW_INSTRUCTION,
    STAGE_5_INSTRUCTION,
)

# ---------------------------------------------------------------------------
# Pre-builder snapshots (updated for F2: PRE-DISPATCH block removed;
# POST-EXIT now references start_stage instead of get_pipeline_status)
# ---------------------------------------------------------------------------

# A3 dropped the per-HARD_STOP worktree-isolation reminder; the rule now lives
# only in the dispatch preamble wrapped around every subagent_instruction.
_NO = ""

_SNAP_STAGE_1 = (
    "<HARD_STOP>\n" + _NO + "You MUST NOT call any Stage 1 tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "Sub-agent tools: get_pipeline_status, submit_input_report\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, extract the run_id from its output, "
    "then call complete_stage(run_id='<run_id_from_submit>'), "
    "then call start_stage(run_id='<run_id_from_submit>') to get the next dispatch.\n"
    "If Stage 1 is not complete, re-dispatch the sub-agent. Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)

_SNAP_STAGE_2 = (
    "<HARD_STOP>\n" + _NO + "You MUST NOT call any Stage 2 tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "Sub-agent tools: get_pipeline_status, validate_dataset, "
    "detect_and_parse_dataset, transform_dataset, save_routing_context, "
    "stratified_split, save_proposed_mapping\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call start_stage(run_id='{run_id}') to get the next dispatch.\n"
    "If Stage 2 is not complete with a non-empty detail field, follow the generic\n"
    "user-mediation flow: read detail.artifact_path, present detail.prompt_to_user\n"
    "to the user, wait for their real reply, call start_stage again, re-dispatch the\n"
    "sub-agent with the reply in context. If the detail kind is 'halt', do NOT proceed\n"
    "to downstream stages. If the detail's halt_on_failure_after limit is reached,\n"
    "report the error to the user and halt.\n"
    "If Stage 2 is incomplete with no detail, call start_stage again and re-dispatch.\n"
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)

_SNAP_STAGE_3 = (
    "<HARD_STOP>\n" + _NO + "You MUST NOT perform backend setup from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "Sub-agent tools: get_pipeline_status, get_default_pricing, save_backend_options\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call start_stage(run_id='{run_id}') to get the next dispatch.\n"
    "If Stage 3 is not complete with a non-empty detail field, follow the generic\n"
    "user-mediation flow: read detail.artifact_path, present detail.prompt_to_user\n"
    "to the user, wait for their real reply, call start_stage again, re-dispatch the\n"
    "sub-agent with the reply in context. If the detail's halt_on_failure_after limit\n"
    "is reached, report the error to the user and halt.\n"
    "If Stage 3 is incomplete with no detail, call start_stage again and re-dispatch.\n"
    "Do not perform backend setup yourself.\n"
    "</HARD_STOP>"
)

_SNAP_STAGE_4_COLD = (
    "<HARD_STOP>\n" + _NO + "You MUST NOT call any Stage 4 tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state, "
    "build_review_briefing, record_directive_outcomes, query_dev_examples\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call start_stage(run_id='{run_id}') to get the next dispatch.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)

_S4_BUILD_BODY = (
    "<HARD_STOP>\n" + _NO + "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state, get_routing_context, "
    "get_child_variants, get_edit_directives, get_prompt_text, get_score_report, "
    "init_search_state, register_candidate, record_eval_result, "
    "advance_step, save_prompt, run_eval"
)
_S4_BUILD_TAIL = (
    "\n"
    "Your tools: get_pipeline_status only\n\n"
    "NOTE: optimize_routing_prompt is the pipeline entry-point tool (orchestrator-level only). "
    "Do not call it from within the sub-agent.\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call start_stage(run_id='{run_id}') to get the next dispatch.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)
_S4_DISPATCH_CTX = (
    "<DISPATCH_CONTEXT>\n"
    "This is an optimization round (round 2+ in the refinement loop). A search state already exists for this run.\n"
    "- Begin by calling get_search_state (NOT init_search_state).\n"
    "- Skip Phase 1 of your system prompt entirely. Proceed directly to Phase 2.\n"
    "- Calling init_search_state now would clobber the optimization history.\n"
    "</DISPATCH_CONTEXT>\n\n"
)
_S4_RECOVERY_PARA = (
    "\n\n"
    "RECOVERY MODE: active_evals is non-empty. The sub-agent must call "
    "run_batch_eval(run_id='{run_id}', candidates=[]) to resume in-flight evaluations. "
    "Completed evals (eval_status='complete') are recovered from disk automatically; "
    "only missing or incomplete evals (eval_status='pending' or 'running') are re-run."
)

_SNAP_BUILD_V1 = _S4_BUILD_BODY + _S4_BUILD_TAIL
_SNAP_BUILD_OPTIMIZE = _S4_DISPATCH_CTX + _S4_BUILD_BODY + _S4_BUILD_TAIL
_SNAP_BUILD_RECOVER = _S4_BUILD_BODY + ", run_batch_eval" + _S4_RECOVERY_PARA + _S4_BUILD_TAIL

_SNAP_STAGE_4_RERUN = (
    "<HARD_STOP>\n" + _NO + "You MUST NOT call any Stage 4 build-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state, get_routing_context, "
    "get_prompt_text, init_search_state, register_candidate, record_eval_result, "
    "advance_step, save_prompt, run_eval\n"
    "Your tools: get_pipeline_status only\n\n"
    "NOTE: This is a rerun — the Prompt Builder Rerun agent will restructure the existing prompt "
    "for the new backend. Source prompt version: '{source_prompt_version}'. "
    "New backend: '{new_backend}'.\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call start_stage(run_id='{run_id}') to get the next dispatch.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)

_SNAP_STAGE_4_REVIEW = (
    "<HARD_STOP>\n" + _NO + "You MUST NOT call any Stage 4 review-phase tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "Sub-agent tools: get_pipeline_status, get_search_state, "
    "build_review_briefing, record_directive_outcomes, "
    "get_prompt_text, query_dev_examples, query_holdout_examples\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call start_stage(run_id='{run_id}') to get the next dispatch.\n"
    "If Stage 4 is not complete, re-dispatch the appropriate sub-agent. "
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)

_SNAP_STAGE_5 = (
    "<HARD_STOP>\n" + _NO + "You MUST NOT call any Stage 5 tools from the current context.\n\n"
    "REQUIRED: Spawn a sub-agent with the `sub_agent_prompt` field returned by `start_stage` as its prompt.\n\n"
    "Sub-agent tools: get_pipeline_status, filter_holdout_dataset, "
    "list_pareto_candidates, run_holdout_eval, "
    "build_final_report_briefing, save_final_report\n"
    "Your tools: get_pipeline_status only\n\n"
    "POST-EXIT: After the sub-agent returns, call complete_stage(run_id='{run_id}'), "
    "then call start_stage(run_id='{run_id}') to get the next dispatch.\n"
    "If Stage 5 is not complete with a non-empty detail field, follow the generic\n"
    "user-mediation flow: read detail.artifact_path, present detail.prompt_to_user\n"
    "to the user, wait for their real reply, call start_stage again, re-dispatch the\n"
    "sub-agent with the reply in context. If the detail's halt_on_failure_after limit\n"
    "is reached, report the error to the user and halt.\n"
    "If Stage 5 is incomplete with no detail, call start_stage again and re-dispatch.\n"
    "Do not call stage tools yourself.\n"
    "</HARD_STOP>"
)


# ---------------------------------------------------------------------------
# Snapshot tests
# ---------------------------------------------------------------------------


class TestHardStopBuilderSnapshots:
    """Each builder call must produce output byte-identical to the pre-builder string."""

    def test_stage_1_snapshot(self) -> None:
        assert STAGE_1_INSTRUCTION == _SNAP_STAGE_1

    def test_stage_2_snapshot(self) -> None:
        assert STAGE_2_INSTRUCTION == _SNAP_STAGE_2

    def test_stage_3_snapshot(self) -> None:
        assert STAGE_3_INSTRUCTION == _SNAP_STAGE_3

    def test_stage_4_cold_start_snapshot(self) -> None:
        assert STAGE_4_COLD_START_INSTRUCTION == _SNAP_STAGE_4_COLD

    def test_stage_4_build_first_round_snapshot(self) -> None:
        assert STAGE_4_BUILD_INSTRUCTION(is_first_round=True) == _SNAP_BUILD_V1

    def test_stage_4_build_optimize_snapshot(self) -> None:
        assert STAGE_4_BUILD_INSTRUCTION() == _SNAP_BUILD_OPTIMIZE

    def test_stage_4_build_recover_snapshot(self) -> None:
        assert STAGE_4_BUILD_INSTRUCTION(recover_active_evals=True) == _SNAP_BUILD_RECOVER

    def test_stage_4_build_v1_constant_snapshot(self) -> None:
        assert _STAGE_4_BUILD_V1_INSTRUCTION == _SNAP_BUILD_V1

    def test_stage_4_build_optimize_constant_snapshot(self) -> None:
        assert _STAGE_4_BUILD_OPTIMIZE_INSTRUCTION == _SNAP_BUILD_OPTIMIZE

    def test_stage_4_build_recovering_constant_snapshot(self) -> None:
        assert _STAGE_4_BUILD_RECOVERING_INSTRUCTION == _SNAP_BUILD_RECOVER

    def test_stage_4_rerun_snapshot(self) -> None:
        assert STAGE_4_RERUN_INSTRUCTION == _SNAP_STAGE_4_RERUN

    def test_stage_4_review_snapshot(self) -> None:
        assert STAGE_4_REVIEW_INSTRUCTION == _SNAP_STAGE_4_REVIEW

    def test_stage_5_snapshot(self) -> None:
        assert STAGE_5_INSTRUCTION == _SNAP_STAGE_5
