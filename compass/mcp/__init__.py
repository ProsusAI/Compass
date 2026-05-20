"""MCP server package for Compass."""

from compass.agents.pipeline.status import get_pipeline_status as _get_pipeline_status  # noqa: F401
from compass.agents.prompt_builder.search_ops import get_search_state as _get_search_state_ops  # noqa: F401
from compass.eval.backends.registry import BackendRegistry  # noqa: F401

# Re-export tool functions so existing ``from compass.mcp import <tool>`` works.
from compass.mcp.backend_setup_tools import get_default_pricing
from compass.mcp.data_validation_tools import (
    detect_and_parse_dataset,
    get_routing_context,
    save_routing_context,
    stratified_split,
    transform_dataset,
    validate_dataset,
)
from compass.mcp.final_report_tools import (
    build_final_report_briefing,
    filter_holdout_dataset,
    run_holdout_eval,
    save_final_report,
)
from compass.mcp.input_report_tools import submit_input_report
from compass.mcp.orchestrator_tools import (
    complete_stage,
    get_pipeline_status,
    optimize_routing_prompt,
    start_stage,
)
from compass.mcp.prompt_building_tools import (
    advance_step,
    get_child_variants,
    get_edit_directives,
    get_search_state,
    init_search_state,
    record_eval_result,
    register_candidate,
    run_batch_eval,
)
from compass.mcp.prompts import (
    compass_review_agent_cold_start,
    compass_review_agent_iterative,
)
from compass.mcp.resources import (
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
from compass.mcp.review_tools import (
    build_review_briefing,
    get_dataset_oracle_distribution,
    get_per_class_recall,
    get_prompt_text,
    get_score_report,
    query_dev_examples,
    query_eval_results,
    query_holdout_examples,
    record_directive_outcomes,
)
from compass.mcp.server import (
    _PROJECT_ROOT,
    STAGE_REGISTRY,
    _load_text,
    create_app,
    main,
    mcp,
)

# Also re-export helpers that tests patch via ``compass.mcp.<name>``.
from compass.project_dir import resolve_project_dir  # noqa: F401

__all__ = [
    "_PROJECT_ROOT",
    "_load_text",
    "create_app",
    "main",
    "mcp",
    # Tools
    "STAGE_REGISTRY",
    "advance_step",
    "build_final_report_briefing",
    "build_review_briefing",
    "complete_stage",
    "detect_and_parse_dataset",
    "filter_holdout_dataset",
    "get_dataset_oracle_distribution",
    "get_default_pricing",
    "get_child_variants",
    "get_edit_directives",
    "get_per_class_recall",
    "get_pipeline_status",
    "get_prompt_text",
    "query_eval_results",
    "get_routing_context",
    "get_score_report",
    "get_search_state",
    "init_search_state",
    "optimize_routing_prompt",
    "query_dev_examples",
    "query_holdout_examples",
    "record_directive_outcomes",
    "record_eval_result",
    "register_candidate",
    "run_batch_eval",
    "run_holdout_eval",
    "save_final_report",
    "save_routing_context",
    "start_stage",
    "stratified_split",
    "submit_input_report",
    "transform_dataset",
    "validate_dataset",
    # Prompts
    "compass_review_agent_cold_start",
    "compass_review_agent_iterative",
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
