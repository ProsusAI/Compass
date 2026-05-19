"""Tool allowlists for Stage 4 sub-agent dispatch."""

COLD_REVIEW_TOOLS: list[str] = [
    "get_search_state",
    "build_review_briefing",
    "record_directive_outcomes",
    "query_dev_examples",
    "query_eval_results",
    "get_score_report",
    "get_confusion_cell",
    "get_round_child_variants",
]

REVIEW_TOOLS: list[str] = [
    "get_search_state",
    "build_review_briefing",
    "record_directive_outcomes",
    "get_prompt_text",
    "query_dev_examples",
    "query_holdout_examples",
    "query_eval_results",
    "get_score_report",
    "get_confusion_cell",
    "get_round_child_variants",
]

BUILD_TOOLS: list[str] = [
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
    "run_batch_eval",
]

RERUN_TOOLS: list[str] = [
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
