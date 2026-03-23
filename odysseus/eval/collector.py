"""Concrete ResultsCollector implementation — writes JSONL results and JSON reports."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from odysseus.eval.diff import compute_metric_diffs
from odysseus.eval.models import EvalResult, RunReport

logger = logging.getLogger(__name__)


class JsonResultsCollector:
    """Persists evaluation results as JSONL and reports as pretty-printed JSON."""

    def write_results(self, results: list[EvalResult], path: str) -> None:
        """Write each EvalResult as a JSON line to *path*."""
        with open(path, "w") as f:
            for result in results:
                f.write(result.model_dump_json() + "\n")

    def append_result(self, result: EvalResult, path: str) -> None:
        """Append a single EvalResult as a JSON line to *path*."""
        with open(path, "a") as f:
            f.write(result.model_dump_json() + "\n")

    def read_completed_ids(self, path: str) -> set[str]:
        """Read example IDs from a partial results file.

        Returns an empty set if the file does not exist or is empty.
        Skips malformed lines (e.g. from a truncated write).
        """
        p = Path(path)
        if not p.exists():
            return set()
        ids: set[str] = set()
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                eid = record.get("example_id")
                if eid is not None:
                    ids.add(eid)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed line in partial results: %s", path)
        return ids

    def write_report(self, report: RunReport, path: str) -> None:
        """Write the full RunReport as pretty-printed JSON to *path*.

        If a previous report exists at *path*, log a human-readable diff
        of changed metrics and router overhead at INFO level.
        """
        previous = self._read_previous_report(path)

        with open(path, "w") as f:
            f.write(report.model_dump_json(indent=2) + "\n")

        if previous is not None:
            old_metrics = previous.get("metrics")
            if old_metrics is not None:
                self._log_metric_diff(old_metrics, report.metrics)

            old_summary = previous.get("summary")
            if old_summary is not None:
                self._log_overhead_diff(old_summary, report.summary.total_cost, report.summary.duration_seconds)

    @staticmethod
    def _read_previous_report(path: str) -> dict[str, Any] | None:
        """Read the full previous report dict, or return None."""
        p = Path(path)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _log_metric_diff(old: dict[str, float], new: dict[str, float]) -> None:
        """Log changed, added, and removed metrics."""
        diffs = compute_metric_diffs(old, new)
        if not diffs:
            return
        lines: list[str] = []
        for d in diffs:
            if d.status == "changed":
                lines.append(f"  {d.key}: {d.old} → {d.new}")
            elif d.status == "added":
                lines.append(f"  {d.key}: (new) {d.new}")
            else:
                lines.append(f"  {d.key}: {d.old} (removed)")
        logger.info("Metric diff vs previous run:\n%s", "\n".join(lines))

    @staticmethod
    def _log_overhead_diff(
        old_summary: dict[str, Any],
        new_cost: float,
        new_duration: float,
    ) -> None:
        """Log router overhead changes (cost and latency).

        Preserves original behavior: logs cost diff even if old_duration is
        missing, and vice versa.
        """
        old_cost = old_summary.get("total_cost")
        old_duration = old_summary.get("duration_seconds")
        diffs: list[str] = []
        if old_cost is not None and old_cost != new_cost:
            diffs.append(f"  cost: ${old_cost:.4f} → ${new_cost:.4f}")
        if old_duration is not None and old_duration != new_duration:
            diffs.append(f"  latency: {old_duration}s → {new_duration}s")
        if diffs:
            logger.info("Router overhead diff vs previous run:\n%s", "\n".join(diffs))
