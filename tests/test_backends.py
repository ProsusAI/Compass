"""Tests for odysseus.eval.backends package."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from odysseus.eval.backends.profile import BackendProfile

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
        assert p.pricing_model is None
        assert p.api_key_env is None
        assert p.api_base is None
        assert p.max_tokens is None
        assert p.temperature is None
        assert p.extra_params == {}
        assert p.provider_params == {}

    def test_profile_valid_full(self) -> None:
        p = BackendProfile(
            model="claude-3-opus",
            pricing_model="claude-3-opus-20240229",
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
        assert p.pricing_model == "claude-3-opus-20240229"
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
# BackendProfile — effective_pricing_model
# ---------------------------------------------------------------------------


class TestBackendProfilePricingModel:
    def test_profile_effective_pricing_model_default(self) -> None:
        p = BackendProfile(**MINIMAL_PROFILE)
        assert p.effective_pricing_model == "gpt-4o"

    def test_profile_effective_pricing_model_override(self) -> None:
        p = BackendProfile(**{**MINIMAL_PROFILE, "pricing_model": "gpt-4o-2024-05-13"})
        assert p.effective_pricing_model == "gpt-4o-2024-05-13"


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
            "pricing_model": "gpt-4o-2024-05-13",
            "api_key_env": "OPENAI_API_KEY",
            "api_base": "https://api.openai.com",
            "max_tokens": 2048,
            "temperature": 0.5,
            "extra_params": {"top_p": 0.9},
            "provider_params": {"organization": "org-123"},
        }
        path = _write_profile(tmp_path, "backend.yaml", full)
        p = BackendProfile.from_yaml(path)
        assert p.pricing_model == "gpt-4o-2024-05-13"
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
