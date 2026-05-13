import json
import time
from pathlib import Path

from odysseus.agents.pipeline.instructions import (
    STAGE_4_BUILD_INSTRUCTION,
    _STAGE_4_BUILD_OPTIMIZE_INSTRUCTION,
    _STAGE_4_BUILD_RECOVERING_INSTRUCTION,
    _STAGE_4_BUILD_V1_INSTRUCTION,
)
from odysseus.agents.pipeline.status import (
    _detect_stage_4_phase,
    _read_rerun_config,
    discover_runs,
    get_pipeline_status,
)


class TestReadRerunConfig:
    def test_returns_none_when_no_file(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        assert _read_rerun_config(run_dir) is None

    def test_returns_dict_when_file_exists(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        config = {
            "mode": "rerun",
            "source_prompt_version": "v3",
            "original_backend": "anthropic",
            "new_backend": None,
        }
        (run_dir / "rerun_config.json").write_text(json.dumps(config))
        result = _read_rerun_config(run_dir)
        assert result is not None
        assert result["source_prompt_version"] == "v3"
        assert result["new_backend"] is None

    def test_returns_none_on_malformed_json(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        (run_dir / "rerun_config.json").write_text("not valid json {")
        assert _read_rerun_config(run_dir) is None


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
        """Stage 2 is complete only when validation files AND split outputs are present."""
        _setup_through_stage2(tmp_path, "abc12345")
        result = get_pipeline_status(tmp_path, "abc12345", project_dir=tmp_path)
        assert result["stages"][1]["status"] == "complete"
        assert result["current_stage"] == 3

    def test_validation_without_split_incomplete(self, tmp_path: Path) -> None:
        """Stage 2 incomplete when split outputs (dev.jsonl, holdout.jsonl) are missing."""
        _setup_stage1(tmp_path, "abc12345")
        (tmp_path / "abc12345" / "validation").mkdir(parents=True, exist_ok=True)
        for f in ["transformed.jsonl", "data_quality_report.json", "routing_context.json"]:
            (tmp_path / "abc12345" / "validation" / f).write_text("{}")
        result = get_pipeline_status(tmp_path, "abc12345")
        assert result["stages"][1]["status"] == "incomplete"
        assert result["current_stage"] == 2

    def test_critical_schema_fail_blocks_stage_2(self, tmp_path: Path) -> None:
        """Stage 2 is incomplete with detail 'data_quality_critical_fail' when the
        data quality report has any critical-severity failure, even if all artifact
        files exist."""
        _setup_through_stage2(tmp_path, "abc12345")
        report = {
            "schema_findings": [
                {
                    "field": "route_in_routes",
                    "status": "fail",
                    "severity": "critical",
                    "violation": "expected.route not found in expected.routes keys",
                    "row_indices": [0, 1, 2],
                }
            ]
        }
        (tmp_path / "abc12345" / "validation" / "data_quality_report.json").write_text(json.dumps(report))
        result = get_pipeline_status(tmp_path, "abc12345", project_dir=tmp_path)
        assert result["stages"][1]["status"] == "incomplete"
        assert result["stages"][1]["detail"] == "data_quality_critical_fail"
        assert result["current_stage"] == 2

    def test_warning_severity_does_not_block(self, tmp_path: Path) -> None:
        """Warning-severity failures do not block stage completion."""
        _setup_through_stage2(tmp_path, "abc12345")
        report = {
            "schema_findings": [
                {
                    "field": "non_empty_routes",
                    "status": "fail",
                    "severity": "warning",
                    "violation": "expected.routes is empty",
                    "row_indices": [0],
                }
            ]
        }
        (tmp_path / "abc12345" / "validation" / "data_quality_report.json").write_text(json.dumps(report))
        result = get_pipeline_status(tmp_path, "abc12345", project_dir=tmp_path)
        assert result["stages"][1]["status"] == "complete"

    def test_blocked_stages(self, tmp_path: Path) -> None:
        (tmp_path / "abc12345" / "input").mkdir(parents=True)
        (tmp_path / "abc12345" / "input" / "input_report.md").write_text("# Report")
        result = get_pipeline_status(tmp_path, "abc12345")
        assert result["stages"][2]["status"] == "blocked"  # backend configured (stage 3)
        assert result["stages"][3]["status"] == "blocked"  # refinement loop (stage 4)

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


def _setup_stage1(base: Path, run_id: str) -> None:
    (base / run_id / "input").mkdir(parents=True, exist_ok=True)
    (base / run_id / "input" / "input_report.md").write_text("# Report")


def _setup_through_validation(base: Path, run_id: str) -> None:
    """Set up stage 1 + validation files only (no split outputs). Stage 2 will be incomplete."""
    _setup_stage1(base, run_id)
    (base / run_id / "validation").mkdir(parents=True, exist_ok=True)
    for f in ["transformed.jsonl", "data_quality_report.json", "routing_context.json"]:
        (base / run_id / "validation" / f).write_text("{}")


def _setup_through_stage2(base: Path, run_id: str) -> None:
    """Set up stages 1 and 2 complete: validation files + split outputs."""
    _setup_through_validation(base, run_id)
    analysis = base / run_id / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    for f in ["dev.jsonl", "holdout.jsonl"]:
        (analysis / f).write_text("{}")


def _setup_analysis(base: Path, run_id: str) -> None:
    """Create split output files required by stage 2."""
    analysis = base / run_id / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    for f in ["dev.jsonl", "holdout.jsonl"]:
        (analysis / f).write_text("{}")


def _setup_through_stage3(base: Path, run_id: str) -> None:
    """Set up stages 1-3 complete: validation + split + backend."""
    _setup_through_stage2(base, run_id)
    (base / "backends").mkdir(parents=True, exist_ok=True)
    (base / "backends" / "mock.yaml").write_text(
        "model: mock-model\n"
        "provider: mock_echo\n"
        "requests_per_minute: 100\n"
        "tokens_per_minute: 100000\n"
        "pricing:\n"
        "  input_cost_per_million_tokens: 0.0\n"
        "  cached_cost_per_million_tokens: 0.0\n"
        "  output_cost_per_million_tokens: 0.0\n"
    )


def _setup_stage4_cold_start_done(base: Path, run_id: str) -> None:
    """Stage 4 after cold-start: directive_history exists, no v1, no search_state."""
    _setup_through_stage3(base, run_id)
    search = base / run_id / "search"
    search.mkdir(parents=True, exist_ok=True)
    (search / "child_variants.json").write_text("[]")


def _setup_stage4_v1_done(base: Path, run_id: str) -> None:
    """Stage 4 after v1: v1 exists, search_state exists, not converged."""
    _setup_stage4_cold_start_done(base, run_id)
    (base / run_id / "prompts").mkdir(parents=True, exist_ok=True)
    (base / run_id / "prompts" / "v1.txt").write_text("prompt: test")
    search = base / run_id / "search"
    (search / "search_state.json").write_text(json.dumps({"round": 1, "converged": False, "loop_phase": "review"}))


def _setup_stage4_converged(base: Path, run_id: str) -> None:
    """Stage 4 complete: converged=True."""
    _setup_stage4_v1_done(base, run_id)
    search = base / run_id / "search"
    (search / "search_state.json").write_text(json.dumps({"round": 5, "converged": True, "loop_phase": "build"}))


class TestSubagentInstruction:
    """subagent_instruction field is present and correctly populated."""

    def test_stage1_has_subagent_instruction(self, tmp_path: Path) -> None:
        result = get_pipeline_status(tmp_path, run_id=None)
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "<HARD_STOP>" in instr
        assert "</HARD_STOP>" in instr
        # The stage system prompt is no longer embedded in subagent_instruction;
        # it is returned by start_stage in the sub_agent_prompt field.
        assert "<stage_system_prompt></stage_system_prompt>" not in instr
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
        # The stage system prompt is no longer embedded in subagent_instruction;
        # it is returned by start_stage in the sub_agent_prompt field.
        assert "<stage_system_prompt></stage_system_prompt>" not in instr
        assert "get_pipeline_status" in instr
        assert "validate_dataset" in instr
        assert "detect_and_parse_dataset" in instr
        assert "transform_dataset" in instr
        assert "save_routing_context" in instr
        assert "stratified_split_tool" in instr

    def test_stage4_has_subagent_instruction(self, tmp_path: Path) -> None:
        """Stage 4 initial dispatch has a subagent instruction (cold-start on trunk)."""
        _setup_through_stage3(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "<HARD_STOP>" in instr
        assert "<stage_system_prompt></stage_system_prompt>" not in instr
        assert result["activate_prompt"] == "odysseus_review_agent_cold_start"

    def test_stage4_available_tools_correct(self, tmp_path: Path) -> None:
        """Stage 4 cold-start available_tools should include review tools."""
        _setup_through_stage3(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        tools = result["available_tools"]
        assert "optimize_routing_prompt" not in tools
        assert "build_review_briefing_tool" in tools
        assert "record_directive_outcomes_tool" in tools
        assert "get_search_state_tool" in tools

    def test_no_runs_has_subagent_instruction(self, tmp_path: Path) -> None:
        result = get_pipeline_status(tmp_path, run_id=None)
        instr = result["subagent_instruction"]
        assert instr is not None

    def test_stage2_available_tools_complete(self, tmp_path: Path) -> None:
        """available_tools for stage 2 includes all stage tools including stratified_split_tool."""
        _setup_stage1(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1")
        tools = result["available_tools"]
        assert "validate_dataset" in tools
        assert "detect_and_parse_dataset" in tools
        assert "transform_dataset" in tools
        assert "save_routing_context" in tools
        assert "stratified_split_tool" in tools

    def test_stage5_has_subagent_instruction(self, tmp_path: Path) -> None:
        """Stage 5 (Final Report) has a subagent instruction."""
        _setup_stage4_converged(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 5
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "HARD_STOP" in instr
        assert "final_report" in instr
        assert "build_final_report_briefing_tool" in instr
        assert "save_final_report" in instr


class TestStage4ThreePhaseDetection:
    """Stage 4 phase detection: trunk uses hill-climb three-phase logic."""

    def test_cold_start_when_no_files(self, tmp_path: Path) -> None:
        # On trunk, _ensure_stage4_search_state fails (RuntimeError, caught and logged),
        # so no search_state.json is created → phase detector returns 'cold_start'.
        _setup_through_stage3(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 4
        assert result["activate_prompt"] == "odysseus_review_agent_cold_start"

    def test_build_v1_after_cold_start(self, tmp_path: Path) -> None:
        # After cold-start: child_variants.json exists but no v1 prompt.
        # Phase detector returns 'build_v1' → prompt builder is dispatched.
        _setup_stage4_cold_start_done(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 4
        assert result["activate_prompt"] == "odysseus_prompt_builder"

    def test_normal_loop_review_phase(self, tmp_path: Path) -> None:
        _setup_stage4_v1_done(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 4
        assert result["activate_prompt"] == "odysseus_review_agent_iterative"

    def test_normal_loop_build_phase(self, tmp_path: Path) -> None:
        _setup_stage4_v1_done(tmp_path, "r1")
        search = tmp_path / "r1" / "search"
        (search / "search_state.json").write_text(json.dumps({"round": 1, "converged": False, "loop_phase": "build"}))
        # Defense-in-depth guard: build_dispatched.json must exist to confirm
        # the Prompt Builder is in-flight (otherwise phase is re-flipped to review).
        (search / "build_dispatched.json").write_text(json.dumps({"round": 1}))
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 4
        assert result["activate_prompt"] == "odysseus_prompt_builder"

    def test_stage4_complete_when_converged(self, tmp_path: Path) -> None:
        _setup_stage4_converged(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][3]["status"] == "complete"
        assert result["current_stage"] == 5

    def test_stage4_incomplete_when_not_converged(self, tmp_path: Path) -> None:
        _setup_stage4_v1_done(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][3]["status"] == "incomplete"
        assert result["current_stage"] == 4

    def test_cold_start_available_tools(self, tmp_path: Path) -> None:
        _setup_through_stage3(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        tools = result["available_tools"]
        assert "build_review_briefing_tool" in tools
        assert "record_directive_outcomes_tool" in tools
        assert "get_search_state_tool" in tools

    def test_build_phase_available_tools(self, tmp_path: Path) -> None:
        _setup_stage4_v1_done(tmp_path, "r1")
        search = tmp_path / "r1" / "search"
        (search / "search_state.json").write_text(json.dumps({"round": 1, "converged": False, "loop_phase": "build"}))
        # Defense-in-depth guard: build_dispatched.json must exist so the
        # phase is not re-flipped to review.
        (search / "build_dispatched.json").write_text(json.dumps({"round": 1}))
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        tools = result["available_tools"]
        assert "init_search_state_tool" in tools
        assert "register_candidate_tool" in tools
        assert "run_eval" in tools
        assert "build_review_briefing_tool" not in tools

    def test_review_phase_available_tools(self, tmp_path: Path) -> None:
        _setup_stage4_v1_done(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        tools = result["available_tools"]
        assert "build_review_briefing_tool" in tools
        assert "record_directive_outcomes_tool" in tools
        assert "register_candidate_tool" not in tools


class TestStage3PricingValidation:
    def test_incomplete_when_yaml_has_no_pricing(self, tmp_path: Path) -> None:
        """Stage 3 is incomplete when backend YAML exists but has no pricing."""
        _setup_through_stage2(tmp_path, "r1")
        backends = tmp_path / "backends"
        backends.mkdir(parents=True, exist_ok=True)
        (backends / "mock.yaml").write_text(
            "model: claude-haiku-4-5\nprovider: anthropic\nrequests_per_minute: 100\ntokens_per_minute: 100000\n"
        )
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][1]["status"] == "complete"
        assert result["stages"][2]["status"] == "incomplete"
        assert result["stages"][2]["detail"] == "pricing_missing"

    def test_incomplete_when_yaml_is_malformed(self, tmp_path: Path) -> None:
        """Stage 3 treats malformed YAML as incomplete, not a crash."""
        _setup_through_stage2(tmp_path, "r1")
        backends = tmp_path / "backends"
        backends.mkdir(parents=True, exist_ok=True)
        (backends / "bad.yaml").write_text("not: valid: yaml: [")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][2]["status"] == "incomplete"

    def test_complete_when_one_backend_has_pricing(self, tmp_path: Path) -> None:
        """Stage 3 is complete when at least one backend has valid pricing (any-semantics)."""
        _setup_through_stage2(tmp_path, "r1")
        backends = tmp_path / "backends"
        backends.mkdir(parents=True, exist_ok=True)
        (backends / "no_pricing.yaml").write_text(
            "model: custom-model\nprovider: openai\nrequests_per_minute: 50\ntokens_per_minute: 50000\n"
        )
        (backends / "with_pricing.yaml").write_text(
            "model: claude-haiku-4-5\n"
            "provider: anthropic\n"
            "requests_per_minute: 100\n"
            "tokens_per_minute: 100000\n"
            "pricing:\n"
            "  input_cost_per_million_tokens: 0.80\n"
            "  cached_cost_per_million_tokens: 0.08\n"
            "  output_cost_per_million_tokens: 4.00\n"
        )
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][2]["status"] == "complete"


class TestStage3RerunMode:
    """Stage 3 in rerun mode: checks specific new_backend instead of any-with-pricing."""

    def _write_rerun_config(self, run_dir: Path, new_backend: str | None) -> None:
        config = {
            "mode": "rerun",
            "source_prompt_version": "v3",
            "original_backend": "anthropic",
            "new_backend": new_backend,
        }
        (run_dir / "rerun_config.json").write_text(json.dumps(config))

    def test_stage3_incomplete_when_new_backend_is_null(self, tmp_path: Path) -> None:
        """rerun_config.json present but new_backend is null → Stage 3 incomplete."""
        _setup_through_stage2(tmp_path, "r1")
        # Add an existing (priced) backend that would satisfy normal Stage 3
        (tmp_path / "backends").mkdir(parents=True, exist_ok=True)
        (tmp_path / "backends" / "anthropic.yaml").write_text(
            "model: claude-haiku-4-5\nprovider: anthropic\n"
            "requests_per_minute: 100\ntokens_per_minute: 100000\n"
            "pricing:\n"
            "  input_cost_per_million_tokens: 0.80\n"
            "  cached_cost_per_million_tokens: 0.08\n"
            "  output_cost_per_million_tokens: 4.00\n"
        )
        self._write_rerun_config(tmp_path / "r1", new_backend=None)
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][2]["status"] == "incomplete"

    def test_stage3_complete_when_new_backend_yaml_has_pricing(self, tmp_path: Path) -> None:
        """rerun_config.json with new_backend set, that YAML has pricing → Stage 3 complete."""
        _setup_through_stage2(tmp_path, "r1")
        (tmp_path / "backends").mkdir(parents=True, exist_ok=True)
        (tmp_path / "backends" / "openai.yaml").write_text(
            "model: gpt-4o\nprovider: openai\n"
            "requests_per_minute: 100\ntokens_per_minute: 100000\n"
            "pricing:\n"
            "  input_cost_per_million_tokens: 2.50\n"
            "  cached_cost_per_million_tokens: 1.25\n"
            "  output_cost_per_million_tokens: 10.00\n"
        )
        self._write_rerun_config(tmp_path / "r1", new_backend="openai")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][2]["status"] == "complete"

    def test_stage3_incomplete_when_new_backend_yaml_missing_pricing(self, tmp_path: Path) -> None:
        """rerun_config.json with new_backend set but that YAML lacks pricing → incomplete."""
        _setup_through_stage2(tmp_path, "r1")
        (tmp_path / "backends").mkdir(parents=True, exist_ok=True)
        (tmp_path / "backends" / "openai.yaml").write_text(
            "model: gpt-4o\nprovider: openai\nrequests_per_minute: 100\ntokens_per_minute: 100000\n"
        )
        self._write_rerun_config(tmp_path / "r1", new_backend="openai")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][2]["status"] == "incomplete"
        assert result["stages"][2]["detail"] == "pricing_missing"

    def test_stage3_incomplete_when_new_backend_yaml_does_not_exist(self, tmp_path: Path) -> None:
        """rerun_config.json references a backend YAML that doesn't exist → incomplete."""
        _setup_through_stage2(tmp_path, "r1")
        (tmp_path / "backends").mkdir(parents=True, exist_ok=True)
        self._write_rerun_config(tmp_path / "r1", new_backend="openai")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][2]["status"] == "incomplete"


class TestStage4RerunMode:
    """Stage 4 in rerun mode: skips three-phase logic, returns rerun instruction."""

    def _setup_rerun_ready(self, base: Path, run_id: str, new_backend: str = "openai") -> None:
        """Stages 1-3 complete in rerun mode: rerun_config set with new_backend."""
        _setup_through_stage2(base, run_id)
        (base / "backends").mkdir(parents=True, exist_ok=True)
        (base / "backends" / f"{new_backend}.yaml").write_text(
            "model: gpt-4o\nprovider: openai\n"
            "requests_per_minute: 100\ntokens_per_minute: 100000\n"
            "pricing:\n"
            "  input_cost_per_million_tokens: 2.50\n"
            "  cached_cost_per_million_tokens: 1.25\n"
            "  output_cost_per_million_tokens: 10.00\n"
        )
        rerun_config = {
            "mode": "rerun",
            "source_prompt_version": "v3",
            "original_backend": "anthropic",
            "new_backend": new_backend,
        }
        (base / run_id / "rerun_config.json").write_text(json.dumps(rerun_config))

    def test_rerun_mode_returns_rerun_instruction(self, tmp_path: Path) -> None:
        """Stage 4 with rerun_config.json returns odysseus_prompt_builder_rerun prompt."""
        self._setup_rerun_ready(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 4
        assert result["activate_prompt"] == "odysseus_prompt_builder_rerun"

    def test_rerun_mode_subagent_instruction_mentions_rerun(self, tmp_path: Path) -> None:
        """Rerun subagent instruction contains source_prompt_version and new_backend."""
        self._setup_rerun_ready(tmp_path, "r1", new_backend="openai")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "v3" in instr
        assert "openai" in instr
        assert "<HARD_STOP>" in instr

    def test_rerun_mode_available_tools_are_build_tools(self, tmp_path: Path) -> None:
        """Rerun mode exposes the same tools as the normal build phase."""
        self._setup_rerun_ready(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        tools = result["available_tools"]
        assert "init_search_state_tool" in tools
        assert "register_candidate_tool" in tools
        assert "run_eval" in tools
        assert "advance_step_tool" in tools
        assert "build_review_briefing_tool" not in tools

    def test_normal_stage4_unaffected_without_rerun_config(self, tmp_path: Path) -> None:
        """Without rerun_config.json, Stage 4 uses normal cold-start detection on trunk."""
        _setup_through_stage3(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["activate_prompt"] == "odysseus_review_agent_cold_start"


class TestStage5FinalReport:
    """Stage 5 (Final Report): holdout eval + report generation."""

    def test_stage5_reached_after_convergence(self, tmp_path: Path) -> None:
        """After stage 4 converges, current_stage is 5."""
        _setup_stage4_converged(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 5
        assert result["stages"][3]["status"] == "complete"  # stage 4

    def test_stage5_incomplete_without_report(self, tmp_path: Path) -> None:
        """Stage 5 incomplete when final_report.md does not exist."""
        _setup_stage4_converged(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][4]["status"] == "incomplete"

    def test_stage5_complete_with_report(self, tmp_path: Path) -> None:
        """Stage 5 is complete when reports/final_report.md exists."""
        _setup_stage4_converged(tmp_path, "r1")
        reports = tmp_path / "r1" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "final_report.md").write_text("# Final Report")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["stages"][4]["status"] == "complete"

    def test_stage5_has_subagent_instruction(self, tmp_path: Path) -> None:
        """Stage 5 has HARD_STOP subagent instruction with final report tools."""
        _setup_stage4_converged(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert result["current_stage"] == 5
        instr = result["subagent_instruction"]
        assert instr is not None
        assert "HARD_STOP" in instr
        assert "final_report" in instr
        assert "build_final_report_briefing_tool" in instr
        assert "save_final_report" in instr
        assert "run_holdout_eval" in instr
        assert "filter_holdout_dataset_tool" in instr

    def test_stage5_available_tools(self, tmp_path: Path) -> None:
        """Stage 5 available_tools includes all final report tools."""
        _setup_stage4_converged(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        tools = result["available_tools"]
        assert "filter_holdout_dataset_tool" in tools
        assert "run_holdout_eval" in tools
        assert "build_final_report_briefing_tool" in tools
        assert "save_final_report" in tools

    def test_pipeline_complete_after_stage5(self, tmp_path: Path) -> None:
        """Pipeline is complete after stage 5 report is written."""
        _setup_stage4_converged(tmp_path, "r1")
        reports = tmp_path / "r1" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "final_report.md").write_text("# Final Report")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        assert all(s["status"] == "complete" for s in result["stages"])
        assert "Pipeline complete" in result["next_action"]


class TestDiscoveredRuns:
    """get_pipeline_status includes discovered_runs with per-run summaries."""

    def test_discovered_runs_empty_when_no_outputs(self, tmp_path: Path) -> None:
        result = get_pipeline_status(tmp_path, run_id=None)
        assert result.get("discovered_runs") == []

    def test_discovered_runs_lists_all_runs(self, tmp_path: Path) -> None:
        _setup_stage1(tmp_path, "run_a")
        _setup_stage1(tmp_path, "run_b")
        result = get_pipeline_status(tmp_path, run_id=None)
        run_ids = [r["run_id"] for r in result["discovered_runs"]]
        assert "run_a" in run_ids
        assert "run_b" in run_ids

    def test_discovered_runs_has_converged_prompt_false_for_incomplete_stage4(self, tmp_path: Path) -> None:
        _setup_stage4_v1_done(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        entry = next(r for r in result["discovered_runs"] if r["run_id"] == "r1")
        assert entry["has_converged_prompt"] is False

    def test_discovered_runs_has_converged_prompt_true_for_converged(self, tmp_path: Path) -> None:
        _setup_stage4_converged(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1", project_dir=tmp_path)
        entry = next(r for r in result["discovered_runs"] if r["run_id"] == "r1")
        assert entry["has_converged_prompt"] is True

    def test_discovered_runs_includes_current_stage(self, tmp_path: Path) -> None:
        _setup_stage1(tmp_path, "r1")
        result = get_pipeline_status(tmp_path, "r1")
        entry = next(r for r in result["discovered_runs"] if r["run_id"] == "r1")
        assert entry["current_stage"] == 2


class TestDetectStage4PhaseRecovery:
    """_detect_stage_4_phase returns ("build", {"recover_active_evals": True}) when active_evals is non-empty."""

    def test_detect_stage_4_phase_returns_build_recovering(self, tmp_path: Path) -> None:
        """loop_phase='build' + active_evals non-empty → ("build", {"recover_active_evals": True})."""
        run_id = "r1"
        # Set up enough state for Phase 3 detection (past cold_review and first-build)
        search = tmp_path / run_id / "search"
        search.mkdir(parents=True, exist_ok=True)
        prompts = tmp_path / run_id / "prompts"
        prompts.mkdir(parents=True, exist_ok=True)
        (prompts / "v1.txt").write_text("prompt: seed")
        (search / "child_variants.json").write_text("[]")
        (search / "search_state.json").write_text(
            json.dumps(
                {
                    "round": 2,
                    "converged": False,
                    "loop_phase": "build",
                    "active_evals": ["v4"],
                }
            )
        )

        phase, flags = _detect_stage_4_phase(tmp_path / run_id, rerun_config=None)

        assert (phase, flags) == ("build", {"recover_active_evals": True})

    def test_detect_stage_4_phase_normal_build_without_active_evals(self, tmp_path: Path) -> None:
        """loop_phase='build' + empty active_evals + dispatched marker → ("build", {})."""
        run_id = "r1"
        search = tmp_path / run_id / "search"
        search.mkdir(parents=True, exist_ok=True)
        prompts = tmp_path / run_id / "prompts"
        prompts.mkdir(parents=True, exist_ok=True)
        (prompts / "v1.txt").write_text("prompt: seed")
        (search / "child_variants.json").write_text("[]")
        (search / "search_state.json").write_text(
            json.dumps(
                {
                    "round": 2,
                    "converged": False,
                    "loop_phase": "build",
                    "active_evals": [],
                }
            )
        )
        # Need the dispatch marker or defense-in-depth will flip to review
        (search / "build_dispatched.json").write_text(json.dumps({"round": 2}))

        phase, flags = _detect_stage_4_phase(tmp_path / run_id, rerun_config=None)

        assert (phase, flags) == ("build", {})


# ---------------------------------------------------------------------------
# Helper for Phase 3 setup (past cold_start and build_v1 gates)
# ---------------------------------------------------------------------------


def _setup_phase3_run(
    base: Path,
    run_id: str,
    loop_phase: str,
    round_: int,
    algorithm: str,
    active_evals: list[str] | None = None,
) -> Path:
    """Create a run dir that passes cold_start and build_v1 checks."""
    search = base / run_id / "search"
    search.mkdir(parents=True, exist_ok=True)
    prompts = base / run_id / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "v1.txt").write_text("prompt: seed")
    (search / "child_variants.json").write_text("[]")
    state: dict = {
        "round": round_,
        "converged": False,
        "loop_phase": loop_phase,
        "algorithm": algorithm,
    }
    if active_evals is not None:
        state["active_evals"] = active_evals
    (search / "search_state.json").write_text(json.dumps(state))
    return base / run_id


class TestDetectStage4PhasePostColdstart:
    """_detect_stage_4_phase post-coldstart phase detection."""

    def test_hill_climb_round1_review_returns_review(self, tmp_path: Path) -> None:
        """Gate: algorithm != 'beam' → returns ("review", {}), not post-coldstart."""
        run_dir = _setup_phase3_run(tmp_path, "r1", "review", round_=1, algorithm="hill_climb")
        phase, flags = _detect_stage_4_phase(run_dir, rerun_config=None)
        assert (phase, flags) == ("review", {})

    def test_beam_round2_review_returns_review(self, tmp_path: Path) -> None:
        """Gate: round != 1 → returns ("review", {}), not post-coldstart."""
        run_dir = _setup_phase3_run(tmp_path, "r1", "review", round_=2, algorithm="beam")
        phase, flags = _detect_stage_4_phase(run_dir, rerun_config=None)
        assert (phase, flags) == ("review", {})

    def test_beam_round1_build_phase_returns_build(self, tmp_path: Path) -> None:
        """Gate: loop_phase != 'review' → returns ("build", {}), not post-coldstart."""
        run_dir = _setup_phase3_run(tmp_path, "r1", "build", round_=1, algorithm="beam", active_evals=[])
        # Need the dispatch marker so defense-in-depth doesn't flip to review
        (run_dir / "search" / "build_dispatched.json").write_text(json.dumps({"round": 1}))
        phase, flags = _detect_stage_4_phase(run_dir, rerun_config=None)
        assert (phase, flags) == ("build", {})


class TestStage4BuildInstructionByteIdentical:
    """STAGE_4_BUILD_INSTRUCTION callable produces byte-identical output to the old constants."""

    def test_first_round_matches_v1_constant(self) -> None:
        result = STAGE_4_BUILD_INSTRUCTION(is_first_round=True)
        assert result == _STAGE_4_BUILD_V1_INSTRUCTION

    def test_steady_state_matches_optimize_constant(self) -> None:
        result = STAGE_4_BUILD_INSTRUCTION()
        assert result == _STAGE_4_BUILD_OPTIMIZE_INSTRUCTION

    def test_recovery_matches_recovering_constant(self) -> None:
        result = STAGE_4_BUILD_INSTRUCTION(recover_active_evals=True)
        assert result == _STAGE_4_BUILD_RECOVERING_INSTRUCTION

    def test_first_round_has_no_dispatch_context(self) -> None:
        result = STAGE_4_BUILD_INSTRUCTION(is_first_round=True)
        assert "<DISPATCH_CONTEXT>" not in result

    def test_steady_state_has_dispatch_context(self) -> None:
        result = STAGE_4_BUILD_INSTRUCTION()
        assert result.startswith("<DISPATCH_CONTEXT>")

    def test_recovery_has_run_batch_eval_in_tools(self) -> None:
        result = STAGE_4_BUILD_INSTRUCTION(recover_active_evals=True)
        assert "run_batch_eval" in result

    def test_non_recovery_has_no_run_batch_eval(self) -> None:
        for variant in [STAGE_4_BUILD_INSTRUCTION(), STAGE_4_BUILD_INSTRUCTION(is_first_round=True)]:
            assert "run_batch_eval" not in variant

    def test_recovery_has_recovery_mode_paragraph(self) -> None:
        result = STAGE_4_BUILD_INSTRUCTION(recover_active_evals=True)
        assert "RECOVERY MODE" in result
