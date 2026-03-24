"""Tests for evaluation data models."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

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
    data = {"backend": "claude-sonnet"}  # missing required fields
    with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        path = Path(f.name)

    with pytest.raises(ValidationError):
        RunConfig.from_yaml(path)

    path.unlink()


def test_metric_config_empty_name_rejected():
    with pytest.raises(ValidationError):
        MetricConfig(name="")


def test_metric_config_whitespace_name_rejected():
    with pytest.raises(ValidationError):
        MetricConfig(name="   ")


def test_metric_config_minimal_name_accepted():
    mc = MetricConfig(name="a")
    assert mc.name == "a"


def test_metric_config_name_stripped():
    mc = MetricConfig(name="  accuracy  ")
    assert mc.name == "accuracy"


def test_concurrency_max_concurrent_zero_rejected():
    with pytest.raises(ValidationError):
        ConcurrencyConfig(max_concurrent_requests=0)


def test_concurrency_old_rate_limit_fields_rejected():
    """requests_per_minute and tokens_per_minute are no longer accepted."""
    with pytest.raises(ValidationError):
        ConcurrencyConfig(requests_per_minute=500)
    with pytest.raises(ValidationError):
        ConcurrencyConfig(tokens_per_minute=100000)


def test_retry_max_attempts_zero_rejected():
    with pytest.raises(ValidationError):
        RetryConfig(max_attempts=0)


def test_retry_backoff_below_one_rejected():
    with pytest.raises(ValidationError):
        RetryConfig(backoff_factor=0.5)


def test_retry_timeout_zero_rejected():
    with pytest.raises(ValidationError):
        RetryConfig(per_call_timeout_seconds=0)


def test_retry_minimum_valid_accepted():
    rc = RetryConfig(max_attempts=1, backoff_factor=1.0, per_call_timeout_seconds=0.1)
    assert rc.max_attempts == 1
    assert rc.backoff_factor == 1.0
    assert rc.per_call_timeout_seconds == 0.1


def test_retry_timeout_301_rejected():
    with pytest.raises(ValidationError):
        RetryConfig(per_call_timeout_seconds=301)


def test_retry_timeout_300_accepted():
    rc = RetryConfig(per_call_timeout_seconds=300)
    assert rc.per_call_timeout_seconds == 300


def test_retry_total_duration_over_1800_rejected():
    with pytest.raises(ValidationError):
        RetryConfig(max_attempts=10, backoff_factor=3.0, per_call_timeout_seconds=60)


def test_retry_total_duration_boundary_rejected():
    # total = 62 + 6*290 = 1802 > 1800
    with pytest.raises(ValidationError):
        RetryConfig(max_attempts=6, backoff_factor=2.0, per_call_timeout_seconds=290)


def test_retry_total_duration_boundary_accepted():
    # total = 62 + 6*289 = 1796 <= 1800
    rc = RetryConfig(max_attempts=6, backoff_factor=2.0, per_call_timeout_seconds=289)
    assert rc.per_call_timeout_seconds == 289


def test_output_results_path_wrong_suffix_rejected():
    with pytest.raises(ValidationError):
        OutputConfig(results_path="foo.txt")


def test_output_report_path_wrong_suffix_rejected():
    with pytest.raises(ValidationError):
        OutputConfig(report_path="bar.csv")


def test_output_minimum_valid_accepted():
    oc = OutputConfig(results_path="r.jsonl", report_path="r.json")
    assert oc.results_path == "r.jsonl"
    assert oc.report_path == "r.json"


def _valid_run_kwargs(**overrides: Any) -> dict[str, Any]:
    """Return valid RunConfig kwargs, with optional overrides."""
    base = {
        "backend": "claude-sonnet",
        "data_source": "data/test.jsonl",
        "data_split": "dev",
        "metrics": [{"name": "accuracy"}],
    }
    base.update(overrides)
    return base


def test_run_config_empty_backend_rejected():
    with pytest.raises(ValidationError):
        RunConfig(**_valid_run_kwargs(backend=""))


def test_run_config_whitespace_prompt_version_rejected():
    with pytest.raises(ValidationError):
        RunConfig(**_valid_run_kwargs(prompt_version="  "))


def test_run_config_whitespace_data_source_rejected():
    with pytest.raises(ValidationError):
        RunConfig(**_valid_run_kwargs(data_source="   "))


def test_run_config_empty_metrics_rejected():
    with pytest.raises(ValidationError):
        RunConfig(**_valid_run_kwargs(metrics=[]))


def test_run_config_invalid_data_split_rejected():
    with pytest.raises(ValidationError):
        RunConfig(**_valid_run_kwargs(data_split="test"))


def test_run_config_backend_stripped():
    config = RunConfig(**_valid_run_kwargs(backend="  claude-sonnet  "))
    assert config.backend == "claude-sonnet"


def test_example_config_round_trip():
    config = RunConfig.from_yaml("configs/example-run.yaml")
    assert config.backend == "claude-sonnet-4-20250514"
    assert config.data_split == "dev"
    assert len(config.metrics) == 2
    assert config.concurrency.max_concurrent_requests == 20
    assert config.retry.max_attempts == 3


class TestModelCostQuality:
    def test_valid_cost_quality(self):
        from odysseus.eval.models import ModelCostQuality

        m = ModelCostQuality(cost=0.05, quality_score=0.98)
        assert m.cost == 0.05
        assert m.quality_score == 0.98

    def test_negative_cost_allowed(self):
        """No range constraints per spec — normalization is conversational."""
        from odysseus.eval.models import ModelCostQuality

        m = ModelCostQuality(cost=-1.0, quality_score=2.0)
        assert m.cost == -1.0
        assert m.quality_score == 2.0


class TestExpected:
    def test_valid_expected(self):
        from odysseus.eval.models import Expected

        e = Expected(
            route="opus",
            routes={
                "opus": {"cost": 0.05, "quality_score": 0.98},
                "sonnet": {"cost": 0.01, "quality_score": 0.88},
            },
        )
        assert e.route == "opus"
        assert e.routes["opus"].cost == 0.05

    def test_route_not_in_routes_is_accepted(self):
        """route_in_routes mismatch is a validation warning, not a model error."""
        from odysseus.eval.models import Expected

        e = Expected(
            route="gpt-4o",
            routes={"opus": {"cost": 0.05, "quality_score": 0.98}},
        )
        assert e.route == "gpt-4o"
        assert "opus" in e.routes

    def test_routes_must_be_non_empty(self):
        from odysseus.eval.models import Expected

        with pytest.raises(ValueError, match="routes must contain at least one entry"):
            Expected(route="opus", routes={})


class TestExampleNewSchema:
    def test_valid_example_string_input(self):
        from odysseus.eval.models import Example

        ex = Example(
            id="ex-1",
            input="Explain quantum entanglement",
            expected={
                "route": "opus",
                "routes": {
                    "opus": {"cost": 0.05, "quality_score": 0.98},
                    "sonnet": {"cost": 0.01, "quality_score": 0.88},
                },
            },
            split="dev",
        )
        assert ex.input == "Explain quantum entanglement"
        assert ex.expected.route == "opus"
        assert ex.split == "dev"

    def test_split_must_be_dev_or_holdout(self):
        from odysseus.eval.models import Example

        with pytest.raises(ValueError):
            Example(
                id="ex-1",
                input="test",
                expected={
                    "route": "opus",
                    "routes": {"opus": {"cost": 0.05, "quality_score": 0.98}},
                },
                split="train",
            )
