"""MCP server package for Odysseus."""

from odysseus.agents.pipeline.status import get_pipeline_status as _get_pipeline_status  # noqa: F401
from odysseus.agents.prompt_builder.search_ops import get_search_state  # noqa: F401
from odysseus.eval.backends.registry import BackendRegistry  # noqa: F401

# Re-export tool functions so existing ``from odysseus.mcp import <tool>`` works.
from odysseus.mcp.backend_setup_tools import get_default_pricing
from odysseus.mcp.data_validation_tools import (
    detect_and_parse_dataset,
    get_routing_context_tool,
    save_routing_context,
    stratified_split_tool,
    transform_dataset,
    validate_dataset,
)
from odysseus.mcp.final_report_tools import (
    build_final_report_briefing_tool,
    filter_holdout_dataset_tool,
    run_holdout_eval,
    save_final_report,
)
from odysseus.mcp.input_report_tools import submit_input_report
from odysseus.mcp.orchestrator_tools import (
    complete_stage,
    get_pipeline_status,
    optimize_routing_prompt,
    start_stage,
)
from odysseus.mcp.prompt_building_tools import (
    advance_step_tool,
    get_child_variants_tool,
    get_edit_directives_tool,
    get_search_state_tool,
    init_search_state_tool,
    record_eval_result_tool,
    register_candidate_tool,
    run_batch_eval,
    run_eval,
)
from odysseus.mcp.prompts import (
    odysseus_review_agent_cold_start,
    odysseus_review_agent_iterative,
)
from odysseus.mcp.resources import (
    backend_profile,
    backend_setup_clarification_skill,
    backend_setup_defaults,
    backend_setup_taxonomy,
    data_validation_format_spec,
    data_validation_output_spec,
    final_report_template,
    input_clarification_skill,
    input_defaults,
    model_specific_conventions,
    prompt_builder_best_practices,
    prompt_builder_conventions_claude,
    prompt_builder_conventions_openai,
    review_agent_guidelines,
)
from odysseus.mcp.review_tools import (
    build_review_briefing_tool,
    get_prompt_text_tool,
    get_score_report_tool,
    query_holdout_examples_tool,
    record_directive_outcomes_tool,
)
from odysseus.mcp.server import (
    _PROJECT_ROOT,
    STAGE_REGISTRY,
    _load_text,
    create_app,
    main,
    mcp,
)

# Also re-export helpers that tests patch via ``odysseus.mcp.<name>``.
from odysseus.project_dir import resolve_project_dir  # noqa: F401

__all__ = [
    "_PROJECT_ROOT",
    "_load_text",
    "create_app",
    "main",
    "mcp",
    # Tools
    "STAGE_REGISTRY",
    "advance_step_tool",
    "build_final_report_briefing_tool",
    "build_review_briefing_tool",
    "complete_stage",
    "detect_and_parse_dataset",
    "filter_holdout_dataset_tool",
    "get_default_pricing",
    "get_child_variants_tool",
    "get_edit_directives_tool",
    "get_pipeline_status",
    "get_prompt_text_tool",
    "get_routing_context_tool",
    "get_score_report_tool",
    "get_search_state_tool",
    "init_search_state_tool",
    "optimize_routing_prompt",
    "query_holdout_examples_tool",
    "record_directive_outcomes_tool",
    "record_eval_result_tool",
    "register_candidate_tool",
    "run_batch_eval",
    "run_eval",
    "run_holdout_eval",
    "save_final_report",
    "save_routing_context",
    "start_stage",
    "stratified_split_tool",
    "submit_input_report",
    "transform_dataset",
    "validate_dataset",
    # Prompts
    "odysseus_review_agent_cold_start",
    "odysseus_review_agent_iterative",
    # Resources
    "backend_profile",
    "backend_setup_clarification_skill",
    "backend_setup_defaults",
    "backend_setup_taxonomy",
    "data_validation_format_spec",
    "data_validation_output_spec",
    "final_report_template",
    "input_clarification_skill",
    "input_defaults",
    "model_specific_conventions",
    "prompt_builder_best_practices",
    "prompt_builder_conventions_claude",
    "prompt_builder_conventions_openai",
    "review_agent_guidelines",
]
