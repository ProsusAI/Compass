"""Tests for evaluation data models."""

from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

from odysseus.eval.models import (
    ConcurrencyConfig,
    MetricConfig,
    OutputConfig,
    RetryConfig,
    RunConfig,
)


def test_metric_config_defaults():
    mc = MetricConfig(name="accuracy")
    assert mc.name == "accuracy"
    assert mc.params == {}


def test_metric_config_with_params():
    mc = MetricConfig(name="f1", params={"average": "macro"})
    assert mc.params == {"average": "macro"}


def test_concurrency_config_defaults():
    cc = ConcurrencyConfig()
    assert cc.max_concurrent_requests == 20
    assert cc.requests_per_minute == 500
    assert cc.tokens_per_minute == 100_000


def test_retry_config_defaults():
    rc = RetryConfig()
    assert rc.max_attempts == 3
    assert rc.backoff_factor == 2.0
    assert rc.per_call_timeout_seconds == 60.0


def test_output_config_defaults():
    oc = OutputConfig()
    assert oc.results_path == "outputs/results.jsonl"
    assert oc.report_path == "outputs/report.json"


def test_run_config_minimal():
    config = RunConfig(
        backend="claude-sonnet",
        data_source="data/test.jsonl",
        data_split="dev",
        metrics=[MetricConfig(name="accuracy")],
    )
    assert config.prompt_version == "latest"
    assert config.concurrency.max_concurrent_requests == 20
    assert config.retry.max_attempts == 3


def test_run_config_from_yaml():
    data = {
        "backend": "claude-sonnet",
        "data_source": "data/test.jsonl",
        "data_split": "dev",
        "metrics": [{"name": "accuracy"}],
        "concurrency": {"max_concurrent_requests": 10},
    }
    with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        path = Path(f.name)

    config = RunConfig.from_yaml(path)
    assert config.backend == "claude-sonnet"
    assert config.concurrency.max_concurrent_requests == 10
    assert config.retry.max_attempts == 3  # default

    path.unlink()


def test_run_config_from_yaml_invalid():
    import pytest
    from pydantic import ValidationError

    data = {"backend": "claude-sonnet"}  # missing required fields
    with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        path = Path(f.name)

    with pytest.raises(ValidationError):
        RunConfig.from_yaml(path)

    path.unlink()
