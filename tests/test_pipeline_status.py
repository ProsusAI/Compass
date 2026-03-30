import json
import time
from pathlib import Path

from odysseus.agents.pipeline_status import discover_runs, get_pipeline_status


class TestDiscoverRuns:
    def test_no_runs(self, tmp_path: Path) -> None:
        assert discover_runs(tmp_path) == []

    def test_finds_run(self, tmp_path: Path) -> None:
        (tmp_path / "abc12345" / "input").mkdir(parents=True)
        (tmp_path / "abc12345" / "input" / "input_report.md").write_text("# Report")
        assert discover_runs(tmp_path) == ["abc12345"]

    def test_most_recent_first(self, tmp_path: Path) -> None:
        for rid in ["run_old", "run_new"]:
            d = tmp_path / rid / "input"
            d.mkdir(parents=True)
            (d / "input_report.md").write_text("# Report")
            time.sleep(0.05)
        assert discover_runs(tmp_path)[0] == "run_new"


class TestGetPipelineStatus:
    def test_empty_run(self, tmp_path: Path) -> None:
        (tmp_path / "abc12345" / "input").mkdir(parents=True)
        (tmp_path / "abc12345" / "input" / "input_report.md").write_text("# Report")
        result = get_pipeline_status(tmp_path, "abc12345")
        assert result["stages"][0]["status"] == "complete"
        assert result["current_stage"] == 2

    def test_validation_complete(self, tmp_path: Path) -> None:
        _setup_through_validation(tmp_path, "abc12345")
        result = get_pipeline_status(tmp_path, "abc12345")
        assert result["stages"][1]["status"] == "complete"
        assert result["current_stage"] == 3

    def test_analysis_complete(self, tmp_path: Path) -> None:
        _setup_through_validation(tmp_path, "abc12345")
        analysis = tmp_path / "abc12345" / "analysis"
        analysis.mkdir(parents=True)
        for f in [
            "validation_report.json",
            "dev.jsonl",
            "holdout.jsonl",
            "dev_rationale_card_set.json",
            "holdout_rationale_card_set.json",
            "vocabulary_registry.json",
        ]:
            (analysis / f).write_text("{}")
        result = get_pipeline_status(tmp_path, "abc12345")
        assert result["stages"][2]["status"] == "complete"

    def test_blocked_stages(self, tmp_path: Path) -> None:
        (tmp_path / "abc12345" / "input").mkdir(parents=True)
        (tmp_path / "abc12345" / "input" / "input_report.md").write_text("# Report")
        result = get_pipeline_status(tmp_path, "abc12345")
        assert result["stages"][2]["status"] == "blocked"  # routing analysis
        assert result["stages"][4]["status"] == "blocked"  # prompt v1

    def test_no_runs_returns_empty(self, tmp_path: Path) -> None:
        result = get_pipeline_status(tmp_path, run_id=None)
        assert result["run_id"] is None
        assert result["current_stage"] == 1
        assert "submit_input_report" in result["available_tools"]

    def test_run_id_none_uses_most_recent(self, tmp_path: Path) -> None:
        for rid in ["old_run", "new_run"]:
            d = tmp_path / rid / "input"
            d.mkdir(parents=True)
            (d / "input_report.md").write_text("# Report")
            time.sleep(0.05)
        result = get_pipeline_status(tmp_path, run_id=None)
        assert result["run_id"] == "new_run"

    def test_prompt_v1_glob(self, tmp_path: Path) -> None:
        """Stage 5 should detect v1.yaml, not just v1.txt."""
        _setup_through_validation(tmp_path, "r1")
        _setup_analysis(tmp_path, "r1")
        prompts = tmp_path / "r1" / "prompts"
        prompts.mkdir(parents=True)
        (prompts / "v1.yaml").write_text("prompt: test")
        result = get_pipeline_status(tmp_path, "r1")
        assert result["stages"][4]["status"] == "complete"


def _setup_through_validation(base: Path, run_id: str) -> None:
    (base / run_id / "input").mkdir(parents=True, exist_ok=True)
    (base / run_id / "input" / "input_report.md").write_text("# Report")
    (base / run_id / "validation").mkdir(parents=True, exist_ok=True)
    for f in ["transformed.jsonl", "data_quality_report.json", "routing_context.json"]:
        (base / run_id / "validation" / f).write_text("{}")


def _setup_analysis(base: Path, run_id: str) -> None:
    analysis = base / run_id / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    for f in [
        "validation_report.json",
        "dev.jsonl",
        "holdout.jsonl",
        "dev_rationale_card_set.json",
        "holdout_rationale_card_set.json",
        "vocabulary_registry.json",
    ]:
        (analysis / f).write_text("{}")


class TestSubagentInstruction:
    """subagent_instruction field is present and correctly populated."""

    def test_stage1_has_subagent_instruction(self, tmp_path: Path) -> None:
        result = get_pipeline_status(tmp_path, run_id=None)
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "<HARD_STOP>" in instr
        assert "</HARD_STOP>" in instr
        assert "<stage_system_prompt>" in instr
        assert "</stage_system_prompt>" in instr
        assert "odysseus_routing_input" in instr
        assert "get_pipeline_status" in instr
        assert "submit_input_report" in instr
        assert "Stage 1" in instr

    def test_stage2_has_subagent_instruction(self, tmp_path: Path) -> None:
        _setup_stage1(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1")
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "<HARD_STOP>" in instr
        assert "</HARD_STOP>" in instr
        assert "<stage_system_prompt>" in instr
        assert "</stage_system_prompt>" in instr
        assert "odysseus_data_validation" in instr
        assert "get_pipeline_status" in instr
        assert "validate_dataset" in instr
        assert "detect_and_parse_dataset" in instr
        assert "transform_dataset" in instr
        assert "save_routing_context" in instr

    def test_stage3_has_subagent_instruction(self, tmp_path: Path) -> None:
        _setup_through_validation(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1")
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "<HARD_STOP>" in instr
        assert "</HARD_STOP>" in instr
        assert "<stage_system_prompt>" in instr
        assert "</stage_system_prompt>" in instr
        assert "odysseus_routing_analysis" in instr
        assert "get_pipeline_status" in instr
        assert "create_seed_registry_tool" in instr
        assert "resolve_registry_tool" in instr
        assert "validate_rationale_card_set_tool" in instr
        assert "prune_registry_tool" in instr
        assert "stratified_split_tool" in instr

    def test_stage5_has_subagent_instruction(self, tmp_path: Path) -> None:
        _setup_through_stage4(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "<HARD_STOP>" in instr
        assert "<stage_system_prompt>" in instr
        assert "odysseus_prompt_builder" in instr

    def test_stage5_available_tools_correct(self, tmp_path: Path) -> None:
        """Stage 5 available_tools must not include optimize_routing_prompt (pipeline entry tool)."""
        _setup_through_stage4(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        tools = result["available_tools"]
        assert "optimize_routing_prompt" not in tools
        assert "init_search_state_tool" in tools
        assert "register_candidate_tool" in tools
        assert "record_eval_result_tool" in tools
        assert "advance_round_tool" in tools
        assert "get_search_state_tool" in tools
        assert "run_eval" in tools

    def test_stage6_build_phase_has_subagent_instruction(self, tmp_path: Path) -> None:
        """Stage 6 with no search state file -> defaults to build phase -> Prompt Builder."""
        _setup_through_stage5(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "<HARD_STOP>" in instr
        assert "</HARD_STOP>" in instr
        assert "<stage_system_prompt>" in instr
        assert "</stage_system_prompt>" in instr
        assert "odysseus_prompt_builder" in instr
        assert "get_pipeline_status" in instr
        assert "register_candidate_tool" in instr
        assert "run_eval" in instr

    def test_stage6_review_phase_has_subagent_instruction(self, tmp_path: Path) -> None:
        """Stage 6 with loop_phase=review -> Review Agent instruction."""
        _setup_through_stage5(tmp_path, "r1")
        search = tmp_path / "r1" / "search"
        search.mkdir(parents=True, exist_ok=True)
        (search / "search_state.json").write_text(
            json.dumps({"round": 1, "converged": False, "loop_phase": "review"})
        )
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "odysseus_review_agent" in instr
        assert "build_review_briefing_tool" in instr
        assert "record_directive_outcomes_tool" in instr

    def test_stage7_has_null_subagent_instruction(self, tmp_path: Path) -> None:
        # Stage 6 complete (converged=True), stage 7 not yet complete (no holdout report)
        _setup_through_stage6_converged(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 7
        assert result["subagent_instruction"] is None

    def test_no_runs_has_subagent_instruction(self, tmp_path: Path) -> None:
        result = get_pipeline_status(tmp_path, run_id=None)
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "odysseus_routing_input" in instr

    def test_stage2_available_tools_complete(self, tmp_path: Path) -> None:
        """available_tools for stage 2 includes all 4 stage tools."""
        _setup_stage1(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1")
        tools = result["available_tools"]
        assert "validate_dataset" in tools
        assert "detect_and_parse_dataset" in tools
        assert "transform_dataset" in tools
        assert "save_routing_context" in tools

    def test_stage3_available_tools_complete(self, tmp_path: Path) -> None:
        """available_tools for stage 3 includes all 5 stage tools."""
        _setup_through_validation(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1")
        tools = result["available_tools"]
        assert "create_seed_registry_tool" in tools
        assert "resolve_registry_tool" in tools
        assert "validate_rationale_card_set_tool" in tools
        assert "prune_registry_tool" in tools
        assert "stratified_split_tool" in tools

    def test_stage6_build_phase_available_tools(self, tmp_path: Path) -> None:
        """Build phase tools: eval tools present, review tools absent."""
        _setup_through_stage5(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        tools = result["available_tools"]
        for tool in [
            "init_search_state_tool", "register_candidate_tool",
            "record_eval_result_tool", "advance_round_tool",
            "get_search_state_tool", "run_eval",
        ]:
            assert tool in tools
        assert "build_review_briefing_tool" not in tools
        assert "record_directive_outcomes_tool" not in tools

    def test_stage6_review_phase_available_tools(self, tmp_path: Path) -> None:
        """Review phase tools: review tools present, eval mutation tools absent."""
        _setup_through_stage5(tmp_path, "r1")
        search = tmp_path / "r1" / "search"
        search.mkdir(parents=True, exist_ok=True)
        (search / "search_state.json").write_text(
            json.dumps({"round": 1, "converged": False, "loop_phase": "review"})
        )
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        tools = result["available_tools"]
        assert "build_review_briefing_tool" in tools
        assert "record_directive_outcomes_tool" in tools
        assert "get_search_state_tool" in tools
        assert "register_candidate_tool" not in tools
        assert "run_eval" not in tools


class TestStage6NewBehavior:
    """Stage 6 is complete only when converged == true."""

    def test_stage6_incomplete_when_round_gte_1_but_not_converged(self, tmp_path: Path) -> None:
        """round >= 1 no longer completes Stage 6."""
        _setup_through_stage5(tmp_path, "r1")
        search = tmp_path / "r1" / "search"
        search.mkdir(parents=True, exist_ok=True)
        (search / "search_state.json").write_text(
            json.dumps({"round": 3, "converged": False, "loop_phase": "review"})
        )
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][5]["status"] == "incomplete"   # Stage 6 index
        assert result["current_stage"] == 6

    def test_stage6_complete_when_converged(self, tmp_path: Path) -> None:
        _setup_through_stage5(tmp_path, "r1")
        search = tmp_path / "r1" / "search"
        search.mkdir(parents=True, exist_ok=True)
        (search / "search_state.json").write_text(
            json.dumps({"round": 5, "converged": True, "loop_phase": "build"})
        )
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][5]["status"] == "complete"
        assert result["current_stage"] == 7  # Holdout Validation


class TestStage6DynamicHardStop:
    """Stage 6 HARD_STOP depends on loop_phase."""

    def test_build_phase_spawns_prompt_builder(self, tmp_path: Path) -> None:
        _setup_through_stage5(tmp_path, "r1")
        search = tmp_path / "r1" / "search"
        search.mkdir(parents=True, exist_ok=True)
        (search / "search_state.json").write_text(
            json.dumps({"round": 1, "converged": False, "loop_phase": "build"})
        )
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 6
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "odysseus_prompt_builder" in instr
        # Eval tools present
        assert "register_candidate_tool" in result["available_tools"]
        assert "run_eval" in result["available_tools"]
        assert "advance_round_tool" in result["available_tools"]
        # Review tools absent
        assert "build_review_briefing_tool" not in result["available_tools"]
        assert "record_directive_outcomes_tool" not in result["available_tools"]

    def test_review_phase_spawns_review_agent(self, tmp_path: Path) -> None:
        _setup_through_stage5(tmp_path, "r1")
        search = tmp_path / "r1" / "search"
        search.mkdir(parents=True, exist_ok=True)
        (search / "search_state.json").write_text(
            json.dumps({"round": 1, "converged": False, "loop_phase": "review"})
        )
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 6
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "odysseus_review_agent" in instr
        # Review tools present
        assert "build_review_briefing_tool" in result["available_tools"]
        assert "record_directive_outcomes_tool" in result["available_tools"]
        # Eval tools absent
        assert "register_candidate_tool" not in result["available_tools"]
        assert "run_eval" not in result["available_tools"]

    def test_no_search_state_defaults_to_build_phase(self, tmp_path: Path) -> None:
        """Stage 6 before any search state exists: treat as build phase."""
        _setup_through_stage5(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 6
        assert "odysseus_prompt_builder" in result["subagent_instruction"]


def _setup_stage1(base: Path, run_id: str) -> None:
    (base / run_id / "input").mkdir(parents=True, exist_ok=True)
    (base / run_id / "input" / "input_report.md").write_text("# Report")


def _setup_through_stage4(base: Path, run_id: str) -> None:
    _setup_through_validation(base, run_id)
    _setup_analysis(base, run_id)
    (base / "backends").mkdir(parents=True, exist_ok=True)
    (base / "backends" / "mock.yaml").write_text("label: mock")


def _setup_through_stage5(base: Path, run_id: str) -> None:
    _setup_through_validation(base, run_id)
    _setup_analysis(base, run_id)
    # Stage 4: backends dir under base so _check_stage_4 finds it when
    # get_pipeline_status is called with project_dir=base.
    (base / "backends").mkdir(parents=True, exist_ok=True)
    (base / "backends" / "mock.yaml").write_text("label: mock")
    # Stage 5: v1 prompt
    (base / run_id / "prompts").mkdir(parents=True, exist_ok=True)
    (base / run_id / "prompts" / "v1.yaml").write_text("prompt: test")


def _setup_through_stage6_converged(base: Path, run_id: str) -> None:
    """Stage 6 complete (converged=True), Stage 7 not yet complete (no holdout report)."""
    _setup_through_stage5(base, run_id)
    search = base / run_id / "search"
    search.mkdir(parents=True, exist_ok=True)
    (search / "search_state.json").write_text(
        json.dumps({"round": 5, "converged": True, "loop_phase": "build"})
    )
