"""Tool allowlists for Stage 4 sub-agent dispatch."""

COLD_REVIEW_TOOLS: list[str] = [
    "get_search_state_tool",
    "build_review_briefing_tool",
    "record_directive_outcomes_tool",
    "get_score_report_tool",
    "get_confusion_cell_tool",
    "get_directive_history_tool",
    "get_batch_outcomes_tool",
    "get_round_child_variants_tool",
]

REVIEW_TOOLS: list[str] = [
    "get_search_state_tool",
    "build_review_briefing_tool",
    "record_directive_outcomes_tool",
    "get_prompt_text_tool",
    "query_holdout_examples_tool",
    "get_score_report_tool",
    "get_confusion_cell_tool",
    "get_directive_history_tool",
    "get_batch_outcomes_tool",
    "get_round_child_variants_tool",
]

BUILD_TOOLS: list[str] = [
    "get_search_state_tool",
    "get_routing_context_tool",
    "get_child_variants_tool",
    "get_edit_directives_tool",
    "get_prompt_text_tool",
    "get_score_report_tool",
    "init_search_state_tool",
    "register_candidate_tool",
    "record_eval_result_tool",
    "advance_step_tool",
    "save_prompt_tool",
    "run_eval",
    "run_batch_eval",
]

RERUN_TOOLS: list[str] = [
    "get_search_state_tool",
    "get_routing_context_tool",
    "get_prompt_text_tool",
    "init_search_state_tool",
    "register_candidate_tool",
    "record_eval_result_tool",
    "advance_step_tool",
    "save_prompt_tool",
    "run_eval",
]
