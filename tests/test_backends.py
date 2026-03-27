"""Tests for odysseus.eval.backends package."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from pydantic import ValidationError

from odysseus.eval.backends.anthropic_backend import AnthropicBackend
from odysseus.eval.backends.bedrock_backend import BedrockBackend
from odysseus.eval.backends.openai_backend import OpenAIBackend
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


EXAMPLE = Example(
    id="ex1",
    input="hello",
    expected={
        "route": "greeting",
        "routes": {"greeting": {"cost": 0.01, "quality_score": 0.9}},
    },
    split="dev",
)


# ---------------------------------------------------------------------------
# Mock response builders
# ---------------------------------------------------------------------------


def _make_anthropic_mock_response(
    text: str = "response text",
    input_tokens: int = 10,
    output_tokens: int = 20,
    cache_read_input_tokens: int | None = 5,
    ephemeral_5m_input_tokens: int = 0,
    ephemeral_1h_input_tokens: int = 0,
) -> MagicMock:
    """Build a mock Anthropic response object."""
    content_block = MagicMock()
    content_block.text = text

    usage = MagicMock(spec=["input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation"])
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    if cache_read_input_tokens is not None:
        usage.cache_read_input_tokens = cache_read_input_tokens
    else:
        del usage.cache_read_input_tokens

    cache_creation = MagicMock(spec=["ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"])
    cache_creation.ephemeral_5m_input_tokens = ephemeral_5m_input_tokens
    cache_creation.ephemeral_1h_input_tokens = ephemeral_1h_input_tokens
    usage.cache_creation = cache_creation

    resp = MagicMock()
    resp.content = [content_block]
    resp.usage = usage
    return resp


def _make_openai_mock_response(
    content: str = "response text",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
    cached_tokens: int | None = 5,
) -> MagicMock:
    """Build a mock OpenAI response object."""
    choice = MagicMock()
    choice.message.content = content

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    if cached_tokens is not None:
        details = MagicMock()
        details.cached_tokens = cached_tokens
        usage.prompt_tokens_details = details
    else:
        usage.prompt_tokens_details = None

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


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
# BackendProfile — provider field
# ---------------------------------------------------------------------------


def test_profile_provider_defaults_to_anthropic(tmp_path: Path):
    """BackendProfile.provider defaults to 'anthropic'."""
    profile_path = tmp_path / "default.yaml"
    profile_path.write_text(
        yaml.dump(
            {
                "model": "claude-sonnet-4-20250514",
                "requests_per_minute": 100,
                "tokens_per_minute": 100000,
            }
        )
    )
    profile = BackendProfile.from_yaml(profile_path)
    assert profile.provider == "anthropic"


def test_profile_provider_mock_echo(tmp_path: Path):
    """BackendProfile.provider can be set to 'mock_echo'."""
    profile_path = tmp_path / "mock.yaml"
    profile_path.write_text(
        yaml.dump(
            {
                "model": "mock-echo",
                "provider": "mock_echo",
                "requests_per_minute": 10000,
                "tokens_per_minute": 1000000,
            }
        )
    )
    profile = BackendProfile.from_yaml(profile_path)
    assert profile.provider == "mock_echo"


def test_profile_provider_openai():
    """BackendProfile.provider can be set to 'openai'."""
    profile = BackendProfile(model="gpt-4o", provider="openai", requests_per_minute=100, tokens_per_minute=50000)
    assert profile.provider == "openai"


def test_profile_provider_bedrock():
    """BackendProfile.provider can be set to 'bedrock'."""
    profile = BackendProfile(
        model="anthropic.claude-3-sonnet", provider="bedrock", requests_per_minute=100, tokens_per_minute=50000
    )
    assert profile.provider == "bedrock"


# ---------------------------------------------------------------------------
# BackendProfile — reasoning_level field
# ---------------------------------------------------------------------------


class TestBackendProfileReasoningLevel:
    def test_reasoning_level_defaults_to_none(self) -> None:
        profile = BackendProfile(**MINIMAL_PROFILE)
        assert profile.reasoning_level is None

    def test_reasoning_level_accepts_valid_values(self) -> None:
        for level in ("low", "medium", "high"):
            profile = BackendProfile(**{**MINIMAL_PROFILE, "reasoning_level": level})
            assert profile.reasoning_level == level

    def test_reasoning_level_rejects_invalid_value(self) -> None:
        with pytest.raises(ValidationError):
            BackendProfile(**{**MINIMAL_PROFILE, "reasoning_level": "extreme"})

    def test_reasoning_level_from_yaml(self, tmp_path: Path) -> None:
        yaml_content = """
model: test-model
provider: anthropic
requests_per_minute: 100
tokens_per_minute: 50000
reasoning_level: high
"""
        p = tmp_path / "test.yaml"
        p.write_text(yaml_content)
        profile = BackendProfile.from_yaml(p)
        assert profile.reasoning_level == "high"


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


# ---------------------------------------------------------------------------
# Registry — create_backend dispatch
# ---------------------------------------------------------------------------


def test_registry_create_backend_anthropic() -> None:
    profile = BackendProfile(
        model="claude-sonnet-4-20250514", provider="anthropic", requests_per_minute=100, tokens_per_minute=50000
    )
    reg = BackendRegistry(profiles={"claude": profile})
    backend = reg.create_backend("claude")
    assert isinstance(backend, AnthropicBackend)
    assert backend.model_name == "claude-sonnet-4-20250514"


@patch("odysseus.eval.backends.openai_backend.openai.AsyncOpenAI")
def test_registry_create_backend_openai(mock_client_cls: MagicMock) -> None:
    profile = BackendProfile(model="gpt-4o", provider="openai", requests_per_minute=100, tokens_per_minute=50000)
    reg = BackendRegistry(profiles={"gpt": profile})
    backend = reg.create_backend("gpt")
    assert isinstance(backend, OpenAIBackend)
    assert backend.model_name == "gpt-4o"


def test_registry_create_backend_bedrock() -> None:
    with (
        patch("odysseus.eval.backends.bedrock_backend.boto3.Session"),
        patch("odysseus.eval.backends.bedrock_backend.anthropic.AsyncAnthropicBedrock"),
    ):
        profile = BackendProfile(
            model="anthropic.claude-3-sonnet",
            provider="bedrock",
            requests_per_minute=100,
            tokens_per_minute=50000,
        )
        reg = BackendRegistry(profiles={"bedrock": profile})
        backend = reg.create_backend("bedrock")
        assert isinstance(backend, BedrockBackend)
        assert backend.model_name == "anthropic.claude-3-sonnet"


def test_registry_create_backend_mock_echo(tmp_path: Path) -> None:
    """Registry creates MockEchoBackend when profile provider is 'mock_echo'."""
    backends_dir = tmp_path / "backends"
    backends_dir.mkdir()
    (backends_dir / "mock.yaml").write_text(
        yaml.dump(
            {
                "model": "mock-echo",
                "provider": "mock_echo",
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
# AnthropicBackend
# ---------------------------------------------------------------------------


class TestAnthropicBackend:
    def test_backend_model_name(self) -> None:
        profile = BackendProfile(
            model="claude-sonnet-4-20250514", provider="anthropic", requests_per_minute=100, tokens_per_minute=50000
        )
        backend = AnthropicBackend(profile)
        assert backend.model_name == "claude-sonnet-4-20250514"

    def test_backend_pricing_none_by_default(self) -> None:
        profile = BackendProfile(
            model="claude-sonnet-4-20250514", provider="anthropic", requests_per_minute=100, tokens_per_minute=50000
        )
        backend = AnthropicBackend(profile)
        assert backend.pricing is None

    def test_backend_pricing_from_profile(self) -> None:
        pricing = ModelPricing(
            input_cost_per_million_tokens=3.0,
            cached_cost_per_million_tokens=0.3,
            output_cost_per_million_tokens=15.0,
        )
        profile = BackendProfile(
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            requests_per_minute=100,
            tokens_per_minute=50000,
            pricing=pricing,
        )
        backend = AnthropicBackend(profile)
        assert backend.pricing is pricing

    def test_backend_missing_env_var_raises(self) -> None:
        profile = BackendProfile(
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            requests_per_minute=100,
            tokens_per_minute=50000,
            api_key_env="NONEXISTENT_KEY_12345",
        )
        with pytest.raises(KeyError):
            AnthropicBackend(profile)

    @patch("odysseus.eval.backends.anthropic_backend.anthropic.AsyncAnthropic")
    async def test_backend_call_token_normalisation(self, mock_client_cls: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            return_value=_make_anthropic_mock_response(
                input_tokens=100,
                output_tokens=50,
                cache_read_input_tokens=30,
            )
        )
        profile = BackendProfile(
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=1024,
        )
        backend = AnthropicBackend(profile)
        output, usage = await backend.call("prompt", EXAMPLE)

        assert output == {"content": "response text"}
        assert usage.input_tokens == 100
        assert usage.cached_tokens == 30
        assert usage.output_tokens == 50
        assert usage.cache_write_5m_tokens == 0
        assert usage.cache_write_1h_tokens == 0

    @patch("odysseus.eval.backends.anthropic_backend.anthropic.AsyncAnthropic")
    async def test_backend_call_cache_write_tokens_from_usage(self, mock_client_cls: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            return_value=_make_anthropic_mock_response(
                input_tokens=100,
                output_tokens=50,
                cache_read_input_tokens=10,
                ephemeral_5m_input_tokens=200,
                ephemeral_1h_input_tokens=50,
            )
        )
        profile = BackendProfile(
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=1024,
        )
        backend = AnthropicBackend(profile)
        _, usage = await backend.call("prompt", EXAMPLE)

        assert usage.cache_write_5m_tokens == 200
        assert usage.cache_write_1h_tokens == 50

    @patch("odysseus.eval.backends.anthropic_backend.anthropic.AsyncAnthropic")
    async def test_backend_call_no_cache_tokens(self, mock_client_cls: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            return_value=_make_anthropic_mock_response(
                input_tokens=100,
                output_tokens=50,
                cache_read_input_tokens=None,
            )
        )
        profile = BackendProfile(
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=1024,
        )
        backend = AnthropicBackend(profile)
        _, usage = await backend.call("prompt", EXAMPLE)

        assert usage.cached_tokens == 0

    @patch("odysseus.eval.backends.anthropic_backend.anthropic.AsyncAnthropic")
    async def test_backend_call_passes_extra_params(self, mock_client_cls: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=_make_anthropic_mock_response())
        profile = BackendProfile(
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=1024,
            temperature=0.5,
            extra_params={"top_p": 0.9},
        )
        backend = AnthropicBackend(profile)
        await backend.call("test prompt", EXAMPLE)

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-sonnet-4-20250514"
        assert call_kwargs.kwargs["max_tokens"] == 1024
        assert call_kwargs.kwargs["temperature"] == 0.5
        assert call_kwargs.kwargs["top_p"] == 0.9

    @patch("odysseus.eval.backends.anthropic_backend.anthropic.AsyncAnthropic")
    async def test_backend_provider_params_passed_to_client(self, mock_client_cls: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=_make_anthropic_mock_response())
        profile = BackendProfile(
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=1024,
            provider_params={"default_headers": {"X-Custom": "value"}},
        )
        AnthropicBackend(profile)

        mock_client_cls.assert_called_once()
        call_kwargs = mock_client_cls.call_args.kwargs
        assert call_kwargs["default_headers"] == {"X-Custom": "value"}


# ---------------------------------------------------------------------------
# OpenAIBackend
# ---------------------------------------------------------------------------


class TestOpenAIBackend:
    @patch("odysseus.eval.backends.openai_backend.openai.AsyncOpenAI")
    def test_backend_model_name(self, mock_client_cls: MagicMock) -> None:
        profile = BackendProfile(model="gpt-4o", provider="openai", requests_per_minute=100, tokens_per_minute=50000)
        backend = OpenAIBackend(profile)
        assert backend.model_name == "gpt-4o"

    @patch("odysseus.eval.backends.openai_backend.openai.AsyncOpenAI")
    def test_backend_pricing_none_by_default(self, mock_client_cls: MagicMock) -> None:
        profile = BackendProfile(model="gpt-4o", provider="openai", requests_per_minute=100, tokens_per_minute=50000)
        backend = OpenAIBackend(profile)
        assert backend.pricing is None

    def test_backend_missing_env_var_raises(self) -> None:
        profile = BackendProfile(
            model="gpt-4o",
            provider="openai",
            requests_per_minute=100,
            tokens_per_minute=50000,
            api_key_env="NONEXISTENT_KEY_12345",
        )
        with pytest.raises(KeyError):
            OpenAIBackend(profile)

    @patch("odysseus.eval.backends.openai_backend.openai.AsyncOpenAI")
    async def test_backend_call_token_normalisation(self, mock_client_cls: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_openai_mock_response(
                prompt_tokens=100,
                completion_tokens=50,
                cached_tokens=30,
            )
        )
        profile = BackendProfile(model="gpt-4o", provider="openai", requests_per_minute=100, tokens_per_minute=50000)
        backend = OpenAIBackend(profile)
        output, usage = await backend.call("prompt", EXAMPLE)

        assert output == {"content": "response text"}
        assert usage.input_tokens == 100
        assert usage.cached_tokens == 30
        assert usage.output_tokens == 50

    @patch("odysseus.eval.backends.openai_backend.openai.AsyncOpenAI")
    async def test_backend_call_no_cached_tokens(self, mock_client_cls: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_openai_mock_response(
                prompt_tokens=100,
                completion_tokens=50,
                cached_tokens=None,
            )
        )
        profile = BackendProfile(model="gpt-4o", provider="openai", requests_per_minute=100, tokens_per_minute=50000)
        backend = OpenAIBackend(profile)
        _, usage = await backend.call("prompt", EXAMPLE)

        assert usage.cached_tokens == 0

    @patch("odysseus.eval.backends.openai_backend.openai.AsyncOpenAI")
    async def test_backend_call_passes_extra_params(self, mock_client_cls: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=_make_openai_mock_response())
        profile = BackendProfile(
            model="gpt-4o",
            provider="openai",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=2048,
            temperature=0.5,
            extra_params={"top_p": 0.9},
        )
        backend = OpenAIBackend(profile)
        await backend.call("test prompt", EXAMPLE)

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4o"
        assert call_kwargs.kwargs["max_tokens"] == 2048
        assert call_kwargs.kwargs["temperature"] == 0.5
        assert call_kwargs.kwargs["top_p"] == 0.9

    @patch("odysseus.eval.backends.openai_backend.openai.AsyncOpenAI")
    async def test_backend_provider_params_passed_to_client(self, mock_client_cls: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=_make_openai_mock_response())
        profile = BackendProfile(
            model="gpt-4o",
            provider="openai",
            requests_per_minute=100,
            tokens_per_minute=50000,
            provider_params={"organization": "org-123"},
        )
        OpenAIBackend(profile)

        mock_client_cls.assert_called_once()
        call_kwargs = mock_client_cls.call_args.kwargs
        assert call_kwargs["organization"] == "org-123"


# ---------------------------------------------------------------------------
# OpenAIBackend — reasoning_level
# ---------------------------------------------------------------------------


class TestOpenAIBackendReasoningLevel:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("level", ["low", "medium", "high"])
    @patch("odysseus.eval.backends.openai_backend.openai.AsyncOpenAI")
    async def test_reasoning_level_sets_reasoning_effort(self, mock_client_cls: MagicMock, level: str) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=_make_openai_mock_response(content="test"))
        profile = BackendProfile(
            **{**MINIMAL_PROFILE, "provider": "openai", "reasoning_level": level, "api_key_env": None}
        )
        backend = OpenAIBackend(profile)
        await backend.call("prompt", EXAMPLE)
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["reasoning_effort"] == level

    @pytest.mark.asyncio
    @patch("odysseus.eval.backends.openai_backend.openai.AsyncOpenAI")
    async def test_no_reasoning_level_omits_reasoning_effort(self, mock_client_cls: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=_make_openai_mock_response(content="test"))
        profile = BackendProfile(**{**MINIMAL_PROFILE, "provider": "openai", "api_key_env": None})
        backend = OpenAIBackend(profile)
        await backend.call("prompt", EXAMPLE)
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "reasoning_effort" not in call_kwargs


# ---------------------------------------------------------------------------
# BedrockBackend
# ---------------------------------------------------------------------------


class TestBedrockBackend:
    def test_backend_model_name(self) -> None:
        with (
            patch("odysseus.eval.backends.bedrock_backend.boto3.Session"),
            patch("odysseus.eval.backends.bedrock_backend.anthropic.AsyncAnthropicBedrock"),
        ):
            profile = BackendProfile(
                model="anthropic.claude-3-sonnet",
                provider="bedrock",
                requests_per_minute=100,
                tokens_per_minute=50000,
            )
            backend = BedrockBackend(profile)
            assert backend.model_name == "anthropic.claude-3-sonnet"

    def test_backend_pricing_none_by_default(self) -> None:
        with (
            patch("odysseus.eval.backends.bedrock_backend.boto3.Session"),
            patch("odysseus.eval.backends.bedrock_backend.anthropic.AsyncAnthropicBedrock"),
        ):
            profile = BackendProfile(
                model="anthropic.claude-3-sonnet",
                provider="bedrock",
                requests_per_minute=100,
                tokens_per_minute=50000,
            )
            backend = BedrockBackend(profile)
            assert backend.pricing is None

    @patch("odysseus.eval.backends.bedrock_backend.anthropic.AsyncAnthropicBedrock")
    @patch("odysseus.eval.backends.bedrock_backend.boto3.Session")
    async def test_backend_call_token_normalisation(
        self, mock_session_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            return_value=_make_anthropic_mock_response(
                input_tokens=100,
                output_tokens=50,
                cache_read_input_tokens=30,
            )
        )
        profile = BackendProfile(
            model="anthropic.claude-3-sonnet",
            provider="bedrock",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=1024,
        )
        backend = BedrockBackend(profile)
        output, usage = await backend.call("prompt", EXAMPLE)

        assert output == {"content": "response text"}
        assert usage.input_tokens == 100
        assert usage.cached_tokens == 30
        assert usage.output_tokens == 50

    @patch("odysseus.eval.backends.bedrock_backend.anthropic.AsyncAnthropicBedrock")
    @patch("odysseus.eval.backends.bedrock_backend.boto3.Session")
    async def test_backend_region_from_provider_params(
        self, mock_session_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=_make_anthropic_mock_response())
        profile = BackendProfile(
            model="anthropic.claude-3-sonnet",
            provider="bedrock",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=1024,
            provider_params={"region_name": "eu-west-1"},
        )
        BedrockBackend(profile)

        mock_client_cls.assert_called_once()
        call_kwargs = mock_client_cls.call_args.kwargs
        assert call_kwargs["aws_region"] == "eu-west-1"

    @patch("odysseus.eval.backends.bedrock_backend.anthropic.AsyncAnthropicBedrock")
    @patch("odysseus.eval.backends.bedrock_backend.boto3.Session")
    async def test_backend_provider_params_forwarded_to_session(
        self, mock_session_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=_make_anthropic_mock_response())
        profile = BackendProfile(
            model="anthropic.claude-3-sonnet",
            provider="bedrock",
            requests_per_minute=100,
            tokens_per_minute=50000,
            max_tokens=1024,
            provider_params={"region_name": "eu-west-1", "profile_name": "my-sso-profile"},
        )
        BedrockBackend(profile)

        mock_session_cls.assert_called_once_with(profile_name="my-sso-profile")


# ---------------------------------------------------------------------------
# AnthropicBackend — reasoning_level
# ---------------------------------------------------------------------------


class TestAnthropicBackendReasoningLevel:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "level,expected_budget",
        [
            ("low", 1024),
            ("medium", 4096),
            ("high", 16384),
        ],
    )
    async def test_reasoning_level_sets_thinking_budget(self, level: str, expected_budget: int) -> None:
        profile = BackendProfile(**{**MINIMAL_PROFILE, "reasoning_level": level, "api_key_env": None})
        backend = AnthropicBackend(profile)
        with patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = _make_anthropic_mock_response(text="test")
            await backend.call("prompt", EXAMPLE)
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["thinking"] == {"type": "enabled", "budget_tokens": expected_budget}

    @pytest.mark.asyncio
    async def test_no_reasoning_level_omits_thinking(self) -> None:
        profile = BackendProfile(**{**MINIMAL_PROFILE, "api_key_env": None})
        backend = AnthropicBackend(profile)
        with patch.object(backend._client.messages, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = _make_anthropic_mock_response(text="test")
            await backend.call("prompt", EXAMPLE)
            call_kwargs = mock_create.call_args.kwargs
            assert "thinking" not in call_kwargs


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
