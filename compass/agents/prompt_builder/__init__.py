# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Prompt builder — search state, candidate management, holdout filtering."""

from __future__ import annotations

from compass.agents.prompt_builder.holdout_filter import filter_holdout_dataset
from compass.agents.prompt_builder.search import (
    Candidate,
    RoundSummary,
    SearchState,
    dominates,
    update_pareto_front,
)
from compass.agents.prompt_builder.search_ops import (
    advance_round,
    get_search_state,
    init_search_state,
    record_eval_result,
    register_candidate,
    set_loop_phase,
)

__all__ = [
    "Candidate",
    "RoundSummary",
    "SearchState",
    "advance_round",
    "dominates",
    "filter_holdout_dataset",
    "get_search_state",
    "init_search_state",
    "record_eval_result",
    "register_candidate",
    "set_loop_phase",
    "update_pareto_front",
]
