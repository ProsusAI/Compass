"""Tests for odysseus.eval.backends package."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from pydantic import ValidationError

from odysseus.eval.backends.litellm_backend import LiteLLMBackend
from odysseus.eval.backends.profile import BackendProfile
from odysseus.eval.backends.registry import BackendRegistry
from odysseus.eval.models import EvalResult, Example, MetricConfig, RunReport, TokenUsage
from odysseus.eval.pricing import ModelPricing
from odysseus.eval.protocols import RunDependencies

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_PROFILE = {
    "model": "gpt-4o",
    "requests_per_minute": 100,
    "tokens_per_minute": 50_000,
}


def _write_profile(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(yaml.dump(data))
    return p


# ---------------------------------------------------------------------------
# BackendProfile — construction
# ---------------------------------------------------------------------------


class TestBackendProfileConstruction:
    def test_profile_valid_minimal(self) -> None:
        p = BackendProfile(**MINIMAL_PROFILE)
        assert p.model == "gpt-4o"
        assert p.requests_per_minute == 100
        assert p.tokens_per_minute == 50_000
        assert p.pricing is None
        assert p.api_key_env is None
        assert p.api_base is None
        assert p.max_tokens is None
        assert p.temperature is None
        assert p.extra_params == {}
        assert p.provider_params == {}

    def test_profile_valid_full(self) -> None:
        p = BackendProfile(
            model="claude-3-opus",
            pricing=ModelPricing(
                input_cost_per_million_tokens=15.0,
                cached_cost_per_million_tokens=1.5,
                output_cost_per_million_tokens=75.0,
            ),
            api_key_env="ANTHROPIC_API_KEY",
            api_base="https://api.anthropic.com",
            requests_per_minute=60,
            tokens_per_minute=100_000,
            max_tokens=4096,
            temperature=0.7,
            extra_params={"top_p": 0.9},
            provider_params={"anthropic_version": "2024-01-01"},
        )
        assert p.model == "claude-3-opus"
        assert p.pricing is not None
        assert p.pricing.input_cost_per_million_tokens == 15.0
        assert p.api_key_env == "ANTHROPIC_API_KEY"
        assert p.api_base == "https://api.anthropic.com"
        assert p.max_tokens == 4096
        assert p.temperature == 0.7
        assert p.extra_params == {"top_p": 0.9}
        assert p.provider_params == {"anthropic_version": "2024-01-01"}

    def test_profile_missing_model_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BackendProfile(requests_per_minute=100, tokens_per_minute=50_000)  # type: ignore[call-arg]

    def test_profile_empty_model_rejected(self) -> None:
        with pytest.raises(ValidationError, match="model must be non-empty"):
            BackendProfile(model="", requests_per_minute=100, tokens_per_minute=50_000)

    def test_profile_whitespace_model_rejected(self) -> None:
        with pytest.raises(ValidationError, match="model must be non-empty"):
            BackendProfile(model="   ", requests_per_minute=100, tokens_per_minute=50_000)

    def test_profile_model_stripped(self) -> None:
        p = BackendProfile(model="  gpt-4o  ", requests_per_minute=100, tokens_per_minute=50_000)
        assert p.model == "gpt-4o"

    def test_profile_missing_rpm_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BackendProfile(model="gpt-4o", tokens_per_minute=50_000)  # type: ignore[call-arg]

    def test_profile_missing_tpm_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BackendProfile(model="gpt-4o", requests_per_minute=100)  # type: ignore[call-arg]

    def test_profile_rpm_zero_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 1"):
            BackendProfile(model="gpt-4o", requests_per_minute=0, tokens_per_minute=50_000)

    def test_profile_tpm_negative_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 1"):
            BackendProfile(model="gpt-4o", requests_per_minute=100, tokens_per_minute=-1)


# ---------------------------------------------------------------------------
# BackendProfile — pricing field
# ---------------------------------------------------------------------------


class TestBackendProfilePricing:
    def test_profile_pricing_default_none(self) -> None:
        p = BackendProfile(**MINIMAL_PROFILE)
        assert p.pricing is None

    def test_profile_pricing_from_dict(self) -> None:
        p = BackendProfile(
            **{
                **MINIMAL_PROFILE,
                "pricing": {
                    "input_cost_per_million_tokens": 2.5,
                    "cached_cost_per_million_tokens": 1.25,
                    "output_cost_per_million_tokens": 10.0,
                },
            }
        )
        assert p.pricing is not None
        assert p.pricing.input_cost_per_million_tokens == 2.5


# ---------------------------------------------------------------------------
# BackendProfile — from_yaml
# ---------------------------------------------------------------------------


class TestBackendProfileFromYaml:
    def test_profile_from_yaml_valid(self, tmp_path: Path) -> None:
        path = _write_profile(tmp_path, "backend.yaml", MINIMAL_PROFILE)
        p = BackendProfile.from_yaml(path)
        assert p.model == "gpt-4o"
        assert p.requests_per_minute == 100
        assert p.tokens_per_minute == 50_000

    def test_profile_from_yaml_with_all_fields(self, tmp_path: Path) -> None:
        full = {
            **MINIMAL_PROFILE,
            "pricing": {
                "input_cost_per_million_tokens": 2.5,
                "cached_cost_per_million_tokens": 1.25,
                "output_cost_per_million_tokens": 10.0,
            },
            "api_key_env": "OPENAI_API_KEY",
            "api_base": "https://api.openai.com",
            "max_tokens": 2048,
            "temperature": 0.5,
            "extra_params": {"top_p": 0.9},
            "provider_params": {"organization": "org-123"},
        }
        path = _write_profile(tmp_path, "backend.yaml", full)
        p = BackendProfile.from_yaml(path)
        assert p.pricing is not None
        assert p.pricing.input_cost_per_million_tokens == 2.5
        assert p.api_key_env == "OPENAI_API_KEY"
        assert p.max_tokens == 2048
        assert p.extra_params == {"top_p": 0.9}

    def test_profile_from_yaml_missing_required_field(self, tmp_path: Path) -> None:
        path = _write_profile(tmp_path, "backend.yaml", {"model": "gpt-4o"})
        with pytest.raises(ValidationError):
            BackendProfile.from_yaml(path)

    def test_profile_from_yaml_malformed_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("{{{{not yaml")
        with pytest.raises(yaml.YAMLError):
            BackendProfile.from_yaml(path)

    def test_profile_from_yaml_non_mapping(self, tmp_path: Path) -> None:
        path = tmp_path / "list.yaml"
        path.write_text("- item1\n- item2\n")
        with pytest.raises(ValueError, match="Expected a YAML mapping"):
            BackendProfile.from_yaml(path)


# ---------------------------------------------------------------------------
# BackendRegistry
# ---------------------------------------------------------------------------

PROFILE_A = {**MINIMAL_PROFILE, "model": "model-a"}
PROFILE_B = {**MINIMAL_PROFILE, "model": "model-b"}


class TestBackendRegistry:
    def test_registry_from_directory_loads_profiles(self, tmp_path: Path) -> None:
        _write_profile(tmp_path, "a.yaml", PROFILE_A)
        _write_profile(tmp_path, "b.yaml", PROFILE_B)
        reg = BackendRegistry.from_directory(tmp_path)
        assert len(reg.list_profiles()) == 2

    def test_registry_from_directory_label_is_stem(self, tmp_path: Path) -> None:
        _write_profile(tmp_path, "my-backend.yaml", MINIMAL_PROFILE)
        reg = BackendRegistry.from_directory(tmp_path)
        assert "my-backend" in reg.list_profiles()

    def test_registry_yaml_precedence_over_yml(self, tmp_path: Path) -> None:
        _write_profile(tmp_path, "dup.yaml", PROFILE_A)
        _write_profile(tmp_path, "dup.yml", PROFILE_B)
        reg = BackendRegistry.from_directory(tmp_path)
        profile = reg.get_profile("dup")
        assert profile.model == "model-a"

    def test_registry_loads_yml_if_no_yaml(self, tmp_path: Path) -> None:
        _write_profile(tmp_path, "only.yml", PROFILE_B)
        reg = BackendRegistry.from_directory(tmp_path)
        profile = reg.get_profile("only")
        assert profile.model == "model-b"

    def test_registry_get_profile_unknown_raises(self, tmp_path: Path) -> None:
        reg = BackendRegistry.from_directory(tmp_path)
        with pytest.raises(KeyError, match="Unknown backend profile"):
            reg.get_profile("nonexistent")

    def test_registry_get_profile_returns_profile(self, tmp_path: Path) -> None:
        _write_profile(tmp_path, "x.yaml", MINIMAL_PROFILE)
        reg = BackendRegistry.from_directory(tmp_path)
        p = reg.get_profile("x")
        assert isinstance(p, BackendProfile)
        assert p.model == "gpt-4o"

    def test_registry_empty_directory(self, tmp_path: Path) -> None:
        reg = BackendRegistry.from_directory(tmp_path)
        assert reg.list_profiles() == []

    def test_registry_inject_profiles_directly(self) -> None:
        profile = BackendProfile(**MINIMAL_PROFILE)
        reg = BackendRegistry(profiles={"custom": profile})
        assert reg.list_profiles() == ["custom"]
        assert reg.get_profile("custom") is profile

    def test_registry_create_backend(self) -> None:
        profile = BackendProfile(**MINIMAL_PROFILE)
        reg = BackendRegistry(profiles={"gpt": profile})
        backend = reg.create_backend("gpt")
        assert isinstance(backend, LiteLLMBackend)
        assert backend.model_name == "gpt-4o"


# ---------------------------------------------------------------------------
# LiteLLMBackend
# ---------------------------------------------------------------------------

EXAMPLE = Example(id="ex1", input={"text": "hello"}, expected={"label": "greeting"})


def _make_mock_response(
    content: str = "response text",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
    cache_read_input_tokens: int | None = 5,
) -> MagicMock:
    """Build a mock litellm response object."""
    choice = MagicMock()
    choice.message.content = content

    if cache_read_input_tokens is not None:
        usage = MagicMock()
        usage.prompt_tokens = prompt_tokens
        usage.completion_tokens = completion_tokens
        usage.cache_read_input_tokens = cache_read_input_tokens
    else:
        # Simulate usage object that lacks cache_read_input_tokens attr
        usage = MagicMock(spec=["prompt_tokens", "completion_tokens"])
        usage.prompt_tokens = prompt_tokens
        usage.completion_tokens = completion_tokens

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


class TestLiteLLMBackend:
    def test_backend_model_name(self) -> None:
        profile = BackendProfile(**MINIMAL_PROFILE)
        backend = LiteLLMBackend(profile)
        assert backend.model_name == "gpt-4o"

    def test_backend_pricing_none_by_default(self) -> None:
        profile = BackendProfile(**MINIMAL_PROFILE)
        backend = LiteLLMBackend(profile)
        assert backend.pricing is None

    def test_backend_pricing_from_profile(self) -> None:
        pricing = ModelPricing(
            input_cost_per_million_tokens=2.5,
            cached_cost_per_million_tokens=1.25,
            output_cost_per_million_tokens=10.0,
        )
        profile = BackendProfile(**{**MINIMAL_PROFILE, "pricing": pricing})
        backend = LiteLLMBackend(profile)
        assert backend.pricing is pricing

    def test_backend_missing_env_var_raises(self) -> None:
        profile = BackendProfile(**{**MINIMAL_PROFILE, "api_key_env": "NONEXISTENT_KEY_12345"})
        with pytest.raises(KeyError):
            LiteLLMBackend(profile)

    def test_backend_api_key_not_in_repr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_KEY_SECRET", "sk-super-secret-value")
        profile = BackendProfile(**{**MINIMAL_PROFILE, "api_key_env": "TEST_KEY_SECRET"})
        backend = LiteLLMBackend(profile)
        assert "sk-super-secret-value" not in repr(backend._api_key)

    @patch("odysseus.eval.backends.litellm_backend.litellm.acompletion", new_callable=AsyncMock)
    async def test_backend_call_passes_kwargs(self, mock_acompletion: AsyncMock) -> None:
        mock_acompletion.return_value = _make_mock_response()
        profile = BackendProfile(
            model="gpt-4o",
            requests_per_minute=100,
            tokens_per_minute=50_000,
            max_tokens=1024,
            temperature=0.5,
            api_base="https://custom.api.com",
            provider_params={"org": "org-1"},
            extra_params={"top_p": 0.9},
        )
        backend = LiteLLMBackend(profile)
        await backend.call("test prompt", EXAMPLE)

        mock_acompletion.assert_called_once()
        call_kwargs = mock_acompletion.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4o"
        assert call_kwargs.kwargs["max_tokens"] == 1024
        assert call_kwargs.kwargs["temperature"] == 0.5
        assert call_kwargs.kwargs["base_url"] == "https://custom.api.com"
        assert call_kwargs.kwargs["org"] == "org-1"
        assert call_kwargs.kwargs["top_p"] == 0.9

    @patch("odysseus.eval.backends.litellm_backend.litellm.acompletion", new_callable=AsyncMock)
    async def test_backend_call_token_normalisation(self, mock_acompletion: AsyncMock) -> None:
        mock_acompletion.return_value = _make_mock_response(
            prompt_tokens=100, completion_tokens=50, cache_read_input_tokens=30
        )
        profile = BackendProfile(**MINIMAL_PROFILE)
        backend = LiteLLMBackend(profile)
        output, usage = await backend.call("prompt", EXAMPLE)

        assert output == {"content": "response text"}
        assert usage.input_tokens == 100
        assert usage.cached_tokens == 30
        assert usage.output_tokens == 50

    @patch("odysseus.eval.backends.litellm_backend.litellm.acompletion", new_callable=AsyncMock)
    async def test_backend_call_no_cache_tokens(self, mock_acompletion: AsyncMock) -> None:
        mock_acompletion.return_value = _make_mock_response(
            prompt_tokens=100, completion_tokens=50, cache_read_input_tokens=None
        )
        profile = BackendProfile(**MINIMAL_PROFILE)
        backend = LiteLLMBackend(profile)
        _, usage = await backend.call("prompt", EXAMPLE)

        assert usage.cached_tokens == 0

    @patch("odysseus.eval.backends.litellm_backend.litellm.acompletion", new_callable=AsyncMock)
    async def test_backend_call_minimal_kwargs(self, mock_acompletion: AsyncMock) -> None:
        mock_acompletion.return_value = _make_mock_response()
        profile = BackendProfile(**MINIMAL_PROFILE)
        backend = LiteLLMBackend(profile)
        await backend.call("prompt", EXAMPLE)

        call_kwargs = mock_acompletion.call_args.kwargs
        assert "api_key" not in call_kwargs
        assert "base_url" not in call_kwargs
        assert "max_tokens" not in call_kwargs
        assert "temperature" not in call_kwargs

    @patch("odysseus.eval.backends.litellm_backend.litellm.acompletion", new_callable=AsyncMock)
    async def test_backend_extra_params_overrides_provider_params(self, mock_acompletion: AsyncMock) -> None:
        mock_acompletion.return_value = _make_mock_response()
        profile = BackendProfile(
            **{
                **MINIMAL_PROFILE,
                "provider_params": {"key": "provider_value"},
                "extra_params": {"key": "extra_value"},
            }
        )
        backend = LiteLLMBackend(profile)
        await backend.call("prompt", EXAMPLE)

        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["key"] == "extra_value"


# ---------------------------------------------------------------------------
# RunDependencies validation tests
# ---------------------------------------------------------------------------


class _MockBackend:
    @property
    def model_name(self) -> str:
        return "test"

    @property
    def pricing(self) -> ModelPricing | None:
        return None

    async def call(self, prompt: str, example: Example) -> tuple[dict[str, Any], TokenUsage]:
        return {}, TokenUsage(input_tokens=0, cached_tokens=0, output_tokens=0)


class _MockPromptManager:
    def load(self, version: str) -> str:
        return ""


class _MockDatasetManager:
    def load(self, path: str, split: Literal["dev", "holdout"]) -> list[Example]:
        return []


class _MockMetricsEngine:
    def compute(
        self, results: list[EvalResult], examples: list[Example], metric_configs: list[MetricConfig]
    ) -> dict[str, float]:
        return {}


class _MockResultsCollector:
    def write_results(self, results: list[EvalResult], path: str) -> None:
        pass

    def write_report(self, report: RunReport, path: str) -> None:
        pass


def _make_run_deps(**overrides: Any) -> RunDependencies:
    defaults: dict[str, Any] = {
        "backend": _MockBackend(),
        "prompt_manager": _MockPromptManager(),
        "dataset_manager": _MockDatasetManager(),
        "metrics_engine": _MockMetricsEngine(),
        "results_collector": _MockResultsCollector(),
        "requests_per_minute": 100,
        "tokens_per_minute": 50000,
    }
    defaults.update(overrides)
    return RunDependencies(**defaults)


# ---------------------------------------------------------------------------
# BackendProfile — type field
# ---------------------------------------------------------------------------


def test_profile_type_defaults_to_litellm(tmp_path: Path):
    """BackendProfile.type defaults to 'litellm'."""
    profile_path = tmp_path / "default.yaml"
    profile_path.write_text(
        yaml.dump(
            {
                "model": "gpt-4",
                "requests_per_minute": 100,
                "tokens_per_minute": 100000,
            }
        )
    )
    profile = BackendProfile.from_yaml(profile_path)
    assert profile.type == "litellm"


def test_profile_type_mock_echo(tmp_path: Path):
    """BackendProfile.type can be set to 'mock_echo'."""
    profile_path = tmp_path / "mock.yaml"
    profile_path.write_text(
        yaml.dump(
            {
                "model": "mock-echo",
                "type": "mock_echo",
                "requests_per_minute": 10000,
                "tokens_per_minute": 1000000,
            }
        )
    )
    profile = BackendProfile.from_yaml(profile_path)
    assert profile.type == "mock_echo"


def test_registry_creates_mock_echo_backend(tmp_path: Path):
    """Registry creates MockEchoBackend when profile type is 'mock_echo'."""
    backends_dir = tmp_path / "backends"
    backends_dir.mkdir()
    (backends_dir / "mock.yaml").write_text(
        yaml.dump(
            {
                "model": "mock-echo",
                "type": "mock_echo",
                "requests_per_minute": 10000,
                "tokens_per_minute": 1000000,
            }
        )
    )
    registry = BackendRegistry.from_directory(backends_dir)
    backend = registry.create_backend("mock")

    from odysseus.eval.backends.mock_echo import MockEchoBackend

    assert isinstance(backend, MockEchoBackend)


# ---------------------------------------------------------------------------
# RunDependencies validation tests
# ---------------------------------------------------------------------------


def test_run_dependencies_valid():
    """RunDependencies accepts valid rate limit values."""
    deps = _make_run_deps()
    assert deps.requests_per_minute == 100
    assert deps.tokens_per_minute == 50000


def test_run_dependencies_rpm_zero_rejected():
    """RunDependencies rejects requests_per_minute < 1."""
    with pytest.raises(ValueError, match="requests_per_minute must be >= 1"):
        _make_run_deps(requests_per_minute=0)


def test_run_dependencies_tpm_negative_rejected():
    """RunDependencies rejects tokens_per_minute < 1."""
    with pytest.raises(ValueError, match="tokens_per_minute must be >= 1"):
        _make_run_deps(tokens_per_minute=-1)
