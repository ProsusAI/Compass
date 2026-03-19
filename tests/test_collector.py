"""Tests for the results collector."""

import json
import logging  # noqa: F401
from datetime import UTC, datetime  # noqa: F401

from odysseus.eval.collector import JsonResultsCollector
from odysseus.eval.models import (
    EvalResult,
    MetricConfig,  # noqa: F401
    OutputConfig,  # noqa: F401
    RunConfig,  # noqa: F401
    RunReport,  # noqa: F401
    RunSummary,  # noqa: F401
    TokenUsage,
)
from odysseus.eval.protocols import ResultsCollector  # noqa: F401


def _make_result(example_id: str = "ex-1", error: str | None = None) -> EvalResult:
    return EvalResult(
        example_id=example_id,
        model="test-model",
        output={"answer": "42"} if error is None else None,
        error=error,
        latency_ms=123.4,
        retries=0,
        token_usage=TokenUsage(input_tokens=10, cached_tokens=0, output_tokens=5) if error is None else None,
        cost=0.001 if error is None else None,
    )


def test_write_results_creates_jsonl(tmp_path):
    """Each EvalResult is written as one JSON line."""
    collector = JsonResultsCollector()
    results = [_make_result("ex-1"), _make_result("ex-2")]
    path = str(tmp_path / "results.jsonl")

    collector.write_results(results, path)

    lines = (tmp_path / "results.jsonl").read_text().strip().split("\n")
    assert len(lines) == 2
    parsed = json.loads(lines[0])
    assert parsed["example_id"] == "ex-1"
    assert parsed["model"] == "test-model"


def test_write_results_empty_list(tmp_path):
    """Empty results list produces an empty file."""
    collector = JsonResultsCollector()
    path = str(tmp_path / "results.jsonl")

    collector.write_results([], path)

    assert (tmp_path / "results.jsonl").read_text() == ""
