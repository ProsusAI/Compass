"""Concrete ResultsCollector implementation — writes JSONL results and JSON reports."""

from __future__ import annotations

from odysseus.eval.models import EvalResult, RunReport


class JsonResultsCollector:
    """Persists evaluation results as JSONL and reports as pretty-printed JSON."""

    def write_results(self, results: list[EvalResult], path: str) -> None:
        """Write each EvalResult as a JSON line to *path*."""
        with open(path, "w") as f:
            for result in results:
                f.write(result.model_dump_json() + "\n")

    def write_report(self, report: RunReport, path: str) -> None:
        """Write the full RunReport as pretty-printed JSON to *path*."""
        with open(path, "w") as f:
            f.write(report.model_dump_json(indent=2) + "\n")
