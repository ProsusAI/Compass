"""EvalRunnerAgent — orchestrates a single evaluation run."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from odysseus.agents.base import BaseAgent
from odysseus.eval import controller
from odysseus.eval.backends.registry import BackendRegistry
from odysseus.eval.collector import JsonResultsCollector
from odysseus.eval.dataset import JsonlDatasetManager
from odysseus.eval.metrics import create_default_engine
from odysseus.eval.models import RunConfig, RunReport, ScoreReport
from odysseus.eval.protocols import RunDependencies
from odysseus.project_dir import get_project_dir
from odysseus.prompts.manager import FilePromptManager

logger = logging.getLogger(__name__)


class EvalRunnerAgent(BaseAgent):
    """Orchestrates a single evaluation run.

    This agent is used inside the Odysseus pipeline. It extracts parameters
    from the pipeline context, calls the eval controller directly, and returns
    a structured ScoreReport. No internal LLM — the external MCP client
    (Claude Desktop, Cursor, etc.) drives the agent behavior.
    """

    @property
    def name(self) -> str:
        return "eval_runner"

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute an evaluation run.

        Expected context keys:
            prompt_version: str — prompt version to evaluate.
            data_source: str — path to the JSONL dataset.
            backend: str — backend label matching a profile in backends/.
            run_id: str | None — pipeline run identifier; when provided, prompts
                are loaded from outputs/<run_id>/prompts/.

        Config resolution (one of):
            run_config: RunConfig — pre-built config (pipeline runs). Skips YAML.
            config_path: str — path to YAML run config (standalone runs).

        Returns:
            Dict with ScoreReport.CONTEXT_KEY -> ScoreReport on success,
            or {"error": {"category": ..., "detail": ...}} on failure.
        """
        prompt_version = context.get("prompt_version", "latest")
        data_source = context.get("data_source", "")
        backend_label = context.get("backend", "default")
        run_id: str | None = context.get("run_id")

        # 1. Resolve config: pre-built (pipeline) or YAML (standalone)
        pre_built: RunConfig | None = context.get("run_config")
        if pre_built is not None:
            config = pre_built
        else:
            config_path = context.get("config_path", "outputs/run_config.yaml")
            try:
                config = self._load_config(
                    config_path=config_path,
                    prompt_version=prompt_version,
                    data_source=data_source,
                    backend=backend_label,
                )
            except FileNotFoundError as e:
                return {"error": {"category": "not_found", "detail": str(e)}}
            except (ValueError, ValidationError) as e:
                return {"error": {"category": "validation_error", "detail": str(e)}}

        # 2. Wire dependencies
        try:
            deps = self._wire_dependencies(config, run_id=run_id)
        except KeyError as e:
            return {"error": {"category": "not_found", "detail": str(e)}}

        # 3. Load previous report for diffing (before the run overwrites it)
        previous_report = self._load_previous_report(config.output.report_path)

        # 4. Run the eval
        try:
            report = await controller.run(config, deps)
        except FileNotFoundError as e:
            return {"error": {"category": "not_found", "detail": str(e)}}
        except PermissionError as e:
            return {"error": {"category": "permission_denied", "detail": str(e)}}
        except Exception as e:
            logger.error("Eval run failed: %s", e)
            return {"error": {"category": "run_error", "detail": str(e)}}

        # 5. Build and return ScoreReport
        score_report = ScoreReport.from_run_report(
            report,
            report_path=config.output.report_path,
            results_path=config.output.results_path,
            previous_report=previous_report,
        )
        return {ScoreReport.CONTEXT_KEY: score_report}

    def _load_config(
        self,
        config_path: str,
        prompt_version: str,
        data_source: str,
        backend: str,
    ) -> RunConfig:
        """Load YAML config and overlay agent-controlled parameters."""
        with open(config_path) as f:
            config_data: dict = yaml.safe_load(f) or {}

        # Tool params override YAML values
        config_data["backend"] = backend
        config_data["prompt_version"] = prompt_version
        config_data["data_source"] = data_source
        return RunConfig.model_validate(config_data)

    def _wire_dependencies(self, config: RunConfig, run_id: str | None = None) -> RunDependencies:
        """Construct RunDependencies from config."""
        project = get_project_dir()
        registry = BackendRegistry.from_directory(project / "backends")
        profile = registry.get_profile(config.backend)
        backend_instance = registry.create_backend(config.backend)

        prompts_dir = project / "outputs" / run_id / "prompts" if run_id is not None else project / "prompts"

        return RunDependencies(
            backend=backend_instance,
            prompt_manager=FilePromptManager(prompts_dir=prompts_dir),
            dataset_manager=JsonlDatasetManager(),
            metrics_engine=create_default_engine(),
            results_collector=JsonResultsCollector(),
            requests_per_minute=profile.requests_per_minute,
            tokens_per_minute=profile.tokens_per_minute,
        )

    def _load_previous_report(self, report_path: str) -> RunReport | None:
        """Try to load a previous report for diffing. Returns None if unavailable."""
        p = Path(report_path)
        if not p.exists():
            return None
        try:
            return RunReport.model_validate_json(p.read_text())
        except Exception:
            logger.warning("Failed to load previous report at %s for diffing", report_path, exc_info=True)
            return None
