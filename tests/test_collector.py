# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Tests for the results collector."""

import json
import logging  # noqa: F401
from datetime import UTC, datetime  # noqa: F401

from compass.eval.collector import JsonResultsCollector
from compass.eval.models import (
    EvalResult,
    MetricConfig,  # noqa: F401
    OutputConfig,  # noqa: F401
    RunConfig,  # noqa: F401
    RunFingerprint,
    RunReport,  # noqa: F401
    RunSummary,  # noqa: F401
    TokenUsage,
)
from compass.eval.protocols import ResultsCollector  # noqa: F401


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


def _make_report(metrics: dict[str, float] | None = None) -> RunReport:
    config = RunConfig(
        backend="test-model",
        data_source="data/test.jsonl",
        metrics=[MetricConfig(name="accuracy")],
        output=OutputConfig(),
    )
    now = datetime.now(UTC)
    return RunReport(
        config=config,
        metrics=metrics or {"accuracy": 0.85},
        results=[_make_result()],
        summary=RunSummary(
            total=1,
            succeeded=1,
            failed=0,
            total_cost=0.001,
            start_time=now,
            end_time=now,
            duration_seconds=1.0,
        ),
    )


def test_write_report_creates_json(tmp_path):
    """Report is written as pretty-printed JSON."""
    collector = JsonResultsCollector()
    report = _make_report()
    path = str(tmp_path / "report.json")

    collector.write_report(report, path)

    content = (tmp_path / "report.json").read_text()
    parsed = json.loads(content)
    assert parsed["metrics"]["accuracy"] == 0.85
    assert parsed["summary"]["total"] == 1
    # Verify it's indented (pretty-printed)
    assert "\n" in content


def test_write_report_logs_diff_when_previous_exists(tmp_path, caplog):
    """When a previous report exists, metric changes are logged at INFO."""
    collector = JsonResultsCollector()
    path = str(tmp_path / "report.json")

    # Write first report
    old_report = _make_report(metrics={"accuracy": 0.82, "f1": 0.75})
    collector.write_report(old_report, path)

    # Write second report to same path
    new_report = _make_report(metrics={"accuracy": 0.85, "f1": 0.75})
    with caplog.at_level(logging.INFO, logger="compass.eval.collector"):
        collector.write_report(new_report, path)

    assert "accuracy: 0.82 → 0.85" in caplog.text
    # f1 unchanged — should not appear in diff
    assert "f1" not in caplog.text


def test_write_report_no_diff_on_first_run(tmp_path, caplog):
    """No diff is logged when there is no previous report."""
    collector = JsonResultsCollector()
    path = str(tmp_path / "report.json")

    report = _make_report(metrics={"accuracy": 0.85})
    with caplog.at_level(logging.INFO, logger="compass.eval.collector"):
        collector.write_report(report, path)

    assert "→" not in caplog.text


def test_write_report_diff_handles_new_and_removed_metrics(tmp_path, caplog):
    """Diff logs new metrics and removed metrics."""
    collector = JsonResultsCollector()
    path = str(tmp_path / "report.json")

    old_report = _make_report(metrics={"accuracy": 0.80, "old_metric": 0.50})
    collector.write_report(old_report, path)

    new_report = _make_report(metrics={"accuracy": 0.85, "new_metric": 0.90})
    with caplog.at_level(logging.INFO, logger="compass.eval.collector"):
        collector.write_report(new_report, path)

    assert "accuracy: 0.8 → 0.85" in caplog.text
    assert "new_metric: (new) 0.9" in caplog.text
    assert "old_metric: 0.5 (removed)" in caplog.text


def _make_report_with_overhead(
    metrics: dict[str, float] | None = None,
    total_cost: float = 0.001,
    duration_seconds: float = 1.0,
) -> RunReport:
    config = RunConfig(
        backend="test-model",
        data_source="data/test.jsonl",
        metrics=[MetricConfig(name="accuracy")],
        output=OutputConfig(),
    )
    now = datetime.now(UTC)
    return RunReport(
        config=config,
        metrics=metrics or {"accuracy": 0.85},
        results=[_make_result()],
        summary=RunSummary(
            total=1,
            succeeded=1,
            failed=0,
            total_cost=total_cost,
            start_time=now,
            end_time=now,
            duration_seconds=duration_seconds,
        ),
    )


def test_write_report_logs_router_overhead_diff(tmp_path, caplog):
    """Router overhead (cost + latency) changes are logged."""
    collector = JsonResultsCollector()
    path = str(tmp_path / "report.json")

    old_report = _make_report_with_overhead(total_cost=0.0500, duration_seconds=12.5)
    collector.write_report(old_report, path)

    new_report = _make_report_with_overhead(total_cost=0.0350, duration_seconds=9.8)
    with caplog.at_level(logging.INFO, logger="compass.eval.collector"):
        collector.write_report(new_report, path)

    assert "Router overhead" in caplog.text
    assert "cost: $0.0500 → $0.0350" in caplog.text
    assert "latency: 12.5s → 9.8s" in caplog.text


def test_write_report_no_overhead_diff_when_unchanged(tmp_path, caplog):
    """No router overhead section when cost and latency are unchanged."""
    collector = JsonResultsCollector()
    path = str(tmp_path / "report.json")

    old_report = _make_report_with_overhead(total_cost=0.05, duration_seconds=10.0)
    collector.write_report(old_report, path)

    new_report = _make_report_with_overhead(total_cost=0.05, duration_seconds=10.0)
    with caplog.at_level(logging.INFO, logger="compass.eval.collector"):
        collector.write_report(new_report, path)

    assert "Router overhead" not in caplog.text


def test_json_results_collector_satisfies_protocol():
    """JsonResultsCollector is a valid ResultsCollector."""
    collector = JsonResultsCollector()
    assert isinstance(collector, ResultsCollector)


def test_append_result(tmp_path):
    """append_result appends a single line without overwriting."""
    collector = JsonResultsCollector()
    path = str(tmp_path / "results.jsonl")

    r1 = _make_result("ex-1")
    r2 = _make_result("ex-2")

    collector.append_result(r1, path)
    collector.append_result(r2, path)

    lines = [line for line in (tmp_path / "results.jsonl").read_text().splitlines() if line.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["example_id"] == "ex-1"
    assert json.loads(lines[1])["example_id"] == "ex-2"


def test_read_completed_ids(tmp_path):
    """read_completed_ids returns IDs from a partial results file."""
    collector = JsonResultsCollector()
    path = str(tmp_path / "results.jsonl")

    r1 = _make_result("ex-1")
    r2 = _make_result("ex-2")
    collector.append_result(r1, path)
    collector.append_result(r2, path)

    ids = collector.read_completed_ids(path)
    assert ids == {"ex-1", "ex-2"}


def test_read_completed_ids_missing_file(tmp_path):
    """read_completed_ids returns empty set for nonexistent file."""
    collector = JsonResultsCollector()
    ids = collector.read_completed_ids(str(tmp_path / "nope.jsonl"))
    assert ids == set()


def test_read_completed_ids_skips_malformed_lines(tmp_path):
    """read_completed_ids skips truncated/malformed lines."""
    collector = JsonResultsCollector()
    path = tmp_path / "results.jsonl"

    r1 = _make_result("ex-1")
    path.write_text(r1.model_dump_json() + "\n" + '{"truncated": tru\n')

    ids = collector.read_completed_ids(str(path))
    assert ids == {"ex-1"}


def test_read_completed_ids_skips_errored_results(tmp_path):
    """read_completed_ids does not count errored results as completed."""
    collector = JsonResultsCollector()
    path = tmp_path / "results.jsonl"

    r_ok = _make_result("ex-1")
    r_err = _make_result("ex-2", error="Model returned non-JSON output")
    path.write_text(r_ok.model_dump_json() + "\n" + r_err.model_dump_json() + "\n")

    ids = collector.read_completed_ids(str(path))
    assert ids == {"ex-1"}


# --- Tests: RunFingerprint ---


def test_run_fingerprint_round_trip():
    """RunFingerprint serializes with __meta__ key and deserializes back."""
    fp = RunFingerprint.model_validate(
        {
            "__meta__": "run_fingerprint",
            "prompt_version": "v3",
            "backend": "anthropic",
            "data_source": "data/routing.jsonl",
        }
    )
    dumped = fp.model_dump(by_alias=True)
    assert dumped["__meta__"] == "run_fingerprint"
    assert dumped["prompt_version"] == "v3"

    restored = RunFingerprint.model_validate(dumped)
    assert restored == fp


def test_write_and_read_fingerprint(tmp_path):
    """write_fingerprint writes a __meta__ line; read_fingerprint reads it back."""
    collector = JsonResultsCollector()
    path = str(tmp_path / "results.jsonl")
    fp = RunFingerprint.model_validate(
        {
            "__meta__": "run_fingerprint",
            "prompt_version": "v3",
            "backend": "anthropic",
            "data_source": "data/routing.jsonl",
        }
    )
    collector.write_fingerprint(fp, path)

    result = collector.read_fingerprint(path)
    assert result is not None
    assert result == fp


def test_read_fingerprint_missing_file(tmp_path):
    """read_fingerprint returns None for a nonexistent file."""
    collector = JsonResultsCollector()
    assert collector.read_fingerprint(str(tmp_path / "nope.jsonl")) is None


def test_read_fingerprint_no_meta_line(tmp_path):
    """read_fingerprint returns None for a legacy file with no __meta__ header."""
    collector = JsonResultsCollector()
    path = tmp_path / "results.jsonl"
    r = _make_result("ex-1")
    path.write_text(r.model_dump_json() + "\n")

    assert collector.read_fingerprint(str(path)) is None


def test_read_completed_ids_skips_meta_line(tmp_path):
    """read_completed_ids ignores the __meta__ fingerprint line."""
    collector = JsonResultsCollector()
    path = tmp_path / "results.jsonl"
    fp = RunFingerprint.model_validate(
        {
            "__meta__": "run_fingerprint",
            "prompt_version": "v1",
            "backend": "test",
            "data_source": "data.jsonl",
        }
    )
    lines = [
        fp.model_dump_json(by_alias=True),
        _make_result("ex-1").model_dump_json(),
    ]
    path.write_text("\n".join(lines) + "\n")

    ids = collector.read_completed_ids(str(path))
    assert ids == {"ex-1"}


def test_write_results_with_fingerprint(tmp_path):
    """write_results with fingerprint writes header line followed by result lines."""
    collector = JsonResultsCollector()
    path = str(tmp_path / "results.jsonl")
    fp = RunFingerprint.model_validate(
        {
            "__meta__": "run_fingerprint",
            "prompt_version": "v1",
            "backend": "test",
            "data_source": "data.jsonl",
        }
    )
    results = [_make_result("ex-1"), _make_result("ex-2")]
    collector.write_results(results, path, fingerprint=fp)

    file_lines = [line for line in (tmp_path / "results.jsonl").read_text().splitlines() if line.strip()]
    assert len(file_lines) == 3  # 1 fingerprint + 2 results
    header = json.loads(file_lines[0])
    assert header["__meta__"] == "run_fingerprint"
    assert json.loads(file_lines[1])["example_id"] == "ex-1"
    assert json.loads(file_lines[2])["example_id"] == "ex-2"
